# Enhanced HTTP Metrics Implementation Design

## Overview

This design document outlines the implementation of standardized HTTP request metrics for the GlobeCo Portfolio Service. The solution will add three core HTTP metrics (requests total, request duration, and requests in flight) using Prometheus client library, complementing the existing OpenTelemetry instrumentation without conflicts.

The design leverages lessons learned from the HTTP metrics implementation guide to avoid common pitfalls such as inconsistent metrics from multi-worker deployments, duplicate registration errors, and high cardinality issues.

## Architecture

### High-Level Architecture

```mermaid
graph TB
    A[HTTP Request] --> B[LoggingMiddleware]
    B --> C[EnhancedHTTPMetricsMiddleware]
    C --> D[FastAPI Application]
    D --> E[API Endpoints]
    
    C --> F[Prometheus Metrics]
    F --> G[HTTP_REQUESTS_TOTAL Counter]
    F --> H[HTTP_REQUEST_DURATION Histogram]
    F --> I[HTTP_REQUESTS_IN_FLIGHT Gauge]
    
    F --> J[/metrics Endpoint]
    J --> K[OpenTelemetry Collector]
    
    L[Existing OTel Instrumentation] --> M[OTel Collector]
    
    style C fill:#e1f5fe
    style F fill:#f3e5f5
    style J fill:#e8f5e8
```

### Component Integration

The enhanced HTTP metrics will integrate with the existing service architecture:

1. **Middleware Layer**: Custom middleware positioned after logging middleware but before existing OTel instrumentation
2. **Metrics Collection**: Prometheus client library for metric creation and export
3. **Export Mechanism**: Existing `/metrics` endpoint enhanced with new standardized metrics
4. **Configuration**: Integrated with existing settings system for enable/disable control

## Components and Interfaces

### 1. Core Monitoring Module (`app/monitoring.py`)

#### Metrics Registry System
```python
# Global registry to prevent duplicate registration
_METRICS_REGISTRY = {}

def _get_or_create_metric(metric_class, name, description, labels=None, **kwargs):
    """Centralized metric creation with duplicate prevention"""
```

**Purpose**: Prevents duplicate metric registration errors during module reloads or circular imports.

#### Core Metrics
```python
HTTP_REQUESTS_TOTAL = Counter(
    'http_requests_total',
    'Total number of HTTP requests',
    ['method', 'path', 'status']
)

HTTP_REQUEST_DURATION = Histogram(
    'http_request_duration',
    'HTTP request duration in milliseconds',
    ['method', 'path', 'status'],
    buckets=[5, 10, 25, 50, 100, 250, 500, 1000, 2500, 5000, 10000]
)

HTTP_REQUESTS_IN_FLIGHT = Gauge(
    'http_requests_in_flight',
    'Number of HTTP requests currently being processed'
)
```

**Design Decisions**:
- **Millisecond buckets**: Ensures proper OpenTelemetry Collector interpretation
- **Three-label system**: Provides sufficient granularity without excessive cardinality
- **Prometheus-native**: Uses prometheus_client directly for reliability

### 2. Enhanced HTTP Metrics Middleware

#### Middleware Class Structure
```python
class EnhancedHTTPMetricsMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # High-precision timing
        start_time = time.perf_counter()
        
        # In-flight tracking
        HTTP_REQUESTS_IN_FLIGHT.inc()
        
        try:
            response = await call_next(request)
            # Record success metrics
        except Exception:
            # Record error metrics
        finally:
            HTTP_REQUESTS_IN_FLIGHT.dec()
```

**Key Features**:
- **High-precision timing**: Uses `time.perf_counter()` for microsecond accuracy
- **Exception handling**: Ensures metrics are recorded even for failed requests
- **In-flight tracking**: Proper increment/decrement with error handling

#### Route Pattern Extraction

Portfolio Service specific route patterns:
```python
def _extract_route_pattern(self, request: Request) -> str:
    path = request.url.path.rstrip('/')
    
    # Portfolio service specific patterns
    if path.startswith("/api/v1/portfolio"):
        return self._extract_portfolio_v1_route_pattern(path)
    elif path.startswith("/api/v2/portfolios"):
        return self._extract_portfolio_v2_route_pattern(path)
    elif path == "/health":
        return "/health"
    elif path == "/metrics":
        return "/metrics"
    elif path == "/":
        return "/"
    
    return self._sanitize_unmatched_route(path)
```

