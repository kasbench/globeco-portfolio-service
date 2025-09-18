"""
Security middleware for essential security headers and request ID generation.

This module provides essential security middleware that should always be active
regardless of environment configuration.
"""

import uuid
import time
from typing import Callable
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from app.logging_config import get_logger

logger = get_logger(__name__)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """
    Middleware for adding essential security headers to all responses.
    
    This middleware adds security headers that should be present in all
    environments to protect against common web vulnerabilities.
    """
    
    def __init__(self, app, strict_mode: bool = False):
        """
        Initialize security headers middleware.
        
        Args:
            app: ASGI application
            strict_mode: Whether to use strict security headers (production)
        """
        super().__init__(app)
        self.strict_mode = strict_mode
        self._logger = logger
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """
        Add security headers to response.
        
        Args:
            request: HTTP request
            call_next: Next middleware/handler
            
        Returns:
            HTTP response with security headers
        """
        try:
            # Process request
            response = await call_next(request)
            
            # Add essential security headers
            self._add_security_headers(response)
            
            return response
            
        except Exception as e:
            self._logger.error(
                "Security headers middleware error",
                error=str(e),
                error_type=type(e).__name__,
                path=request.url.path,
                method=request.method,
                exc_info=True
            )
            # Continue processing even if security headers fail
            return await call_next(request)
    
    def _add_security_headers(self, response: Response) -> None:
        """
        Add security headers to response.
        
        Args:
            response: HTTP response to modify
        """
        try:
            # Essential security headers for all environments
            headers = {
                # Prevent MIME type sniffing
                "X-Content-Type-Options": "nosniff",
                
                # Enable XSS protection
                "X-XSS-Protection": "1; mode=block",
                
                # Prevent clickjacking
                "X-Frame-Options": "DENY",
                
                # Remove server information
                "Server": "GlobeCo-Portfolio-Service",
                
                # Cache control for API responses
                "Cache-Control": "no-cache, no-store, must-revalidate",
                "Pragma": "no-cache",
                "Expires": "0",
            }
            
            # Add strict security headers in production/strict mode
            if self.strict_mode:
                headers.update({
                    # Strict transport security (HTTPS only)
                    "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
                    
                    # Content security policy (restrictive)
                    "Content-Security-Policy": (
                        "default-src 'self'; "
                        "script-src 'self' 'unsafe-inline'; "
                        "style-src 'self' 'unsafe-inline'; "
                        "img-src 'self' data:; "
                        "connect-src 'self'; "
                        "font-src 'self'; "
                        "object-src 'none'; "
                        "media-src 'self'; "
                        "frame-src 'none';"
                    ),
                    
                    # Referrer policy
                    "Referrer-Policy": "strict-origin-when-cross-origin",
                })
            else:
                # Development-friendly headers
                headers.update({
                    # Permissive CSP for development
                    "Content-Security-Policy": "default-src 'self' 'unsafe-inline' 'unsafe-eval'; connect-src 'self' *;",
                    
                    # Permissive referrer policy
                    "Referrer-Policy": "origin-when-cross-origin",
                })
            
            # Apply headers to response
            for header_name, header_value in headers.items():
                response.headers[header_name] = header_value
            
            self._logger.debug(
                "Security headers applied",
                headers_count=len(headers),
                strict_mode=self.strict_mode,
                status_code=response.status_code
            )
            
        except Exception as e:
            self._logger.warning(
                "Failed to add security headers",
                error=str(e),
                error_type=type(e).__name__,
                strict_mode=self.strict_mode
            )


