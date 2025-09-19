"""
Optimized health check endpoints for Kubernetes probes.

This module provides fast, lightweight health check endpoints optimized for:
- Kubernetes liveness probes
- Kubernetes readiness probes  
- Kubernetes startup probes
- Load balancer health checks

All endpoints are designed to respond in <10ms as per requirements.
"""

import asyncio
import logging
import time
from typing import Dict, Any, Optional
from datetime import datetime, timezone
import threading
from dataclasses import dataclass

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import JSONResponse, PlainTextResponse

from app.database import get_database
from app.monitoring_health import get_monitoring_manager
from app.circuit_breaker import get_circuit_breaker_manager


# Health check cache to avoid repeated expensive operations
@dataclass
class HealthCache:
    """Cache for health check results."""
    last_check_time: float = 0.0
    last_result: Dict[str, Any] = None
    cache_duration: float = 5.0  # Cache for 5 seconds
    lock: threading.Lock = threading.Lock()
    
    def is_valid(self) -> bool:
        """Check if cached result is still valid."""
        return (time.time() - self.last_check_time) < self.cache_duration
    
    def get_cached_result(self) -> Optional[Dict[str, Any]]:
        """Get cached result if valid."""
        with self.lock:
            if self.is_valid() and self.last_result is not None:
                return self.last_result.copy()
        return None
    
    def cache_result(self, result: Dict[str, Any]) -> None:
        """Cache a health check result."""
        with self.lock:
            self.last_check_time = time.time()
            self.last_result = result.copy()


# Global health cache instances
_liveness_cache = HealthCache()
_readiness_cache = HealthCache(cache_duration=2.0)  # Shorter cache for readiness
_startup_cache = HealthCache(cache_duration=1.0)    # Very short cache for startup

# Router for health endpoints
router = APIRouter(tags=["health"])

# Logger
logger = logging.getLogger(__name__)


@router.get("/health", response_class=PlainTextResponse)
async def basic_health() -> str:
    """
    Ultra-fast basic health check.
    
    This endpoint provides the fastest possible health check response
    for basic load balancer health checks. Returns plain text "OK".
    
    Target response time: <5ms
    """
    return "OK"


@router.get("/health/live", response_class=JSONResponse)
async def liveness_probe() -> JSONResponse:
    """
    Kubernetes liveness probe endpoint.
    
    This endpoint checks if the application is alive and should not be restarted.
    It performs minimal checks to ensure fast response times.
    
    Target response time: <10ms
    
    Returns:
        JSON response with liveness status
    """
    start_time = time.perf_counter()
    
    # Check cache first
    cached_result = _liveness_cache.get_cached_result()
    if cached_result is not None:
        cached_result["response_time_ms"] = round((time.perf_counter() - start_time) * 1000, 2)
        cached_result["cached"] = True
        return JSONResponse(content=cached_result, status_code=200)
    
    try:
        # Minimal liveness checks
        current_time = datetime.now(timezone.utc)
        
        # Basic application state check
        is_alive = True  # Application is running if we reach this point
        
        result = {
            "status": "alive" if is_alive else "dead",
            "timestamp": current_time.isoformat(),
            "service": "globeco-portfolio-service",
            "probe_type": "liveness",
            "response_time_ms": round((time.perf_counter() - start_time) * 1000, 2),
            "cached": False
        }
        
        # Cache the result
        _liveness_cache.cache_result(result)
        
        return JSONResponse(
            content=result,
            status_code=200 if is_alive else 503
        )
    
    except Exception as e:
        logger.error(f"Liveness probe failed: {e}", exc_info=True)
        error_result = {
            "status": "dead",
            "error": str(e),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "service": "globeco-portfolio-service",
            "probe_type": "liveness",
            "response_time_ms": round((time.perf_counter() - start_time) * 1000, 2),
            "cached": False
        }
        return JSONResponse(content=error_result, status_code=503)