**Portfolio-Specific Route Handlers**:
```python
def _extract_portfolio_v1_route_pattern(self, path: str) -> str:
    """Handle v1 API routes: /api/v1/portfolio/{portfolioId}"""
    parts = path.split("/")
    
    if len(parts) == 3:  # /api/v1
        return "/api/v1"
    elif len(parts) == 4:  # /api/v1/portfolios or /api/v1/portfolio
        return f"/api/v1/{parts[3]}"
    elif len(parts) == 5:  # /api/v1/portfolio/{portfolioId}
        return "/api/v1/portfolio/{portfolioId}"
    
    return "/api/v1/portfolio/unknown"

def _extract_portfolio_v2_route_pattern(self, path: str) -> str:
    """Handle v2 API routes: /api/v2/portfolios with query params"""
    parts = path.split("/")
    
    if len(parts) == 4:  # /api/v2/portfolios
        return "/api/v2/portfolios"
    
    return "/api/v2/portfolios/unknown"
```

### 3. Configuration Integration

#### Settings Extension
```python
class Settings(BaseSettings):
    # Existing settings...
    enable_metrics: bool = Field(default=True, description="Enable enhanced HTTP metrics")
    metrics_debug_logging: bool = Field(default=False, description="Enable debug logging for metrics")
```

#### Application Integration
```python
def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(lifespan=lifespan)
    
    # Add logging middleware first
    app.add_middleware(LoggingMiddleware, logger=logger)
    
    # Add metrics middleware if enabled
    if settings.enable_metrics:
        app.add_middleware(EnhancedHTTPMetricsMiddleware)
    
    # Existing OTel instrumentation
    FastAPIInstrumentor().instrument_app(app)
```

## Data Models

### Metric Label Structure

#### HTTP Requests Total Counter
```
http_requests_total{method="GET", path="/api/v1/portfolio/{portfolioId}", status="200"} 42
```

#### HTTP Request Duration Histogram
```
http_request_duration_bucket{method="POST", path="/api/v1/portfolios", status="201", le="100"} 15
http_request_duration_sum{method="POST", path="/api/v1/portfolios", status="201"} 1250.5
http_request_duration_count{method="POST", path="/api/v1/portfolios", status="201"} 15
```

#### HTTP Requests In Flight Gauge
```
http_requests_in_flight 3
```

### Route Pattern Mapping

| Actual URL | Route Pattern | Rationale |
|------------|---------------|-----------|
| `/api/v1/portfolios` | `/api/v1/portfolios` | Collection endpoint |
| `/api/v1/portfolio/507f1f77bcf86cd799439011` | `/api/v1/portfolio/{portfolioId}` | MongoDB ObjectId parameterized |
| `/api/v2/portfolios?name=test&limit=10` | `/api/v2/portfolios` | Query params ignored |
| `/health` | `/health` | Health check endpoint |
| `/metrics` | `/metrics` | Metrics endpoint |
| `/` | `/` | Root endpoint |

### ID Detection Logic

The system will detect and parameterize various ID formats:
- **MongoDB ObjectId**: 24-character hexadecimal strings
- **UUID**: Standard UUID format with or without hyphens
- **Numeric IDs**: Pure numeric strings
- **Alphanumeric IDs**: Long alphanumeric identifiers

## Error Handling

### Comprehensive Error Strategy

#### 1. Metric Registration Errors
```python
try:
    metric = Counter(name, description, labels)
    _METRICS_REGISTRY[name] = metric
except ValueError as e:
    if "Duplicated timeseries" in str(e):
        # Create dummy metric to prevent service disruption
        dummy = DummyMetric()
        _METRICS_REGISTRY[name] = dummy
        logger.warning(f"Created dummy metric for {name}")
```

#### 2. Metric Recording Errors
```python
try:
    HTTP_REQUESTS_TOTAL.labels(method=method, path=path, status=status).inc()
except Exception as e:
    logger.error("Failed to record HTTP requests total", 
                error=str(e), method=method, path=path, status=status)
    # Continue processing - don't fail the request
```

#### 3. In-Flight Gauge Protection
```python
in_flight_incremented = False
try:
    HTTP_REQUESTS_IN_FLIGHT.inc()
    in_flight_incremented = True
except Exception as e:
    logger.error("Failed to increment in-flight gauge", error=str(e))

# In finally block:
if in_flight_incremented:
    try:
        HTTP_REQUESTS_IN_FLIGHT.dec()
    except Exception as e:
        logger.error("Failed to decrement in-flight gauge", error=str(e))
```

### Fallback Mechanisms

1. **Route Pattern Extraction**: Falls back to `/unknown` if pattern extraction fails
2. **Status Code Formatting**: Falls back to `"unknown"` for invalid status codes
3. **Method Formatting**: Falls back to `"UNKNOWN"` for invalid HTTP methods
4. **Metric Recording**: Uses dummy metrics if registration fails

## Testing Strategy

### Unit Testing Approach

