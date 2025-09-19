"""
Fast-path middleware for optimized request processing.

This module provides lightweight middleware specifically designed for
fast-path endpoints with minimal overhead and early request validation.
"""

from fastapi import Request, Response, HTTPException
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from app.logging_config import get_logger
from app.environment_config import get_config_manager
import time
from typing import Callable

logger = get_logger(__name__)


class FastPathMiddleware(BaseHTTPMiddleware):
    """
    Lightweight middleware for fast-path endpoints.
    
    Provides:
    - Request size validation and early rejection
    - Minimal request/response logging
    - Performance timing headers
    - Fast error handling
    """
    
    def __init__(self, app, max_request_size: int = 1024 * 1024):  # 1MB default
        super().__init__(app)
        self.max_request_size = max_request_size
        self._config_manager = None
    
    def _get_config_manager(self):
        """Get configuration manager with caching."""
        if self._config_manager is None:
            try:
                self._config_manager = get_config_manager()
            except Exception:
                self._config_manager = None
        return self._config_manager
    
    def _should_log_requests(self) -> bool:
        """Determine if requests should be logged based on environment."""
        config_manager = self._get_config_manager()
        if config_manager:
            middleware_config = config_manager.get_middleware_config()
            return middleware_config.enable_request_logging
        return False  # Default to no logging for performance
    
    def _is_fast_path(self, path: str) -> bool:
        """Check if request is for a fast-path endpoint."""
        return path.startswith("/api/fast/")
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Process request with fast-path optimizations."""
        start_time = time.perf_counter()
        
        # Only apply fast-path processing to fast-path endpoints
        if not self._is_fast_path(request.url.path):
            return await call_next(request)
        
        try:
            # Fast request size validation for fast-path endpoints
            if hasattr(request, "headers"):
                content_length = request.headers.get("content-length")
                if content_length:
                    try:
                        size = int(content_length)
                        if size > self.max_request_size:
                            return JSONResponse(
                                content={
                                    "error": "Request too large",
                                    "detail": f"Request size {size} bytes exceeds {self.max_request_size} bytes",
                                    "maxSizeBytes": self.max_request_size
                                },
                                status_code=413,
                                headers={"X-Fast-Path": "true"}
                            )
                    except ValueError:
                        pass  # Invalid content-length, let the endpoint handle it
            
            # Minimal request logging for fast-path
            if self._should_log_requests():
                logger.debug(
                    f"Fast-path request: {request.method} {request.url.path}",
                    method=request.method,
                    path=request.url.path,
                    fast_path=True
                )
            
            # Process request
            response = await call_next(request)
            
            # Add performance timing headers
            end_time = time.perf_counter()
            processing_time_ms = (end_time - start_time) * 1000
            
            # Add fast-path headers
            response.headers["X-Fast-Path"] = "true"
            response.headers["X-Middleware-Time-Ms"] = str(round(processing_time_ms, 2))
            
            # Minimal response logging
            if self._should_log_requests():
                logger.debug(
                    f"Fast-path response: {response.status_code} in {processing_time_ms:.2f}ms",
                    status_code=response.status_code,
                    processing_time_ms=round(processing_time_ms, 2),
                    fast_path=True
                )
            
            return response
            
        except Exception as e:
            # Fast error handling
            end_time = time.perf_counter()
            processing_time_ms = (end_time - start_time) * 1000
            
            logger.error(
                f"Fast-path middleware error: {str(e)} in {processing_time_ms:.2f}ms",
                error=str(e),
                processing_time_ms=round(processing_time_ms, 2),
                path=request.url.path,
                fast_path=True
            )
            
            return JSONResponse(
                content={
                    "error": "Fast-path processing error",
                    "detail": "An error occurred during fast-path request processing"
                },
                status_code=500,
                headers={
                    "X-Fast-Path": "true",
                    "X-Middleware-Time-Ms": str(round(processing_time_ms, 2))
                }
            )


class RequestSizeValidator:
    """
    Utility class for request size validation with configurable limits.
    """
    
    def __init__(self, max_size: int = 1024 * 1024):  # 1MB default
        self.max_size = max_size
    
    def validate_size(self, request: Request) -> None:
        """
        Validate request size and raise HTTPException if too large.
        
        Args:
            request: FastAPI request object
            
        Raises:
            HTTPException: If request exceeds size limit
        """
        content_length = request.headers.get("content-length")
        if content_length:
            try:
                size = int(content_length)
                if size > self.max_size:
                    raise HTTPException(
                        status_code=413,
                        detail=f"Request too large: {size} bytes exceeds {self.max_size} bytes"
                    )
            except ValueError:
                # Invalid content-length header
                raise HTTPException(
                    status_code=400,
                    detail="Invalid Content-Length header"
                )
    
    async def validate_body_size(self, request: Request) -> bytes:
        """
        Read and validate request body size.
        
        Args:
            request: FastAPI request object
            
        Returns:
            Request body bytes
            
        Raises:
            HTTPException: If request body exceeds size limit
        """
        body = await request.body()
        if len(body) > self.max_size:
            raise HTTPException(
                status_code=413,
                detail=f"Request body too large: {len(body)} bytes exceeds {self.max_size} bytes"
            )
        return body


# Convenience functions for middleware configuration
def create_fast_path_middleware(max_request_size: int = 1024 * 1024) -> FastPathMiddleware:
    """
    Create fast-path middleware with specified configuration.
    
    Args:
        max_request_size: Maximum request size in bytes
        
    Returns:
        Configured FastPathMiddleware instance
    """
    return FastPathMiddleware(None, max_request_size=max_request_size)


def get_fast_path_config() -> dict:
    """
    Get fast-path middleware configuration.
    
    Returns:
        Dictionary with fast-path configuration
    """
    try:
        config_manager = get_config_manager()
        
        if config_manager:
            middleware_config = config_manager.get_middleware_config()
            return {
                "enabled": True,
                "max_request_size": 1024 * 1024,  # 1MB
                "request_logging": middleware_config.enable_request_logging,
                "environment": config_manager.current_environment
            }
        else:
            return {
                "enabled": True,
                "max_request_size": 1024 * 1024,  # 1MB
                "request_logging": False,
                "environment": "unknown"
            }
            
    except Exception as e:
        logger.error(f"Error getting fast-path config: {e}")
        return {
            "enabled": False,
            "error": str(e)
        }