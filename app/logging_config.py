import json
import logging
import logging.config
import sys
import time
import uuid
import random
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from contextvars import ContextVar
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
import socket
import os

# Context variables for request-scoped data
request_id_var: ContextVar[Optional[str]] = ContextVar('request_id', default=None)
correlation_id_var: ContextVar[Optional[str]] = ContextVar('correlation_id', default=None)
user_id_var: ContextVar[Optional[str]] = ContextVar('user_id', default=None)
operation_var: ContextVar[Optional[str]] = ContextVar('operation', default=None)


class LogSampler:
    """
    Log sampling implementation for high-volume operations.
    
    This class implements probabilistic sampling to reduce log volume
    for bulk operations and high-frequency events while ensuring
    error logs are always captured.
    """
    
    def __init__(self, default_rate: float = 1.0):
        """
        Initialize log sampler.
        
        Args:
            default_rate: Default sampling rate (0.0 to 1.0)
        """
        self.default_rate = default_rate
        self.operation_rates: Dict[str, float] = {}
    
    def set_operation_rate(self, operation: str, rate: float) -> None:
        """
        Set sampling rate for specific operation.
        
        Args:
            operation: Operation name
            rate: Sampling rate (0.0 to 1.0)
        """
        if not 0.0 <= rate <= 1.0:
            raise ValueError("Sampling rate must be between 0.0 and 1.0")
        self.operation_rates[operation] = rate
    
    def should_log(self, level: int, operation: Optional[str] = None) -> bool:
        """
        Determine if log entry should be recorded based on sampling.
        
        Args:
            level: Log level (logging.DEBUG, INFO, etc.)
            operation: Optional operation name for specific sampling
            
        Returns:
            True if log should be recorded, False otherwise
        """
        # Always log warnings and errors
        if level >= logging.WARNING:
            return True
        
        # Get sampling rate for operation or use default
        rate = self.operation_rates.get(operation, self.default_rate)
        
        # Sample based on rate
        return random.random() < rate

class JSONFormatter(logging.Formatter):
    """Custom JSON formatter for structured logging"""
    
    def __init__(self, application: str = "globeco-portfolio-service"):
        super().__init__()
        self.application = application
        self.server = socket.gethostname()
    
    def format(self, record: logging.LogRecord) -> str:
        """Format log record as JSON"""
        log_entry = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname.lower(),
            "msg": record.getMessage(),
            "application": self.application,
            "server": self.server,
            "location": f"{record.name}:{record.funcName}:{record.lineno}",
        }
        
        # Add request-scoped context if available
        request_id = request_id_var.get()
        if request_id:
            log_entry["request_id"] = request_id
            
        correlation_id = correlation_id_var.get()
        if correlation_id:
            log_entry["correlation_id"] = correlation_id
        
        # Add extra fields from the log record
        if hasattr(record, 'extra_fields'):
            log_entry.update(record.extra_fields)
        
        # Add exception info if present
        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)
        
        return json.dumps(log_entry, default=str)

class StructuredLogger:
    """Wrapper for structured logging with context"""
    
    def __init__(self, name: str):
        self.logger = logging.getLogger(name)
    
    def _log(self, level: int, msg: str, **extra_fields):
        """Internal log method with extra fields"""
        if self.logger.isEnabledFor(level):
            record = self.logger.makeRecord(
                self.logger.name, level, "", 0, msg, (), None
            )
            record.extra_fields = extra_fields
            self.logger.handle(record)
    
    def info(self, msg: str, **extra_fields):
        self._log(logging.INFO, msg, **extra_fields)
    
    def warning(self, msg: str, **extra_fields):
        self._log(logging.WARNING, msg, **extra_fields)
    
    def error(self, msg: str, **extra_fields):
        self._log(logging.ERROR, msg, **extra_fields)
    
    def debug(self, msg: str, **extra_fields):
        self._log(logging.DEBUG, msg, **extra_fields)
    
    def critical(self, msg: str, **extra_fields):
        self._log(logging.CRITICAL, msg, **extra_fields)