@router.get("/health/ready", response_class=JSONResponse)
async def readiness_probe() -> JSONResponse:
    """
    Kubernetes readiness probe endpoint.
    
    This endpoint checks if the application is ready to serve traffic.
    It performs essential dependency checks while maintaining fast response times.
    
    Target response time: <10ms
    
    Returns:
        JSON response with readiness status
    """
    start_time = time.perf_counter()
    
    # Check cache first
    cached_result = _readiness_cache.get_cached_result()
    if cached_result is not None:
        cached_result["response_time_ms"] = round((time.perf_counter() - start_time) * 1000, 2)
        cached_result["cached"] = True
        return JSONResponse(
            content=cached_result, 
            status_code=200 if cached_result["status"] == "ready" else 503
        )
    
    try:
        current_time = datetime.now(timezone.utc)
        checks = {}
        is_ready = True
        
        # Database connectivity check (with timeout)
        try:
            db_start = time.perf_counter()
            database = get_database()
            
            # Quick ping with very short timeout
            await asyncio.wait_for(
                database.client.admin.command('ping'),
                timeout=0.005  # 5ms timeout
            )
            
            db_time = round((time.perf_counter() - db_start) * 1000, 2)
            checks["database"] = {
                "status": "ready",
                "response_time_ms": db_time
            }
        except asyncio.TimeoutError:
            checks["database"] = {
                "status": "timeout",
                "response_time_ms": 5.0
            }
            is_ready = False
        except Exception as e:
            checks["database"] = {
                "status": "error",
                "error": str(e)[:100]  # Truncate long errors
            }
            is_ready = False
        
        # Circuit breaker status check (very fast)
        try:
            cb_manager = get_circuit_breaker_manager()
            cb_health = cb_manager.get_health_summary()
            
            checks["circuit_breakers"] = {
                "status": "ready" if cb_health["overall_health"] > 0.5 else "degraded",
                "healthy_ratio": cb_health["overall_health"]
            }
            
            # Don't fail readiness for circuit breaker issues
            # as they provide graceful degradation
        except Exception as e:
            checks["circuit_breakers"] = {
                "status": "error",
                "error": str(e)[:100]
            }
        
        result = {
            "status": "ready" if is_ready else "not_ready",
            "timestamp": current_time.isoformat(),
            "service": "globeco-portfolio-service",
            "probe_type": "readiness",
            "checks": checks,
            "response_time_ms": round((time.perf_counter() - start_time) * 1000, 2),
            "cached": False
        }
        
        # Cache the result
        _readiness_cache.cache_result(result)
        
        return JSONResponse(
            content=result,
            status_code=200 if is_ready else 503
        )
    
    except Exception as e:
        logger.error(f"Readiness probe failed: {e}", exc_info=True)
        error_result = {
            "status": "not_ready",
            "error": str(e),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "service": "globeco-portfolio-service",
            "probe_type": "readiness",
            "response_time_ms": round((time.perf_counter() - start_time) * 1000, 2),
            "cached": False
        }
        return JSONResponse(content=error_result, status_code=503)


