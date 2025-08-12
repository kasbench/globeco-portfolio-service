"""
Enhanced HTTP Metrics Monitoring Module for GlobeCo Portfolio Service.

This module provides standardized HTTP metrics collection using Prometheus client
with comprehensive error handling and duplicate registration prevention.
"""

import time
from typing import Any, Dict, Optional

from fastapi import Request
from prometheus_client import Counter, Gauge, Histogram
from app.logging_config import get_logger

logger = get_logger(__name__)

# Global metrics registry to prevent duplicate registration
_METRICS_REGISTRY: Dict[str, Any] = {}


class DummyMetric:
    """
    Dummy metric class for graceful fallback when registration fails.
    
    This class provides the same interface as Prometheus metrics but performs
    no actual operations, preventing service disruption when metric registration
    encounters errors.
    """
    
    def labels(self, **kwargs):
        """Return self to support method chaining."""
        return self
    
    def inc(self, amount: float = 1) -> None:
        """Dummy increment operation."""
        pass
    
    def observe(self, amount: float) -> None:
        """Dummy observe operation."""
        pass
    
    def set(self, value: float) -> None:
        """Dummy set operation."""
        pass
    
    def collect(self):
        """Return empty list for Prometheus collection."""
        return []


def _get_or_create_metric(
    metric_class, 
    name: str, 
    description: str, 
    labels: Optional[list] = None, 
    registry_key: Optional[str] = None, 
    **kwargs
) -> Any:
    """
    Get or create a metric, preventing duplicate registration.
    
    This function implements a global registry pattern to prevent duplicate
    metric registration errors that can occur during module reloads or
    circular imports.
    
    Args:
        metric_class: Prometheus metric class (Counter, Histogram, Gauge)
        name: Metric name
        description: Metric description
        labels: List of label names
        registry_key: Optional custom registry key (defaults to name)
        **kwargs: Additional arguments for metric creation
        
    Returns:
        Prometheus metric instance or DummyMetric on failure
    """
    if registry_key is None:
        registry_key = name

    # Check if metric already exists in our registry
    if registry_key in _METRICS_REGISTRY:
        logger.debug(f"Reusing existing metric: {name}")
        return _METRICS_REGISTRY[registry_key]

    try:
        # Create metric with or without labels
        if labels:
            metric = metric_class(name, description, labels, **kwargs)
        else:
            metric = metric_class(name, description, **kwargs)

        _METRICS_REGISTRY[registry_key] = metric
        logger.info(f"Successfully created metric: {name}")
        return metric

    except ValueError as e:
        if "Duplicated timeseries" in str(e):
            logger.warning(
                "Metric already registered in Prometheus but not in our registry",
                metric_name=name,
                error=str(e),
                error_type=type(e).__name__
            )
            # Create dummy metric to prevent service disruption
            dummy = DummyMetric()
            _METRICS_REGISTRY[registry_key] = dummy
            logger.warning(f"Created dummy metric for {name} to prevent errors")
            return dummy
        else:
            logger.error(
                "Failed to create metric",
                metric_name=name,
                error=str(e),
                error_type=type(e).__name__,
                exc_info=True
            )
            # Create dummy metric as fallback
            dummy = DummyMetric()
            _METRICS_REGISTRY[registry_key] = dummy
            logger.error(f"Created dummy metric for {name} due to creation failure")
            return dummy
    except Exception as e:
        logger.error(
            "Unexpected error creating metric",
            metric_name=name,
            error=str(e),
            error_type=type(e).__name__,
            exc_info=True
        )
        # Create dummy metric as fallback
        dummy = DummyMetric()
        _METRICS_REGISTRY[registry_key] = dummy
        logger.error(f"Created dummy metric for {name} due to unexpected error")
        return dummy


# Create the three standardized HTTP metrics
HTTP_REQUESTS_TOTAL = _get_or_create_metric(
    Counter,
    'http_requests_total',
    'Total number of HTTP requests',
    ['method', 'path', 'status'],
)

