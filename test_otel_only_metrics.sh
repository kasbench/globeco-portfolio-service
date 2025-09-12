#!/bin/bash

# Test script to verify OpenTelemetry-only metrics are working
# This script checks that metrics flow from app -> collector -> Prometheus without conflicts

set -e

echo "🔍 Testing OpenTelemetry-only metrics configuration..."
echo "=================================================="

# Function to check if a URL is accessible
check_url() {
    local url=$1
    local description=$2
    echo -n "Checking $description... "
    if curl -s -f "$url" > /dev/null 2>&1; then
        echo "✅ OK"
        return 0
    else
        echo "❌ FAILED"
        return 1
    fi
}

# Function to count metrics containing specific patterns
count_metrics() {
    local url=$1
    local pattern=$2
    local description=$3
    echo -n "Counting $description... "
    local count=$(curl -s "$url" | grep -c "$pattern" || echo "0")
    echo "$count found"
    return $count
}

# Check if collector is accessible
if ! check_url "http://localhost:8889/metrics" "collector metrics endpoint"; then
    echo "❌ Cannot access collector. Make sure it's running on port 8889"
    exit 1
fi

# Check if app is accessible
if ! check_url "http://localhost:8000/" "application"; then
    echo "❌ Cannot access application. Make sure it's running on port 8000"
    exit 1
fi

echo ""
echo "📊 Initial metrics state:"
count_metrics "http://localhost:8889/metrics" "http_requests_total" "http_requests_total metrics"
count_metrics "http://localhost:8889/metrics" "http_request_duration" "http_request_duration metrics"

echo ""
echo "🚀 Generating test traffic..."
for i in {1..10}; do
    curl -s "http://localhost:8000/" > /dev/null
    echo -n "."
done
echo " done"

echo ""
echo "⏳ Waiting 15 seconds for metrics export..."
sleep 15

echo ""
echo "📈 Final metrics state:"
count_metrics "http://localhost:8889/metrics" "http_requests_total" "http_requests_total metrics"
count_metrics "http://localhost:8889/metrics" "http_request_duration" "http_request_duration metrics"

echo ""
echo "🔍 Sample metrics from collector:"
echo "================================="
curl -s "http://localhost:8889/metrics" | grep -E "http_requests_total|http_request_duration" | head -5

echo ""
echo ""
echo "✅ Test completed!"
echo ""
echo "📋 What to check in Prometheus:"
echo "- Look for: http_requests_total{service_namespace=\"globeco\"}"
echo "- Look for: http_request_duration_bucket{service_namespace=\"globeco\"}"
echo "- These should NOT have otel_ prefix"
echo ""
echo "🔧 If metrics are still missing:"
echo "1. Check collector logs: kubectl logs -n monitor daemonset/otel-collector"
echo "2. Verify Prometheus is scraping collector on port 8889"
echo "3. Check application logs for OpenTelemetry export errors"