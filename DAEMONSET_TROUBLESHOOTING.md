# OpenTelemetry Collector DaemonSet Troubleshooting Guide

## Problem Summary
Custom metrics are not flowing from the application to Prometheus when using OpenTelemetry Collector deployed as a DaemonSet with hostport + node-local routing.

## Root Cause Analysis
The application was configured to send metrics to a service endpoint (`otel-collector.monitor.svc.cluster.local:4318`) instead of the node-local collector instance. In a DaemonSet with hostport setup, each application pod should send metrics to its own node's collector instance.

## Solution Implementation

### 1. Updated Application Configuration
The application now uses `NODE_IP` environment variable to route metrics to the local node's collector:

```yaml
# Before (Service-based routing)
- name: OTEL_EXPORTER_OTLP_METRICS_ENDPOINT
  value: "http://otel-collector.monitor.svc.cluster.local:4318/v1/metrics"

# After (Node-local routing)
- name: OTEL_EXPORTER_OTLP_METRICS_ENDPOINT
  value: "http://$(NODE_IP):4318/v1/metrics"
```

### 2. DaemonSet Configuration
Created `k8s/otel-collector-daemonset.yaml` with:
- DaemonSet deployment (one collector per node)
- hostPort configuration for direct node access
- Proper resource limits and health checks

### 3. Deployment Steps

1. **Deploy the DaemonSet collector:**
   ```bash
   ./deploy_daemonset_collector.sh
   ```

2. **Update the application:**
   ```bash
   kubectl apply -f k8s/globeco-portfolio-service.yaml
   ```

3. **Verify the setup:**
   ```bash
   ./check_metrics_flow.sh
   ```

## Verification Commands

### Check DaemonSet Status
```bash
# Check if collector is running on all nodes
kubectl get daemonset otel-collector -n monitor

# Check collector pods
kubectl get pods -n monitor -l app=otel-collector -o wide

# Verify node coverage
echo "Nodes: $(kubectl get nodes --no-headers | wc -l)"
echo "Collector pods: $(kubectl get pods -n monitor -l app=otel-collector --field-selector=status.phase=Running --no-headers | wc -l)"
```

### Test Connectivity
```bash
# Get a test pod and its node
TEST_POD=$(kubectl get pods -n globeco --field-selector=status.phase=Running --no-headers | head -1 | awk '{print $1}')
NODE_NAME=$(kubectl get pod $TEST_POD -n globeco -o jsonpath='{.spec.nodeName}')
NODE_IP=$(kubectl get node $NODE_NAME -o jsonpath='{.status.addresses[?(@.type=="InternalIP")].address}')

# Test connectivity to collector on same node
kubectl exec -n globeco $TEST_POD -- nc -z $NODE_IP 4318  # HTTP
kubectl exec -n globeco $TEST_POD -- nc -z $NODE_IP 4317  # gRPC
kubectl exec -n globeco $TEST_POD -- nc -z $NODE_IP 8889  # Prometheus
```

### Check Metrics Flow
```bash
# Application metrics (should show custom metrics)
kubectl port-forward -n globeco service/globeco-portfolio-service 8000:8000 &
curl http://localhost:8000/metrics | grep -E "(http_request|http_workers)"

# Collector metrics (should show received custom metrics)
COLLECTOR_POD=$(kubectl get pods -n monitor -l app=otel-collector -o name | head -1)
kubectl port-forward -n monitor $COLLECTOR_POD 8889:8889 &
curl http://localhost:8889/metrics | grep -E "(http_request|http_workers)"
```

### Check Logs
```bash
# Application logs (look for OTel export messages)
kubectl logs -n globeco -l app=globeco-portfolio-service --tail=50 | grep -i "otel\|metric"

# Collector logs (look for received metrics)
kubectl logs -n monitor -l app=otel-collector --tail=50 | grep -i "metric"
```

## Expected Behavior

