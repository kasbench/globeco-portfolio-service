#!/bin/bash

# Deploy the metrics initialization fix
# This script rebuilds and redeploys the service with the corrected OpenTelemetry metrics initialization

set -e

echo "🔧 Deploying OpenTelemetry metrics initialization fix..."

# Build the new image
echo "📦 Building Docker image with metrics fix..."
docker build -t kasbench/globeco-portfolio-service:latest .

# Push to registry (if needed)
echo "📤 Pushing image to registry..."
docker push kasbench/globeco-portfolio-service:latest

# Restart the deployment to pick up the new image
echo "🔄 Restarting deployment..."
kubectl rollout restart deployment/globeco-portfolio-service -n globeco

# Wait for rollout to complete
echo "⏳ Waiting for rollout to complete..."
kubectl rollout status deployment/globeco-portfolio-service -n globeco --timeout=300s

echo "✅ Deployment complete!"

# Show pod status
echo "📊 Current pod status:"
kubectl get pods -n globeco -l app=globeco-portfolio-service

echo ""
echo "🔍 To verify the fix:"
echo "1. Check pod logs: kubectl logs -n globeco -l app=globeco-portfolio-service --tail=50"
echo "2. Look for 'OpenTelemetry metrics initialization completed' message"
echo "3. Test metrics flow: ./test_otel_only_metrics.sh"
echo "4. Check Prometheus for metrics without otel_ prefix"