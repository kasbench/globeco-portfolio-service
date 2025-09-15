#!/bin/bash

# Deploy the attribute format fix for OpenTelemetry metrics
# This changes custom metrics to use the same attribute format as FastAPI instrumentation

set -e

echo "🔧 Deploying OpenTelemetry attribute format fix..."

# Build the new image
echo "📦 Building Docker image with attribute fix..."
docker build -t kasbench/globeco-portfolio-service:latest .

# Push to registry
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
echo "🔍 Key changes applied:"
echo "1. Changed attribute names to match FastAPI instrumentation:"
echo "   - method -> http_method"
echo "   - path -> http_target" 
echo "   - status -> http_status_code"
echo "2. Removed service_name attribute (comes from resource)"
echo "3. Simplified in-flight gauge attributes"

echo ""
echo "🔍 To verify the fix:"
echo "1. Wait 10-15 seconds for metrics export"
echo "2. Check collector: curl \"http://localhost:8889/metrics\" | grep \"app\\.monitoring\""
echo "3. Look for custom metrics with http_method, http_target attributes"
echo "4. Compare with FastAPI metrics format"

echo ""
echo "📋 If this works, you should see:"
echo "- http_requests_total{...http_method=\"GET\",http_target=\"/\"...}"
echo "- http_request_duration_bucket{...http_method=\"GET\",http_target=\"/\"...}"