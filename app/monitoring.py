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
    
    The function detects and parameterizes various ID formats:
    - MongoDB ObjectIds (24-char hex) -> {id}
    - UUIDs (with/without hyphens) -> {id}
    - Numeric IDs -> {id}
    - Long alphanumeric identifiers -> {id}
    
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
                # Keep empty parts (for leading/trailing slashes)
                sanitized_parts.append(part)
                continue
            
            # Check if part looks like an ID that should be parameterized
            if _looks_like_id(part):
                sanitized_parts.append("{id}")
                logger.debug(
                    "Parameterized ID in unmatched route",
                    original_part=part,
                    path=path
                )
            else:
                # Keep the original part but limit length to prevent abuse
                sanitized_part = part[:50] if len(part) > 50 else part
                sanitized_parts.append(sanitized_part)
                
                # Log if we truncated a long part
                if len(part) > 50:
                    logger.debug(
                        "Truncated long path segment in unmatched route",
                        original_length=len(part),
                        truncated_part=sanitized_part,
                        path=path
                    )
        
        result = "/".join(sanitized_parts)
        
        # Ensure we don't create overly long patterns
        if len(result) > 200:
            logger.warning(
                "Route pattern too long after sanitization, using fallback",
                original_path=path,
                sanitized_length=len(result)
            )
            return "/unknown"
        
        # Log the sanitization result for debugging
        if result != path:
            logger.debug(
                "Sanitized unmatched route",
                original_path=path,
                sanitized_pattern=result
            )
        
        return result
        
    except Exception as e:
        logger.error(
            "Failed to sanitize unmatched route",
            error=str(e),
            error_type=type(e).__name__,
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
        if _is_mongodb_objectid(part):
            return True
        
        # UUID format (with hyphens: exactly 8-4-4-4-12 format)
        if _is_uuid_with_hyphens(part):
            return True
        
        # UUID format (without hyphens: exactly 32 character hex)
        if _is_uuid_without_hyphens(part):
            return True
        
        # Numeric ID (pure digits)
        if _is_numeric_id(part):
            return True
        
        # Long alphanumeric ID that looks like an identifier
        if _is_alphanumeric_id(part):
            return True
        
        return False
        
    except Exception:
        # If any error occurs during ID detection, err on the side of caution
        return False


def _is_mongodb_objectid(part: str) -> bool:
    """
    Check if a path part is a MongoDB ObjectId.
    
    MongoDB ObjectIds are exactly 24 characters long and contain only hexadecimal characters.
    
    Args:
        part: Path segment to check
        
    Returns:
        True if the part looks like a MongoDB ObjectId
    """
    if len(part) != 24:
        return False
    
    return all(c in '0123456789abcdefABCDEF' for c in part)


def _is_uuid_with_hyphens(part: str) -> bool:
    """
    Check if a path part is a UUID with hyphens.
    
    Standard UUID format: 8-4-4-4-12 hexadecimal characters separated by hyphens.
    Example: 550e8400-e29b-41d4-a716-446655440000
    
    Args:
        part: Path segment to check
        
    Returns:
        True if the part looks like a UUID with hyphens
    """
    if len(part) != 36 or part.count('-') != 4:
        return False
    
    uuid_parts = part.split('-')
    if (len(uuid_parts) != 5 or 
        len(uuid_parts[0]) != 8 or len(uuid_parts[1]) != 4 or 
        len(uuid_parts[2]) != 4 or len(uuid_parts[3]) != 4 or 
        len(uuid_parts[4]) != 12):
        return False
    
    # Check if all parts are hexadecimal
    try:
        for uuid_part in uuid_parts:
            int(uuid_part, 16)
        return True
    except ValueError:
        return False


def _is_uuid_without_hyphens(part: str) -> bool:
    """
    Check if a path part is a UUID without hyphens.
    
    UUID without hyphens: exactly 32 hexadecimal characters.
    Example: 550e8400e29b41d4a716446655440000
    
    Args:
        part: Path segment to check
        
    Returns:
        True if the part looks like a UUID without hyphens
    """
    if len(part) != 32:
        return False
    
    return all(c in '0123456789abcdefABCDEF' for c in part)


def _is_numeric_id(part: str) -> bool:
    """
    Check if a path part is a numeric ID.
    
    Numeric IDs are strings containing only digits.
    Examples: "123", "456789", "1"
    
    Args:
        part: Path segment to check
        
    Returns:
        True if the part looks like a numeric ID
    """
    return part.isdigit() and len(part) >= 1


def _is_alphanumeric_id(part: str) -> bool:
    """
    Check if a path part is a long alphanumeric identifier.
    
    Alphanumeric IDs are longer identifiers that contain both letters and numbers,
    but are not in the specific formats of ObjectId or UUID.
    
    Criteria:
    - Longer than 8 characters
    - Contains only alphanumeric characters, hyphens, and underscores
    - Must contain at least one digit (number)
    - Not in the 20-40 character range (to avoid confusion with malformed ObjectIds/UUIDs)
    
    Examples: "user-abc123def", "session_token_xyz789"
    
    Args:
        part: Path segment to check
        
    Returns:
        True if the part looks like an alphanumeric ID
    """
    if len(part) <= 8:
        return False
    
    # Must be alphanumeric with allowed separators
    if not part.replace('-', '').replace('_', '').isalnum():
        return False
    
    # Must contain at least one digit (not just letters and separators)
    if not any(c.isdigit() for c in part):
        return False
    
    # Exclude strings that might be malformed hex IDs (close to ObjectId/UUID length)
    if 20 <= len(part) <= 40:
        return False
    
    return True


def _get_method_label(method: str) -> str:
    """
    Format HTTP method as uppercase string for consistent labeling.
    
    Converts HTTP method names to uppercase and validates against known methods.
    Falls back to safe defaults for invalid or unknown methods.
    
    Args:
        method: HTTP method string (e.g., 'get', 'POST', 'Put')
        
    Returns:
        Uppercase HTTP method string or 'UNKNOWN' for invalid methods
    """
    try:
        # Handle None or non-string input
        if not isinstance(method, str):
            logger.warning(
                "Invalid method type for label formatting",
                method=method,
                method_type=type(method).__name__
            )
            return "UNKNOWN"
        
        # Strip whitespace and convert to uppercase
        method_upper = method.strip().upper()
        
        # Handle empty string after stripping
        if not method_upper:
            logger.warning("Empty method string after stripping whitespace")
            return "UNKNOWN"
        
        # Define valid HTTP methods according to RFC 7231 and common extensions
        valid_methods = {
            "GET", "POST", "PUT", "DELETE", "PATCH",
            "HEAD", "OPTIONS", "TRACE", "CONNECT"
        }
        
        # Log warning for unknown methods but still return them
        # This allows for custom methods while maintaining visibility
        if method_upper not in valid_methods:
            logger.debug(
                "Unknown HTTP method encountered",
                method=method,
                method_upper=method_upper
            )
        
        return method_upper
        
    except Exception as e:
        logger.error(
            "Failed to format method label",
            error=str(e),
            error_type=type(e).__name__,
            method=method,
            exc_info=True
        )
        return "UNKNOWN"


def _format_status_code(status_code: int) -> str:
    """
    Format HTTP status code as string for consistent labeling.
    
    Converts numeric HTTP status codes to strings and validates they are
    within the valid HTTP status code range (100-599).
    
    Args:
        status_code: HTTP status code integer (e.g., 200, 404, 500)
        
    Returns:
        Status code as string or 'unknown' for invalid codes
    """
    try:
        # Handle None or non-integer input
        if not isinstance(status_code, int):
            logger.warning(
                "Invalid status code type for label formatting",
                status_code=status_code,
                status_code_type=type(status_code).__name__
            )
            return "unknown"
        
        # Validate status code is within valid HTTP range
        # HTTP status codes are defined as 100-599 in RFC 7231
        if status_code < 100 or status_code > 599:
            logger.warning(
                "Status code out of valid HTTP range (100-599)",
                status_code=status_code
            )
            return "unknown"
        
        # Convert to string for consistent labeling
        return str(status_code)
        
    except Exception as e:
        logger.error(
            "Failed to format status code label",
            error=str(e),
            error_type=type(e).__name__,
            status_code=status_code,
            exc_info=True
        )
        return "unknown"


# Initialize metrics on module import
logger.info("Enhanced HTTP metrics monitoring module initialized")
logger.info(f"Metrics registry contains {len(_METRICS_REGISTRY)} metrics")

# Log metric status for debugging
if logger.logger.isEnabledFor(10):  # DEBUG level
    for name, status in get_metric_status().items():
        logger.debug(f"Metric {name}: {status}")