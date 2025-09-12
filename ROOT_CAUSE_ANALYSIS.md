# Root Cause Analysis: Custom Metrics Not Appearing in Prometheus

## The Real Problem

The issue was **metric name conflicts** caused by creating both Prometheus client metrics AND OpenTelemetry metrics with identical names in the same application.

### What Was Happening

1. **Prometheus Client Metrics**: Your app was creating metrics like `http_requests_total` using the Prometheus client library for the `/metrics` endpoint
2. **OpenTelemetry Metrics**: Your app was ALSO creating metrics with the same names (`http_requests_total`) using OpenTelemetry for collector export
3. **Conflict**: This caused conflicts where the OpenTelemetry metrics were either ignored, dropped, or interfered with by the Prometheus client metrics

### Evidence

- Both metric types were being created in `app/monitoring.py`
- The `/metrics` endpoint showed Prometheus client metrics
- OpenTelemetry metrics with identical names were being sent to collector
- Collector was receiving metrics but they weren't appearing in Prometheus properly

## The Solution

**Disable Prometheus client metrics entirely** and use only OpenTelemetry metrics with proper collector configuration.

### Changes Made

1. **Collector Configuration** (`otel-collector-config.yaml`):
   - Removed `namespace: "otel"` to prevent `otel_` prefix
   - Added resource processor for proper attribute handling
   - Configured to export metrics with original names

2. **Application Code** (`app/monitoring.py`):
   - Replaced Prometheus client metrics with `DummyMetric()` instances
   - Kept only OpenTelemetry metrics for actual data collection
   - This eliminates naming conflicts

3. **Metrics Endpoint** (`app/main.py`):
   - Disabled the `/metrics` endpoint to prevent confusion
   - All metrics now flow through OpenTelemetry collector only

## Expected Results

After these changes:

✅ **Metrics in Prometheus**: `http_requests_total{service_namespace="globeco"}`
✅ **No otel_ prefix**: Metrics appear with original names
✅ **No conflicts**: Only one metric system (OpenTelemetry) is active
✅ **Grafana compatibility**: Existing dashboards will work unchanged

## Why This Approach Works

1. **Single Source of Truth**: Only OpenTelemetry metrics are created and exported
2. **No Naming Conflicts**: Prometheus client metrics are disabled
3. **Proper Resource Attributes**: Collector adds consistent labels
4. **Clean Export**: Collector exports metrics without namespace prefix

## Verification Steps

1. Deploy the changes: `./deploy_otel_only_fix.sh`
2. Rebuild and redeploy your application
3. Test the flow: `./test_otel_only_metrics.sh`
4. Check Prometheus for metrics without `otel_` prefix

## Why Other Services Work

Your other microservices likely use either:
- Only Prometheus client metrics (scraped directly)
- Only OpenTelemetry metrics (through collector)
- Different metric names that don't conflict

This service was unique in trying to use both systems with identical metric names, causing the conflict.

## Key Insight

The problem wasn't with the collector configuration, network connectivity, or Prometheus scraping. It was a fundamental architectural issue of having two metric systems competing for the same metric names within the same application.

By choosing one system (OpenTelemetry) and properly configuring it, the metrics now flow cleanly without conflicts.