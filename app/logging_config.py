import json
import logging
import sys
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from contextvars import ContextVar
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
import socket

# Context variables for request-scoped data
request_id_var: ContextVar[Optional[str]] = ContextVar('request_id', default=None)
correlation_id_var: ContextVar[Optional[str]] = ContextVar('correlation_id', default=None)

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

class LoggingMiddleware(BaseHTTPMiddleware):
    """Middleware to log all HTTP requests and responses"""
    
    def __init__(self, app, logger: Optional[StructuredLogger] = None):
        super().__init__(app)
        self.logger = logger or StructuredLogger(__name__)
    
    async def dispatch(self, request: Request, call_next):
        # Generate request ID and extract correlation ID
        request_id = str(uuid.uuid4())
        correlation_id = request.headers.get("x-correlation-id", request_id)
        
        # Set context variables
        request_id_var.set(request_id)
        correlation_id_var.set(correlation_id)
        
        # Get client IP
        client_ip = self._get_client_ip(request)
        
        # Record request start time
        start_time = time.time()
        
        # Extract request details
        method = request.method
        path = str(request.url.path)
        query_params = str(request.url.query) if request.url.query else ""
        user_agent = request.headers.get("user-agent", "")
        
        # Log incoming request
        self.logger.info(
            f"Incoming {method} request to {path}",
            method=method,
            path=path,
            query_params=query_params,
            ip_address=client_ip,
            remote_addr=client_ip,
            user_agent=user_agent,
            request_id=request_id,
            correlation_id=correlation_id
        )
        
        try:
            # Process request
            response: Response = await call_next(request)
            
            # Calculate duration
            duration = time.time() - start_time
            
            # Get response size if available
            content_length = response.headers.get("content-length")
            bytes_sent = int(content_length) if content_length else 0
            
            # Log successful response
            self.logger.info(
                f"Completed {method} {path} - {response.status_code}",
                method=method,
                path=path,
                status=response.status_code,
                ip_address=client_ip,
                remote_addr=client_ip,
                user_agent=user_agent,
                bytes=bytes_sent,
                duration=round(duration * 1000, 2),  # Duration in milliseconds
                request_id=request_id,
                correlation_id=correlation_id
            )
            
            # Add request ID to response headers
            response.headers["x-request-id"] = request_id
            if correlation_id != request_id:
                response.headers["x-correlation-id"] = correlation_id
            
            return response
            
        except Exception as e:
            # Calculate duration for error case
            duration = time.time() - start_time
            
            # Log error response
            self.logger.error(
                f"Failed {method} {path} - {str(e)}",
                method=method,
                path=path,
                status=500,
                ip_address=client_ip,
                remote_addr=client_ip,
                user_agent=user_agent,
                duration=round(duration * 1000, 2),
                request_id=request_id,
                correlation_id=correlation_id,
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

def setup_logging(log_level: str = "INFO", application: str = "globeco-portfolio-service"):
    """Configure structured JSON logging"""
    
    # Remove existing handlers
    root_logger = logging.getLogger()
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    
    # Create JSON formatter
    formatter = JSONFormatter(application=application)
    
    # Create console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    
    # Configure root logger
    root_logger.setLevel(getattr(logging, log_level.upper()))
    root_logger.addHandler(console_handler)
    
    # Reduce noise from some third-party libraries
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    
    return StructuredLogger("app")

# Convenience function to get a structured logger
def get_logger(name: str) -> StructuredLogger:
    """Get a structured logger instance"""
    return StructuredLogger(name)