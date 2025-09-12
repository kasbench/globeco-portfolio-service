#!/bin/bash

echo "🧪 Custom Metrics Verification Script"
echo "===================================="

# Function to make test requests and check metrics
test_custom_metrics() {
    local app_url=$1
    local collector_url=$2
    
    echo "📊 Testing custom metrics flow..."
    echo "App URL: $app_url"
    echo "Collector URL: $collector_url"
    
    # Make some test requests to generate metrics
    echo ""
    echo "🔄 Generating test traffic..."
    for i in {1..5}; do
        echo -n "Request $i: "
        response=$(curl -s -o /dev/null -w "%{http_code}" "$app_url/" 2>/dev/null)
        if [ "$response" = "200" ]; then
            echo "✅ Success"
        else
            echo "❌ Failed ($response)"
        fi
        sleep 1
    done
    
    # Wait for metrics to be exported
    echo ""
    echo "⏳ Waiting 15 seconds for metrics export..."
    sleep 15
    
    # Check application metrics
    echo ""
    echo "📈 Checking application /metrics endpoint..."
    app_metrics=$(curl -s "$app_url/metrics" 2>/dev/null)
    
    if [ -n "$app_metrics" ]; then
        echo "✅ Application metrics endpoint accessible"
        
        # Check for custom HTTP metrics
        custom_metrics=(
            "http_requests_total"
            "http_request_duration"
            "http_requests_in_flight"
            "http_workers_active"
            "http_workers_total"
        )
        
        echo ""
        echo "🔍 Custom metrics in application:"
        for metric in "${custom_metrics[@]}"; do
            count=$(echo "$app_metrics" | grep -c "^$metric")
            if [ "$count" -gt 0 ]; then
                echo "  ✅ $metric: $count entries"
                # Show a sample
                echo "$app_metrics" | grep "^$metric" | head -1 | sed 's/^/    /'
            else
                echo "  ❌ $metric: Not found"
            fi
        done
    else
        echo "❌ Cannot access application metrics endpoint"
        return 1
    fi
    
    # Check collector metrics
    echo ""
    echo "📊 Checking collector /metrics endpoint..."
    collector_metrics=$(curl -s "$collector_url/metrics" 2>/dev/null)
    
    if [ -n "$collector_metrics" ]; then
        echo "✅ Collector metrics endpoint accessible"
        
        echo ""
        echo "🔍 Custom metrics in collector (with otel_ prefix):"
        for metric in "${custom_metrics[@]}"; do
            # Look for both prefixed and non-prefixed versions
            count1=$(echo "$collector_metrics" | grep -c "^otel_$metric")
            count2=$(echo "$collector_metrics" | grep -c "^$metric")
            total_count=$((count1 + count2))
            
            if [ "$total_count" -gt 0 ]; then
                echo "  ✅ $metric: $total_count entries"
                # Show a sample
                if [ "$count1" -gt 0 ]; then
                    echo "$collector_metrics" | grep "^otel_$metric" | head -1 | sed 's/^/    /'
                else
                    echo "$collector_metrics" | grep "^$metric" | head -1 | sed 's/^/    /'
                fi
            else
                echo "  ❌ $metric: Not found"
            fi
        done
    else
        echo "❌ Cannot access collector metrics endpoint"
        return 1
    fi
    
    # Summary
    echo ""
    echo "📋 SUMMARY:"
    app_custom_count=$(echo "$app_metrics" | grep -E "^(http_requests_total|http_request_duration|http_requests_in_flight|http_workers)" | wc -l)
    collector_custom_count=$(echo "$collector_metrics" | grep -E "^(otel_)?(http_requests_total|http_request_duration|http_requests_in_flight|http_workers)" | wc -l)
    
    echo "  📱 Application custom metrics: $app_custom_count"
    echo "  🔄 Collector custom metrics: $collector_custom_count"
    
    if [ "$app_custom_count" -gt 0 ] && [ "$collector_custom_count" -gt 0 ]; then
        echo "  🎉 SUCCESS: Custom metrics are flowing correctly!"
        return 0
    elif [ "$app_custom_count" -gt 0 ] && [ "$collector_custom_count" -eq 0 ]; then
        echo "  ⚠️  ISSUE: Custom metrics in app but not reaching collector"
        echo "     Check connectivity and collector configuration"
        return 1
    elif [ "$app_custom_count" -eq 0 ]; then
        echo "  ❌ ISSUE: No custom metrics in application"
        echo "     Check OpenTelemetry metrics initialization"
        return 1
    else
        echo "  ❓ UNKNOWN: Unexpected state"
        return 1
    fi
}

# Main execution
if [ "$#" -eq 2 ]; then
    # Direct URLs provided
    test_custom_metrics "$1" "$2"
    exit $?
fi

# Kubernetes mode - set up port forwards
echo "🚀 Setting up Kubernetes port forwards..."

# Check if kubectl is available
if ! command -v kubectl &> /dev/null; then
    echo "❌ kubectl not found. Please install kubectl or provide direct URLs:"
    echo "Usage: $0 <app_url> <collector_url>"
    echo "Example: $0 http://localhost:8000 http://localhost:8889"
    exit 1
fi

# Set up port forward for application
echo "📱 Setting up application port forward..."
kubectl port-forward -n globeco service/globeco-portfolio-service 8000:8000 &> /dev/null &
app_pf_pid=$!

# Set up port forward for collector (pick any collector pod)
echo "🔄 Setting up collector port forward..."
collector_pod=$(kubectl get pods -n monitor -l app=otel-collector --field-selector=status.phase=Running -o name | head -1)

if [ -z "$collector_pod" ]; then
    echo "❌ No running collector pods found"
    kill $app_pf_pid 2>/dev/null
    exit 1
fi

kubectl port-forward -n monitor "$collector_pod" 8889:8889 &> /dev/null &
collector_pf_pid=$!

# Wait for port forwards to establish
echo "⏳ Waiting for port forwards to establish..."
sleep 3

# Test the metrics
test_custom_metrics "http://localhost:8000" "http://localhost:8889"
result=$?

# Clean up port forwards
echo ""
echo "🧹 Cleaning up port forwards..."
kill $app_pf_pid $collector_pf_pid 2>/dev/null

exit $result