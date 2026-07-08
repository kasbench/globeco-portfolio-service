#!/bin/bash

# Deploy enhanced logging version to debug OpenTelemetry metrics issue
# This adds extensive logging to see exactly what's happening in the middleware

set -e

echo "🔧 Deploying enhanced logging version for debugging..."

# Build the new image
echo "📦 Building Docker image with enhanced logging..."
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
echo "🔍 Enhanced logging added:"
echo "1. Middleware dispatch logging (always on)"
echo "2. Metrics recording logging (always on)"
echo "3. OpenTelemetry metric state logging (always on)"
echo "4. Detailed error and warning messages"
echo "5. Meter provider debugging and comparison"

echo ""
echo "🔍 To test and see logs:"
echo "1. Make HTTP requests: curl http://localhost:8000/"
echo "2. Check logs: kubectl logs -n globeco -l app=globeco-portfolio-service --tail=50"
echo "3. Look for 'Current meter provider before custom metrics initialization' messages"
echo "4. Look for 'Getting meter from current meter provider' messages"
echo "5. Look for 'Successfully created OpenTelemetry HTTP and thread metrics' messages"
echo "6. Check if meter provider IDs match between configured and current"