class OptimizedLoggingMiddleware(BaseHTTPMiddleware):
    """
    Optimized middleware for request/response logging with correlation IDs.
    
    This middleware provides structured logging with correlation ID propagation,
    conditional logging based on environment, and log sampling for high-volume
    operations to reduce overhead in production.
    """
    
    def __init__(self, app, logger: Optional['OptimizedStructuredLogger'] = None,
                 enable_request_logging: bool = True):
        """
        Initialize optimized logging middleware.
        
        Args:
            app: FastAPI application
            logger: Structured logger instance
            enable_request_logging: Whether to log requests/responses
        """
        super().__init__(app)
        self.logger = logger or OptimizedStructuredLogger(__name__)
        self.enable_request_logging = enable_request_logging
    
    async def dispatch(self, request: Request, call_next):
        # Always generate request ID and extract correlation ID
        request_id = str(uuid.uuid4())
        correlation_id = request.headers.get("x-correlation-id", request_id)
        
        # Set context variables for all subsequent logging
        request_id_var.set(request_id)
        correlation_id_var.set(correlation_id)
        
        # Skip detailed logging if disabled (production optimization)
        if not self.enable_request_logging:
            try:
                response: Response = await call_next(request)
                # Always add request ID to response headers
                response.headers["x-request-id"] = request_id
                if correlation_id != request_id:
                    response.headers["x-correlation-id"] = correlation_id
                return response
            except Exception as e:
                # Always log errors even if request logging is disabled
                self.logger.error(
                    f"Request failed: {request.method} {request.url.path}",
                    operation="request_error",
                    error=str(e)
                )
                raise
        
        # Full request/response logging (development/staging)
        client_ip = self._get_client_ip(request)
        start_time = time.time()
        method = request.method
        path = str(request.url.path)
        
        # Log incoming request (sampled)
        self.logger.debug(
            f"Request: {method} {path}",
            operation="request",
            method=method,
            path=path,
            ip=client_ip
        )
        
        try:
            # Process request
            response: Response = await call_next(request)
            duration = time.time() - start_time
            
            # Log response (sampled, but always log slow requests)
            if duration > 1.0:  # Always log slow requests (>1s)
                self.logger.warning(
                    f"Slow request: {method} {path} - {response.status_code}",
                    operation="slow_request",
                    method=method,
                    path=path,
                    status=response.status_code,
                    duration=round(duration * 1000, 2)
                )
            else:
                self.logger.debug(
                    f"Response: {method} {path} - {response.status_code}",
                    operation="response",
                    method=method,
                    path=path,
                    status=response.status_code,
                    duration=round(duration * 1000, 2)
                )
            
            # Add request ID to response headers
            response.headers["x-request-id"] = request_id
            if correlation_id != request_id:
                response.headers["x-correlation-id"] = correlation_id
            
            return response
            
        except Exception as e:
            duration = time.time() - start_time
            
            # Always log errors
            self.logger.error(
                f"Request error: {method} {path}",
                operation="request_error",
                method=method,
                path=path,
                duration=round(duration * 1000, 2),
                error=str(e)
            )
            raise
    
    def _get_client_ip(self, request: Request) -> str:
        """Extract client IP address from request"""
        # Check for forwarded headers first (for load balancers/proxies)
        forwarded_for = request.headers.get("x-forwarded-for")
        if forwarded_for:
            return forwarded_for.split(",")[0].strip()
        
        real_ip = request.headers.get("x-real-ip")
        if real_ip:
            return real_ip
        
        # Fall back to direct client IP
        if hasattr(request, "client") and request.client:
            return request.client.host
        
        return "unknown"


class LoggingMiddleware(OptimizedLoggingMiddleware):
    """
    Legacy LoggingMiddleware for backward compatibility.
    
    This class maintains the original interface while delegating to the
    optimized implementation with default settings.
    """
    
    def __init__(self, app, logger: Optional[StructuredLogger] = None):
        """
        Initialize legacy logging middleware.
        
        Args:
            app: FastAPI application
            logger: Legacy structured logger (converted to optimized)
        """
        # Convert legacy logger to optimized logger if needed
        if logger and isinstance(logger, StructuredLogger):
            optimized_logger = OptimizedStructuredLogger(logger.logger.name)
        else:
            optimized_logger = OptimizedStructuredLogger(__name__)
        
        super().__init__(app, optimized_logger, enable_request_logging=True)


class CorrelationMiddleware(BaseHTTPMiddleware):
    """
    Dedicated middleware for correlation ID generation and propagation.
    
    This middleware handles correlation ID generation, extraction from headers,
    and propagation through context variables for structured logging across
    the entire request lifecycle.
    """
    
    def __init__(self, app):
        """Initialize correlation middleware."""
        super().__init__(app)
    
    async def dispatch(self, request: Request, call_next):
        """
        Process request with correlation ID handling.
        
        Generates or extracts correlation IDs and sets context variables
        for use throughout the request processing pipeline.
        """
        # Generate unique request ID
        request_id = str(uuid.uuid4())
        
        # Extract or generate correlation ID
        correlation_id = (
            request.headers.get("x-correlation-id") or
            request.headers.get("correlation-id") or
            request.headers.get("trace-id") or
            request_id
        )
        
        # Extract user ID if available (from auth headers)
        user_id = (
            request.headers.get("x-user-id") or
            request.headers.get("user-id")
        )
        
        # Set context variables for the entire request
        request_id_var.set(request_id)
        correlation_id_var.set(correlation_id)
        if user_id:
            user_id_var.set(user_id)
        
        try:
            # Process request
            response = await call_next(request)
            
            # Add correlation headers to response
            response.headers["x-request-id"] = request_id
            response.headers["x-correlation-id"] = correlation_id
            
            return response
            
        finally:
            # Clean up context variables
            request_id_var.set(None)
            correlation_id_var.set(None)
            user_id_var.set(None)
            operation_var.set(None)


