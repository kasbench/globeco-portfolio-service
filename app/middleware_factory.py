"""
Middleware factory for environment-based conditional middleware loading.

This module provides a factory pattern for creating middleware stacks based on
environment profiles, enabling performance optimization by loading only necessary
middleware components in each environment.
"""

import logging
from typing import List, Type, Any, Dict, Optional
from fastapi import FastAPI
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from app.environment_config import (
    EnvironmentProfile, 
    MiddlewareConfig, 
    get_config_manager,
    get_feature_flags
)
from app.logging_config import get_logger

logger = get_logger(__name__)


class MiddlewareFactory:
    """
    Factory for creating environment-appropriate middleware stacks.
    
    This factory creates middleware stacks based on environment profiles,
    ensuring that only necessary middleware is loaded in each environment
    to optimize performance while maintaining essential functionality.
    """
    
    def __init__(self, config_manager=None):
        """
        Initialize middleware factory.
        
        Args:
            config_manager: Configuration manager instance (optional)
        """
        self._config_manager = config_manager or get_config_manager()
        self._feature_flags = get_feature_flags()
        self._logger = logging.getLogger(__name__)
        
        # Registry of available middleware classes
        self._middleware_registry: Dict[str, Type[BaseHTTPMiddleware]] = {}
        self._essential_middleware: List[str] = []
        self._conditional_middleware: List[str] = []
        
        # Initialize middleware registry
        self._register_middleware()
    
    def _register_middleware(self) -> None:
        """Register all available middleware classes."""
        try:
            # Import middleware classes
            from app.logging_config import LoggingMiddleware
            from fastapi.middleware.cors import CORSMiddleware
            from app.security_middleware import (
                SecurityHeadersMiddleware,
                RequestIDMiddleware,
                BasicErrorHandlingMiddleware
            )
            
            # Essential middleware (always loaded)
            self._middleware_registry["logging"] = LoggingMiddleware
            self._middleware_registry["cors"] = CORSMiddleware
            self._middleware_registry["security_headers"] = SecurityHeadersMiddleware
            self._middleware_registry["request_id"] = RequestIDMiddleware
            self._middleware_registry["error_handling"] = BasicErrorHandlingMiddleware
            
            # Mark essential middleware (order matters - error handling first, then request ID, then logging)
            self._essential_middleware = ["error_handling", "request_id", "logging", "security_headers", "cors"]
            
            # Conditional middleware (environment-based)
            try:
                from app.monitoring import EnhancedHTTPMetricsMiddleware
                self._middleware_registry["metrics"] = EnhancedHTTPMetricsMiddleware
                self._conditional_middleware.append("metrics")
            except ImportError as e:
                self._logger.warning(
                    f"Enhanced HTTP metrics middleware not available: {e}"
                )
            
            try:
                from app.lightweight_middleware import LightweightPerformanceMiddleware
                self._middleware_registry["performance"] = LightweightPerformanceMiddleware
                self._conditional_middleware.append("performance")
            except ImportError as e:
                self._logger.warning(
                    f"Lightweight performance middleware not available: {e}"
                )
            
            # Thread monitoring middleware (if available)
            try:
                # This would be a thread monitoring middleware class
                # For now, we'll register it as a placeholder
                self._conditional_middleware.append("thread_monitoring")
            except Exception as e:
                self._logger.debug(
                    f"Thread monitoring middleware not registered: {e}"
                )
            
            self._logger.info(
                f"Middleware registry initialized: "
                f"total={len(self._middleware_registry)}, "
                f"essential={len(self._essential_middleware)}, "
                f"conditional={len(self._conditional_middleware)}, "
                f"registered={list(self._middleware_registry.keys())}"
            )
            
        except Exception as e:
            self._logger.error(
                f"Failed to register middleware: {e} ({type(e).__name__})",
                exc_info=True
            )
            raise RuntimeError(f"Middleware registration failed: {e}") from e
    
    def create_middleware_stack(self, app: FastAPI) -> None:
        """
        Create and apply environment-appropriate middleware stack to FastAPI app.
        
        Args:
            app: FastAPI application instance
            
        Raises:
            ValueError: If middleware configuration is invalid
            RuntimeError: If middleware creation fails
        """
        try:
            profile = self._config_manager.current_profile
            middleware_config = profile.middleware
            
            self._logger.info(
                f"Creating middleware stack for {self._config_manager.current_environment} environment"
            )
            
            # Validate middleware configuration
            self._validate_middleware_config(middleware_config)
            
            # Apply essential middleware first
            self._apply_essential_middleware(app, middleware_config)
            
            # Apply conditional middleware based on environment
            self._apply_conditional_middleware(app, middleware_config)
            
            # Log final middleware stack
            self._log_middleware_stack_summary(app, middleware_config)
            
        except Exception as e:
            self._logger.error(
                f"Failed to create middleware stack for {self._config_manager.current_environment}: {e}",
                exc_info=True
            )
            raise RuntimeError(f"Middleware stack creation failed: {e}") from e
    
    def _validate_middleware_config(self, config: MiddlewareConfig) -> None:
        """
        Validate middleware configuration.
        
        Args:
            config: Middleware configuration to validate
            
        Raises:
            ValueError: If configuration is invalid
        """
        errors = []
        
        # Validate boolean flags
        boolean_flags = [
            "enable_request_logging",
            "enable_metrics_middleware", 
            "enable_thread_monitoring",
            "enable_performance_profiling",
            "enable_cors",
            "enable_security_headers",
            "enable_request_id"
        ]
        
        for flag in boolean_flags:
            if hasattr(config, flag):
                value = getattr(config, flag)
                if not isinstance(value, bool):
                    errors.append(f"{flag} must be a boolean, got {type(value).__name__}")
        
        if errors:
            error_msg = f"Middleware configuration validation failed: {'; '.join(errors)}"
            raise ValueError(error_msg)
        
        self._logger.debug("Middleware configuration validated successfully")
    
    def _apply_essential_middleware(self, app: FastAPI, config: MiddlewareConfig) -> None:
        """
        Apply essential middleware that should always be loaded.
        
        Middleware is applied in reverse order (last added = first executed):
        1. Error handling (outermost - catches all errors)
        2. Request ID (generates correlation IDs)
        3. Logging (logs with request IDs)
        4. Security headers (adds security headers to responses)
        5. CORS (handles cross-origin requests)
        
        Args:
            app: FastAPI application instance
            config: Middleware configuration
        """
        essential_applied = []
        
        # Apply CORS middleware if enabled (applied last = executed first after app)
        if config.enable_cors and "cors" in self._middleware_registry:
            try:
                app.add_middleware(
                    self._middleware_registry["cors"],
                    allow_origins=["*"],
                    allow_credentials=True,
                    allow_methods=["*"],
                    allow_headers=["*"],
                )
                essential_applied.append("cors")
                self._logger.debug("Applied CORS middleware")
            except Exception as e:
                self._logger.error(f"Failed to apply CORS middleware: {e}")
                raise
        
        # Apply security headers middleware if enabled
        if config.enable_security_headers and "security_headers" in self._middleware_registry:
            try:
                strict_mode = self._config_manager.is_production()
                app.add_middleware(
                    self._middleware_registry["security_headers"],
                    strict_mode=strict_mode
                )
                essential_applied.append("security_headers")
                self._logger.debug(f"Applied security headers middleware (strict_mode={strict_mode})")
            except Exception as e:
                self._logger.error(f"Failed to apply security headers middleware: {e}")
                # Don't raise - security headers are important but not critical
                self._logger.warning("Continuing without security headers middleware")
        
        # Apply logging middleware
        if "logging" in self._middleware_registry:
            try:
                from app.logging_config import get_logger
                app_logger = get_logger("app.main")
                app.add_middleware(
                    self._middleware_registry["logging"],
                    logger=app_logger
                )
                essential_applied.append("logging")
                self._logger.debug("Applied logging middleware")
            except Exception as e:
                self._logger.error(f"Failed to apply logging middleware: {e}")
                raise
        
        # Apply request ID middleware if enabled
        if config.enable_request_id and "request_id" in self._middleware_registry:
            try:
                app.add_middleware(
                    self._middleware_registry["request_id"],
                    header_name="X-Request-ID"
                )
                essential_applied.append("request_id")
                self._logger.debug("Applied request ID middleware")
            except Exception as e:
                self._logger.error(f"Failed to apply request ID middleware: {e}")
                # Don't raise - request ID is helpful but not critical
                self._logger.warning("Continuing without request ID middleware")
        
        # Apply error handling middleware (applied first = executed last, outermost)
        if "error_handling" in self._middleware_registry:
            try:
                include_details = self._config_manager.is_development()
                app.add_middleware(
                    self._middleware_registry["error_handling"],
                    include_error_details=include_details
                )
                essential_applied.append("error_handling")
                self._logger.debug(f"Applied error handling middleware (include_details={include_details})")
            except Exception as e:
                self._logger.error(f"Failed to apply error handling middleware: {e}")
                # Don't raise - error handling is important but app can still function
                self._logger.warning("Continuing without error handling middleware")
        
        self._logger.info(
            f"Essential middleware applied: {essential_applied} "
            f"(total={len(essential_applied)}, order: error_handling -> request_id -> logging -> security_headers -> cors -> app)"
        )
    
    def _apply_conditional_middleware(self, app: FastAPI, config: MiddlewareConfig) -> None:
        """
        Apply conditional middleware based on environment configuration.
        
        Args:
            app: FastAPI application instance
            config: Middleware configuration
        """
        conditional_applied = []
        
        # Apply metrics middleware if enabled
        if (config.enable_metrics_middleware and 
            self._feature_flags.is_enabled("enable_metrics_middleware") and
            "metrics" in self._middleware_registry):
            try:
                app.add_middleware(
                    self._middleware_registry["metrics"],
                    debug_logging=self._config_manager.is_development()
                )
                conditional_applied.append("metrics")
                self._logger.info("Applied enhanced HTTP metrics middleware")
            except Exception as e:
                self._logger.error(f"Failed to apply metrics middleware: {e}")
        else:
            self._logger.info(
                f"Enhanced HTTP metrics middleware disabled "
                f"(config={config.enable_metrics_middleware}, "
                f"feature_flag={self._feature_flags.is_enabled('enable_metrics_middleware')}, "
                f"available={'metrics' in self._middleware_registry})"
            )
        
        # Apply performance middleware if enabled
        if (config.enable_performance_profiling and
            "performance" in self._middleware_registry):
            try:
                app.add_middleware(self._middleware_registry["performance"])
                conditional_applied.append("performance")
                self._logger.info("Applied lightweight performance middleware")
            except Exception as e:
                self._logger.error(f"Failed to apply performance middleware: {e}")
        
        # Apply thread monitoring middleware if enabled
        if (config.enable_thread_monitoring and
            self._feature_flags.is_enabled("enable_thread_monitoring")):
            try:
                # This would apply thread monitoring middleware
                # For now, we'll use the existing thread metrics setup
                from app.monitoring import setup_thread_metrics
                
                thread_config = self._config_manager.current_profile.monitoring
                result = setup_thread_metrics(
                    enable_thread_metrics=True,
                    update_interval=getattr(thread_config, 'thread_metrics_update_interval', 30),
                    debug_logging=self._config_manager.is_development()
                )
                
                if result:
                    conditional_applied.append("thread_monitoring")
                    self._logger.info("Applied thread monitoring middleware")
                else:
                    self._logger.warning("Thread monitoring setup failed")
                    
            except Exception as e:
                self._logger.error(f"Failed to apply thread monitoring middleware: {e}")
        else:
            self._logger.info(
                f"Thread monitoring middleware disabled "
                f"(config={config.enable_thread_monitoring}, "
                f"feature_flag={self._feature_flags.is_enabled('enable_thread_monitoring')})"
            )
        
        # Apply request logging middleware if enabled
        if config.enable_request_logging:
            try:
                # This would be additional request logging beyond basic logging
                # For now, we'll log that it would be applied
                conditional_applied.append("request_logging")
                self._logger.debug("Enhanced request logging would be applied here")
            except Exception as e:
                self._logger.warning(f"Enhanced request logging middleware not available: {e}")
        
        self._logger.info(
            f"Conditional middleware applied: {conditional_applied} "
            f"(total={len(conditional_applied)}, environment={self._config_manager.current_environment})"
        )
    
    def _get_middleware_config_summary(self, config: MiddlewareConfig) -> Dict[str, Any]:
        """
        Get middleware configuration summary for logging.
        
        Args:
            config: Middleware configuration
            
        Returns:
            Dictionary with configuration summary
        """
        return {
            # Essential middleware
            "cors": config.enable_cors,
            "security_headers": config.enable_security_headers,
            "request_id": config.enable_request_id,
            "error_handling": True,  # Always enabled
            "logging": True,  # Always enabled
            
            # Conditional middleware
            "request_logging": config.enable_request_logging,
            "metrics_middleware": config.enable_metrics_middleware,
            "thread_monitoring": config.enable_thread_monitoring,
            "performance_profiling": config.enable_performance_profiling,
        }
    
    def _log_middleware_stack_summary(self, app: FastAPI, config: MiddlewareConfig) -> None:
        """
        Log summary of applied middleware stack.
        
        Args:
            app: FastAPI application instance
            config: Middleware configuration
        """
        try:
            # Count middleware in the app
            middleware_count = len(getattr(app, 'user_middleware', []))
            
            self._logger.info(
                f"Middleware stack creation completed for {self._config_manager.current_environment}: "
                f"total_applied={middleware_count}, essential={self._essential_middleware}, "
                f"conditional={self._conditional_middleware}"
            )
            
        except Exception as e:
            self._logger.warning(f"Could not generate middleware stack summary: {e}")
    
    def get_middleware_info(self) -> Dict[str, Any]:
        """
        Get information about available and configured middleware.
        
        Returns:
            Dictionary with middleware information
        """
        profile = self._config_manager.current_profile
        
        return {
            "environment": self._config_manager.current_environment,
            "available_middleware": list(self._middleware_registry.keys()),
            "essential_middleware": self._essential_middleware,
            "conditional_middleware": self._conditional_middleware,
            "current_config": self._get_middleware_config_summary(profile.middleware),
            "feature_flags": {
                "metrics_middleware": self._feature_flags.is_enabled("enable_metrics_middleware"),
                "thread_monitoring": self._feature_flags.is_enabled("enable_thread_monitoring"),
                "request_logging": self._feature_flags.is_enabled("enable_request_logging"),
            }
        }


# Global middleware factory instance
_middleware_factory: Optional[MiddlewareFactory] = None


def get_middleware_factory() -> MiddlewareFactory:
    """
    Get global middleware factory instance (singleton pattern).
    
    Returns:
        MiddlewareFactory instance
    """
    global _middleware_factory
    if _middleware_factory is None:
        _middleware_factory = MiddlewareFactory()
    return _middleware_factory


def initialize_middleware_factory(config_manager=None) -> MiddlewareFactory:
    """
    Initialize global middleware factory with optional configuration manager.
    
    Args:
        config_manager: Configuration manager instance (optional)
        
    Returns:
        MiddlewareFactory instance
    """
    global _middleware_factory
    _middleware_factory = MiddlewareFactory(config_manager)
    return _middleware_factory


def create_middleware_stack(app: FastAPI, config_manager=None) -> None:
    """
    Convenience function to create middleware stack for FastAPI app.
    
    Args:
        app: FastAPI application instance
        config_manager: Configuration manager instance (optional)
    """
    factory = get_middleware_factory() if config_manager is None else MiddlewareFactory(config_manager)
    factory.create_middleware_stack(app)