@router.get("/health/startup", response_class=JSONResponse)
async def startup_probe() -> JSONResponse:
    """
    Kubernetes startup probe endpoint.
    
    This endpoint checks if the application has started successfully.
    It performs comprehensive startup validation while maintaining reasonable response times.
    
    Target response time: <10ms (after initial startup)
    
    Returns:
        JSON response with startup status
    """
    start_time = time.perf_counter()
    
    # Check cache first (very short cache for startup)
    cached_result = _startup_cache.get_cached_result()
    if cached_result is not None:
        cached_result["response_time_ms"] = round((time.perf_counter() - start_time) * 1000, 2)
        cached_result["cached"] = True
        return JSONResponse(
            content=cached_result,
            status_code=200 if cached_result["status"] == "started" else 503
        )
    
    try:
        current_time = datetime.now(timezone.utc)
        checks = {}
        is_started = True
        
        # Database connection check
        try:
            db_start = time.perf_counter()
            database = get_database()
            
            # Ping database with short timeout
            await asyncio.wait_for(
                database.client.admin.command('ping'),
                timeout=0.008  # 8ms timeout for startup
            )
            
            db_time = round((time.perf_counter() - db_start) * 1000, 2)
            checks["database"] = {
                "status": "connected",
                "response_time_ms": db_time
            }
        except Exception as e:
            checks["database"] = {
                "status": "error",
                "error": str(e)[:100]
            }
            is_started = False
        
        # Monitoring system check (optional, don't fail startup)
        try:
            monitoring_manager = get_monitoring_manager()
            monitoring_status = monitoring_manager.get_status()
            
            checks["monitoring"] = {
                "status": "initialized",
                "healthy": monitoring_status["health_checker"]["is_healthy"],
                "fallback_mode": monitoring_status["fallback_mode"]
            }
        except Exception as e:
            checks["monitoring"] = {
                "status": "error",
                "error": str(e)[:100]
            }
            # Don't fail startup for monitoring issues
        
        result = {
            "status": "started" if is_started else "starting",
            "timestamp": current_time.isoformat(),
            "service": "globeco-portfolio-service",
            "probe_type": "startup",
            "checks": checks,
            "response_time_ms": round((time.perf_counter() - start_time) * 1000, 2),
            "cached": False
        }
        
        # Cache the result
        _startup_cache.cache_result(result)
        
        return JSONResponse(
            content=result,
            status_code=200 if is_started else 503
        )
    
    except Exception as e:
        logger.error(f"Startup probe failed: {e}", exc_info=True)
        error_result = {
            "status": "starting",
            "error": str(e),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "service": "globeco-portfolio-service",
            "probe_type": "startup",
            "response_time_ms": round((time.perf_counter() - start_time) * 1000, 2),
            "cached": False
        }
        return JSONResponse(content=error_result, status_code=503)


@router.get("/health/detailed", response_class=JSONResponse)
async def detailed_health() -> JSONResponse:
    """
    Detailed health check endpoint for debugging and monitoring.
    
    This endpoint provides comprehensive health information including:
    - All dependency statuses
    - Performance metrics
    - Circuit breaker states
    - Monitoring system status
    
    Note: This endpoint may take longer than probe endpoints.
    
    Returns:
        JSON response with detailed health information
    """
    start_time = time.perf_counter()
    
    try:
        current_time = datetime.now(timezone.utc)
        health_info = {
            "status": "healthy",
            "timestamp": current_time.isoformat(),
            "service": "globeco-portfolio-service",
            "probe_type": "detailed",
            "checks": {}
        }
        
        overall_healthy = True
        
        # Database health
        try:
            db_start = time.perf_counter()
            database = get_database()
            
            # More comprehensive database check
            await database.client.admin.command('ping')
            server_info = await database.client.server_info()
            
            db_time = round((time.perf_counter() - db_start) * 1000, 2)
            health_info["checks"]["database"] = {
                "status": "healthy",
                "response_time_ms": db_time,
                "server_version": server_info.get("version", "unknown"),
                "connection_count": len(database.client.nodes)
            }
        except Exception as e:
            health_info["checks"]["database"] = {
                "status": "unhealthy",
                "error": str(e)
            }
            overall_healthy = False
        
        # Circuit breaker health
        try:
            cb_manager = get_circuit_breaker_manager()
            cb_health = cb_manager.get_health_summary()
            
            health_info["checks"]["circuit_breakers"] = {
                "status": "healthy" if cb_health["overall_health"] > 0.5 else "degraded",
                "total_breakers": cb_health["total_breakers"],
                "healthy_breakers": cb_health["healthy_breakers"],
                "open_breakers": cb_health["open_breakers"],
                "overall_health": cb_health["overall_health"]
            }
        except Exception as e:
            health_info["checks"]["circuit_breakers"] = {
                "status": "error",
                "error": str(e)
            }
        
        # Monitoring system health
        try:
            monitoring_manager = get_monitoring_manager()
            monitoring_status = monitoring_manager.get_status()
            
            health_info["checks"]["monitoring"] = {
                "status": "healthy" if monitoring_status["health_checker"]["is_healthy"] else "degraded",
                "health_checker": monitoring_status["health_checker"],
                "fallback_mode": monitoring_status["fallback_mode"]
            }
        except Exception as e:
            health_info["checks"]["monitoring"] = {
                "status": "error",
                "error": str(e)
            }
        
        # Overall status
        health_info["status"] = "healthy" if overall_healthy else "unhealthy"
        health_info["response_time_ms"] = round((time.perf_counter() - start_time) * 1000, 2)
        
        return JSONResponse(
            content=health_info,
            status_code=200 if overall_healthy else 503
        )
    
    except Exception as e:
        logger.error(f"Detailed health check failed: {e}", exc_info=True)
        error_result = {
            "status": "unhealthy",
            "error": str(e),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "service": "globeco-portfolio-service",
            "probe_type": "detailed",
            "response_time_ms": round((time.perf_counter() - start_time) * 1000, 2)
        }
        return JSONResponse(content=error_result, status_code=503)