class EnhancedStructuredFormatter(logging.Formatter):
    """
    Enhanced structured logging formatter with correlation IDs and essential fields.
    
    This formatter creates structured log entries with correlation IDs,
    user context, and operation tracking while maintaining minimal overhead
    for production environments.
    """
    
    def __init__(self, application: str = "globeco-portfolio-service", 
                 include_location: bool = False):
        """
        Initialize enhanced structured formatter.
        
        Args:
            application: Application name
            include_location: Whether to include code location (disabled in production)
        """
        super().__init__()
        self.application = application
        self.server = socket.gethostname()
        self.include_location = include_location
    
    def format(self, record: logging.LogRecord) -> str:
        """Format log record with enhanced structured fields"""
        # Core log entry
        log_entry = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname.lower(),
            "message": record.getMessage(),
            "application": self.application,
        }
        
        # Add correlation context
        request_id = request_id_var.get()
        if request_id:
            log_entry["request_id"] = request_id
            
        correlation_id = correlation_id_var.get()
        if correlation_id and correlation_id != request_id:
            log_entry["correlation_id"] = correlation_id
            
        user_id = user_id_var.get()
        if user_id:
            log_entry["user_id"] = user_id
            
        operation = operation_var.get()
        if operation:
            log_entry["operation"] = operation
        
        # Add location info if enabled (development only)
        if self.include_location:
            log_entry["location"] = f"{record.name}:{record.funcName}:{record.lineno}"
            log_entry["server"] = self.server
        
        # Add extra fields from log record
        if hasattr(record, 'extra_fields') and record.extra_fields:
            log_entry.update(record.extra_fields)
        
        # Add exception info for errors
        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)
        
        return json.dumps(log_entry, separators=(',', ':'), default=str)


class ContextualLogger:
    """
    Contextual logger that automatically includes correlation IDs and operation context.
    
    This logger provides structured logging with automatic context propagation,
    making it easy to trace requests across service boundaries and operations.
    """
    
    def __init__(self, name: str, sampler: Optional[LogSampler] = None):
        """
        Initialize contextual logger.
        
        Args:
            name: Logger name
            sampler: Optional log sampler
        """
        self.logger = logging.getLogger(name)
        self.sampler = sampler or LogSampler()
        self.name = name
    
    def set_operation_context(self, operation: str) -> None:
        """
        Set operation context for subsequent log entries.
        
        Args:
            operation: Operation name (e.g., 'create_portfolio', 'bulk_insert')
        """
        operation_var.set(operation)
    
    def clear_operation_context(self) -> None:
        """Clear operation context."""
        operation_var.set(None)
    
    def _should_log(self, level: int, operation: Optional[str] = None) -> bool:
        """Check if log should be recorded based on level and sampling"""
        return (self.logger.isEnabledFor(level) and 
                self.sampler.should_log(level, operation))
    
    def _log_with_context(self, level: int, msg: str, operation: Optional[str] = None, 
                         **extra_fields):
        """Log with automatic context inclusion"""
        if self._should_log(level, operation):
            # Add current operation to extra fields if not specified
            if operation:
                extra_fields['operation'] = operation
            elif not extra_fields.get('operation'):
                current_op = operation_var.get()
                if current_op:
                    extra_fields['operation'] = current_op
            
            record = self.logger.makeRecord(
                self.logger.name, level, "", 0, msg, (), None
            )
            if extra_fields:
                record.extra_fields = extra_fields
            self.logger.handle(record)
    
    def info(self, msg: str, operation: Optional[str] = None, **extra_fields):
        """Log info message with context"""
        self._log_with_context(logging.INFO, msg, operation, **extra_fields)
    
    def warning(self, msg: str, operation: Optional[str] = None, **extra_fields):
        """Log warning message with context"""
        self._log_with_context(logging.WARNING, msg, operation, **extra_fields)
    
    def error(self, msg: str, operation: Optional[str] = None, **extra_fields):
        """Log error message with context"""
        self._log_with_context(logging.ERROR, msg, operation, **extra_fields)
    
    def debug(self, msg: str, operation: Optional[str] = None, **extra_fields):
        """Log debug message with context"""
        self._log_with_context(logging.DEBUG, msg, operation, **extra_fields)
    
    def critical(self, msg: str, operation: Optional[str] = None, **extra_fields):
        """Log critical message with context"""
        self._log_with_context(logging.CRITICAL, msg, operation, **extra_fields)
    
    def operation_start(self, operation: str, **context):
        """Log operation start with context"""
        self.set_operation_context(operation)
        self.info(f"Operation started: {operation}", operation=f"{operation}_start", **context)
    
    def operation_end(self, operation: str, duration_ms: float = None, 
                     success: bool = True, **context):
        """Log operation end with context"""
        level = logging.INFO if success else logging.WARNING
        extra = {"success": success}
        if duration_ms is not None:
            extra["duration_ms"] = duration_ms
        extra.update(context)
        
        self._log_with_context(
            level, 
            f"Operation {'completed' if success else 'failed'}: {operation}",
            operation=f"{operation}_end",
            **extra
        )
        self.clear_operation_context()

