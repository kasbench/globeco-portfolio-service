#!/bin/bash

echo "🚀 Deploying ULTRA Performance Mode..."
echo "This will completely remove all monitoring overhead"
echo "=" * 60

# Enable performance mode locally
python enable_performance_mode.py

# Build new Docker image with performance optimizations
echo "🐳 Building performance-optimized Docker image..."
docker build -t globeco-portfolio-service:performance .

# Tag for your registry (adjust as needed)
docker tag globeco-portfolio-service:performance your-registry/globeco-portfolio-service:performance

echo "📤 Push to registry:"
echo "  docker push your-registry/globeco-portfolio-service:performance"
echo ""
echo "🔧 Update Kubernetes deployment:"
echo "  kubectl set image deployment/globeco-portfolio-service globeco-portfolio-service=your-registry/globeco-portfolio-service:performance -n globeco"
echo ""
echo "⚡ Or apply the performance patch directly:"

# Create a performance patch
cat << EOF > performance-patch.yaml
spec:
  template:
    spec:
      containers:
      - name: globeco-portfolio-service
        env:
        - name: LOG_LEVEL
          value: "ERROR"
        - name: ENABLE_METRICS
          value: "false"
        - name: ENABLE_THREAD_METRICS
          value: "false"
        - name: OTEL_METRICS_LOGGING_ENABLED
          value: "false"
        resources:
          requests:
            memory: "128Mi"
            cpu: "100m"
          limits:
            memory: "512Mi"
            cpu: "500m"
EOF

echo "kubectl patch deployment globeco-portfolio-service -n globeco --patch-file performance-patch.yaml"

echo ""
echo "🧪 Test performance with:"
echo "  python test_performance_breakdown.py"