#### 1. Metrics Creation Tests
```python
def test_metric_creation():
    """Test that all three metrics are created correctly"""
    assert HTTP_REQUESTS_TOTAL is not None
    assert HTTP_REQUEST_DURATION is not None
    assert HTTP_REQUESTS_IN_FLIGHT is not None

def test_duplicate_registration_handling():
    """Test graceful handling of duplicate metric registration"""
    # Attempt to create duplicate metrics
    # Verify dummy metrics are created
```

#### 2. Route Pattern Extraction Tests
```python
@pytest.mark.parametrize("url,expected", [
    ("/api/v1/portfolios", "/api/v1/portfolios"),
    ("/api/v1/portfolio/507f1f77bcf86cd799439011", "/api/v1/portfolio/{portfolioId}"),
    ("/api/v2/portfolios?name=test", "/api/v2/portfolios"),
    ("/health", "/health"),
])
def test_route_pattern_extraction(url, expected):
    """Test portfolio-specific route pattern extraction"""
```

#### 3. Middleware Integration Tests
```python
@pytest.mark.asyncio
async def test_middleware_metrics_recording():
    """Test that middleware records all three metrics correctly"""
    # Mock request/response
    # Verify counter increments
    # Verify histogram records duration
    # Verify gauge increments/decrements
```

### Integration Testing

#### 1. End-to-End Metrics Validation
```python
@pytest.mark.asyncio
async def test_full_request_metrics():
    """Test complete request flow with metrics"""
    # Make actual HTTP requests
    # Verify metrics are recorded
    # Check /metrics endpoint output
```

#### 2. Load Testing Validation
```python
def test_concurrent_requests_metrics():
    """Test metrics accuracy under concurrent load"""
    # Use asyncio to make concurrent requests
    # Verify final metrics counts match request counts
```

### Mock Strategy for Unit Tests

```python
@pytest.fixture(autouse=True)
def mock_prometheus_metrics():
    """Mock Prometheus metrics to prevent external dependencies"""
    with patch('app.monitoring.HTTP_REQUESTS_TOTAL') as mock_counter, \
         patch('app.monitoring.HTTP_REQUEST_DURATION') as mock_histogram, \
         patch('app.monitoring.HTTP_REQUESTS_IN_FLIGHT') as mock_gauge:
        yield {
            'counter': mock_counter,
            'histogram': mock_histogram,
            'gauge': mock_gauge
        }
```

## Performance Considerations

### Timing Precision
- **High-precision timing**: Uses `time.perf_counter()` for microsecond accuracy
- **Minimal overhead**: Timing operations are lightweight
- **Millisecond buckets**: Optimized for typical web service response times

### Memory Management
- **Controlled cardinality**: Route parameterization prevents unbounded label values
- **Efficient storage**: Prometheus client uses efficient internal storage
- **Garbage collection**: No manual cleanup required for metrics

### CPU Impact
- **Minimal processing**: Simple string operations for label extraction
- **Optimized patterns**: Pre-compiled regex patterns where beneficial
- **Error handling**: Fast-path for common cases, detailed handling for errors

## Deployment Considerations

### Single-Process Requirement
The service must maintain single-process deployment to ensure consistent metrics:

```dockerfile
# Use uvicorn directly, not gunicorn with workers
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8088"]
```

**Rationale**: Multiple worker processes each maintain separate metric registries, leading to inconsistent and confusing metrics.

### Configuration Management
```yaml
# Environment variables
ENABLE_METRICS: "true"
METRICS_DEBUG_LOGGING: "false"
LOG_LEVEL: "INFO"
```

### Monitoring Integration
The metrics will be automatically scraped by the existing OpenTelemetry Collector configuration, requiring no changes to Kubernetes manifests or monitoring setup.

## Security Considerations

### Metric Data Exposure
- **No sensitive data**: Route patterns are sanitized to remove sensitive path parameters
- **Controlled access**: `/metrics` endpoint follows existing security patterns
- **Rate limiting**: Existing rate limiting applies to metrics collection

### Error Information
- **Safe error logging**: Error messages don't expose sensitive system information
- **Structured logging**: Consistent with existing logging patterns
- **Debug information**: Only available when debug logging is explicitly enabled

## Compatibility and Migration

### Backward Compatibility
- **No breaking changes**: Existing API functionality remains unchanged
- **Optional feature**: Can be disabled via configuration
- **Existing metrics**: Complements rather than replaces existing OTel metrics

### Migration Strategy
1. **Phase 1**: Deploy with metrics enabled in development
2. **Phase 2**: Enable in staging with monitoring validation
3. **Phase 3**: Production deployment with gradual rollout
4. **Phase 4**: Integration with existing dashboards and alerts

This design ensures a robust, maintainable, and performant implementation of standardized HTTP metrics that integrates seamlessly with the existing GlobeCo Portfolio Service architecture.