def get_production_log_config(application: str = "globeco-portfolio-service") -> Dict[str, Any]:
    """
    Get production-optimized logging configuration with WARNING level default.
    
    This function creates a minimal logging configuration optimized for production
    environments with reduced overhead and essential information only.
    
    Args:
        application: Application name for log entries
        
    Returns:
        Dictionary with production logging configuration
    """
    return {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "production": {
                "()": ProductionFormatter,
                "application": application,
            },
            "minimal": {
                "format": "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
                "datefmt": "%Y-%m-%d %H:%M:%S",
            }
        },
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "level": "WARNING",
                "formatter": "production",
                "stream": "ext://sys.stdout",
            },
            "error_console": {
                "class": "logging.StreamHandler", 
                "level": "ERROR",
                "formatter": "production",
                "stream": "ext://sys.stderr",
            }
        },
        "loggers": {
            "app": {
                "level": "WARNING",
                "handlers": ["console"],
                "propagate": False,
            },
            "uvicorn": {
                "level": "WARNING",
                "handlers": ["console"],
                "propagate": False,
            },
            "uvicorn.access": {
                "level": "ERROR",  # Disable access logs in production
                "handlers": [],
                "propagate": False,
            },
            "httpx": {
                "level": "ERROR",
                "handlers": ["console"],
                "propagate": False,
            },
            "motor": {
                "level": "ERROR",
                "handlers": ["console"],
                "propagate": False,
            },
            "pymongo": {
                "level": "ERROR",
                "handlers": ["console"],
                "propagate": False,
            }
        },
        "root": {
            "level": "WARNING",
            "handlers": ["console", "error_console"],
        }
    }


class ProductionFormatter(logging.Formatter):
    """
    Minimal logging formatter optimized for production environments.
    
    This formatter creates compact log entries with essential fields only,
    reducing logging overhead while maintaining necessary information for
    debugging and monitoring.
    """
    
    def __init__(self, application: str = "globeco-portfolio-service"):
        super().__init__()
        self.application = application
        self.server = socket.gethostname()
    
    def format(self, record: logging.LogRecord) -> str:
        """Format log record with minimal essential fields"""
        # Essential fields only for production
        log_entry = {
            "ts": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname.lower(),
            "msg": record.getMessage(),
            "app": self.application,
        }
        
        # Add request context if available (minimal)
        request_id = request_id_var.get()
        if request_id:
            log_entry["req_id"] = request_id
            
        correlation_id = correlation_id_var.get()
        if correlation_id and correlation_id != request_id:
            log_entry["corr_id"] = correlation_id
        
        # Add exception info only for errors
        if record.levelno >= logging.ERROR and record.exc_info:
            log_entry["exc"] = self.formatException(record.exc_info)
        
        # Add extra fields if present (limited)
        if hasattr(record, 'extra_fields') and record.extra_fields:
            # Only include essential extra fields in production
            essential_fields = ['duration', 'status', 'error', 'operation']
            for field in essential_fields:
                if field in record.extra_fields:
                    log_entry[field] = record.extra_fields[field]
        
        return json.dumps(log_entry, separators=(',', ':'), default=str)