HTTP_REQUEST_DURATION = _get_or_create_metric(
    Histogram,
    'http_request_duration',
    'HTTP request duration in milliseconds',
    ['method', 'path', 'status'],
    buckets=[5, 10, 25, 50, 100, 250, 500, 1000, 2500, 5000, 10000],
)

HTTP_REQUESTS_IN_FLIGHT = _get_or_create_metric(
    Gauge,
    'http_requests_in_flight',
    'Number of HTTP requests currently being processed'
)


def get_metrics_registry() -> Dict[str, Any]:
    """
    Get the current metrics registry for testing and debugging.
    
    Returns:
        Dictionary containing all registered metrics
    """
    return _METRICS_REGISTRY.copy()


def clear_metrics_registry() -> None:
    """
    Clear the metrics registry for testing purposes.
    
    Warning: This should only be used in tests to reset state.
    """
    global _METRICS_REGISTRY
    _METRICS_REGISTRY.clear()
    logger.debug("Metrics registry cleared")


def is_dummy_metric(metric: Any) -> bool:
    """
    Check if a metric is a dummy metric.
    
    Args:
        metric: Metric instance to check
        
    Returns:
        True if metric is a DummyMetric instance
    """
    return isinstance(metric, DummyMetric)


def get_metric_status() -> Dict[str, Dict[str, Any]]:
    """
    Get status information about all registered metrics.
    
    Returns:
        Dictionary with metric names and their status information
    """
    status = {}
    for name, metric in _METRICS_REGISTRY.items():
        status[name] = {
            'type': type(metric).__name__,
            'is_dummy': is_dummy_metric(metric),
            'class_module': type(metric).__module__
        }
    return status


def _extract_route_pattern(request: Request) -> str:
    """
    Extract route pattern from request URL to prevent high cardinality metrics.
    
    Converts URLs with parameters to route patterns specific to the GlobeCo Portfolio Service.
    For example: /api/v1/portfolio/507f1f77bcf86cd799439011 -> /api/v1/portfolio/{portfolioId}
    
    Args:
        request: FastAPI Request object
        
    Returns:
        Route pattern string with parameterized IDs
    """
    try:
        path = request.url.path.rstrip('/')
        
        if not path:
            return "/"
        
        # Portfolio service specific route patterns
        if path.startswith("/api/v1/portfolio"):
            return _extract_portfolio_v1_route_pattern(path)
        elif path.startswith("/api/v2/portfolios"):
            return _extract_portfolio_v2_route_pattern(path)
        elif path == "/health":
            return "/health"
        elif path == "/metrics":
            return "/metrics"
        elif path == "/":
            return "/"
        
        # Fallback for unmatched routes
        return _sanitize_unmatched_route(path)
        
    except Exception as e:
        # Safely get path for logging without causing another exception
        try:
            path_for_logging = getattr(request.url, 'path', 'unknown')
        except Exception:
            path_for_logging = 'unknown'
            
        logger.error(
            "Failed to extract route pattern",
            error=str(e),
            error_type=type(e).__name__,
            path=path_for_logging,
            exc_info=True
        )
        return "/unknown"


def _extract_portfolio_v1_route_pattern(path: str) -> str:
    """
    Extract route pattern for v1 API portfolio endpoints.
    
    Handles:
    - /api/v1/portfolios (collection operations)
    - /api/v1/portfolio/{portfolioId} (individual portfolio operations)
    
    Args:
        path: URL path string
        
    Returns:
        Parameterized route pattern
    """
    parts = path.split("/")
    
    if len(parts) == 4:  # /api/v1/portfolios
        return "/api/v1/portfolios"
    elif len(parts) == 5:  # /api/v1/portfolio/{portfolioId}
        return "/api/v1/portfolio/{portfolioId}"
    
    # Fallback for unexpected v1 patterns
    return "/api/v1/portfolio/unknown"


