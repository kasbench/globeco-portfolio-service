"""
CPU Burn Middleware for High-CPU variant of the portfolio service.

This middleware artificially increases CPU consumption per request by performing
CPU-intensive work (iterative math computations) after each API call completes.
It is designed for performance benchmarking to simulate a service that consumes
approximately 500m additional CPU per request.

The middleware is enabled via the HIGH_CPU_MODE environment variable.
The burn duration can be tuned via CPU_BURN_DURATION_MS (default: 50ms per request).
"""

import os
import time
import math
import logging
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger(__name__)

# Configuration via environment variables
HIGH_CPU_MODE = os.getenv("HIGH_CPU_MODE", "false").lower() in ("1", "true", "yes")
CPU_BURN_DURATION_MS = int(os.getenv("CPU_BURN_DURATION_MS", "50"))

# Paths to skip (health checks, metrics endpoints)
SKIP_PATHS = frozenset({
    "/health",
    "/health/live",
    "/health/ready",
    "/health/startup",
    "/metrics",
    "/",
})


def cpu_burn(duration_ms: int) -> None:
    """
    Burn CPU for approximately the specified duration using iterative math.
    
    This performs repeated floating-point calculations (trig functions, sqrt)
    that cannot be optimized away by the interpreter, ensuring real CPU usage.
    
    Args:
        duration_ms: Target burn duration in milliseconds
    """
    deadline = time.perf_counter() + (duration_ms / 1000.0)
    x = 1.0
    while time.perf_counter() < deadline:
        # Perform a batch of math operations to reduce time.perf_counter() overhead
        for _ in range(100):
            x = math.sin(x) * math.cos(x) + math.sqrt(abs(x) + 1.0)
            x = math.atan2(x, x + 0.1) + math.log1p(abs(x))


class CPUBurnMiddleware(BaseHTTPMiddleware):
    """
    Middleware that artificially burns CPU after each request to simulate
    a high-CPU service variant for performance benchmarking.
    
    The burn happens AFTER the response is generated, adding to the total
    request CPU time without affecting the response content.
    """
    
    def __init__(self, app, burn_duration_ms: int = None):
        super().__init__(app)
        self.burn_duration_ms = burn_duration_ms or CPU_BURN_DURATION_MS
        logger.info(
            f"CPUBurnMiddleware initialized: burn_duration_ms={self.burn_duration_ms}"
        )
    
    async def dispatch(self, request: Request, call_next) -> Response:
        # Skip health/metrics endpoints to avoid interfering with probes
        if request.url.path in SKIP_PATHS:
            return await call_next(request)
        
        # Process the actual request
        response = await call_next(request)
        
        # Burn CPU after the response is ready
        cpu_burn(self.burn_duration_ms)
        
        return response