class RequestIDMiddleware(BaseHTTPMiddleware):
    """
    Middleware for generating and tracking request IDs.
    
    This middleware generates unique request IDs for correlation and tracking
    across the entire request lifecycle.
    """
    
    def __init__(self, app, header_name: str = "X-Request-ID"):
        """
        Initialize request ID middleware.
        
        Args:
            app: ASGI application
            header_name: Header name for request ID
        """
        super().__init__(app)
        self.header_name = header_name
        self._logger = logger
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """
        Generate request ID and add to request/response.
        
        Args:
            request: HTTP request
            call_next: Next middleware/handler
            
        Returns:
            HTTP response with request ID header
        """
        try:
            # Generate or extract request ID
            request_id = self._get_or_generate_request_id(request)
            
            # Add request ID to request state for use by other components
            request.state.request_id = request_id
            
            # Process request
            start_time = time.time()
            response = await call_next(request)
            duration_ms = (time.time() - start_time) * 1000
            
            # Add request ID to response headers
            response.headers[self.header_name] = request_id
            
            # Log request completion with ID
            self._logger.debug(
                "Request completed",
                request_id=request_id,
                method=request.method,
                path=request.url.path,
                status_code=response.status_code,
                duration_ms=f"{duration_ms:.2f}"
            )
            
            return response
            
        except Exception as e:
            self._logger.error(
                "Request ID middleware error",
                error=str(e),
                error_type=type(e).__name__,
                path=request.url.path,
                method=request.method,
                exc_info=True
            )
            # Continue processing even if request ID fails
            response = await call_next(request)
            # Try to add a fallback request ID
            try:
                response.headers[self.header_name] = str(uuid.uuid4())
            except Exception:
                pass
            return response
    
    def _get_or_generate_request_id(self, request: Request) -> str:
        """
        Get existing request ID from headers or generate new one.
        
        Args:
            request: HTTP request
            
        Returns:
            Request ID string
        """
        try:
            # Check if request ID already exists in headers
            existing_id = request.headers.get(self.header_name)
            if existing_id:
                self._logger.debug(
                    "Using existing request ID from headers",
                    request_id=existing_id,
                    header_name=self.header_name
                )
                return existing_id
            
            # Check for other common request ID headers
            common_headers = [
                "X-Correlation-ID",
                "X-Trace-ID", 
                "X-Request-Id",
                "Request-ID"
            ]
            
            for header in common_headers:
                existing_id = request.headers.get(header)
                if existing_id:
                    self._logger.debug(
                        "Using existing request ID from alternate header",
                        request_id=existing_id,
                        source_header=header
                    )
                    return existing_id
            
            # Generate new request ID
            new_id = str(uuid.uuid4())
            self._logger.debug(
                "Generated new request ID",
                request_id=new_id,
                method=request.method,
                path=request.url.path
            )
            return new_id
            
        except Exception as e:
            self._logger.warning(
                "Error handling request ID, generating fallback",
                error=str(e),
                error_type=type(e).__name__
            )
            return str(uuid.uuid4())


class BasicErrorHandlingMiddleware(BaseHTTPMiddleware):
    """
    Basic error handling middleware for essential error processing.
    
    This middleware provides basic error handling and logging that should
    always be active to ensure proper error responses and logging.
    """
    
    def __init__(self, app, include_error_details: bool = False):
        """
        Initialize basic error handling middleware.
        
        Args:
            app: ASGI application
            include_error_details: Whether to include error details in responses
        """
        super().__init__(app)
        self.include_error_details = include_error_details
        self._logger = logger
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """
        Handle errors and provide consistent error responses.
        
        Args:
            request: HTTP request
            call_next: Next middleware/handler
            
        Returns:
            HTTP response (potentially error response)
        """
        try:
            response = await call_next(request)
            return response
            
        except Exception as e:
            # Log the error
            request_id = getattr(request.state, 'request_id', 'unknown')
            
            self._logger.error(
                "Unhandled error in request processing",
                request_id=request_id,
                method=request.method,
                path=request.url.path,
                error=str(e),
                error_type=type(e).__name__,
                exc_info=True
            )
            
            # Create error response
            from fastapi import HTTPException
            from fastapi.responses import JSONResponse
            
            # Determine error status code
            status_code = 500
            if isinstance(e, HTTPException):
                status_code = e.status_code
            elif hasattr(e, 'status_code'):
                status_code = e.status_code
            
            # Create error response body
            error_body = {
                "error": "Internal server error",
                "request_id": request_id,
                "timestamp": time.time()
            }
            
            # Include error details if configured (development mode)
            if self.include_error_details:
                error_body.update({
                    "error_type": type(e).__name__,
                    "error_message": str(e),
                })
            
            return JSONResponse(
                status_code=status_code,
                content=error_body
            )