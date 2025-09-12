#!/bin/bash

echo "🔍 OpenTelemetry Metrics Flow Diagnostic"
echo "========================================"

# Check if kubectl is available
if ! command -v kubectl &> /dev/null; then
    echo "❌ kubectl not found. Please install kubectl to run this diagnostic."
    exit 1
fi

# Function to check if a pod is running
check_pod_status() {
    local namespace=$1
    local app_label=$2
    local description=$3
    
    echo -n "📦 Checking $description... "
    
    pod_status=$(kubectl get pods -n $namespace -l app=$app_label --no-headers 2>/dev/null | awk '{print $3}' | head -1)
    
    if [ "$pod_status" = "Running" ]; then
        echo "✅ Running"
        return 0
    else
        echo "❌ Not running (Status: $pod_status)"
        return 1
    fi
}

# Function to check service endpoints
check_service() {
    local namespace=$1
    local service_name=$2
    local description=$3
    
    echo -n "🌐 Checking $description service... "
    
    if kubectl get service $service_name -n $namespace &> /dev/null; then
        endpoints=$(kubectl get endpoints $service_name -n $namespace -o jsonpath='{.subsets[*].addresses[*].ip}' 2>/dev/null)
        if [ -n "$endpoints" ]; then
            echo "✅ Available (Endpoints: $endpoints)"
            return 0
        else
            echo "⚠️  Service exists but no endpoints"
            return 1
        fi
    else
        echo "❌ Not found"
        return 1
    fi
}

# Function to test connectivity
test_connectivity() {
    local namespace=$1
    local service=$2
    local port=$3
    local description=$4
    
    echo -n "🔗 Testing $description connectivity... "
    
    # Get a pod to run the test from
    test_pod=$(kubectl get pods -n $namespace --no-headers | grep Running | head -1 | awk '{print $1}')
    
    if [ -z "$test_pod" ]; then
        echo "❌ No running pods found to test from"
        return 1
    fi
    
    # Test connectivity
    if kubectl exec -n $namespace $test_pod -- nc -z $service $port &> /dev/null; then
        echo "✅ Connected"
        return 0
    else
        echo "❌ Connection failed"
        return 1
    fi
}

# Function to check logs for errors
check_logs() {
    local namespace=$1
    local app_label=$2
    local description=$3
    local search_term=$4
    
    echo "📋 Checking $description logs for '$search_term'..."
    
    pod_name=$(kubectl get pods -n $namespace -l app=$app_label --no-headers | head -1 | awk '{print $1}')
    
    if [ -z "$pod_name" ]; then
        echo "   ❌ No pods found"
        return 1
    fi
    
    # Get recent logs and search for the term
    log_matches=$(kubectl logs -n $namespace $pod_name --tail=100 | grep -i "$search_term" | tail -5)
    
    if [ -n "$log_matches" ]; then
        echo "   📄 Recent matches found:"
        echo "$log_matches" | sed 's/^/      /'
    else
        echo "   ℹ️  No recent matches found"
    fi
}