@router.get("/health/metrics", response_class=JSONResponse)
async def health_metrics() -> JSONResponse:
    """
    Health metrics endpoint for monitoring systems.
    
    This endpoint provides health metrics in a format suitable for
    monitoring systems and alerting.
    
    Returns:
        JSON response with health metrics
    """
    start_time = time.perf_counter()
    
    try:
        current_time = datetime.now(timezone.utc)
        
        # Collect basic metrics
        metrics = {
            "timestamp": current_time.isoformat(),
            "service": "globeco-portfolio-service",
            "uptime_seconds": time.time() - start_time,  # Approximate
            "health_checks": {
                "liveness_cache_hit_rate": 1.0 if _liveness_cache.is_valid() else 0.0,
                "readiness_cache_hit_rate": 1.0 if _readiness_cache.is_valid() else 0.0,
                "startup_cache_hit_rate": 1.0 if _startup_cache.is_valid() else 0.0,
            }
        }
        
        # Add circuit breaker metrics
        try:
            cb_manager = get_circuit_breaker_manager()
            cb_health = cb_manager.get_health_summary()
            metrics["circuit_breakers"] = cb_health
        except Exception:
            pass
        
        # Add monitoring metrics
        try:
            monitoring_manager = get_monitoring_manager()
            monitoring_status = monitoring_manager.get_status()
            metrics["monitoring"] = {
                "is_healthy": monitoring_status["health_checker"]["is_healthy"],
                "fallback_mode": monitoring_status["fallback_mode"],
                "buffer_size": monitoring_status["health_checker"]["buffer"]["size"],
                "statistics": monitoring_status["health_checker"]["statistics"]
            }
        except Exception:
            pass
        
        metrics["response_time_ms"] = round((time.perf_counter() - start_time) * 1000, 2)
        
        return JSONResponse(content=metrics, status_code=200)
    
    except Exception as e:
        logger.error(f"Health metrics failed: {e}", exc_info=True)
        error_result = {
            "error": str(e),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "service": "globeco-portfolio-service",
            "response_time_ms": round((time.perf_counter() - start_time) * 1000, 2)
        }
        return JSONResponse(content=error_result, status_code=503)


# Health check cache management functions
def clear_health_caches() -> None:
    """Clear all health check caches."""
    global _liveness_cache, _readiness_cache, _startup_cache
    
    with _liveness_cache.lock:
        _liveness_cache.last_check_time = 0.0
        _liveness_cache.last_result = None
    
    with _readiness_cache.lock:
        _readiness_cache.last_check_time = 0.0
        _readiness_cache.last_result = None
    
    with _startup_cache.lock:
        _startup_cache.last_check_time = 0.0
        _startup_cache.last_result = None
    
    logger.info("Health check caches cleared")


def get_cache_stats() -> Dict[str, Any]:
    """Get health check cache statistics."""
    return {
        "liveness": {
            "valid": _liveness_cache.is_valid(),
            "age_seconds": time.time() - _liveness_cache.last_check_time,
            "cache_duration": _liveness_cache.cache_duration
        },
        "readiness": {
            "valid": _readiness_cache.is_valid(),
            "age_seconds": time.time() - _readiness_cache.last_check_time,
            "cache_duration": _readiness_cache.cache_duration
        },
        "startup": {
            "valid": _startup_cache.is_valid(),
            "age_seconds": time.time() - _startup_cache.last_check_time,
            "cache_duration": _startup_cache.cache_duration
        }
    }