class OptimizedStructuredLogger:
    """
    Optimized structured logger with sampling and minimal overhead.
    
    This logger provides structured logging with correlation IDs,
    log sampling for bulk operations, and environment-based configuration.
    """
    
    def __init__(self, name: str, sampler: Optional[LogSampler] = None):
        """
        Initialize optimized structured logger.
        
        Args:
            name: Logger name
            sampler: Log sampler for volume control
        """
        self.logger = logging.getLogger(name)
        self.sampler = sampler or LogSampler()
    
    def _should_log(self, level: int, operation: Optional[str] = None) -> bool:
        """Check if log should be recorded based on level and sampling"""
        return (self.logger.isEnabledFor(level) and 
                self.sampler.should_log(level, operation))
    
    def _log(self, level: int, msg: str, operation: Optional[str] = None, **extra_fields):
        """Internal log method with sampling and extra fields"""
        if self._should_log(level, operation):
            record = self.logger.makeRecord(
                self.logger.name, level, "", 0, msg, (), None
            )
            # Only add extra fields if they exist to minimize overhead
            if extra_fields:
                record.extra_fields = extra_fields
            self.logger.handle(record)
    
    def info(self, msg: str, operation: Optional[str] = None, **extra_fields):
        """Log info message with optional sampling"""
        self._log(logging.INFO, msg, operation, **extra_fields)
    
    def warning(self, msg: str, operation: Optional[str] = None, **extra_fields):
        """Log warning message (always recorded)"""
        self._log(logging.WARNING, msg, operation, **extra_fields)
    
    def error(self, msg: str, operation: Optional[str] = None, **extra_fields):
        """Log error message (always recorded)"""
        self._log(logging.ERROR, msg, operation, **extra_fields)
    
    def debug(self, msg: str, operation: Optional[str] = None, **extra_fields):
        """Log debug message with optional sampling"""
        self._log(logging.DEBUG, msg, operation, **extra_fields)
    
    def critical(self, msg: str, operation: Optional[str] = None, **extra_fields):
        """Log critical message (always recorded)"""
        self._log(logging.CRITICAL, msg, operation, **extra_fields)
    
    def bulk_operation_start(self, operation: str, count: int) -> None:
        """Log start of bulk operation (sampled)"""
        self.info(f"Bulk operation started: {operation}", 
                 operation="bulk_start", count=count, op=operation)
    
    def bulk_operation_end(self, operation: str, count: int, duration_ms: float, 
                          errors: int = 0) -> None:
        """Log end of bulk operation (sampled)"""
        level = logging.WARNING if errors > 0 else logging.INFO
        self._log(level, f"Bulk operation completed: {operation}", 
                 operation="bulk_end", count=count, duration=duration_ms, 
                 errors=errors, op=operation)


def setup_environment_logging(environment: str = None, 
                            log_sampling_rate: float = None,
                            application: str = "globeco-portfolio-service") -> OptimizedStructuredLogger:
    """
    Setup environment-appropriate logging configuration.
    
    This function configures logging based on environment with optimized
    settings for each deployment target (development, staging, production).
    
    Args:
        environment: Environment name (development, staging, production)
        log_sampling_rate: Override sampling rate
        application: Application name
        
    Returns:
        OptimizedStructuredLogger instance
    """
    # Detect environment if not provided
    if environment is None:
        environment = os.getenv("PORTFOLIO_SERVICE_ENV", 
                              os.getenv("ENVIRONMENT", 
                                      os.getenv("ENV", "development"))).lower()
    
    # Remove existing handlers
    root_logger = logging.getLogger()
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    
    # Configure based on environment
    if environment == "production":
        # Production: minimal logging with WARNING level
        config = get_production_log_config(application)
        logging.config.dictConfig(config)
        
        # Setup log sampling for production
        sampler = LogSampler(default_rate=log_sampling_rate or 0.1)
        sampler.set_operation_rate("bulk_start", 0.05)  # 5% sampling for bulk starts
        sampler.set_operation_rate("bulk_end", 0.2)     # 20% sampling for bulk ends
        sampler.set_operation_rate("request", 0.01)     # 1% sampling for requests
        
    elif environment == "staging":
        # Staging: moderate logging with INFO level
        formatter = JSONFormatter(application=application)
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(formatter)
        console_handler.setLevel(logging.INFO)
        
        root_logger.setLevel(logging.INFO)
        root_logger.addHandler(console_handler)
        
        # Moderate sampling for staging
        sampler = LogSampler(default_rate=log_sampling_rate or 0.5)
        sampler.set_operation_rate("bulk_start", 0.3)
        sampler.set_operation_rate("bulk_end", 0.8)
        sampler.set_operation_rate("request", 0.1)
        
    else:
        # Development: full logging with DEBUG level
        formatter = JSONFormatter(application=application)
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(formatter)
        console_handler.setLevel(logging.DEBUG)
        
        root_logger.setLevel(logging.DEBUG)
        root_logger.addHandler(console_handler)
        
        # No sampling in development
        sampler = LogSampler(default_rate=1.0)
    
    # Configure third-party library logging
    if environment == "production":
        logging.getLogger("uvicorn.access").setLevel(logging.ERROR)
        logging.getLogger("httpx").setLevel(logging.ERROR)
        logging.getLogger("motor").setLevel(logging.ERROR)
        logging.getLogger("pymongo").setLevel(logging.ERROR)
    else:
        logging.getLogger("uvicorn.access").setLevel(logging.INFO)
        logging.getLogger("httpx").setLevel(logging.WARNING)
        logging.getLogger("motor").setLevel(logging.WARNING)
        logging.getLogger("pymongo").setLevel(logging.WARNING)
    
    return OptimizedStructuredLogger("app", sampler)


