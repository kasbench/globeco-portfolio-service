# Final Troubleshooting Steps for Custom Metrics

## Current Status
- Reverted to working Prometheus client metrics (visible on `/metrics` endpoint)
- Simplified OpenTelemetry configuration to use standard exporter
- Both systems should now coexist without conflicts

## Key Changes Made

1. **Restored Prometheus Client Metrics**: Your `/metrics` endpoint should work again
2. **Simplified OpenTelemetry Export**: Removed custom logging exporters that might cause issues
3. **Kept Same Metric Names**: Both systems use identical names (this should work)

## Diagnostic Steps

### Step 1: Verify App Metrics
```bash
curl http://localhost:8000/metrics | grep -E "http_requests_total|http_request_duration"
```
You should see metrics like:
```
http_requests_total{service_namespace="globeco",method="GET",path="/",status="200"} 123
```

### Step 2: Test OpenTelemetry Export
```bash
python3 test_otel_metrics_simple.py
```
This creates a minimal test to verify OpenTelemetry export is working.

### Step 3: Debug Full Flow
```bash
python3 debug_metrics_export.py
```
This checks the complete flow from app → collector → Prometheus.

### Step 4: Check Collector Metrics
```bash
curl http://localhost:8889/metrics | grep -E "http_requests_total.*service_namespace.*globeco"
```
You should see metrics from your service in the collector output.

## Expected Results

After rebuilding and deploying:

1. **App `/metrics` endpoint**: Shows Prometheus client metrics with `service_namespace="globeco"`
2. **Collector `/metrics` endpoint**: Shows the same metrics received via OpenTelemetry
3. **Prometheus**: Shows metrics scraped from collector

## Most Likely Issues

### Issue 1: OpenTelemetry Export Not Working
**Symptoms**: Metrics visible in app `/metrics` but not in collector
**Check**: 
- App logs for OpenTelemetry export errors
- `OTEL_EXPORTER_OTLP_METRICS_ENDPOINT` environment variable
- Network connectivity to collector

### Issue 2: Collector Not Processing Metrics
**Symptoms**: Collector receiving metrics but not exporting them
**Check**:
- Collector logs for processing errors
- Collector configuration for metrics pipeline
- Resource attribute processing

### Issue 3: Prometheus Not Scraping Collector
**Symptoms**: Metrics in collector but not in Prometheus
**Check**:
- Prometheus configuration for collector scrape target
- Collector port 8889 accessibility
- Prometheus target health status

## Key Environment Variables

Verify these are set correctly in your deployment:

```yaml
- name: OTEL_EXPORTER_OTLP_METRICS_ENDPOINT
  value: "http://$(NODE_IP):4318/v1/metrics"
- name: OTEL_METRICS_LOGGING_ENABLED
  value: "true"
- name: ENABLE_METRICS
  value: "true"
```

## Success Criteria

✅ **App metrics working**: `curl http://localhost:8000/metrics` shows custom metrics
✅ **OpenTelemetry export working**: Collector receives metrics from your service
✅ **Prometheus scraping working**: Metrics appear in Prometheus queries
✅ **No otel_ prefix**: Metrics have original names for Grafana compatibility

## If Still Not Working

The issue is likely one of these:

1. **Resource Attributes**: OpenTelemetry metrics need proper resource attributes
2. **Export Timing**: Metrics export interval might be too long
3. **Collector Configuration**: Your production collector might have different processing rules
4. **Network Issues**: Connectivity between app and collector

Run the diagnostic scripts to identify which component is failing.