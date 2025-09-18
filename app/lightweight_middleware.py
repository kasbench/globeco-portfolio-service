"""
Lightweight middleware for performance-critical operations.
"""

import time
from typing import Callable
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from app.performance_config import performance_config
from app.logging_config import get_logger

logger = get_logger(__name__)

class LightweightPerformanceMiddleware(BaseHTTPMiddleware):
    """
    Lightweight middleware that bypasses heavy monitoring for bulk operations.
    """
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Process request with minimal overhead for bulk operations"""
        
        # Check if this is a bulk operation
        is_bulk = performance_config.is_bulk_operation(
            request.url.path, 
            request.method
        )
        
        if is_bulk:
            # Minimal processing for bulk operations
            start_time = time.time()
            
            # Log start with minimal details
            if not performance_config.MINIMAL_LOGGING_FOR_BULK:
                logger.info(
                    "Bulk operation started",
                    method=request.method,
                    path=request.url.path
                )
            
            # Process request
            response = await call_next(request)
            
            # Calculate duration
            duration_ms = (time.time() - start_time) * 1000
            
            # Log completion with timing
            logger.info(
                "Bulk operation completed",
                method=request.method,
                path=request.url.path,
                status_code=response.status_code,
                duration_ms=f"{duration_ms:.1f}"
            )
            
            return response
        
        else:
            # Normal processing for non-bulk operations
            return await call_next(request)