def setup_logging(log_level: str = "INFO", application: str = "globeco-portfolio-service"):
    """
    Configure structured JSON logging (legacy compatibility).
    
    This function maintains backward compatibility while delegating to
    the new environment-based logging setup.
    """
    # Map log level to environment for backward compatibility
    environment_map = {
        "DEBUG": "development",
        "INFO": "staging", 
        "WARNING": "production",
        "ERROR": "production"
    }
    
    environment = environment_map.get(log_level.upper(), "development")
    return setup_environment_logging(environment, application=application)

# Convenience functions to get loggers
def get_logger(name: str) -> StructuredLogger:
    """Get a structured logger instance (legacy compatibility)"""
    return StructuredLogger(name)


def get_optimized_logger(name: str, sampler: Optional[LogSampler] = None) -> OptimizedStructuredLogger:
    """
    Get an optimized structured logger instance.
    
    Args:
        name: Logger name
        sampler: Optional log sampler for volume control
        
    Returns:
        OptimizedStructuredLogger instance
    """
    return OptimizedStructuredLogger(name, sampler)


def create_bulk_operation_logger(environment: str = "production") -> OptimizedStructuredLogger:
    """
    Create a logger optimized for bulk operations with appropriate sampling.
    
    Args:
        environment: Environment name for sampling configuration
        
    Returns:
        OptimizedStructuredLogger configured for bulk operations
    """
    # Configure sampler based on environment
    if environment == "production":
        sampler = LogSampler(default_rate=0.1)
        sampler.set_operation_rate("bulk_start", 0.05)
        sampler.set_operation_rate("bulk_end", 0.2)
        sampler.set_operation_rate("bulk_progress", 0.01)
    elif environment == "staging":
        sampler = LogSampler(default_rate=0.5)
        sampler.set_operation_rate("bulk_start", 0.3)
        sampler.set_operation_rate("bulk_end", 0.8)
        sampler.set_operation_rate("bulk_progress", 0.1)
    else:
        # Development: no sampling
        sampler = LogSampler(default_rate=1.0)
    
    return OptimizedStructuredLogger("bulk_operations", sampler)


def get_contextual_logger(name: str, environment: str = "production") -> ContextualLogger:
    """
    Get a contextual logger with correlation ID support and environment-based sampling.
    
    Args:
        name: Logger name
        environment: Environment for sampling configuration
        
    Returns:
        ContextualLogger instance with appropriate sampling
    """
    # Configure sampler based on environment
    if environment == "production":
        sampler = LogSampler(default_rate=0.1)
        sampler.set_operation_rate("request", 0.01)
        sampler.set_operation_rate("bulk_start", 0.05)
        sampler.set_operation_rate("bulk_end", 0.2)
    elif environment == "staging":
        sampler = LogSampler(default_rate=0.5)
        sampler.set_operation_rate("request", 0.1)
        sampler.set_operation_rate("bulk_start", 0.3)
        sampler.set_operation_rate("bulk_end", 0.8)
    else:
        # Development: no sampling
        sampler = LogSampler(default_rate=1.0)
    
    return ContextualLogger(name, sampler)


def setup_correlation_logging(environment: str = "production", 
                            application: str = "globeco-portfolio-service") -> ContextualLogger:
    """
    Setup complete correlation-based logging system.
    
    This function configures the entire logging system with correlation ID support,
    structured formatting, and environment-appropriate sampling.
    
    Args:
        environment: Environment name (development, staging, production)
        application: Application name
        
    Returns:
        ContextualLogger instance ready for use
    """
    # Remove existing handlers
    root_logger = logging.getLogger()
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    
    # Configure formatter based on environment
    include_location = environment == "development"
    formatter = EnhancedStructuredFormatter(application, include_location)
    
    # Create console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    
    # Set log level based on environment
    if environment == "production":
        log_level = logging.WARNING
    elif environment == "staging":
        log_level = logging.INFO
    else:
        log_level = logging.DEBUG
    
    console_handler.setLevel(log_level)
    root_logger.setLevel(log_level)
    root_logger.addHandler(console_handler)
    
    # Configure third-party library logging
    if environment == "production":
        logging.getLogger("uvicorn.access").setLevel(logging.ERROR)
        logging.getLogger("httpx").setLevel(logging.ERROR)
        logging.getLogger("motor").setLevel(logging.ERROR)
        logging.getLogger("pymongo").setLevel(logging.ERROR)
    else:
        logging.getLogger("uvicorn.access").setLevel(logging.INFO)
        logging.getLogger("httpx").setLevel(logging.WARNING)
        logging.getLogger("motor").setLevel(logging.WARNING)
        logging.getLogger("pymongo").setLevel(logging.WARNING)
    
    return get_contextual_logger("app", environment)


