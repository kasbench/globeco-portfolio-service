#!/bin/bash

# Script to apply the updated collector configuration and restart the daemonset

set -e

echo "🔧 Applying updated OpenTelemetry collector configuration..."

# Apply the updated ConfigMap
echo "📝 Updating collector ConfigMap..."
kubectl apply -f otel-collector-config.yaml

# Restart the collector daemonset to pick up the new configuration
echo "🔄 Restarting collector daemonset..."
kubectl rollout restart daemonset/otel-collector -n monitor

# Wait for rollout to complete
echo "⏳ Waiting for rollout to complete..."
kubectl rollout status daemonset/otel-collector -n monitor --timeout=120s

# Check collector pods are running
echo "✅ Checking collector pod status..."
kubectl get pods -n monitor -l app=otel-collector

echo ""
echo "🎉 Collector configuration updated successfully!"
echo ""
echo "📋 Next steps:"
echo "1. Wait 30 seconds for metrics to start flowing"
echo "2. Run: python3 test_metrics_flow.py"
echo "3. Check Prometheus for otel_* metrics"
echo "4. Look for metrics like: otel_http_requests_total{service_namespace=\"globeco\"}"
echo ""
echo "🔍 To check collector logs:"
echo "kubectl logs -n monitor daemonset/otel-collector -f"