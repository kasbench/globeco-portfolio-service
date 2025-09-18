#!/bin/bash

echo "🚀 Deploying performance-optimized portfolio service..."

# Set performance-optimized environment variables
export ENABLE_METRICS=false
export METRICS_DEBUG_LOGGING=false
export ENABLE_THREAD_METRICS=false
export THREAD_METRICS_DEBUG_LOGGING=false
export OTEL_METRICS_LOGGING_ENABLED=false
export LOG_LEVEL=WARNING

echo "✅ Performance optimizations enabled:"
echo "  - Metrics collection: DISABLED"
echo "  - Thread metrics: DISABLED" 
echo "  - Debug logging: DISABLED"
echo "  - Log level: WARNING"

# Update Kubernetes deployment with performance settings
kubectl patch deployment globeco-portfolio-service -n globeco --type='merge' -p='{
  "spec": {
    "template": {
      "spec": {
        "containers": [{
          "name": "globeco-portfolio-service",
          "env": [
            {"name": "ENABLE_METRICS", "value": "false"},
            {"name": "METRICS_DEBUG_LOGGING", "value": "false"},
            {"name": "ENABLE_THREAD_METRICS", "value": "false"},
            {"name": "THREAD_METRICS_DEBUG_LOGGING", "value": "false"},
            {"name": "OTEL_METRICS_LOGGING_ENABLED", "value": "false"},
            {"name": "LOG_LEVEL", "value": "WARNING"}
          ]
        }]
      }
    }
  }
}'

echo "🔄 Waiting for deployment to roll out..."
kubectl rollout status deployment/globeco-portfolio-service -n globeco --timeout=300s

if [ $? -eq 0 ]; then
    echo "✅ Performance-optimized deployment completed successfully!"
    echo ""
    echo "🧪 Test the performance with:"
    echo "  python test_performance_breakdown.py"
    echo ""
    echo "📊 Monitor the logs with:"
    echo "  kubectl logs -f deployment/globeco-portfolio-service -n globeco"
else
    echo "❌ Deployment failed!"
    exit 1
fi