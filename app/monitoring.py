"""
Enhanced HTTP Metrics Monitoring Module for GlobeCo Portfolio Service.

This module provides standardized HTTP metrics collection using both Prometheus client
(for /metrics endpoint) and OpenTelemetry (for collector export) with comprehensive 
error handling and duplicate registration prevention.
"""

import time
from typing import Any, Dict, Optional, Callable

from fastapi import Request, Response
from prometheus_client import Counter, Gauge, Histogram
from starlette.middleware.base import BaseHTTPMiddleware
from app.logging_config import get_logger

# OpenTelemetry imports for collector integration
from opentelemetry import metrics
from opentelemetry.metrics import Counter as OTelCounter, Histogram as OTelHistogram, UpDownCounter as OTelGauge

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
        logger.debug(
            "Reusing existing metric from registry",
            metric_name=name,
            registry_key=registry_key,
            metric_type=type(_METRICS_REGISTRY[registry_key]).__name__
        )
        return _METRICS_REGISTRY[registry_key]

    try:
        # Log metric creation attempt
        logger.debug(
            "Attempting to create new metric",
            metric_name=name,
            metric_class=metric_class.__name__ if hasattr(metric_class, '__name__') else str(metric_class),
            description=description,
            labels=labels,
            registry_key=registry_key,
            additional_kwargs=list(kwargs.keys()) if kwargs else []
        )
        
        # Create metric with or without labels
        if labels:
            metric = metric_class(name, description, labels, **kwargs)
        else:
            metric = metric_class(name, description, **kwargs)

        _METRICS_REGISTRY[registry_key] = metric
        logger.info(
            "Successfully created and registered metric",
            metric_name=name,
            metric_type=type(metric).__name__,
            registry_key=registry_key,
            has_labels=bool(labels),
            label_count=len(labels) if labels else 0,
            registry_size=len(_METRICS_REGISTRY)
        )
        return metric

    except ValueError as e:
        if "Duplicated timeseries" in str(e):
            logger.warning(
                "Metric already registered in Prometheus registry but not in our internal registry",
                metric_name=name,
                registry_key=registry_key,
                error=str(e),
                error_type=type(e).__name__,
                prometheus_registry_conflict=True
            )
            # Create dummy metric to prevent service disruption
            dummy = DummyMetric()
            _METRICS_REGISTRY[registry_key] = dummy
            logger.warning(
                "Created dummy metric to prevent service disruption",
                metric_name=name,
                registry_key=registry_key,
                fallback_type="DummyMetric",
                reason="prometheus_registry_conflict"
            )
            return dummy
        else:
            logger.error(
                "ValueError during metric creation - using dummy metric fallback",
                metric_name=name,
                registry_key=registry_key,
                error=str(e),
                error_type=type(e).__name__,
                metric_class=metric_class.__name__ if hasattr(metric_class, '__name__') else str(metric_class),
                exc_info=True
            )
            # Create dummy metric as fallback
            dummy = DummyMetric()
            _METRICS_REGISTRY[registry_key] = dummy
            logger.error(
                "Created dummy metric due to ValueError",
                metric_name=name,
                registry_key=registry_key,
                fallback_type="DummyMetric",
                reason="value_error"
            )
            return dummy
    except Exception as e:
        logger.error(
            "Unexpected error during metric creation - using dummy metric fallback",
            metric_name=name,
            registry_key=registry_key,
            error=str(e),
            error_type=type(e).__name__,
            metric_class=metric_class.__name__ if hasattr(metric_class, '__name__') else str(metric_class),
            exc_info=True
        )
        # Create dummy metric as fallback
        dummy = DummyMetric()
        _METRICS_REGISTRY[registry_key] = dummy
        logger.error(
            "Created dummy metric due to unexpected error",
            metric_name=name,
            registry_key=registry_key,
            fallback_type="DummyMetric",
            reason="unexpected_error"
        )
        return dummy


# Create the three standardized HTTP metrics (Prometheus - for /metrics endpoint)
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

# Create the four thread worker metrics (Prometheus - for /metrics endpoint)
HTTP_WORKERS_ACTIVE = _get_or_create_metric(
    Gauge,
    'http_workers_active',
    'Number of threads currently executing requests or performing work'
)

HTTP_WORKERS_TOTAL = _get_or_create_metric(
    Gauge,
    'http_workers_total',
    'Total number of threads currently alive in the thread pool'
)

