#!/bin/bash

echo "🚀 Deploying OpenTelemetry Collector as DaemonSet"
echo "================================================="

# Check if kubectl is available
if ! command -v kubectl &> /dev/null; then
    echo "❌ kubectl not found. Please install kubectl first."
    exit 1
fi

# Create monitor namespace if it doesn't exist
echo "📦 Ensuring monitor namespace exists..."
kubectl create namespace monitor --dry-run=client -o yaml | kubectl apply -f -

# Apply the collector configuration
echo "⚙️  Applying OpenTelemetry Collector configuration..."
kubectl apply -f otel-collector-config.yaml

# Remove existing deployment if it exists
echo "🧹 Removing existing collector deployment (if any)..."
kubectl delete deployment otel-collector -n monitor --ignore-not-found=true

# Apply the daemonset
echo "🔄 Deploying OpenTelemetry Collector as DaemonSet..."
kubectl apply -f k8s/otel-collector-daemonset.yaml

# Wait for daemonset to be ready
echo "⏳ Waiting for DaemonSet to be ready..."
kubectl rollout status daemonset/otel-collector -n monitor --timeout=120s

# Check daemonset status
echo ""
echo "📊 DaemonSet Status:"
kubectl get daemonset otel-collector -n monitor -o wide

echo ""
echo "📦 Collector Pods:"
kubectl get pods -n monitor -l app=otel-collector -o wide

# Check if pods are running on all nodes
echo ""
echo "🏗️  Node Coverage:"
echo "Nodes in cluster:"
kubectl get nodes --no-headers | wc -l | xargs echo "  Total nodes:"
echo "Collector pods running:"
kubectl get pods -n monitor -l app=otel-collector --field-selector=status.phase=Running --no-headers | wc -l | xargs echo "  Running pods:"

# Test connectivity from a pod
echo ""
echo "🔗 Testing Connectivity:"
echo "Getting a test pod to verify collector connectivity..."

# Find a running pod in the globeco namespace
TEST_POD=$(kubectl get pods -n globeco --field-selector=status.phase=Running --no-headers | head -1 | awk '{print $1}')

if [ -n "$TEST_POD" ]; then
    echo "Using test pod: $TEST_POD"
    
    # Get the node IP where the test pod is running
    NODE_NAME=$(kubectl get pod $TEST_POD -n globeco -o jsonpath='{.spec.nodeName}')
    NODE_IP=$(kubectl get node $NODE_NAME -o jsonpath='{.status.addresses[?(@.type=="InternalIP")].address}')
    
    echo "Test pod is on node: $NODE_NAME ($NODE_IP)"
    
    # Test connectivity to collector on the same node
    echo "Testing OTLP HTTP connectivity..."
    kubectl exec -n globeco $TEST_POD -- nc -z $NODE_IP 4318 && echo "✅ OTLP HTTP (4318) - Connected" || echo "❌ OTLP HTTP (4318) - Failed"
    
    echo "Testing OTLP gRPC connectivity..."
    kubectl exec -n globeco $TEST_POD -- nc -z $NODE_IP 4317 && echo "✅ OTLP gRPC (4317) - Connected" || echo "❌ OTLP gRPC (4317) - Failed"
    
    echo "Testing Prometheus endpoint..."
    kubectl exec -n globeco $TEST_POD -- nc -z $NODE_IP 8889 && echo "✅ Prometheus (8889) - Connected" || echo "❌ Prometheus (8889) - Failed"
else
    echo "⚠️  No running pods found in globeco namespace for connectivity testing"
fi

echo ""
echo "🎯 Next Steps:"
echo "1. Deploy the updated portfolio service configuration:"
echo "   kubectl apply -f k8s/globeco-portfolio-service.yaml"
echo ""
echo "2. Check collector logs:"
echo "   kubectl logs -n monitor -l app=otel-collector -f"
echo ""
echo "3. Verify metrics are flowing:"
echo "   ./check_metrics_flow.sh"
echo ""
echo "4. Test metrics endpoints:"
echo "   # Application metrics:"
echo "   kubectl port-forward -n globeco service/globeco-portfolio-service 8000:8000"
echo "   curl http://localhost:8000/metrics | grep http_request"
echo ""
echo "   # Collector metrics (pick any node):"
echo "   kubectl port-forward -n monitor \$(kubectl get pods -n monitor -l app=otel-collector -o name | head -1) 8889:8889"
echo "   curl http://localhost:8889/metrics | grep http_request"

echo ""
echo "✅ DaemonSet deployment complete!"