# Custom Metrics Troubleshooting Guide

## Problem
Custom metrics are visible on the `/metrics` endpoint but not appearing in Prometheus through the OpenTelemetry collector.

## Root Cause Analysis

Based on the code analysis, here are the most likely causes:

### 1. Metric Name Conflicts
**Issue**: Your application creates both Prometheus metrics (for `/metrics` endpoint) and OpenTelemetry metrics (for collector export) with identical names.

**Evidence**: 
- Prometheus metrics: `http_requests_total`, `http_request_duration`, etc.
- OpenTelemetry metrics: Same names in `app/monitoring.py`

**Impact**: This can cause conflicts when the collector exports to Prometheus.

### 2. Missing Resource Attributes
**Issue**: OpenTelemetry metrics might not have proper resource attributes that Prometheus expects.

**Evidence**: The collector config was missing a resource processor.

### 3. Export Configuration Issues
**Issue**: The metrics export configuration might have timing or endpoint issues.

**Evidence**: Custom logging exporters and complex middleware setup.

## Solutions

### Solution 1: Fix Collector Configuration (RECOMMENDED)

I've updated your `otel-collector-config.yaml` to include a resource processor:

```yaml
processors:
  batch:
    timeout: 1s
    send_batch_size: 1024
  memory_limiter:
    limit_mib: 512
  resource:
    attributes:
      - key: service.namespace
        value: "globeco"
        action: upsert
      - key: deployment.environment
        value: "production"
        action: upsert

service:
  pipelines:
    metrics:
      receivers: [otlp]
      processors: [memory_limiter, resource, batch]
      exporters: [prometheus, debug]
```

### Solution 2: Verify Prometheus Scraping

Your custom metrics should appear in Prometheus with the `otel_` prefix due to the collector's namespace configuration:

- `otel_http_requests_total`
- `otel_http_request_duration`
- `otel_http_requests_in_flight`

## Diagnostic Steps

### Step 1: Test Metrics Export
```bash
python3 test_simple_otel_export.py
```

This will create test metrics and verify the export pipeline is working.

### Step 2: Check Metrics Flow
```bash
python3 test_metrics_flow.py [APP_URL] [COLLECTOR_URL]
```

Example:
```bash
python3 test_metrics_flow.py http://localhost:8000 http://localhost:8889
```

### Step 3: Check Prometheus Configuration
```bash
python3 check_prometheus_config.py [PROMETHEUS_URL]
```

Example:
```bash
python3 check_prometheus_config.py http://localhost:9090
```

## Expected Results

After applying the fixes:

1. **In Prometheus**: Look for metrics with `otel_` prefix:
   - `otel_http_requests_total{service_namespace="globeco",...}`
   - `otel_http_request_duration_bucket{service_namespace="globeco",...}`

2. **In Collector logs**: You should see debug output showing metrics being received and exported.

3. **In Application logs**: With `OTEL_METRICS_LOGGING_ENABLED=true`, you should see export confirmations.

## Common Issues and Fixes

### Issue: "No custom metrics in Prometheus"
**Check**: 
- Prometheus is scraping the collector on port 8889
- Collector is receiving metrics from the application
- Resource attributes are being added correctly

### Issue: "Collector not receiving metrics"
**Check**:
- `OTEL_EXPORTER_OTLP_METRICS_ENDPOINT` is correct
- Network connectivity between app and collector
- Collector is listening on the correct ports (4317/4318)

### Issue: "Metrics have wrong labels"
**Check**:
- Resource processor is adding required attributes
- Application is setting correct attributes when recording metrics

## Verification Commands

### Check collector is receiving metrics:
```bash
kubectl logs -n monitor daemonset/otel-collector | grep -i metric
```

### Check Prometheus targets:
```bash
curl http://localhost:9090/api/v1/targets | jq '.data.activeTargets[] | select(.labels.job | contains("otel"))'
```

### Query specific metrics in Prometheus:
```bash
curl 'http://localhost:9090/api/v1/query?query=otel_http_requests_total'
```

## Next Steps

1. **Deploy the updated collector configuration**
2. **Restart the collector daemonset**
3. **Run the diagnostic scripts**
4. **Check Prometheus for `otel_*` metrics**
5. **Verify metrics have the expected labels**

The key insight is that your custom metrics should appear in Prometheus with the `otel_` prefix, not with the original names. This is because the collector's Prometheus exporter is configured with `namespace: "otel"`.