### Application Logs Should Show:
```
[OTel] [HTTP] ResourceMetric[0]: X scope metrics, Resource attrs: {...}
[OTel] [HTTP] Export result: ExportResult.SUCCESS
Sending metrics to OTel collector via LoggingOTLPMetricExporterHTTP exporter
```

### Collector Logs Should Show:
```
2024-XX-XX DEBUG [otlp] Received metrics request
2024-XX-XX DEBUG [prometheus] Exporting metrics
```

### Application /metrics Endpoint Should Include:
```
http_requests_total{method="GET",path="/",status="200",service_namespace="globeco"} 1
http_request_duration_bucket{method="GET",path="/",status="200",service_namespace="globeco",le="5"} 1
http_requests_in_flight{service_namespace="globeco"} 0
http_workers_active{service_namespace="globeco"} 2
```

### Collector /metrics Endpoint Should Include:
```
otel_http_requests_total{method="GET",path="/",status="200",service_namespace="globeco"} 1
otel_http_request_duration_bucket{method="GET",path="/",status="200",service_namespace="globeco",le="5"} 1
```

## Common Issues and Solutions

### Issue: Collector pods not starting
**Symptoms:** DaemonSet shows 0/X ready
**Solutions:**
- Check node selectors and tolerations
- Verify hostPort availability (no conflicts)
- Check resource constraints

### Issue: Application can't connect to collector
**Symptoms:** Connection refused errors in app logs
**Solutions:**
- Verify NODE_IP environment variable is set correctly
- Check if collector pod is running on the same node
- Test connectivity with `nc -z $NODE_IP 4318`

### Issue: Metrics not appearing in collector
**Symptoms:** App exports successfully but collector doesn't receive
**Solutions:**
- Check collector configuration (receivers section)
- Verify network policies don't block traffic
- Check collector logs for parsing errors

### Issue: Standard metrics work but custom metrics don't
**Symptoms:** Built-in metrics appear but custom HTTP metrics missing
**Solutions:**
- Verify OpenTelemetry metrics initialization in app
- Check if middleware is properly registered
- Ensure metrics are being recorded (check app logs)

## Monitoring and Alerting

### Key Metrics to Monitor:
1. **DaemonSet health:** `kube_daemonset_status_number_ready`
2. **Collector connectivity:** Custom probe to each node's 4318 port
3. **Metrics flow rate:** Compare app export rate vs collector receive rate
4. **Custom metrics presence:** Alert if expected metrics disappear

### Recommended Alerts:
```yaml
# DaemonSet not fully deployed
- alert: OTelCollectorDaemonSetNotReady
  expr: kube_daemonset_status_number_ready{daemonset="otel-collector"} < kube_daemonset_status_desired_number_scheduled{daemonset="otel-collector"}

# Custom metrics missing
- alert: CustomMetricsMissing
  expr: absent(http_requests_total{service_namespace="globeco"})
```

## Performance Considerations

### Resource Allocation:
- **CPU:** 100m request, 500m limit per collector pod
- **Memory:** 128Mi request, 512Mi limit per collector pod
- **Network:** Monitor hostPort usage and conflicts

### Scaling Considerations:
- DaemonSet automatically scales with cluster nodes
- Each collector handles metrics from pods on its node only
- No load balancing needed (node-local routing)

## Rollback Plan

If issues persist, rollback to service-based routing:

1. **Revert application config:**
   ```bash
   # Change back to service endpoint
   kubectl patch deployment globeco-portfolio-service -n globeco -p '{"spec":{"template":{"spec":{"containers":[{"name":"globeco-portfolio-service","env":[{"name":"OTEL_EXPORTER_OTLP_METRICS_ENDPOINT","value":"http://otel-collector.monitor.svc.cluster.local:4318/v1/metrics"}]}]}}}}'
   ```

2. **Deploy collector as Deployment:**
   ```bash
   kubectl delete daemonset otel-collector -n monitor
   kubectl apply -f otel-collector.yaml  # Original deployment config
   ```

3. **Verify service-based routing works:**
   ```bash
   ./check_metrics_flow.sh
   ```