class BulkOperationLogger:
    """
    Specialized logger for bulk operations with intelligent sampling.
    
    This logger provides optimized logging for high-volume bulk operations
    with configurable sampling rates to reduce log volume while maintaining
    visibility into operation progress and errors.
    """
    
    def __init__(self, logger: ContextualLogger, operation_name: str):
        """
        Initialize bulk operation logger.
        
        Args:
            logger: Base contextual logger
            operation_name: Name of the bulk operation
        """
        self.logger = logger
        self.operation_name = operation_name
        self.start_time = None
        self.processed_count = 0
        self.error_count = 0
        self.last_progress_log = 0
        self.progress_interval = 100  # Log every N items in production
    
    def start_operation(self, total_count: int, **context):
        """
        Log start of bulk operation.
        
        Args:
            total_count: Total number of items to process
            **context: Additional context fields
        """
        self.start_time = time.time()
        self.processed_count = 0
        self.error_count = 0
        self.last_progress_log = 0
        
        self.logger.operation_start(
            self.operation_name,
            total_count=total_count,
            **context
        )
    
    def log_progress(self, processed: int, errors: int = 0, force: bool = False, **context):
        """
        Log bulk operation progress with intelligent sampling.
        
        Args:
            processed: Number of items processed so far
            errors: Number of errors encountered
            force: Force logging regardless of sampling
            **context: Additional context fields
        """
        self.processed_count = processed
        self.error_count = errors
        
        # Log progress at intervals or if forced
        if force or (processed - self.last_progress_log) >= self.progress_interval:
            self.logger.info(
                f"Bulk operation progress: {self.operation_name}",
                operation="bulk_progress",
                processed=processed,
                errors=errors,
                **context
            )
            self.last_progress_log = processed
    
    def log_batch_result(self, batch_size: int, batch_errors: int = 0, 
                        batch_duration_ms: float = None, **context):
        """
        Log individual batch processing result (sampled).
        
        Args:
            batch_size: Size of the processed batch
            batch_errors: Number of errors in this batch
            batch_duration_ms: Duration of batch processing
            **context: Additional context fields
        """
        extra = {
            "batch_size": batch_size,
            "batch_errors": batch_errors,
        }
        if batch_duration_ms is not None:
            extra["batch_duration_ms"] = batch_duration_ms
        extra.update(context)
        
        # Always log batches with errors, sample successful batches
        if batch_errors > 0:
            self.logger.warning(
                f"Batch completed with errors: {self.operation_name}",
                operation="bulk_batch_error",
                **extra
            )
        else:
            self.logger.debug(
                f"Batch completed: {self.operation_name}",
                operation="bulk_batch",
                **extra
            )
    
    def end_operation(self, success: bool = True, **context):
        """
        Log end of bulk operation with summary.
        
        Args:
            success: Whether operation completed successfully
            **context: Additional context fields
        """
        duration_ms = None
        if self.start_time:
            duration_ms = (time.time() - self.start_time) * 1000
        
        self.logger.operation_end(
            self.operation_name,
            duration_ms=duration_ms,
            success=success,
            total_processed=self.processed_count,
            total_errors=self.error_count,
            **context
        )
    
    def log_error(self, error: Exception, item_index: int = None, **context):
        """
        Log individual item processing error.
        
        Args:
            error: Exception that occurred
            item_index: Index of the item that failed (optional)
            **context: Additional context fields
        """
        extra = {
            "error": str(error),
            "error_type": type(error).__name__,
        }
        if item_index is not None:
            extra["item_index"] = item_index
        extra.update(context)
        
        self.logger.error(
            f"Item processing error: {self.operation_name}",
            operation="bulk_item_error",
            **extra
        )


