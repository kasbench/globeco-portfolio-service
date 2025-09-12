#!/bin/bash

# Deploy the OpenTelemetry-only metrics configuration
# This removes Prometheus client metrics conflicts and ensures clean metric export

set -e

echo "🚀 Deploying OpenTelemetry-only metrics configuration..."
echo "======================================================="

# Step 1: Update collector configuration
echo "📝 Step 1: Updating collector configuration..."
kubectl apply -f otel-collector-config.yaml
echo "✅ Collector ConfigMap updated"

# Step 2: Restart collector to pick up new config
echo "🔄 Step 2: Restarting collector daemonset..."
kubectl rollout restart daemonset/otel-collector -n monitor
kubectl rollout status daemonset/otel-collector -n monitor --timeout=120s
echo "✅ Collector restarted"

# Step 3: Rebuild and redeploy application (user needs to do this)
echo "🏗️  Step 3: Application deployment needed..."
echo "   Please rebuild and redeploy your application with the updated code"
echo "   The key changes:"
echo "   - Disabled Prometheus client metrics to avoid conflicts"
echo "   - Only OpenTelemetry metrics will be exported"
echo "   - Collector configured to export without otel_ prefix"

echo ""
echo "⏳ Waiting for collector to be ready..."
sleep 10

# Step 4: Check collector status
echo "✅ Step 4: Checking collector status..."
kubectl get pods -n monitor -l app=otel-collector

echo ""
echo "🎉 Configuration deployed successfully!"
echo ""
echo "📋 Next steps:"
echo "1. Rebuild and redeploy your application"
echo "2. Wait 30 seconds for metrics to flow"
echo "3. Run: ./test_otel_only_metrics.sh"
echo "4. Check Prometheus for metrics WITHOUT otel_ prefix"
echo "5. Look for: http_requests_total{service_namespace=\"globeco\"}"
echo ""
echo "🔍 To monitor progress:"
echo "- Collector logs: kubectl logs -n monitor daemonset/otel-collector -f"
echo "- Collector metrics: curl http://localhost:8889/metrics | grep http_requests"
echo ""
echo "⚠️  Important: The /metrics endpoint is now disabled to prevent conflicts"
echo "   All metrics will be available through the OpenTelemetry collector only"