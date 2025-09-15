#!/bin/bash

# Simple test to check OpenTelemetry metrics recording
# This script makes HTTP requests and checks logs for OpenTelemetry activity

set -e

echo "🔍 Testing OpenTelemetry metrics recording..."

# Start port-forward in background
echo "🌐 Starting port-forward..."
kubectl port-forward -n globeco svc/globeco-portfolio-service 8000:8000 &
PORT_FORWARD_PID=$!

# Wait for port-forward to be ready
sleep 3

# Function to cleanup
cleanup() {
    echo "🧹 Cleaning up..."
    kill $PORT_FORWARD_PID 2>/dev/null || true
}
trap cleanup EXIT

# Test app accessibility
echo "🔍 Testing app accessibility..."
if curl -s http://localhost:8000/health > /dev/null; then
    echo "✅ App is accessible"
else
    echo "❌ App is not accessible"
    exit 1
fi

# Start log monitoring in background
echo "📋 Starting log monitoring..."
kubectl logs -n globeco -l app=globeco-portfolio-service -f --tail=0 > /tmp/otel_test_logs.txt &
LOG_PID=$!

# Wait for log monitoring to start
sleep 2

# Make test HTTP requests
echo "🚀 Making test HTTP requests..."

endpoints=("/" "/health" "/api/v1/portfolios" "/metrics" "/nonexistent")

for endpoint in "${endpoints[@]}"; do
    echo "   Making request to: $endpoint"
    curl -s "http://localhost:8000$endpoint" > /dev/null || true
    sleep 1
done

# Wait for logs to be captured
echo "⏳ Waiting for logs and metrics export (10 seconds)..."
sleep 10

# Stop log monitoring
kill $LOG_PID 2>/dev/null || true

# Analyze logs
echo "📊 Analyzing logs..."

if [ -f /tmp/otel_test_logs.txt ]; then
    # Count different types of log entries
    otel_recording_count=$(grep -c "Successfully recorded OpenTelemetry" /tmp/otel_test_logs.txt || echo "0")
    otel_skipping_count=$(grep -c "Skipping OpenTelemetry" /tmp/otel_test_logs.txt || echo "0")
    middleware_count=$(grep -c -i "middleware\|HTTP" /tmp/otel_test_logs.txt || echo "0")
    
    echo "   OpenTelemetry recording logs: $otel_recording_count"
    echo "   OpenTelemetry skipping logs: $otel_skipping_count"
    echo "   Middleware activity logs: $middleware_count"
    
    if [ "$otel_recording_count" -gt 0 ]; then
        echo "   ✅ OpenTelemetry metrics ARE being recorded!"
        echo "   Sample recording logs:"
        grep "Successfully recorded OpenTelemetry" /tmp/otel_test_logs.txt | head -3 | sed 's/^/     /'
    elif [ "$otel_skipping_count" -gt 0 ]; then
        echo "   ❌ OpenTelemetry metrics are being SKIPPED!"
        echo "   Sample skipping logs:"
        grep "Skipping OpenTelemetry" /tmp/otel_test_logs.txt | head -3 | sed 's/^/     /'
    else
        echo "   ❓ No OpenTelemetry recording activity found"
        echo "   All captured logs:"
        cat /tmp/otel_test_logs.txt | sed 's/^/     /'
    fi
    
    # Clean up log file
    rm -f /tmp/otel_test_logs.txt
else
    echo "   ❌ No logs captured"
fi

# Check collector for metrics
echo "📈 Checking collector for custom metrics..."

collector_metrics=$(curl -s "http://localhost:8889/metrics" | grep -c "otel_scope_name=\"app.monitoring\".*globeco-portfolio-service" || echo "0")

echo "   Custom metrics in collector: $collector_metrics"

if [ "$collector_metrics" -gt 0 ]; then
    echo "   ✅ SUCCESS: Custom OpenTelemetry metrics found in collector!"
    echo "   Sample metrics:"
    curl -s "http://localhost:8889/metrics" | grep "otel_scope_name=\"app.monitoring\".*globeco-portfolio-service" | head -3 | sed 's/^/     /'
else
    echo "   ❌ No custom metrics found in collector"
fi

echo ""
echo "🔍 SUMMARY:"
if [ "$otel_recording_count" -gt 0 ] && [ "$collector_metrics" -gt 0 ]; then
    echo "✅ OpenTelemetry metrics are working correctly!"
    exit 0
elif [ "$otel_recording_count" -gt 0 ]; then
    echo "⚠️  OpenTelemetry metrics are being recorded but not reaching collector"
    echo "   → Check export configuration and collector connectivity"
    exit 1
elif [ "$otel_skipping_count" -gt 0 ]; then
    echo "❌ OpenTelemetry metrics are being skipped (still None)"
    echo "   → Check initialization and dynamic access fix"
    exit 1
else
    echo "❓ OpenTelemetry metrics status unclear"
    echo "   → Check debug logging and middleware triggering"
    exit 1
fi