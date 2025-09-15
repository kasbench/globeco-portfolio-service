# Dynamic OpenTelemetry Metrics Access Fix

## Root Cause Analysis

The issue was identified as a **module-level import timing problem**:

1. **Middleware imports OpenTelemetry metrics at module load time** - gets `None` references
2. **Metrics are initialized later** in `main.py` after meter provider setup  
3. **Middleware keeps stale `None` references** even after initialization
4. **Result**: Prometheus metrics work (direct object access) but OpenTelemetry metrics are never recorded

## The Problem in Detail

**Before Fix:**
```python
# At module level in monitoring.py
otel_http_requests_total = None  # Initially None

def initialize_otel_metrics():
    global otel_http_requests_total
    otel_http_requests_total = meter.create_counter(...)  # Updates global

# In middleware class
class EnhancedHTTPMetricsMiddleware:
    def _record_metrics(self, ...):
        # This uses the None reference captured at import time!
        if otel_http_requests_total is not None:  # Always None!
            otel_http_requests_total.add(1, ...)
```

**The middleware was checking a stale `None` reference that never got updated.**

## The Fix

**Dynamic Module Access:**
```python
# In middleware class  
class EnhancedHTTPMetricsMiddleware:
    def _record_metrics(self, ...):
        # Import dynamically to get current values after initialization
        import app.monitoring as monitoring_module
        current_otel_counter = getattr(monitoring_module, 'otel_http_requests_total', None)
        
        if current_otel_counter is not None:  # Now gets the real metric!
            current_otel_counter.add(1, attributes=otel_attributes)
```

## Additional Improvements

1. **Reduced Export Interval**: From 10 seconds to 5 seconds for faster testing
2. **Enhanced Logging**: Added detailed export configuration logging
3. **Better Error Handling**: More specific error messages and debugging info
4. **Increased Export Timeout**: From 5 seconds to 10 seconds for reliability

## Expected Results

After this fix:

✅ **OpenTelemetry metrics will be recorded** when HTTP requests are made  
✅ **Metrics will be exported** to the collector every 5 seconds  
✅ **Debug logs will show** "Successfully recorded OpenTelemetry..." messages  
✅ **Collector will receive** the metrics and export to Prometheus  
✅ **Prometheus will show** metrics with `service_namespace="globeco"`  

## Verification Steps

1. **Deploy the fix**: `./deploy_dynamic_metrics_fix.sh`
2. **Check logs**: `kubectl logs -n globeco -l app=globeco-portfolio-service | grep -i otel`
3. **Make HTTP requests**: Trigger the middleware by accessing endpoints
4. **Wait 5-10 seconds**: For export cycle to complete
5. **Check collector**: `curl http://localhost:8889/metrics | grep globeco-portfolio-service`
6. **Check Prometheus**: Query for `http_requests_total{service_namespace="globeco"}`

## Why This Wasn't Caught Earlier

- **Initialization logs looked correct** - metrics were being created successfully
- **Prometheus metrics worked** - suggested middleware was functioning
- **No obvious errors** - the `None` check prevented exceptions
- **Subtle timing issue** - only affected OpenTelemetry, not Prometheus metrics

## Key Insight

**The issue wasn't with export configuration, collector connectivity, or metric creation.** It was a fundamental Python module import timing issue where the middleware was holding stale references to `None` values that were updated after the middleware class was instantiated.

This fix ensures the middleware always gets the current, initialized OpenTelemetry metrics by accessing them dynamically rather than holding stale references.