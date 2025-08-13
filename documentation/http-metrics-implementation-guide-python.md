# HTTP Metrics Implementation Guide for GlobeCo Python Microservices

## Overview

This guide provides step-by-step instructions for implementing standardized HTTP metrics in Python microservices using FastAPI and Prometheus. This implementation ensures consistent observability across the GlobeCo microservices architecture without requiring external OpenTelemetry collectors.

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Core Implementation](#core-implementation)
3. [Middleware Setup](#middleware-setup)
4. [Application Integration](#application-integration)
5. [Deployment Configuration](#deployment-configuration)
6. [Common Pitfalls and Solutions](#common-pitfalls-and-solutions)
7. [Testing and Validation](#testing-and-validation)
8. [Troubleshooting](#troubleshooting)

## Prerequisites

### Required Dependencies

Add these dependencies to your `pyproject.toml`:

```toml
[project.dependencies]
fastapi = "^0.104.0"
uvicorn = "^0.24.0"
prometheus-client = "^0.19.0"
prometheus-fastapi-instrumentator = "^6.1.0"
# OpenTelemetry dependencies (REQUIRED when using OpenTelemetry Collector)
opentelemetry-api = "^1.20.0"
opentelemetry-sdk = "^1.20.0"
opentelemetry-exporter-otlp = "^1.20.0"
```

**IMPORTANT**: When using OpenTelemetry Collector in your infrastructure, you MUST implement both Prometheus metrics (for `/metrics` endpoint) AND OpenTelemetry metrics (for collector export). Using only Prometheus metrics will result in metrics being visible in `/metrics` but not appearing in your monitoring system.

### Environment Variables

Ensure these environment variables are set:

```bash
ENABLE_METRICS=true
LOG_LEVEL=DEBUG  # For development, INFO for production
```

## Core Implementation

### 1. Create the Monitoring Module

Create `src/core/monitoring.py` with the following implementation:

```python
"""
Monitoring and observability module for GlobeCo microservices.

This module provides standardized HTTP metrics collection using both Prometheus
(for /metrics endpoint) and OpenTelemetry (for collector export).

CRITICAL: When using OpenTelemetry Collector, you MUST implement both systems
to ensure metrics appear in your monitoring infrastructure.
"""

import time
from typing import Any, Callable, Dict

from fastapi import Request, Response
from prometheus_client import Counter, Gauge, Histogram
from prometheus_fastapi_instrumentator import Instrumentator, metrics
from starlette.middleware.base import BaseHTTPMiddleware

# OpenTelemetry imports for collector integration
from opentelemetry import metrics as otel_metrics
from opentelemetry.metrics import Counter as OTelCounter, Histogram as OTelHistogram, UpDownCounter as OTelGauge

from src.core.utils import get_logger

logger = get_logger(__name__)

# Global metrics registry to prevent duplicate registration
_METRICS_REGISTRY = {}

def _get_or_create_metric(metric_class, name, description, labels=None, registry_key=None, **kwargs):
    """Get or create a metric, preventing duplicate registration."""
    if registry_key is None:
        registry_key = name

    # Check if metric already exists in our registry
    if registry_key in _METRICS_REGISTRY:
        logger.debug(f"Reusing existing metric: {name}")
        return _METRICS_REGISTRY[registry_key]

    try:
        if labels:
            metric = metric_class(name, description, labels, **kwargs)
        else:
            metric = metric_class(name, description, **kwargs)

        _METRICS_REGISTRY[registry_key] = metric
        logger.debug(f"Created new metric: {name}")
        return metric

    except ValueError as e:
        if "Duplicated timeseries" in str(e):
            logger.warning(f"Metric {name} already registered in Prometheus, but not in our registry. This indicates a module reload issue.")
            # Create a dummy metric that won't interfere
            class DummyMetric:
                def labels(self, **kwargs):
                    return self
                def inc(self, amount=1):
                    pass
                def observe(self, amount):
                    pass
                def set(self, value):
                    pass
                def collect(self):
                    return []

            dummy = DummyMetric()
            _METRICS_REGISTRY[registry_key] = dummy
            logger.warning(f"Created dummy metric for {name} to prevent errors")
            return dummy
        else:
            logger.error(f"Failed to create metric {name}: {e}")
            raise

# Prometheus HTTP metrics (exposed via /metrics endpoint)
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

# OpenTelemetry HTTP metrics (for collector export)
# CRITICAL: These are required when using OpenTelemetry Collector
try:
    meter = otel_metrics.get_meter(__name__)
    
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
    
    logger.info("Successfully created OpenTelemetry HTTP metrics")
    
except Exception as e:
    logger.error(f"Failed to create OpenTelemetry metrics: {e}")
    # Create dummy metrics as fallback
    class DummyOTelMetric:
        def add(self, amount, attributes=None):
            pass
        def record(self, amount, attributes=None):
            pass
    
    otel_http_requests_total = DummyOTelMetric()
    otel_http_request_duration = DummyOTelMetric()
    otel_http_requests_in_flight = DummyOTelMetric()
    logger.warning("Created dummy OpenTelemetry metrics due to initialization failure")


class EnhancedHTTPMetricsMiddleware(BaseHTTPMiddleware):
    """
    Enhanced middleware to collect standardized HTTP request metrics.

    This middleware implements the standardized HTTP metrics with proper timing,
    in-flight tracking, and comprehensive error handling using Prometheus.
    """

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """
        Process request and collect all three standardized HTTP metrics.

        Args:
            request: The incoming request
            call_next: The next middleware/endpoint to call

        Returns:
            Response with metrics recorded
        """
        # Start high-precision timing using perf_counter for millisecond precision
        start_time = time.perf_counter()

        # Increment in-flight requests gauge (both Prometheus and OpenTelemetry)
        in_flight_incremented = False
        otel_in_flight_incremented = False
        
        # Increment Prometheus in-flight gauge
        try:
            HTTP_REQUESTS_IN_FLIGHT.inc()
            in_flight_incremented = True
            logger.debug("Successfully incremented Prometheus in-flight requests gauge")
        except Exception as e:
            logger.error(
                "Failed to increment Prometheus in-flight requests gauge",
                error=str(e),
                error_type=type(e).__name__,
                exc_info=True,
            )
        
        # Increment OpenTelemetry in-flight gauge
        try:
            otel_http_requests_in_flight.add(1)
            otel_in_flight_incremented = True
            logger.debug("Successfully incremented OpenTelemetry in-flight requests gauge")
        except Exception as e:
            logger.error(
                "Failed to increment OpenTelemetry in-flight requests gauge",
                error=str(e),
                error_type=type(e).__name__,
                exc_info=True,
            )

        try:
            # Process request
            response = await call_next(request)

            # Calculate duration in milliseconds with high precision
            duration_ms = (time.perf_counter() - start_time) * 1000

            # Extract labels for metrics
            method = self._get_method_label(request.method)
            path = self._extract_route_pattern(request)
            status = self._format_status_code(response.status_code)

            # Record all three metrics with proper error handling
            self._record_metrics(method, path, status, duration_ms)

            # Log slow requests (> 1000ms)
            if duration_ms > 1000:
                logger.warning(
                    "Slow request detected",
                    method=method,
                    path=path,
                    duration_ms=duration_ms,
                    status=status,
                )

            return response

        except Exception as e:
            # Calculate duration even for exceptions
            duration_ms = (time.perf_counter() - start_time) * 1000

            # Extract labels for error metrics
            method = self._get_method_label(request.method)
            path = self._extract_route_pattern(request)
            status = "500"  # All exceptions result in 500 status for metrics

            # Record metrics even when exceptions occur
            self._record_metrics(method, path, status, duration_ms)

            logger.error(
                "Request processing error - metrics collection attempted",
                error=str(e),
                error_type=type(e).__name__,
                method=method,
                path=path,
                duration_ms=duration_ms,
                exc_info=True,
            )

            raise
        finally:
            # Always decrement in-flight requests gauge (both systems)
            # Only decrement if we successfully incremented to avoid negative values
            if in_flight_incremented:
                try:
                    HTTP_REQUESTS_IN_FLIGHT.dec()
                    logger.debug("Successfully decremented Prometheus in-flight requests gauge")
                except Exception as e:
                    logger.error(
                        "Failed to decrement Prometheus in-flight requests gauge",
                        error=str(e),
                        error_type=type(e).__name__,
                        exc_info=True,
                    )
            
            # Decrement OpenTelemetry in-flight gauge
            if otel_in_flight_incremented:
                try:
                    otel_http_requests_in_flight.add(-1)
                    logger.debug("Successfully decremented OpenTelemetry in-flight requests gauge")
                except Exception as e:
                    logger.error(
                        "Failed to decrement OpenTelemetry in-flight requests gauge",
                        error=str(e),
                        error_type=type(e).__name__,
                        exc_info=True,
                    )

    def _record_metrics(
        self, method: str, path: str, status: str, duration_ms: float
    ) -> None:
        """
        Record all three HTTP metrics with comprehensive error handling.
        
        CRITICAL: Records to BOTH systems:
        - Prometheus (exposed via /metrics endpoint)
        - OpenTelemetry (sent to collector and then to monitoring system)

        Args:
            method: HTTP method (uppercase)
            path: Route pattern
            status: Status code as string
            duration_ms: Request duration in milliseconds
        """
        # Debug logging for metric values during development
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

        # Record OpenTelemetry counter metrics with error handling
        try:
            otel_http_requests_total.add(1, attributes=otel_attributes)
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

    def _extract_route_pattern(self, request: Request) -> str:
        """
        Extract route pattern from request URL to prevent high cardinality metrics.

        Converts URLs with parameters to route patterns (e.g., /api/v1/models/123 -> /api/v1/models/{model_id})

        CUSTOMIZE THIS METHOD for your specific API routes!
        """
        try:
            path = request.url.path.rstrip('/')

            if not path:
                return "/"

            # CUSTOMIZE: Add your service-specific route patterns here
            # Example patterns:
            if path.startswith("/api/v1/users"):
                return self._extract_users_route_pattern(path)
            elif path.startswith("/api/v1/orders"):
                return self._extract_orders_route_pattern(path)
            elif path.startswith("/health"):
                return self._extract_health_route_pattern(path)
            elif path == "/metrics":
                return "/metrics"
            elif path == "/":
                return "/"

            # Fallback for unmatched routes
            return self._sanitize_unmatched_route(path)

        except Exception as e:
            logger.error(
                "Failed to extract route pattern",
                error=str(e),
                error_type=type(e).__name__,
                path=getattr(request.url, 'path', 'unknown'),
                exc_info=True,
            )
            return "/unknown"

    def _extract_users_route_pattern(self, path: str) -> str:
        """CUSTOMIZE: Extract route pattern for /api/v1/users endpoints."""
        parts = path.split("/")

        if len(parts) == 4:  # /api/v1/users
            return "/api/v1/users"
        elif len(parts) == 5:  # /api/v1/users/{user_id}
            return "/api/v1/users/{user_id}"
        elif len(parts) == 6:  # /api/v1/users/{user_id}/profile
            return f"/api/v1/users/{{user_id}}/{parts[5]}"

        return f"/api/v1/users/{'/'.join(parts[4:])}"

    def _extract_orders_route_pattern(self, path: str) -> str:
        """CUSTOMIZE: Extract route pattern for /api/v1/orders endpoints."""
        parts = path.split("/")

        if len(parts) == 4:  # /api/v1/orders
            return "/api/v1/orders"
        elif len(parts) == 5:  # /api/v1/orders/{order_id}
            return "/api/v1/orders/{order_id}"

        return f"/api/v1/orders/{'/'.join(parts[4:])}"

    def _extract_health_route_pattern(self, path: str) -> str:
        """Extract route pattern for /health endpoints."""
        parts = path.split("/")

        if len(parts) == 2:  # /health
            return "/health"
        elif len(parts) == 3:  # /health/{check_type}
            return "/health/{check_type}"

        return f"/health/{'/'.join(parts[2:])}"

    def _sanitize_unmatched_route(self, path: str) -> str:
        """Sanitize unmatched routes to prevent high cardinality."""
        try:
            parts = path.split("/")
            sanitized_parts = []

            for part in parts:
                if not part:
                    sanitized_parts.append(part)
                    continue

                # Check if part looks like an ID
                if self._looks_like_id(part):
                    sanitized_parts.append("{id}")
                else:
                    # Keep the original part but limit length
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
                exc_info=True,
            )
            return "/unknown"

    def _looks_like_id(self, part: str) -> bool:
        """Check if a path part looks like an ID that should be parameterized."""
        try:
            # MongoDB ObjectId (24 character hex)
            if len(part) == 24 and all(c in '0123456789abcdefABCDEF' for c in part):
                return True

            # UUID format (with or without hyphens)
            if len(part) == 36 and part.count('-') == 4:
                return True
            if len(part) == 32 and all(c in '0123456789abcdefABCDEF' for c in part):
                return True

            # Numeric ID
            if part.isdigit() and len(part) >= 1:
                return True

            # Alphanumeric ID that looks like an identifier
            if len(part) > 8 and part.replace('-', '').replace('_', '').isalnum():
                return True

            return False

        except Exception:
            return False

    def _format_status_code(self, status_code: int) -> str:
        """Format HTTP status code as string for consistent labeling."""
        try:
            if not isinstance(status_code, int):
                logger.warning(
                    "Invalid status code type",
                    status_code=status_code,
                    status_code_type=type(status_code).__name__,
                )
                return "unknown"

            if status_code < 100 or status_code > 599:
                logger.warning("Status code out of valid range", status_code=status_code)
                return "unknown"

            return str(status_code)

        except Exception as e:
            logger.error(
                "Failed to format status code",
                error=str(e),
                status_code=status_code,
                exc_info=True,
            )
            return "unknown"

    def _get_method_label(self, method: str) -> str:
        """Get uppercase HTTP method name for consistent labeling."""
        try:
            if not isinstance(method, str):
                logger.warning(
                    "Invalid method type",
                    method=method,
                    method_type=type(method).__name__,
                )
                return "UNKNOWN"

            method_upper = method.strip().upper()

            valid_methods = {
                "GET", "POST", "PUT", "DELETE", "PATCH",
                "HEAD", "OPTIONS", "TRACE", "CONNECT",
            }

            if method_upper not in valid_methods:
                logger.warning("Unknown HTTP method", method=method, method_upper=method_upper)

            return method_upper if method_upper else "UNKNOWN"

        except Exception as e:
            logger.error(
                "Failed to format method label",
                error=str(e),
                method=method,
                exc_info=True,
            )
            return "UNKNOWN"


def setup_monitoring(app) -> Instrumentator:
    """
    Setup monitoring and observability for the FastAPI application.

    Args:
        app: FastAPI application instance

    Returns:
        Configured Instrumentator instance
    """
    from src.config import get_settings

    settings = get_settings()

    if not settings.enable_metrics:
        logger.info("Metrics disabled, skipping monitoring setup")
        return None

    # Create instrumentator with minimal conflicting metrics
    instrumentator = Instrumentator(
        should_group_status_codes=False,
        should_ignore_untemplated=True,
        should_respect_env_var=False,
        should_instrument_requests_inprogress=False,  # We use our own in-flight tracking
        excluded_handlers=["/metrics"],  # Only exclude metrics endpoint
    )

    # Add only non-conflicting metrics
    instrumentator.add(metrics.combined_size())  # Request/response size metrics

    # Instrument the app
    instrumentator.instrument(app)

    logger.info("Monitoring and observability setup complete")
    return instrumentator
```

### 2. Application Integration

Update your `src/main.py`:

```python
from fastapi import FastAPI
from prometheus_client import make_asgi_app

from src.core.monitoring import EnhancedHTTPMetricsMiddleware, setup_monitoring
from src.config import get_settings

def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title="Your Microservice Name",
        description="Your microservice description",
        version="1.0.0",
    )

    # Add custom middleware BEFORE other middleware
    if settings.enable_metrics:
        app.add_middleware(EnhancedHTTPMetricsMiddleware)

    # Add other middleware here...

    # Setup monitoring and observability
    if settings.enable_metrics:
        instrumentator = setup_monitoring(app)

        # Mount Prometheus metrics endpoint
        metrics_app = make_asgi_app()
        app.mount("/metrics", metrics_app)

    # Add your routers here...

    return app

app = create_app()
```

### 3. Configuration Settings

Add to your `src/config.py`:

```python
from pydantic import Field
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # Existing settings...

    # Metrics configuration
    enable_metrics: bool = Field(default=True, description="Enable Prometheus metrics")

    class Config:
        env_file = ".env"
        case_sensitive = False

def get_settings() -> Settings:
    return Settings()
```

## Deployment Configuration

### 1. Production Startup Script

Create `scripts/start-production.sh`:

```bash
#!/bin/bash
set -e

# Convert LOG_LEVEL to lowercase for uvicorn
UVICORN_LOG_LEVEL=$(echo "${LOG_LEVEL:-INFO}" | tr '[:upper:]' '[:lower:]')

# Start uvicorn directly (single process for consistent metrics)
exec /app/.venv/bin/uvicorn src.main:app \
     --host 0.0.0.0 \
     --port ${PORT:-8088} \
     --log-level "$UVICORN_LOG_LEVEL" \
     --access-log \
     --no-use-colors
```

### 2. Dockerfile Configuration

**CRITICAL**: Use single-process deployment for consistent metrics:

```dockerfile
# Production stage
FROM base AS production

# Copy startup script
COPY --chown=appuser:appuser scripts/start-production.sh /app/
RUN chmod +x /app/start-production.sh

# Use single process for consistent metrics
CMD ["/app/start-production.sh"]
```

**❌ AVOID**: Multi-worker deployments like:
```bash
# DON'T DO THIS - causes inconsistent metrics
gunicorn --workers 4 src.main:app
```

## Common Pitfalls and Solutions

### 1. **Metrics Visible in /metrics but Not in Monitoring System (CRITICAL ISSUE)**

**Problem**: HTTP metrics appear in the `/metrics` endpoint but don't show up in Prometheus/Grafana dashboards.

**Cause**: Only implementing Prometheus metrics without OpenTelemetry integration when using OpenTelemetry Collector infrastructure.

**Solution**: Implement BOTH Prometheus metrics (for `/metrics` endpoint) AND OpenTelemetry metrics (for collector export) as shown in the code above.

**How to Identify**: 
- `curl http://your-service:8088/metrics` shows metrics
- Prometheus queries return no data: `http_requests_total{service="your-service"}`
- OpenTelemetry Collector logs show no incoming metrics from your service

**Prevention**: Always implement dual metrics system when using OpenTelemetry Collector.

### 2. **Inconsistent Metrics (Second Most Common Issue)**

**Problem**: Metrics counts go up and down randomly, don't match actual API calls.

**Cause**: Multiple worker processes, each with separate metrics registries.

**Solution**: Use single-process deployment (Uvicorn instead of multi-worker Gunicorn).

### 3. **Duplicate Registration Errors**

**Problem**: `ValueError: Duplicated timeseries in CollectorRegistry`

**Cause**: Module reloading or circular imports.

**Solution**: Use the `_get_or_create_metric()` pattern shown in the code above.

### 4. **High Cardinality Metrics**

**Problem**: Too many unique label combinations, causing memory issues.

**Cause**: Not parameterizing URLs with IDs.

**Solution**: Implement proper route pattern extraction in `_extract_route_pattern()`.

### 5. **Missing Metrics for Some Endpoints**

**Problem**: Some endpoints don't show up in metrics.

**Cause**: Middleware not applied to all routes, or instrumentator exclusions.

**Solution**: Ensure middleware is added early and check exclusion lists.

## Testing and Validation

### 1. Unit Testing Setup

To prevent unit tests from attempting external connections, add this to your test files:

```python
import os
from unittest.mock import Mock, patch

# Set environment variables to disable any external metric exporters
os.environ['OTEL_SDK_DISABLED'] = 'true'
os.environ['OTEL_TRACES_EXPORTER'] = 'none'
os.environ['OTEL_METRICS_EXPORTER'] = 'none'
os.environ['OTEL_LOGS_EXPORTER'] = 'none'

# Mock any remaining OpenTelemetry components if present
@pytest.fixture(autouse=True)
def mock_opentelemetry_metrics():
    """Mock OpenTelemetry metrics to prevent network calls during unit tests."""
    with patch('src.core.monitoring.otel_http_requests_total', Mock()), \
         patch('src.core.monitoring.otel_http_request_duration', Mock()), \
         patch('src.core.monitoring.otel_http_requests_in_flight', Mock()):
        yield
```

### 2. Local Testing

```bash
# Start your service
uvicorn src.main:app --host 0.0.0.0 --port 8088

# Make some API calls
curl http://localhost:8088/api/v1/users
curl http://localhost:8088/api/v1/orders/123

# Check metrics
curl http://localhost:8088/metrics | grep http_request_duration_count
```

### 3. Validation Checklist

#### Prometheus Metrics (via /metrics endpoint)
- [ ] Metrics endpoint (`/metrics`) returns data
- [ ] `http_requests_total` counter increases with each request
- [ ] `http_request_duration_count` matches `http_requests_total`
- [ ] `http_requests_in_flight` shows 0 when no requests are processing
- [ ] Route patterns are parameterized (no raw IDs in labels)
- [ ] Status codes are properly formatted as strings
- [ ] Methods are uppercase

#### OpenTelemetry Integration (CRITICAL for Collector setups)
- [ ] OpenTelemetry Collector logs show incoming metrics from your service
- [ ] Prometheus queries return data: `http_requests_total{service="your-service"}`
- [ ] Both Prometheus and OpenTelemetry metrics have identical values
- [ ] Service logs show "Successfully recorded OpenTelemetry" messages
- [ ] No "Failed to record OpenTelemetry" errors in logs

#### End-to-End Validation
```bash
# 1. Check /metrics endpoint
curl http://localhost:8088/metrics | grep http_requests_total

# 2. Check OpenTelemetry Collector logs
kubectl logs -n monitoring deployment/otel-collector-collector | grep http_requests_total

# 3. Query Prometheus directly
curl -G 'http://prometheus:9090/api/v1/query' \
  --data-urlencode 'query=http_requests_total{service="your-service"}'

# 4. Verify metrics appear in Grafana dashboards
```

### 4. Load Testing

```bash
# Use Apache Bench to test consistency
ab -n 100 -c 10 http://localhost:8088/api/v1/users

# Check that metrics count equals 100
curl http://localhost:8088/metrics | grep 'http_request_duration_count.*users.*200'
```

## Troubleshooting

### Debug Logging

Enable debug logging to see detailed metrics collection:

```bash
export LOG_LEVEL=DEBUG
```

Look for these log messages:
- `"Successfully recorded HTTP requests total counter"`
- `"Successfully recorded HTTP request duration histogram"`
- `"Recording HTTP metrics"`

### Common Error Messages

1. **"Failed to record OpenTelemetry HTTP requests total counter"**
   - OpenTelemetry meter not properly initialized
   - Check that OpenTelemetry SDK is configured in your main.py
   - Verify OTLP exporters are configured correctly

2. **"Failed to create OpenTelemetry metrics"**
   - OpenTelemetry dependencies missing or not imported
   - MeterProvider not set up correctly
   - Check that `opentelemetry-api` and `opentelemetry-sdk` are installed

3. **"Failed to record HTTP requests total counter"** (Prometheus)
   - Check if Prometheus metrics are properly initialized
   - Verify no duplicate registration issues

4. **"Metric already registered in Prometheus"**
   - Module reload issue, should be handled gracefully by dummy metrics

5. **"Invalid status code type"**
   - Response object not returning proper status code
   - Check your FastAPI response handling

### OpenTelemetry-Specific Troubleshooting

**Problem**: Metrics visible in `/metrics` but not in Prometheus
```bash
# Check if OpenTelemetry Collector is receiving metrics
kubectl logs -n monitoring deployment/otel-collector-collector | grep "http_requests_total"

# Check if your service is sending to collector
kubectl logs your-service-pod | grep "OpenTelemetry"

# Verify collector configuration includes your service
kubectl get configmap -n monitoring otel-collector-config -o yaml
```

**Problem**: OpenTelemetry metrics initialization fails
```python
# Add this debug code to verify OpenTelemetry setup
from opentelemetry import metrics as otel_metrics
try:
    meter = otel_metrics.get_meter(__name__)
    print(f"Meter: {meter}")
    print(f"MeterProvider: {otel_metrics.get_meter_provider()}")
except Exception as e:
    print(f"OpenTelemetry setup issue: {e}")
```

### Prometheus Query Examples

```promql
# Total requests per endpoint
sum by (path, method) (http_requests_total)

# Request rate per minute
rate(http_requests_total[1m])

# 95th percentile response time
histogram_quantile(0.95, rate(http_request_duration_bucket[5m]))

# Requests in flight
http_requests_in_flight
```

## Customization for Your Service

### 1. Route Pattern Extraction

Customize the `_extract_route_pattern()` method for your specific API routes:

```python
def _extract_route_pattern(self, request: Request) -> str:
    path = request.url.path.rstrip('/')

    # Add your service-specific patterns
    if path.startswith("/api/v1/your-resource"):
        return self._extract_your_resource_route_pattern(path)

    # Continue with other patterns...
```

### 2. Additional Metrics

Add service-specific metrics:

```python
# Business metrics
ORDER_COUNT = _get_or_create_metric(
    Counter,
    'orders_total',
    'Total number of orders processed',
    ['status', 'type']
)

# Performance metrics
PROCESSING_DURATION = _get_or_create_metric(
    Histogram,
    'processing_duration_seconds',
    'Time spent processing business logic',
    ['operation'],
    buckets=[0.1, 0.5, 1.0, 2.5, 5.0, 10.0]
)
```

### 3. Health Check Integration

Add metrics to your health checks:

```python
from src.core.monitoring import HTTP_REQUESTS_IN_FLIGHT

@app.get("/health/live")
async def health_live():
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "requests_in_flight": HTTP_REQUESTS_IN_FLIGHT._value._value
    }
```

## Best Practices

1. **Dual Metrics System**: ALWAYS implement both Prometheus and OpenTelemetry metrics when using OpenTelemetry Collector
2. **Single Process Deployment**: Always use single-process deployment for consistent metrics
3. **Route Parameterization**: Always parameterize URLs with IDs to prevent high cardinality
4. **Error Handling**: Wrap all metric operations in try-catch blocks for both systems
5. **Structured Logging**: Use structured logging for better observability
6. **Testing**: Always test BOTH Prometheus and OpenTelemetry metrics in your CI/CD pipeline
7. **Documentation**: Document your service-specific route patterns
8. **End-to-End Validation**: Verify metrics flow from service → collector → Prometheus → dashboards
9. **Monitoring the Monitoring**: Set up alerts for metric collection failures
10. **Consistent Naming**: Use identical metric names and attributes across both systems

## Support

For questions or issues with this implementation:

1. Check the troubleshooting section above
2. Review the logs for error messages
3. Validate your deployment uses single-process configuration
4. Ensure route patterns are properly parameterized

## Testing Dual Metrics System

### Integration Test Template

Create this test to verify both systems work together:

```python
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from unittest.mock import patch

def test_dual_metrics_system():
    """Test that both Prometheus and OpenTelemetry metrics are recorded."""
    app = FastAPI()
    app.add_middleware(EnhancedHTTPMetricsMiddleware)
    
    @app.get("/test")
    async def test_endpoint():
        return {"message": "test"}
    
    client = TestClient(app)
    
    # Mock OpenTelemetry metrics to verify they're called
    with patch('src.core.monitoring.otel_http_requests_total') as mock_otel_counter, \
         patch('src.core.monitoring.otel_http_request_duration') as mock_otel_histogram:
        
        # Make request
        response = client.get("/test")
        assert response.status_code == 200
        
        # Verify OpenTelemetry metrics were called
        mock_otel_counter.add.assert_called_once_with(
            1, 
            attributes={"method": "GET", "path": "/test", "status": "200"}
        )
        mock_otel_histogram.record.assert_called_once()
        
        # Verify Prometheus metrics via /metrics endpoint
        # (Add Prometheus endpoint to test app and verify metrics appear)
```

### Verification Script

Use this script to validate your implementation:

```python
#!/usr/bin/env python3
"""Verify dual metrics system is working correctly."""

import requests
import time

def verify_metrics_integration(service_url):
    """Verify both Prometheus and OpenTelemetry metrics work."""
    
    # 1. Make test requests
    for i in range(5):
        response = requests.get(f"{service_url}/health")
        print(f"Request {i+1}: {response.status_code}")
    
    # 2. Check Prometheus /metrics endpoint
    metrics_response = requests.get(f"{service_url}/metrics")
    if "http_requests_total" in metrics_response.text:
        print("✅ Prometheus metrics working")
    else:
        print("❌ Prometheus metrics missing")
    
    # 3. Check if metrics appear in Prometheus (requires Prometheus URL)
    # prometheus_response = requests.get(
    #     f"{prometheus_url}/api/v1/query",
    #     params={"query": f'http_requests_total{{service="{service_name}"}}'}
    # )
    # if prometheus_response.json()["data"]["result"]:
    #     print("✅ OpenTelemetry metrics working")
    # else:
    #     print("❌ OpenTelemetry metrics missing")

if __name__ == "__main__":
    verify_metrics_integration("http://localhost:8088")
```

This implementation has been tested and validated in the GlobeCo Portfolio Service and provides consistent, reliable HTTP metrics using both Prometheus (for `/metrics` endpoint) and OpenTelemetry (for collector export). This dual approach ensures metrics appear in your monitoring infrastructure regardless of collection method.
