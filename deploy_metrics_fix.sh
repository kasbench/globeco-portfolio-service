#!/bin/bash

# Deploy Python runtime metrics enhancement
# This script adds Python runtime metrics (equivalent to Prometheus python_* metrics)

set -e

echo "🔧 Deploying Python runtime metrics enhancement..."

# Build and push the updated image
echo "📦 Building updated Docker image..."
docker build -t kasbench/globeco-portfolio-service:latest .

echo "🚀 Pushing image to registry..."
docker push kasbench/globeco-portfolio-service:latest

# Apply the deployment
echo "🎯 Applying Kubernetes deployment..."
kubectl apply -f k8s/globeco-portfolio-service.yaml

# Wait for rollout to complete
echo "⏳ Waiting for deployment rollout..."
kubectl rollout status deployment/globeco-portfolio-service -n globeco --timeout=300s

# Check pod status
echo "📊 Checking pod status..."
kubectl get pods -n globeco -l app=globeco-portfolio-service

echo "✅ Deployment completed successfully!"

# Show recent logs to verify the fix
echo "📋 Recent logs (last 50 lines):"
kubectl logs -n globeco -l app=globeco-portfolio-service --tail=50

echo ""
echo "🔍 To monitor metrics, check:"
echo "1. Pod logs: kubectl logs -n globeco -l app=globeco-portfolio-service -f"
echo "2. Prometheus metrics: Check for these metrics:"
echo "   - otel_http_* (HTTP request metrics)"
echo "   - python_* (Python runtime info)"
echo "   - process_* (Process metrics)"
echo "   - python_gc_* (Garbage collection)"
echo "   - python_threads (Thread count)"
echo "3. Service health: curl http://service-ip:8000/health"