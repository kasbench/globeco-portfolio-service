#!/bin/bash

# Deploy the dynamic metrics access fix
# This script applies the fix for OpenTelemetry metrics not being exported

set -e

echo "🔧 Deploying dynamic OpenTelemetry metrics access fix..."

# Build the new image
echo "📦 Building Docker image with dynamic metrics fix..."
docker build -t kasbench/globeco-portfolio-service:latest .

# Push to registry
echo "📤 Pushing image to registry..."
docker push kasbench/globeco-portfolio-service:latest

# Apply the updated deployment configuration (with reduced export interval)
echo "🔄 Applying updated deployment configuration..."
kubectl apply -f k8s/globeco-portfolio-service.yaml

# Restart the deployment to pick up the new image and config
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
echo "🔍 Key changes applied:"
echo "1. Dynamic OpenTelemetry metrics access in middleware"
echo "2. Reduced export interval from 10s to 5s"
echo "3. Enhanced export logging and error handling"
echo "4. Fixed potential import timing issues"

echo ""
echo "🔍 To verify the fix:"
echo "1. Check pod logs: kubectl logs -n globeco -l app=globeco-portfolio-service --tail=100"
echo "2. Look for 'Successfully recorded OpenTelemetry' messages"
echo "3. Make some HTTP requests to trigger metrics"
echo "4. Wait 5-10 seconds and check collector metrics"
echo "5. Check Prometheus for metrics with service_namespace=\"globeco\""

echo ""
echo "📋 Troubleshooting commands:"
echo "kubectl logs -n globeco -l app=globeco-portfolio-service | grep -i otel"
echo "curl http://localhost:8889/metrics | grep globeco-portfolio-service | grep http_request"