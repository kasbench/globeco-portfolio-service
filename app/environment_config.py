"""
Environment-based configuration system for Portfolio Service streamlining.

This module provides environment-specific configuration profiles that optimize
the service for different deployment environments (development, staging, production).
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Optional
from pydantic import BaseModel, Field


class MonitoringMode(str, Enum):
    """Monitoring modes for different environments."""
    FULL = "full"          # Development: Full observability
    STANDARD = "standard"  # Staging: Standard observability  
    MINIMAL = "minimal"    # Production: Minimal observability


class LogLevel(str, Enum):
    """Logging levels."""
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


@dataclass
class MonitoringConfig:
    """Configuration for monitoring and observability."""
    mode: MonitoringMode = MonitoringMode.MINIMAL
    enable_tracing: bool = False
    enable_metrics: bool = True
    enable_prometheus: bool = False  # Will be completely removed
    sample_rate: float = 0.1  # 10% sampling for production
    export_interval: int = 60  # seconds
    otlp_endpoint: str = "http://localhost:4317"
    enable_database_tracing: bool = False
    
    def __post_init__(self):
        """Validate configuration after initialization."""
        if not 0.0 <= self.sample_rate <= 1.0:
            raise ValueError("sample_rate must be between 0.0 and 1.0")
        if self.export_interval < 10:
            raise ValueError("export_interval must be at least 10 seconds")


@dataclass
class ResourceLimits:
    """Resource limits and requests for container deployment."""
    memory_request: str = "128Mi"
    memory_limit: str = "256Mi"
    cpu_request: str = "100m"
    cpu_limit: str = "200m"
    max_connections: int = 20
    connection_timeout: int = 30  # seconds


@dataclass
class MiddlewareConfig:
    """Configuration for conditional middleware loading."""
    enable_request_logging: bool = False
    enable_metrics_middleware: bool = False
    enable_thread_monitoring: bool = False
    enable_performance_profiling: bool = False
    enable_cors: bool = True
    enable_security_headers: bool = True
    enable_request_id: bool = True


@dataclass
class LoggingConfig:
    """Configuration for logging system."""
    level: LogLevel = LogLevel.WARNING
    enable_structured_logging: bool = True
    enable_correlation_ids: bool = True
    enable_request_response_logging: bool = False
    log_sampling_rate: float = 1.0  # 100% by default
    
    def __post_init__(self):
        """Validate configuration after initialization."""
        if not 0.0 <= self.log_sampling_rate <= 1.0:
            raise ValueError("log_sampling_rate must be between 0.0 and 1.0")


@dataclass
class DatabaseConfig:
    """Configuration for database operations."""
    enable_connection_pooling: bool = True
    max_pool_size: int = 20
    min_pool_size: int = 5
    connection_timeout: int = 30000  # milliseconds
    enable_query_logging: bool = False
    enable_bulk_optimization: bool = True


@dataclass
class EnvironmentProfile:
    """Complete environment profile with all configuration settings."""
    name: str
    monitoring: MonitoringConfig = field(default_factory=MonitoringConfig)
    resources: ResourceLimits = field(default_factory=ResourceLimits)
    middleware: MiddlewareConfig = field(default_factory=MiddlewareConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)
    database: DatabaseConfig = field(default_factory=DatabaseConfig)


# Environment-specific profiles
PROFILES: Dict[str, EnvironmentProfile] = {
    "development": EnvironmentProfile(
        name="development",
        monitoring=MonitoringConfig(
            mode=MonitoringMode.FULL,
            enable_tracing=True,
            enable_metrics=True,
            enable_prometheus=False,  # Removed even in development
            sample_rate=1.0,  # 100% sampling in development
            export_interval=10,
            enable_database_tracing=True,
        ),
        resources=ResourceLimits(
            memory_request="256Mi",
            memory_limit="512Mi",
            cpu_request="200m",
            cpu_limit="500m",
            max_connections=50,
        ),
        middleware=MiddlewareConfig(
            enable_request_logging=True,
            enable_metrics_middleware=True,
            enable_thread_monitoring=True,
            enable_performance_profiling=True,
        ),
        logging=LoggingConfig(
            level=LogLevel.DEBUG,
            enable_request_response_logging=True,
            log_sampling_rate=1.0,
        ),
        database=DatabaseConfig(
            max_pool_size=50,
            min_pool_size=10,
            enable_query_logging=True,
        ),
    ),
    
    "staging": EnvironmentProfile(
        name="staging",
        monitoring=MonitoringConfig(
            mode=MonitoringMode.STANDARD,
            enable_tracing=True,
            enable_metrics=True,
            enable_prometheus=False,  # Removed
            sample_rate=0.5,  # 50% sampling in staging
            export_interval=30,
            enable_database_tracing=False,
        ),
        resources=ResourceLimits(
            memory_request="192Mi",
            memory_limit="384Mi",
            cpu_request="150m",
            cpu_limit="300m",
            max_connections=30,
        ),
        middleware=MiddlewareConfig(
            enable_request_logging=True,
            enable_metrics_middleware=True,
            enable_thread_monitoring=False,
            enable_performance_profiling=False,
        ),
        logging=LoggingConfig(
            level=LogLevel.INFO,
            enable_request_response_logging=False,
            log_sampling_rate=0.5,
        ),
        database=DatabaseConfig(
            max_pool_size=30,
            min_pool_size=8,
            enable_query_logging=False,
        ),
    ),
    
    "production": EnvironmentProfile(
        name="production",
        monitoring=MonitoringConfig(
            mode=MonitoringMode.MINIMAL,
            enable_tracing=False,
            enable_metrics=True,
            enable_prometheus=False,  # Completely removed
            sample_rate=0.1,  # 10% sampling in production
            export_interval=60,
            enable_database_tracing=False,
        ),
        resources=ResourceLimits(
            memory_request="128Mi",
            memory_limit="256Mi",
            cpu_request="100m",
            cpu_limit="200m",
            max_connections=20,
        ),
        middleware=MiddlewareConfig(
            enable_request_logging=False,
            enable_metrics_middleware=False,
            enable_thread_monitoring=False,
            enable_performance_profiling=False,
        ),
        logging=LoggingConfig(
            level=LogLevel.WARNING,
            enable_request_response_logging=False,
            log_sampling_rate=0.1,
        ),
        database=DatabaseConfig(
            max_pool_size=20,
            min_pool_size=5,
            enable_query_logging=False,
        ),
    ),
}


def get_profile(environment: str) -> EnvironmentProfile:
    """
    Get environment profile by name.
    
    Args:
        environment: Environment name (development, staging, production)
        
    Returns:
        EnvironmentProfile for the specified environment
        
    Raises:
        ValueError: If environment is not found
    """
    if environment not in PROFILES:
        available = ", ".join(PROFILES.keys())
        raise ValueError(f"Unknown environment '{environment}'. Available: {available}")
    
    return PROFILES[environment]


def list_environments() -> list[str]:
    """List all available environment names."""
    return list(PROFILES.keys())

import os
import logging
from typing import Optional


class ConfigurationManager:
    """
    Manages environment-based configuration with validation and automatic profile selection.
    
    This class handles:
    - Environment detection from environment variables
    - Automatic profile selection based on environment
    - Configuration validation with proper error handling
    - Runtime configuration updates
    """
    
    def __init__(self, environment: Optional[str] = None):
        """
        Initialize configuration manager.
        
        Args:
            environment: Override environment detection (for testing)
        """
        self._logger = logging.getLogger(__name__)
        self._current_environment = environment or self._detect_environment()
        self._current_profile: Optional[EnvironmentProfile] = None
        self._load_profile()
    
    def _detect_environment(self) -> str:
        """
        Detect current environment from environment variables.
        
        Checks multiple environment variables in order of preference:
        1. PORTFOLIO_SERVICE_ENV
        2. ENVIRONMENT
        3. ENV
        4. Kubernetes namespace detection
        5. Default to 'development'
        
        Returns:
            Detected environment name
        """
        # Check explicit environment variables
        env_vars = ["PORTFOLIO_SERVICE_ENV", "ENVIRONMENT", "ENV"]
        for var in env_vars:
            env_value = os.getenv(var)
            if env_value:
                env_value = env_value.lower().strip()
                if env_value in PROFILES:
                    self._logger.info(f"Environment detected from {var}: {env_value}")
                    return env_value
                else:
                    self._logger.warning(
                        f"Invalid environment '{env_value}' from {var}. "
                        f"Available: {', '.join(PROFILES.keys())}"
                    )
        
        # Check Kubernetes namespace for environment hints
        k8s_namespace = os.getenv("MY_NAMESPACE") or os.getenv("KUBERNETES_NAMESPACE")
        if k8s_namespace:
            namespace_lower = k8s_namespace.lower()
            if "prod" in namespace_lower:
                self._logger.info(f"Environment detected from K8s namespace '{k8s_namespace}': production")
                return "production"
            elif "stag" in namespace_lower:
                self._logger.info(f"Environment detected from K8s namespace '{k8s_namespace}': staging")
                return "staging"
        
        # Default to development
        self._logger.info("No environment specified, defaulting to development")
        return "development"
    
    def _load_profile(self) -> None:
        """
        Load and validate the current environment profile.
        
        Raises:
            ValueError: If profile validation fails
            RuntimeError: If profile loading fails
        """
        try:
            self._current_profile = get_profile(self._current_environment)
            self._validate_profile(self._current_profile)
            self._logger.info(
                f"Configuration profile loaded successfully: environment={self._current_environment}, "
                f"monitoring_mode={self._current_profile.monitoring.mode.value}, "
                f"log_level={self._current_profile.logging.level.value}"
            )
        except Exception as e:
            self._logger.error(
                f"Failed to load configuration profile: environment={self._current_environment}, "
                f"error={str(e)}, error_type={type(e).__name__}"
            )
            raise RuntimeError(f"Configuration loading failed: {e}") from e
    
    def _validate_profile(self, profile: EnvironmentProfile) -> None:
        """
        Validate environment profile configuration.
        
        Args:
            profile: Profile to validate
            
        Raises:
            ValueError: If validation fails
        """
        errors = []
        
        # Validate monitoring configuration
        try:
            if profile.monitoring.sample_rate < 0.0 or profile.monitoring.sample_rate > 1.0:
                errors.append("monitoring.sample_rate must be between 0.0 and 1.0")
            
            if profile.monitoring.export_interval < 10:
                errors.append("monitoring.export_interval must be at least 10 seconds")
                
            if not profile.monitoring.otlp_endpoint:
                errors.append("monitoring.otlp_endpoint cannot be empty")
        except Exception as e:
            errors.append(f"monitoring configuration error: {e}")
        
        # Validate resource limits
        try:
            if profile.resources.max_connections <= 0:
                errors.append("resources.max_connections must be positive")
                
            if profile.resources.connection_timeout <= 0:
                errors.append("resources.connection_timeout must be positive")
        except Exception as e:
            errors.append(f"resource configuration error: {e}")
        
        # Validate logging configuration
        try:
            if profile.logging.log_sampling_rate < 0.0 or profile.logging.log_sampling_rate > 1.0:
                errors.append("logging.log_sampling_rate must be between 0.0 and 1.0")
        except Exception as e:
            errors.append(f"logging configuration error: {e}")
        
        # Validate database configuration
        try:
            if profile.database.max_pool_size <= 0:
                errors.append("database.max_pool_size must be positive")
                
            if profile.database.min_pool_size < 0:
                errors.append("database.min_pool_size must be non-negative")
                
            if profile.database.min_pool_size > profile.database.max_pool_size:
                errors.append("database.min_pool_size cannot exceed max_pool_size")
                
            if profile.database.connection_timeout <= 0:
                errors.append("database.connection_timeout must be positive")
        except Exception as e:
            errors.append(f"database configuration error: {e}")
        
        if errors:
            error_msg = f"Profile validation failed for '{profile.name}': {'; '.join(errors)}"
            raise ValueError(error_msg)
    
    @property
    def current_environment(self) -> str:
        """Get current environment name."""
        return self._current_environment
    
    @property
    def current_profile(self) -> EnvironmentProfile:
        """Get current environment profile."""
        if self._current_profile is None:
            raise RuntimeError("No profile loaded")
        return self._current_profile
    
    def reload_profile(self, environment: Optional[str] = None) -> None:
        """
        Reload configuration profile, optionally changing environment.
        
        Args:
            environment: New environment name (optional)
        """
        if environment:
            if environment not in PROFILES:
                available = ", ".join(PROFILES.keys())
                raise ValueError(f"Unknown environment '{environment}'. Available: {available}")
            self._current_environment = environment
        
        old_env = self._current_environment
        self._load_profile()
        
        if environment and environment != old_env:
            self._logger.info(
                f"Environment changed: old_environment={old_env}, "
                f"new_environment={self._current_environment}"
            )
    
    def get_monitoring_config(self) -> MonitoringConfig:
        """Get monitoring configuration for current environment."""
        return self.current_profile.monitoring
    
    def get_resource_limits(self) -> ResourceLimits:
        """Get resource limits for current environment."""
        return self.current_profile.resources
    
    def get_middleware_config(self) -> MiddlewareConfig:
        """Get middleware configuration for current environment."""
        return self.current_profile.middleware
    
    def get_logging_config(self) -> LoggingConfig:
        """Get logging configuration for current environment."""
        return self.current_profile.logging
    
    def get_database_config(self) -> DatabaseConfig:
        """Get database configuration for current environment."""
        return self.current_profile.database
    
    def is_production(self) -> bool:
        """Check if running in production environment."""
        return self._current_environment == "production"
    
    def is_development(self) -> bool:
        """Check if running in development environment."""
        return self._current_environment == "development"
    
    def is_staging(self) -> bool:
        """Check if running in staging environment."""
        return self._current_environment == "staging"
    
    def get_config_summary(self) -> dict:
        """
        Get a summary of current configuration for logging/debugging.
        
        Returns:
            Dictionary with configuration summary
        """
        profile = self.current_profile
        return {
            "environment": self._current_environment,
            "monitoring_mode": profile.monitoring.mode.value,
            "tracing_enabled": profile.monitoring.enable_tracing,
            "metrics_enabled": profile.monitoring.enable_metrics,
            "prometheus_enabled": profile.monitoring.enable_prometheus,
            "sample_rate": profile.monitoring.sample_rate,
            "log_level": profile.logging.level.value,
            "memory_limit": profile.resources.memory_limit,
            "cpu_limit": profile.resources.cpu_limit,
            "max_connections": profile.resources.max_connections,
            "middleware_count": sum([
                profile.middleware.enable_request_logging,
                profile.middleware.enable_metrics_middleware,
                profile.middleware.enable_thread_monitoring,
                profile.middleware.enable_performance_profiling,
            ])
        }


# Global configuration manager instance
_config_manager: Optional[ConfigurationManager] = None


def get_config_manager() -> ConfigurationManager:
    """
    Get global configuration manager instance (singleton pattern).
    
    Returns:
        ConfigurationManager instance
    """
    global _config_manager
    if _config_manager is None:
        _config_manager = ConfigurationManager()
    return _config_manager


def initialize_config_manager(environment: Optional[str] = None) -> ConfigurationManager:
    """
    Initialize global configuration manager with optional environment override.
    
    Args:
        environment: Override environment detection
        
    Returns:
        ConfigurationManager instance
    """
    global _config_manager
    _config_manager = ConfigurationManager(environment)
    return _config_manager


from threading import Lock
from typing import Any, Callable, Dict


class FeatureFlags:
    """
    Runtime feature flag system for observability components.
    
    Provides dynamic control over observability features without service restart.
    Feature flags can be updated at runtime and have environment-based defaults.
    """
    
    def __init__(self, config_manager: ConfigurationManager):
        """
        Initialize feature flags with environment-based defaults.
        
        Args:
            config_manager: Configuration manager for environment-based defaults
        """
        self._config_manager = config_manager
        self._flags: Dict[str, Any] = {}
        self._lock = Lock()
        self._logger = logging.getLogger(__name__)
        self._update_callbacks: Dict[str, list[Callable]] = {}
        
        # Initialize with environment-based defaults
        self._initialize_defaults()
    
    def _initialize_defaults(self) -> None:
        """Initialize feature flags with environment-based defaults."""
        profile = self._config_manager.current_profile
        
        # Observability feature flags
        self._flags.update({
            # Monitoring flags
            "enable_tracing": profile.monitoring.enable_tracing,
            "enable_metrics": profile.monitoring.enable_metrics,
            "enable_prometheus": profile.monitoring.enable_prometheus,
            "enable_database_tracing": profile.monitoring.enable_database_tracing,
            "metrics_sample_rate": profile.monitoring.sample_rate,
            
            # Middleware flags
            "enable_request_logging": profile.middleware.enable_request_logging,
            "enable_metrics_middleware": profile.middleware.enable_metrics_middleware,
            "enable_thread_monitoring": profile.middleware.enable_thread_monitoring,
            "enable_performance_profiling": profile.middleware.enable_performance_profiling,
            
            # Logging flags
            "enable_structured_logging": profile.logging.enable_structured_logging,
            "enable_correlation_ids": profile.logging.enable_correlation_ids,
            "enable_request_response_logging": profile.logging.enable_request_response_logging,
            "log_sampling_rate": profile.logging.log_sampling_rate,
            
            # Database flags
            "enable_query_logging": profile.database.enable_query_logging,
            "enable_bulk_optimization": profile.database.enable_bulk_optimization,
            
            # Performance flags
            "enable_connection_pooling": profile.database.enable_connection_pooling,
            "enable_validation_caching": True,  # Always enabled for performance
            "enable_circuit_breaker": True,    # Always enabled for reliability
        })
        
        self._logger.info(
            f"Feature flags initialized with environment defaults: "
            f"environment={self._config_manager.current_environment}, "
            f"flags_count={len(self._flags)}"
        )
    
    def get(self, flag_name: str, default: Any = None) -> Any:
        """
        Get feature flag value.
        
        Args:
            flag_name: Name of the feature flag
            default: Default value if flag not found
            
        Returns:
            Feature flag value or default
        """
        with self._lock:
            return self._flags.get(flag_name, default)
    
    def set(self, flag_name: str, value: Any) -> None:
        """
        Set feature flag value and trigger callbacks.
        
        Args:
            flag_name: Name of the feature flag
            value: New value for the flag
        """
        old_value = None
        with self._lock:
            old_value = self._flags.get(flag_name)
            self._flags[flag_name] = value
        
        # Log flag change
        self._logger.info(
            f"Feature flag updated: flag_name={flag_name}, "
            f"old_value={old_value}, new_value={value}"
        )
        
        # Trigger callbacks
        self._trigger_callbacks(flag_name, value, old_value)
    
    def update(self, flags: Dict[str, Any]) -> None:
        """
        Update multiple feature flags at once.
        
        Args:
            flags: Dictionary of flag names and values
        """
        changes = {}
        with self._lock:
            for flag_name, value in flags.items():
                old_value = self._flags.get(flag_name)
                self._flags[flag_name] = value
                changes[flag_name] = (old_value, value)
        
        # Log batch update
        self._logger.info(
            f"Feature flags batch update: flags_updated={len(flags)}, "
            f"flag_names={list(flags.keys())}"
        )
        
        # Trigger callbacks for each changed flag
        for flag_name, (old_value, new_value) in changes.items():
            self._trigger_callbacks(flag_name, new_value, old_value)
    
    def is_enabled(self, flag_name: str) -> bool:
        """
        Check if a boolean feature flag is enabled.
        
        Args:
            flag_name: Name of the feature flag
            
        Returns:
            True if flag is enabled, False otherwise
        """
        return bool(self.get(flag_name, False))
    
    def register_callback(self, flag_name: str, callback: Callable[[Any, Any], None]) -> None:
        """
        Register callback for feature flag changes.
        
        Args:
            flag_name: Name of the feature flag to watch
            callback: Function to call when flag changes (new_value, old_value)
        """
        with self._lock:
            if flag_name not in self._update_callbacks:
                self._update_callbacks[flag_name] = []
            self._update_callbacks[flag_name].append(callback)
        
        self._logger.debug(f"Callback registered for feature flag '{flag_name}'")
    
    def _trigger_callbacks(self, flag_name: str, new_value: Any, old_value: Any) -> None:
        """
        Trigger callbacks for a feature flag change.
        
        Args:
            flag_name: Name of the changed flag
            new_value: New flag value
            old_value: Previous flag value
        """
        callbacks = self._update_callbacks.get(flag_name, [])
        for callback in callbacks:
            try:
                callback(new_value, old_value)
            except Exception as e:
                self._logger.error(
                    f"Feature flag callback failed: flag_name={flag_name}, "
                    f"callback={callback.__name__}, error={str(e)}",
                    exc_info=True
                )
    
    def get_all_flags(self) -> Dict[str, Any]:
        """
        Get all feature flags as a dictionary.
        
        Returns:
            Dictionary of all feature flags
        """
        with self._lock:
            return self._flags.copy()
    
    def reset_to_defaults(self) -> None:
        """Reset all feature flags to environment-based defaults."""
        with self._lock:
            old_flags = self._flags.copy()
            self._flags.clear()
            self._initialize_defaults()
        
        self._logger.info("Feature flags reset to environment defaults")
        
        # Trigger callbacks for changed flags
        for flag_name, new_value in self._flags.items():
            old_value = old_flags.get(flag_name)
            if old_value != new_value:
                self._trigger_callbacks(flag_name, new_value, old_value)
    
    def reload_from_environment(self) -> None:
        """Reload feature flags from current environment configuration."""
        self._config_manager.reload_profile()
        self.reset_to_defaults()
        
        self._logger.info(
            f"Feature flags reloaded from environment: "
            f"environment={self._config_manager.current_environment}"
        )
    
    def get_observability_summary(self) -> Dict[str, Any]:
        """
        Get summary of observability-related feature flags.
        
        Returns:
            Dictionary with observability flag summary
        """
        with self._lock:
            return {
                "tracing": {
                    "enabled": self._flags.get("enable_tracing", False),
                    "database_tracing": self._flags.get("enable_database_tracing", False),
                },
                "metrics": {
                    "enabled": self._flags.get("enable_metrics", True),
                    "prometheus": self._flags.get("enable_prometheus", False),
                    "middleware": self._flags.get("enable_metrics_middleware", False),
                    "sample_rate": self._flags.get("metrics_sample_rate", 0.1),
                },
                "logging": {
                    "structured": self._flags.get("enable_structured_logging", True),
                    "correlation_ids": self._flags.get("enable_correlation_ids", True),
                    "request_response": self._flags.get("enable_request_response_logging", False),
                    "sampling_rate": self._flags.get("log_sampling_rate", 1.0),
                },
                "middleware": {
                    "request_logging": self._flags.get("enable_request_logging", False),
                    "thread_monitoring": self._flags.get("enable_thread_monitoring", False),
                    "performance_profiling": self._flags.get("enable_performance_profiling", False),
                },
                "performance": {
                    "connection_pooling": self._flags.get("enable_connection_pooling", True),
                    "validation_caching": self._flags.get("enable_validation_caching", True),
                    "circuit_breaker": self._flags.get("enable_circuit_breaker", True),
                    "bulk_optimization": self._flags.get("enable_bulk_optimization", True),
                }
            }


# Global feature flags instance
_feature_flags: Optional[FeatureFlags] = None


def get_feature_flags() -> FeatureFlags:
    """
    Get global feature flags instance.
    
    Returns:
        FeatureFlags instance
        
    Raises:
        RuntimeError: If feature flags not initialized
    """
    global _feature_flags
    if _feature_flags is None:
        # Auto-initialize with config manager
        config_manager = get_config_manager()
        _feature_flags = FeatureFlags(config_manager)
    return _feature_flags


def initialize_feature_flags(config_manager: Optional[ConfigurationManager] = None) -> FeatureFlags:
    """
    Initialize global feature flags instance.
    
    Args:
        config_manager: Configuration manager (optional, will create if not provided)
        
    Returns:
        FeatureFlags instance
    """
    global _feature_flags
    if config_manager is None:
        config_manager = get_config_manager()
    _feature_flags = FeatureFlags(config_manager)
    return _feature_flags


# Convenience functions for common feature flag checks
def is_tracing_enabled() -> bool:
    """Check if tracing is enabled."""
    return get_feature_flags().is_enabled("enable_tracing")


def is_metrics_enabled() -> bool:
    """Check if metrics collection is enabled."""
    return get_feature_flags().is_enabled("enable_metrics")


def is_prometheus_enabled() -> bool:
    """Check if Prometheus metrics are enabled (should always be False)."""
    return get_feature_flags().is_enabled("enable_prometheus")


def is_database_tracing_enabled() -> bool:
    """Check if database tracing is enabled."""
    return get_feature_flags().is_enabled("enable_database_tracing")


def get_metrics_sample_rate() -> float:
    """Get current metrics sampling rate."""
    return get_feature_flags().get("metrics_sample_rate", 0.1)


def is_middleware_enabled(middleware_name: str) -> bool:
    """
    Check if specific middleware is enabled.
    
    Args:
        middleware_name: Name of middleware (request_logging, metrics_middleware, etc.)
        
    Returns:
        True if middleware is enabled
    """
    flag_name = f"enable_{middleware_name}"
    return get_feature_flags().is_enabled(flag_name)