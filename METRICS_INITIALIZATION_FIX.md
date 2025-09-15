# OpenTelemetry Metrics Initialization Fix

## Root Cause Identified

The specific metrics (`http_requests_total`, `http_request_duration`, `http_requests_in_flight`) were not appearing in Prometheus because of a **critical initialization order issue**:

1. **OpenTelemetry metrics were being created at module import time** in `app/monitoring.py`
2. **The meter provider was set up later** in `app/main.py`
3. **This meant metrics were created with a default (non-functional) meter provider**
4. **The metrics appeared to work locally but failed to export to the collector**

## The Fix

### 1. Deferred Metrics Initialization

**Before (Broken):**
```python
# In app/monitoring.py - executed at import time
try:
    meter = metrics.get_meter("app.monitoring")  # Uses default meter provider!
    otel_http_requests_total = meter.create_counter(...)
    # ... other metrics
except Exception as e:
    # Creates dummy metrics
```

**After (Fixed):**
```python
# In app/monitoring.py - metrics are None initially
otel_http_requests_total = None
otel_http_request_duration = None
otel_http_requests_in_flight = None

def initialize_otel_metrics():
    """Initialize after meter provider is set up"""
    global otel_http_requests_total, otel_http_request_duration, otel_http_requests_in_flight
    
    meter = metrics.get_meter("app.monitoring")  # Uses proper meter provider!
    otel_http_requests_total = meter.create_counter(...)
    # ... other metrics
```

### 2. Proper Initialization Order

**In app/main.py:**
```python
# Set up meter provider first
meter_provider = MeterProvider(resource=resource, metric_readers=[metric_reader])
set_meter_provider(meter_provider)

# THEN initialize OpenTelemetry metrics
from app.monitoring import initialize_otel_metrics
otel_metrics_initialized = initialize_otel_metrics()
```

### 3. Safe Metric Recording

**Updated middleware to handle None metrics:**
```python
# Before: Would fail if metrics were None
otel_http_requests_total.add(1, attributes=otel_attributes)

# After: Safe handling
if otel_http_requests_total is not None:
    otel_http_requests_total.add(1, attributes=otel_attributes)
```

### 4. Fixed Duplicate Recording Bug

**Removed duplicate counter recording in `_record_metrics()` method:**
- Was calling `otel_http_requests_total.add()` twice
- This could cause double-counting of requests

## Why This Fixes the Issue

1. **Proper Meter Provider**: Metrics are now created with the correctly configured meter provider that exports to the collector
2. **No More Dummy Metrics**: The initialization order ensures real metrics are created, not dummy fallbacks  
3. **Consistent Export**: All metrics now use the same properly configured export pipeline
4. **No Conflicts**: Eliminated the duplicate recording that could cause inconsistencies

## Expected Results After Fix

✅ **Metrics in /metrics endpoint**: Prometheus client metrics still work  
✅ **Metrics in collector**: OpenTelemetry metrics properly exported  
✅ **Metrics in Prometheus**: Both sources appear correctly  
✅ **No otel_ prefix**: Collector configured to export with original names  
✅ **Consistent counts**: No more duplicate recording  

## Verification Steps

1. **Deploy the fix**: `./deploy_metrics_fix.sh`
2. **Check logs**: Look for "OpenTelemetry metrics initialization completed: success=True"
3. **Test metrics flow**: `./test_otel_only_metrics.sh`
4. **Query Prometheus**: Look for `http_requests_total{service_namespace="globeco"}`

## Why Other Services Work

Other microservices likely:
- Use only Prometheus client metrics (direct scraping)
- Use only OpenTelemetry metrics (proper initialization)
- Have different initialization patterns that avoid this race condition

This service was unique in having both systems with the specific initialization order problem.

## Key Insight

**The issue wasn't network connectivity, collector configuration, or Prometheus scraping.** It was a fundamental initialization race condition where metrics were created before the proper meter provider was available, causing them to use a non-functional default provider that couldn't export to the collector.

This fix ensures the OpenTelemetry metrics are created with the proper meter provider and export pipeline, allowing them to reach Prometheus through the collector as intended.