def create_bulk_logger(operation_name: str, environment: str = "production") -> BulkOperationLogger:
    """
    Create a bulk operation logger with environment-appropriate sampling.
    
    Args:
        operation_name: Name of the bulk operation
        environment: Environment for sampling configuration
        
    Returns:
        BulkOperationLogger instance
    """
    contextual_logger = get_contextual_logger(f"bulk.{operation_name}", environment)
    bulk_logger = BulkOperationLogger(contextual_logger, operation_name)
    
    # Adjust progress interval based on environment
    if environment == "production":
        bulk_logger.progress_interval = 1000  # Log every 1000 items
    elif environment == "staging":
        bulk_logger.progress_interval = 500   # Log every 500 items
    else:
        bulk_logger.progress_interval = 100   # Log every 100 items
    
    return bulk_logger


def disable_verbose_logging_for_production():
    """
    Disable verbose request/response logging in production environment.
    
    This function configures logging to remove verbose request/response
    logging that can impact performance in production environments.
    """
    # Disable uvicorn access logs
    logging.getLogger("uvicorn.access").setLevel(logging.ERROR)
    logging.getLogger("uvicorn.access").disabled = True
    
    # Reduce third-party library verbosity
    logging.getLogger("httpx").setLevel(logging.ERROR)
    logging.getLogger("motor").setLevel(logging.ERROR)
    logging.getLogger("pymongo").setLevel(logging.ERROR)
    logging.getLogger("bson").setLevel(logging.ERROR)
    
    # Disable FastAPI request logging
    logging.getLogger("fastapi").setLevel(logging.WARNING)
    
    # Create a null handler to completely suppress certain loggers
    null_handler = logging.NullHandler()
    logging.getLogger("uvicorn.access").addHandler(null_handler)


def configure_bulk_operation_sampling(environment: str = "production") -> Dict[str, float]:
    """
    Configure sampling rates for different bulk operations based on environment.
    
    Args:
        environment: Environment name
        
    Returns:
        Dictionary of operation names to sampling rates
    """
    if environment == "production":
        return {
            "bulk_portfolio_create": 0.05,      # 5% sampling
            "bulk_portfolio_update": 0.1,       # 10% sampling
            "bulk_portfolio_delete": 0.2,       # 20% sampling (more important)
            "bulk_validation": 0.01,             # 1% sampling (very high volume)
            "bulk_progress": 0.02,               # 2% sampling for progress logs
            "bulk_batch": 0.1,                   # 10% sampling for batch logs
        }
    elif environment == "staging":
        return {
            "bulk_portfolio_create": 0.3,
            "bulk_portfolio_update": 0.5,
            "bulk_portfolio_delete": 0.8,
            "bulk_validation": 0.1,
            "bulk_progress": 0.2,
            "bulk_batch": 0.5,
        }
    else:
        # Development: no sampling (100% logging)
        return {
            "bulk_portfolio_create": 1.0,
            "bulk_portfolio_update": 1.0,
            "bulk_portfolio_delete": 1.0,
            "bulk_validation": 1.0,
            "bulk_progress": 1.0,
            "bulk_batch": 1.0,
        }


def setup_optimized_logging_from_config():
    """
    Setup optimized logging system using environment configuration.
    
    This function integrates with the environment configuration system
    to automatically configure logging based on the current environment
    profile and feature flags.
    
    Returns:
        Tuple of (ContextualLogger, BulkOperationLogger) for general use
    """
    try:
        # Import here to avoid circular imports
        from .environment_config import get_config_manager, get_feature_flags
        
        config_manager = get_config_manager()
        feature_flags = get_feature_flags()
        
        environment = config_manager.current_environment
        logging_config = config_manager.get_logging_config()
        
        # Setup base logging system
        if feature_flags.is_enabled("enable_structured_logging"):
            logger = setup_correlation_logging(environment)
        else:
            # Fallback to basic logging
            logger = setup_environment_logging(environment)
        
        # Configure bulk operation sampling
        if feature_flags.is_enabled("log_sampling_rate"):
            sampling_rates = configure_bulk_operation_sampling(environment)
            
            # Apply sampling rates to logger
            if hasattr(logger, 'sampler'):
                for operation, rate in sampling_rates.items():
                    logger.sampler.set_operation_rate(operation, rate)
        
        # Disable verbose logging in production
        if environment == "production" and not feature_flags.is_enabled("enable_request_response_logging"):
            disable_verbose_logging_for_production()
        
        # Create bulk logger for common operations
        bulk_logger = create_bulk_logger("portfolio_operations", environment)
        
        return logger, bulk_logger
        
    except ImportError:
        # Fallback if environment config not available
        logger = setup_environment_logging("production")
        bulk_logger = create_bulk_logger("portfolio_operations", "production")
        return logger, bulk_logger