def _extract_portfolio_v2_route_pattern(path: str) -> str:
    """
    Extract route pattern for v2 API portfolio endpoints.
    
    Handles:
    - /api/v2/portfolios (search with query parameters)
    
    Args:
        path: URL path string
        
    Returns:
        Parameterized route pattern
    """
    parts = path.split("/")
    
    if len(parts) == 4:  # /api/v2/portfolios
        return "/api/v2/portfolios"
    
    # Fallback for unexpected v2 patterns
    return "/api/v2/portfolios/unknown"


def _sanitize_unmatched_route(path: str) -> str:
    """
    Sanitize unmatched routes to prevent high cardinality metrics.
    
    This method handles routes that don't match the known portfolio service patterns
    by parameterizing ID-like path segments to prevent metric explosion.
    
    Args:
        path: URL path string
        
    Returns:
        Sanitized route pattern with IDs parameterized
    """
    try:
        parts = path.split("/")
        sanitized_parts = []
        
        for part in parts:
            if not part:
                sanitized_parts.append(part)
                continue
            
            # Check if part looks like an ID that should be parameterized
            if _looks_like_id(part):
                sanitized_parts.append("{id}")
            else:
                # Keep the original part but limit length to prevent abuse
                sanitized_part = part[:50] if len(part) > 50 else part
                sanitized_parts.append(sanitized_part)
        
        result = "/".join(sanitized_parts)
        
        # Ensure we don't create overly long patterns
        if len(result) > 200:
            return "/unknown"
        
        return result
        
    except Exception as e:
        logger.error(
            "Failed to sanitize unmatched route",
            error=str(e),
            path=path,
            exc_info=True
        )
        return "/unknown"


def _looks_like_id(part: str) -> bool:
    """
    Check if a path part looks like an ID that should be parameterized.
    
    Detects various ID formats commonly used in APIs:
    - MongoDB ObjectId (24-character hexadecimal)
    - UUID (with or without hyphens)
    - Numeric IDs
    - Long alphanumeric identifiers
    
    Args:
        part: Path segment to check
        
    Returns:
        True if the part looks like an ID that should be parameterized
    """
    try:
        # Early return for empty or None
        if not part:
            return False
        
        # MongoDB ObjectId (exactly 24 character hex)
        if len(part) == 24 and all(c in '0123456789abcdefABCDEF' for c in part):
            return True
        
        # UUID format (with hyphens: exactly 8-4-4-4-12 format)
        if len(part) == 36 and part.count('-') == 4:
            uuid_parts = part.split('-')
            if (len(uuid_parts) == 5 and 
                len(uuid_parts[0]) == 8 and len(uuid_parts[1]) == 4 and 
                len(uuid_parts[2]) == 4 and len(uuid_parts[3]) == 4 and 
                len(uuid_parts[4]) == 12):
                # Check if all parts are hexadecimal
                try:
                    for uuid_part in uuid_parts:
                        int(uuid_part, 16)
                    return True
                except ValueError:
                    return False
        
        # UUID format (without hyphens: exactly 32 character hex)
        if len(part) == 32 and all(c in '0123456789abcdefABCDEF' for c in part):
            return True
        
        # Numeric ID (pure digits)
        if part.isdigit() and len(part) >= 1:
            return True
        
        # Long alphanumeric ID that looks like an identifier
        # Only consider if it doesn't match the specific formats above
        if (len(part) > 8 and 
            part.replace('-', '').replace('_', '').isalnum() and
            not part.isalpha() and  # Must contain at least one non-letter
            # Exclude strings that look like malformed hex IDs (close to ObjectId/UUID length)
            not (20 <= len(part) <= 40)):
            return True
        
        return False
        
    except Exception:
        # If any error occurs during ID detection, err on the side of caution
        return False


# Initialize metrics on module import
logger.info("Enhanced HTTP metrics monitoring module initialized")
logger.info(f"Metrics registry contains {len(_METRICS_REGISTRY)} metrics")

# Log metric status for debugging
if logger.logger.isEnabledFor(10):  # DEBUG level
    for name, status in get_metric_status().items():
        logger.debug(f"Metric {name}: {status}")