# Function to get metrics from endpoint
check_metrics_endpoint() {
    local namespace=$1
    local service=$2
    local port=$3
    local path=$4
    local description=$5
    local search_pattern=$6
    
    echo -n "📊 Checking $description metrics... "
    
    # Port forward to access the metrics
    kubectl port-forward -n $namespace service/$service $port:$port &> /dev/null &
    pf_pid=$!
    
    # Wait a moment for port forward to establish
    sleep 2
    
    # Try to get metrics
    metrics_output=$(curl -s http://localhost:$port$path 2>/dev/null)
    curl_exit_code=$?
    
    # Kill port forward
    kill $pf_pid 2>/dev/null
    
    if [ $curl_exit_code -eq 0 ] && [ -n "$metrics_output" ]; then
        # Count matching metrics
        metric_count=$(echo "$metrics_output" | grep -c "$search_pattern" 2>/dev/null || echo "0")
        echo "✅ Available ($metric_count '$search_pattern' metrics found)"
        
        if [ $metric_count -gt 0 ]; then
            echo "   📈 Sample metrics:"
            echo "$metrics_output" | grep "$search_pattern" | head -3 | sed 's/^/      /'
        fi
        return 0
    else
        echo "❌ Failed to retrieve"
        return 1
    fi
}

echo ""
echo "🏗️  INFRASTRUCTURE STATUS"
echo "========================"

# Check application pod
check_pod_status "globeco" "globeco-portfolio-service" "Portfolio Service"
app_running=$?

# Check collector daemonset
echo -n "📦 Checking OpenTelemetry Collector DaemonSet... "
collector_pods=$(kubectl get pods -n monitor -l app=otel-collector --field-selector=status.phase=Running --no-headers | wc -l)
total_nodes=$(kubectl get nodes --no-headers | wc -l)

if [ "$collector_pods" -gt 0 ]; then
    echo "✅ Running ($collector_pods/$total_nodes nodes)"
    collector_running=0
else
    echo "❌ No running collector pods"
    collector_running=1
fi

echo ""
echo "🌐 SERVICE STATUS"
echo "================"

# Check services
check_service "globeco" "globeco-portfolio-service" "Portfolio Service"
check_service "monitor" "otel-collector" "OpenTelemetry Collector"

echo ""
echo "🔗 CONNECTIVITY TESTS"
echo "===================="

if [ $app_running -eq 0 ] && [ $collector_running -eq 0 ]; then
    # Test connectivity from app to collector (daemonset with hostport)
    # Get a test pod and its node IP
    test_pod=$(kubectl get pods -n globeco --field-selector=status.phase=Running --no-headers | head -1 | awk '{print $1}')
    if [ -n "$test_pod" ]; then
        node_name=$(kubectl get pod $test_pod -n globeco -o jsonpath='{.spec.nodeName}')
        node_ip=$(kubectl get node $node_name -o jsonpath='{.status.addresses[?(@.type=="InternalIP")].address}')
        echo "🔗 Testing from pod $test_pod on node $node_name ($node_ip)"
        
        # Test connectivity to node IP (daemonset hostport)
        echo -n "🔗 Testing App to Collector HTTP (hostport)... "
        if kubectl exec -n globeco $test_pod -- nc -z $node_ip 4318 &> /dev/null; then
            echo "✅ Connected"
        else
            echo "❌ Connection failed"
        fi
        
        echo -n "🔗 Testing App to Collector gRPC (hostport)... "
        if kubectl exec -n globeco $test_pod -- nc -z $node_ip 4317 &> /dev/null; then
            echo "✅ Connected"
        else
            echo "❌ Connection failed"
        fi
    else
        echo "⚠️  No test pod available for connectivity testing"
    fi
fi

echo ""
echo "📋 LOG ANALYSIS"
echo "==============="

# Check application logs for OpenTelemetry metrics
check_logs "globeco" "globeco-portfolio-service" "Portfolio Service" "otel.*metric"
check_logs "globeco" "globeco-portfolio-service" "Portfolio Service" "http_request"

# Check collector logs for incoming metrics
check_logs "monitor" "otel-collector" "OpenTelemetry Collector" "metric"

echo ""
echo "📊 METRICS ENDPOINTS"
echo "==================="

# Check application metrics endpoint
if [ $app_running -eq 0 ]; then
    check_metrics_endpoint "globeco" "globeco-portfolio-service" "8000" "/metrics" "Application" "http_request"
fi

# Check collector metrics endpoint
if [ $collector_running -eq 0 ]; then
    check_metrics_endpoint "monitor" "otel-collector" "8889" "/metrics" "Collector" "http_request"
fi

echo ""
echo "🔍 CONFIGURATION VERIFICATION"
echo "============================="

echo "📋 Checking OpenTelemetry environment variables..."
if [ $app_running -eq 0 ]; then
    pod_name=$(kubectl get pods -n globeco -l app=globeco-portfolio-service --no-headers | head -1 | awk '{print $1}')
    if [ -n "$pod_name" ]; then
        echo "   OTEL_EXPORTER_OTLP_METRICS_ENDPOINT:"
        kubectl exec -n globeco $pod_name -- printenv OTEL_EXPORTER_OTLP_METRICS_ENDPOINT 2>/dev/null | sed 's/^/      /' || echo "      ❌ Not set"
        
        echo "   OTEL_METRICS_LOGGING_ENABLED:"
        kubectl exec -n globeco $pod_name -- printenv OTEL_METRICS_LOGGING_ENABLED 2>/dev/null | sed 's/^/      /' || echo "      ❌ Not set"
        
        echo "   ENABLE_METRICS:"
        kubectl exec -n globeco $pod_name -- printenv ENABLE_METRICS 2>/dev/null | sed 's/^/      /' || echo "      ❌ Not set"
    fi
fi

echo ""
echo "🎯 RECOMMENDATIONS"
echo "=================="

if [ $app_running -ne 0 ]; then
    echo "❌ Portfolio Service is not running - deploy the application first"
fi

if [ $collector_running -ne 0 ]; then
    echo "❌ OpenTelemetry Collector is not running - deploy the collector first"
fi

if [ $app_running -eq 0 ] && [ $collector_running -eq 0 ]; then
    echo "✅ Both services are running"
    echo "📝 Next steps:"
    echo "   1. Check the metrics endpoints above for custom metrics"
    echo "   2. If app has metrics but collector doesn't, check connectivity"
    echo "   3. Review the log analysis for any error messages"
    echo "   4. Verify the OpenTelemetry configuration matches the collector service name"
fi

echo ""
echo "🔧 TROUBLESHOOTING COMMANDS"
echo "=========================="
echo "# View application logs:"
echo "kubectl logs -n globeco -l app=globeco-portfolio-service -f"
echo ""
echo "# View collector logs:"
echo "kubectl logs -n monitor -l app=otel-collector -f"
echo ""
echo "# Test application metrics endpoint:"
echo "kubectl port-forward -n globeco service/globeco-portfolio-service 8000:8000"
echo "curl http://localhost:8000/metrics | grep http_request"
echo ""
echo "# Test collector metrics endpoint:"
echo "kubectl port-forward -n monitor service/otel-collector 8889:8889"
echo "curl http://localhost:8889/metrics | grep http_request"