HTTP_WORKERS_MAX_CONFIGURED = _get_or_create_metric(
    Gauge,
    'http_workers_max_configured',
    'Maximum number of threads that can be created in the thread pool'
)

HTTP_REQUESTS_QUEUED = _get_or_create_metric(
    Gauge,
    'http_requests_queued',
    'Number of pending requests waiting in the queue for thread assignment'
)

# Create OpenTelemetry metrics (for collector export)
# These will be sent to the OpenTelemetry Collector and then to Prometheus
try:
    meter = metrics.get_meter(__name__)
    
    # OpenTelemetry HTTP metrics
    otel_http_requests_total = meter.create_counter(
        name="http_requests_total",
        description="Total number of HTTP requests",
        unit="1"
    )
    
    otel_http_request_duration = meter.create_histogram(
        name="http_request_duration",
        description="HTTP request duration in milliseconds", 
        unit="ms"
    )
    
    otel_http_requests_in_flight = meter.create_up_down_counter(
        name="http_requests_in_flight",
        description="Number of HTTP requests currently being processed",
        unit="1"
    )
    
    # OpenTelemetry thread worker metrics
    otel_http_workers_active = meter.create_up_down_counter(
        name="http_workers_active",
        description="Number of threads currently executing requests or performing work",
        unit="1"
    )
    
    otel_http_workers_total = meter.create_up_down_counter(
        name="http_workers_total",
        description="Total number of threads currently alive in the thread pool",
        unit="1"
    )
    
    otel_http_workers_max_configured = meter.create_up_down_counter(
        name="http_workers_max_configured",
        description="Maximum number of threads that can be created in the thread pool",
        unit="1"
    )
    
    otel_http_requests_queued = meter.create_up_down_counter(
        name="http_requests_queued",
        description="Number of pending requests waiting in the queue for thread assignment",
        unit="1"
    )
    
    logger.info("Successfully created OpenTelemetry HTTP and thread metrics")
    
except Exception as e:
    logger.error(
        "Failed to create OpenTelemetry metrics",
        error=str(e),
        error_type=type(e).__name__,
        exc_info=True
    )
    # Create dummy metrics as fallback
    class DummyOTelMetric:
        def add(self, amount, attributes=None):
            pass
        def record(self, amount, attributes=None):
            pass
    
    otel_http_requests_total = DummyOTelMetric()
    otel_http_request_duration = DummyOTelMetric()
    otel_http_requests_in_flight = DummyOTelMetric()
    otel_http_workers_active = DummyOTelMetric()
    otel_http_workers_total = DummyOTelMetric()
    otel_http_workers_max_configured = DummyOTelMetric()
    otel_http_requests_queued = DummyOTelMetric()
    logger.warning("Created dummy OpenTelemetry metrics due to initialization failure")


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
            url_for_logging = str(request.url) if hasattr(request, 'url') else 'unknown'
        except Exception:
            path_for_logging = 'unknown'
            url_for_logging = 'unknown'
            
        logger.error(
            "Critical error in route pattern extraction - using fallback pattern",
            error=str(e),
            error_type=type(e).__name__,
            path=path_for_logging,
            url=url_for_logging,
            fallback_pattern="/unknown",
            impact="metrics_cardinality_protection",
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
                "Route pattern exceeds maximum length after sanitization - using fallback",
                original_path=path,
                sanitized_pattern=result[:50] + "..." if len(result) > 50 else result,
                sanitized_length=len(result),
                max_allowed_length=200,
                fallback_pattern="/unknown",
                reason="length_protection"
            )
            return "/unknown"
        
        # Log the sanitization result for debugging
        if result != path:
            logger.debug(
                "Successfully sanitized unmatched route pattern",
                original_path=path,
                sanitized_pattern=result,
                path_segments_count=len(parts),
                parameterized_segments=sum(1 for part in sanitized_parts if part == "{id}"),
                truncated_segments=sum(1 for i, part in enumerate(parts) if part and len(part) > 50 and sanitized_parts[i] != "{id}")
            )
        
        return result
        
    except Exception as e:
        logger.error(
            "Critical error during route sanitization - using fallback pattern",
            error=str(e),
            error_type=type(e).__name__,
            path=path,
            fallback_pattern="/unknown",
            impact="metrics_cardinality_protection",
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
                "Non-standard HTTP method encountered - allowing but logging for visibility",
                method=method,
                method_upper=method_upper,
                valid_methods=list(valid_methods),
                action="allow_with_logging"
            )
        
        return method_upper
        
    except Exception as e:
        logger.error(
            "Critical error formatting HTTP method label - using fallback",
            error=str(e),
            error_type=type(e).__name__,
            method=method,
            method_type=type(method).__name__ if method is not None else "NoneType",
            fallback_value="UNKNOWN",
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
                "HTTP status code outside valid range - using fallback",
                status_code=status_code,
                valid_range="100-599",
                fallback_value="unknown",
                rfc_reference="RFC 7231"
            )
            return "unknown"
        
        # Convert to string for consistent labeling
        status_str = str(status_code)
        logger.debug(
            "Successfully formatted status code label",
            status_code=status_code,
            formatted_label=status_str
        )
        return status_str
        
    except Exception as e:
        logger.error(
            "Critical error formatting HTTP status code label - using fallback",
            error=str(e),
            error_type=type(e).__name__,
            status_code=status_code,
            status_code_type=type(status_code).__name__ if status_code is not None else "NoneType",
            fallback_value="unknown",
            exc_info=True
        )
        return "unknown"


