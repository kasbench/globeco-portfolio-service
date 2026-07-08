# Root Cause: OpenTelemetry Semantic Conventions Mismatch

## The Real Issue

The problem was **attribute naming inconsistency** between your custom metrics and OpenTelemetry semantic conventions.

### What Was Happening

1. **FastAPI Instrumentation**: Creates automatic metrics using standard OpenTelemetry semantic conventions:
   - `http.method` instead of `method`
   - `http.route` instead of `path` 
   - `http.status_code` instead of `status`
   - `service.namespace` instead of `service_namespace`

2. **Your Custom Metrics**: Were using non-standard attribute names:
   - `method`, `path`, `status`, `service_namespace`

3. **Collector Processing**: The OpenTelemetry collector likely filters or processes metrics differently based on semantic conventions, causing your custom metrics to be dropped or not properly exported.

## The Fix

Changed all custom metric attributes to use OpenTelemetry semantic conventions:

### Before:
```python
otel_attributes = {
    "method": method,
    "path": path, 
    "status": status,
    "service_namespace": settings.service_namespace
}
```

### After:
```python
otel_attributes = {
    "http.method": method,
    "http.route": path,
    "http.status_code": status,
    "service.namespace": settings.service_namespace,
    "service.name": "globeco-portfolio-service"
}
```

## Why This Matters

1. **Collector Processing**: OpenTelemetry collectors are optimized to handle standard semantic conventions
2. **Metric Correlation**: Standard attributes allow proper correlation with automatic instrumentation metrics
3. **Export Consistency**: Ensures all metrics follow the same attribute naming patterns

## Expected Results

After this fix, your custom metrics should:

✅ **Appear in Prometheus** with proper attribute names
✅ **Correlate with automatic metrics** from FastAPI instrumentation  
✅ **Follow OpenTelemetry standards** for better compatibility
✅ **Export consistently** through the collector

## Verification

Look for these metrics in Prometheus:
- `http_requests_total{service.namespace="globeco",http.method="GET",...}`
- `http_request_duration_bucket{service.namespace="globeco",http.method="GET",...}`
- `http_requests_in_flight{service.namespace="globeco",...}`

Note the attribute names now use dots (`.`) instead of underscores (`_`) following OpenTelemetry semantic conventions.

## Why Standard Metrics Worked

The automatic FastAPI instrumentation was already using correct semantic conventions, so those metrics flowed through properly. Your custom metrics were using non-standard attribute names, causing them to be processed differently or dropped by the collector.

This is a subtle but critical difference that explains why some metrics worked while others didn't.