class EnhancedHTTPMetricsMiddleware(BaseHTTPMiddleware):
    """
    Enhanced middleware to collect standardized HTTP request metrics.

    This middleware implements the standardized HTTP metrics with proper timing,
    in-flight tracking, and comprehensive error handling using Prometheus.
    
    Collects three core metrics:
    - http_requests_total: Counter of total HTTP requests
    - http_request_duration: Histogram of request durations in milliseconds
    - http_requests_in_flight: Gauge of currently processing requests
    """

    def __init__(self, app, debug_logging: bool = False):
        """
        Initialize the middleware.
        
        Args:
            app: ASGI application
            debug_logging: Enable debug logging for metrics collection
        """
        super().__init__(app)
        self.debug_logging = debug_logging
        
        # Log middleware initialization with comprehensive details
        logger.info(
            "EnhancedHTTPMetricsMiddleware initialized successfully",
            debug_logging_enabled=self.debug_logging,
            middleware_version="enhanced",
            metrics_collected=["http_requests_total", "http_request_duration", "http_requests_in_flight"],
            timing_precision="milliseconds",
            error_handling="comprehensive"
        )
        
        if self.debug_logging:
            logger.debug(
                "Debug logging enabled for HTTP metrics middleware - verbose metrics information will be logged",
                log_level="debug",
                performance_impact="minimal",
                recommended_for="development_and_troubleshooting"
            )
            
        # Validate that metrics are available
        try:
            # Test that metrics are accessible
            if is_dummy_metric(HTTP_REQUESTS_TOTAL):
                logger.warning(
                    "HTTP requests total counter is using dummy metric - metrics may not be recorded",
                    metric_name="http_requests_total",
                    metric_type="DummyMetric",
                    impact="counter_metrics_disabled"
                )
            
            if is_dummy_metric(HTTP_REQUEST_DURATION):
                logger.warning(
                    "HTTP request duration histogram is using dummy metric - duration metrics may not be recorded",
                    metric_name="http_request_duration",
                    metric_type="DummyMetric",
                    impact="duration_metrics_disabled"
                )
                
            if is_dummy_metric(HTTP_REQUESTS_IN_FLIGHT):
                logger.warning(
                    "HTTP requests in-flight gauge is using dummy metric - in-flight metrics may not be recorded",
                    metric_name="http_requests_in_flight",
                    metric_type="DummyMetric",
                    impact="in_flight_metrics_disabled"
                )
                
        except Exception as e:
            logger.error(
                "Error validating metrics during middleware initialization",
                error=str(e),
                error_type=type(e).__name__,
                impact="metrics_validation_failed",
                exc_info=True
            )

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """
        Process request and collect all three standardized HTTP metrics.

        Uses high-precision timing with time.perf_counter() for millisecond accuracy.
        Implements comprehensive error handling to ensure metrics are recorded
        even when request processing fails.

        Args:
            request: The incoming HTTP request
            call_next: The next middleware/endpoint to call

        Returns:
            Response with metrics recorded for the request
        """
        # Start high-precision timing using perf_counter for millisecond precision
        start_time = time.perf_counter()
        
        # Extract basic request information for logging
        request_method = getattr(request, 'method', 'UNKNOWN')
        request_path = 'unknown'
        request_url = 'unknown'
        
        try:
            if hasattr(request, 'url'):
                request_path = getattr(request.url, 'path', 'unknown')
                request_url = str(request.url)
        except Exception as e:
            logger.debug(
                "Could not extract request URL information for logging",
                error=str(e),
                fallback_path=request_path,
                fallback_url=request_url
            )

        if self.debug_logging:
            logger.debug(
                "Starting HTTP request processing with metrics collection",
                method=request_method,
                path=request_path,
                url=request_url,
                start_time=start_time,
                timing_precision="perf_counter_milliseconds"
            )

        # Increment in-flight requests gauge with error protection
        in_flight_incremented = False
        otel_in_flight_incremented = False
        
        # Increment Prometheus in-flight gauge
        try:
            HTTP_REQUESTS_IN_FLIGHT.inc()
            in_flight_incremented = True
            if self.debug_logging:
                logger.debug(
                    "Successfully incremented Prometheus in-flight requests gauge",
                    method=request_method,
                    path=request_path,
                    gauge_operation="increment"
                )
        except Exception as e:
            logger.error(
                "Failed to increment Prometheus in-flight requests gauge - continuing request processing",
                error=str(e),
                error_type=type(e).__name__,
                method=request_method,
                path=request_path,
                gauge_operation="increment",
                impact="in_flight_prometheus_metrics_disabled",
                exc_info=True,
            )
        
        # Increment OpenTelemetry in-flight gauge
        try:
            otel_http_requests_in_flight.add(1)
            otel_in_flight_incremented = True
            if self.debug_logging:
                logger.debug(
                    "Successfully incremented OpenTelemetry in-flight requests gauge",
                    method=request_method,
                    path=request_path,
                    gauge_operation="increment"
                )
        except Exception as e:
            logger.error(
                "Failed to increment OpenTelemetry in-flight requests gauge - continuing request processing",
                error=str(e),
                error_type=type(e).__name__,
                method=request_method,
                path=request_path,
                gauge_operation="increment",
                impact="in_flight_otel_metrics_disabled",
                exc_info=True,
            )

        try:
            # Process the request through the application
            response = await call_next(request)

            # Calculate duration in milliseconds with high precision
            duration_ms = (time.perf_counter() - start_time) * 1000

            # Extract labels for metrics
            method = _get_method_label(request.method)
            path = _extract_route_pattern(request)
            status = _format_status_code(response.status_code)

            # Record all three metrics with comprehensive error handling
            try:
                self._record_metrics(method, path, status, duration_ms)
            except Exception as metrics_error:
                logger.error(
                    "Failed to record metrics for successful request - continuing request processing",
                    error=str(metrics_error),
                    error_type=type(metrics_error).__name__,
                    method=method,
                    path=path,
                    status=status,
                    duration_ms=round(duration_ms, 2),
                    impact="metrics_recording_failed_but_request_succeeded",
                    exc_info=True
                )

            # Log slow requests (> 1000ms) for performance monitoring
            if duration_ms > 1000:
                logger.warning(
                    "Slow request detected - performance monitoring alert",
                    method=method,
                    path=path,
                    duration_ms=round(duration_ms, 2),
                    status=status,
                    request_url=str(request.url) if hasattr(request, 'url') else 'unknown',
                    slow_request_threshold_ms=1000,
                    performance_impact="high"
                )
                
                # Additional debug info for slow requests if debug logging is enabled
                if self.debug_logging:
                    logger.debug(
                        "Slow request debug information",
                        method=method,
                        path=path,
                        duration_ms=round(duration_ms, 2),
                        status=status,
                        request_headers=dict(request.headers) if hasattr(request, 'headers') else {},
                        client_host=getattr(request.client, 'host', 'unknown') if hasattr(request, 'client') else 'unknown',
                        query_params=str(request.url.query) if hasattr(request, 'url') and hasattr(request.url, 'query') else 'none'
                    )

            return response

        except Exception as e:
            # Calculate duration even for exceptions to maintain accurate metrics
            duration_ms = (time.perf_counter() - start_time) * 1000

            # Extract labels for error metrics with comprehensive error handling
            method = "UNKNOWN"
            path = "/unknown"
            
            try:
                method = _get_method_label(request.method)
            except Exception as method_error:
                logger.debug(
                    "Could not extract method for error metrics",
                    error=str(method_error),
                    fallback_method=method
                )
                
            try:
                path = _extract_route_pattern(request)
            except Exception as path_error:
                logger.debug(
                    "Could not extract path pattern for error metrics",
                    error=str(path_error),
                    fallback_path=path
                )
            
            status = "500"  # All exceptions result in 500 status for metrics

            # Record metrics even when exceptions occur
            try:
                self._record_metrics(method, path, status, duration_ms)
                if self.debug_logging:
                    logger.debug(
                        "Successfully recorded metrics for failed request",
                        method=method,
                        path=path,
                        status=status,
                        duration_ms=round(duration_ms, 2)
                    )
            except Exception as metrics_error:
                logger.error(
                    "Failed to record metrics for failed request - double error condition",
                    original_error=str(e),
                    metrics_error=str(metrics_error),
                    method=method,
                    path=path,
                    status=status,
                    duration_ms=round(duration_ms, 2),
                    impact="metrics_recording_failed"
                )

            logger.error(
                "Request processing failed - attempted metrics collection for error case",
                error=str(e),
                error_type=type(e).__name__,
                method=method,
                path=path,
                status=status,
                duration_ms=round(duration_ms, 2),
                request_url=request_url,
                error_handling="metrics_recorded_for_500_status",
                exc_info=True,
            )

            # Re-raise the exception to maintain normal error handling
            raise
        finally:
            # Always decrement in-flight requests gauge
            # Only decrement if we successfully incremented to avoid negative values
            if in_flight_incremented:
                try:
                    HTTP_REQUESTS_IN_FLIGHT.dec()
                    if self.debug_logging:
                        logger.debug(
                            "Successfully decremented Prometheus in-flight requests gauge",
                            method=request_method,
                            path=request_path,
                            gauge_operation="decrement"
                        )
                except Exception as e:
                    logger.error(
                        "Critical error decrementing Prometheus in-flight requests gauge - gauge may be inaccurate",
                        error=str(e),
                        error_type=type(e).__name__,
                        method=request_method,
                        path=request_path,
                        gauge_operation="decrement",
                        impact="prometheus_gauge_accuracy_compromised",
                        mitigation="gauge_will_self_correct_over_time",
                        exc_info=True,
                    )
            else:
                if self.debug_logging:
                    logger.debug(
                        "Skipping Prometheus in-flight gauge decrement - was not incremented",
                        method=request_method,
                        path=request_path,
                        reason="increment_failed_or_skipped"
                    )
            
            # Decrement OpenTelemetry in-flight gauge
            if otel_in_flight_incremented:
                try:
                    otel_http_requests_in_flight.add(-1)
                    if self.debug_logging:
                        logger.debug(
                            "Successfully decremented OpenTelemetry in-flight requests gauge",
                            method=request_method,
                            path=request_path,
                            gauge_operation="decrement"
                        )
                except Exception as e:
                    logger.error(
                        "Critical error decrementing OpenTelemetry in-flight requests gauge - gauge may be inaccurate",
                        error=str(e),
                        error_type=type(e).__name__,
                        method=request_method,
                        path=request_path,
                        gauge_operation="decrement",
                        impact="otel_gauge_accuracy_compromised",
                        mitigation="gauge_will_self_correct_over_time",
                        exc_info=True,
                    )
            else:
                if self.debug_logging:
                    logger.debug(
                        "Skipping OpenTelemetry in-flight gauge decrement - was not incremented",
                        method=request_method,
                        path=request_path,
                        reason="increment_failed_or_skipped"
                    )

    def _record_metrics(
        self, method: str, path: str, status: str, duration_ms: float
    ) -> None:
        """
        Record all three HTTP metrics with comprehensive error handling.
        
        Records metrics to both:
        - Prometheus (exposed via /metrics endpoint)
        - OpenTelemetry (sent to collector and then to Prometheus)

        Args:
            method: HTTP method (uppercase)
            path: Route pattern with parameterized IDs
            status: HTTP status code as string
            duration_ms: Request duration in milliseconds
        """
        # Debug logging for metric values during development
        if self.debug_logging:
            logger.debug(
                "Recording HTTP metrics to both Prometheus and OpenTelemetry",
                method=method,
                path=path,
                status=status,
                duration_ms=duration_ms,
            )

        # Prepare attributes for OpenTelemetry metrics
        otel_attributes = {
            "method": method,
            "path": path,
            "status": status
        }

        # Record Prometheus counter metrics with error handling
        try:
            HTTP_REQUESTS_TOTAL.labels(method=method, path=path, status=status).inc()
            if self.debug_logging:
                logger.debug(
                    "Successfully recorded Prometheus HTTP requests total counter",
                    method=method,
                    path=path,
                    status=status,
                )
        except Exception as e:
            logger.error(
                "Failed to record Prometheus HTTP requests total counter",
                error=str(e),
                error_type=type(e).__name__,
                method=method,
                path=path,
                status=status,
                exc_info=True,
            )

        # Record Prometheus histogram metrics with error handling
        try:
            HTTP_REQUEST_DURATION.labels(method=method, path=path, status=status).observe(duration_ms)
            if self.debug_logging:
                logger.debug(
                    "Successfully recorded Prometheus HTTP request duration histogram",
                    method=method,
                    path=path,
                    status=status,
                    duration_ms=duration_ms,
                )
        except Exception as e:
            logger.error(
                "Failed to record Prometheus HTTP request duration histogram",
                error=str(e),
                error_type=type(e).__name__,
                method=method,
                path=path,
                status=status,
                duration_ms=duration_ms,
                exc_info=True,
            )

        # Record OpenTelemetry counter metrics with error handling
        try:
            otel_http_requests_total.add(1, attributes=otel_attributes)
            if self.debug_logging:
                logger.debug(
                    "Successfully recorded OpenTelemetry HTTP requests total counter",
                    method=method,
                    path=path,
                    status=status,
                )
        except Exception as e:
            logger.error(
                "Failed to record OpenTelemetry HTTP requests total counter",
                error=str(e),
                error_type=type(e).__name__,
                method=method,
                path=path,
                status=status,
                exc_info=True,
            )

        # Record OpenTelemetry histogram metrics with error handling
        try:
            otel_http_request_duration.record(duration_ms, attributes=otel_attributes)
            if self.debug_logging:
                logger.debug(
                    "Successfully recorded OpenTelemetry HTTP request duration histogram",
                    method=method,
                    path=path,
                    status=status,
                    duration_ms=duration_ms,
                )
        except Exception as e:
            logger.error(
                "Failed to record OpenTelemetry HTTP request duration histogram",
                error=str(e),
                error_type=type(e).__name__,
                method=method,
                path=path,
                status=status,
                duration_ms=duration_ms,
                exc_info=True,
            )

        # Record OpenTelemetry counter metrics with error handling
        try:
            otel_http_requests_total.add(1, attributes=otel_attributes)
            if self.debug_logging:
                logger.debug(
                    "Successfully recorded OpenTelemetry HTTP requests total counter",
                    method=method,
                    path=path,
                    status=status,
                )
        except Exception as e:
            logger.error(
                "Failed to record OpenTelemetry HTTP requests total counter",
                error=str(e),
                error_type=type(e).__name__,
                method=method,
                path=path,
                status=status,
                exc_info=True,
            )

        # Record Prometheus histogram metrics with error handling
        try:
            HTTP_REQUEST_DURATION.labels(
                method=method, path=path, status=status
            ).observe(duration_ms)
            if self.debug_logging:
                logger.debug(
                    "Successfully recorded Prometheus HTTP request duration histogram",
                    method=method,
                    path=path,
                    status=status,
                    duration_ms=duration_ms,
                )
        except Exception as e:
            logger.error(
                "Failed to record Prometheus HTTP request duration histogram",
                error=str(e),
                error_type=type(e).__name__,
                method=method,
                path=path,
                status=status,
                duration_ms=duration_ms,
                exc_info=True,
            )

        # Record OpenTelemetry histogram metrics with error handling
        try:
            otel_http_request_duration.record(duration_ms, attributes=otel_attributes)
            if self.debug_logging:
                logger.debug(
                    "Successfully recorded OpenTelemetry HTTP request duration histogram",
                    method=method,
                    path=path,
                    status=status,
                    duration_ms=duration_ms,
                )
        except Exception as e:
            logger.error(
                "Failed to record OpenTelemetry HTTP request duration histogram",
                error=str(e),
                error_type=type(e).__name__,
                method=method,
                path=path,
                status=status,
                duration_ms=duration_ms,
                exc_info=True,
            )


# Initialize metrics on module import
logger.info("Enhanced HTTP metrics monitoring module initialized")
logger.info(f"Metrics registry contains {len(_METRICS_REGISTRY)} metrics")

# Log metric status for debugging
if logger.logger.isEnabledFor(10):  # DEBUG level
    for name, status in get_metric_status().items():
        logger.debug(f"Metric {name}: {status}")