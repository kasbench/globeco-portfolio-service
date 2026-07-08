#!/usr/bin/env python3
"""
Simple test script to verify metrics flow from app to collector to Prometheus.
This script helps diagnose why custom metrics aren't reaching Prometheus.
"""

import requests
import time
import sys
from typing import Dict, List, Optional

def check_endpoint(url: str, description: str) -> Dict:
    """Check if an endpoint is accessible and return metrics info."""
    try:
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            content = response.text
            lines = content.split('\n')
            
            # Count different types of metrics
            custom_metrics = []
            otel_metrics = []
            
            for line in lines:
                if line.strip() and not line.startswith('#'):
                    # Look for our custom metrics
                    if any(metric in line for metric in ['http_requests_total', 'http_request_duration', 'http_requests_in_flight']):
                        if 'otel_' in line or 'service_namespace="globeco"' in line:
                            otel_metrics.append(line.strip())
                        else:
                            custom_metrics.append(line.strip())
            
            return {
                'status': 'success',
                'total_lines': len(lines),
                'custom_metrics': custom_metrics[:5],  # First 5
                'otel_metrics': otel_metrics[:5],      # First 5
                'custom_count': len(custom_metrics),
                'otel_count': len(otel_metrics)
            }
        else:
            return {'status': 'error', 'message': f'HTTP {response.status_code}'}
    except Exception as e:
        return {'status': 'error', 'message': str(e)}

def trigger_requests(app_url: str, count: int = 5) -> Dict:
    """Trigger test requests to generate metrics."""
    successful = 0
    for i in range(count):
        try:
            response = requests.get(f"{app_url}/", timeout=5)
            if response.status_code == 200:
                successful += 1
        except Exception:
            pass
        time.sleep(0.5)
    
    return {'total': count, 'successful': successful}

def main():
    """Main diagnostic function."""
    app_url = "http://localhost:8000"
    collector_url = "http://localhost:8889"
    
    # Allow command line override
    if len(sys.argv) > 1:
        app_url = sys.argv[1]
    if len(sys.argv) > 2:
        collector_url = sys.argv[2]
    
    print("🔍 OpenTelemetry Metrics Flow Diagnostic")
    print("=" * 50)
    print(f"App URL: {app_url}")
    print(f"Collector URL: {collector_url}")
    print()
    
    # Step 1: Check initial state
    print("📊 Step 1: Checking initial metrics state...")
    app_initial = check_endpoint(f"{app_url}/metrics", "App /metrics")
    collector_initial = check_endpoint(f"{collector_url}/metrics", "Collector /metrics")
    
    print(f"  App /metrics: {app_initial['status']}")
    if app_initial['status'] == 'success':
        print(f"    Custom metrics: {app_initial['custom_count']}")
        print(f"    OTel metrics: {app_initial['otel_count']}")
    
    print(f"  Collector /metrics: {collector_initial['status']}")
    if collector_initial['status'] == 'success':
        print(f"    Custom metrics: {collector_initial['custom_count']}")
        print(f"    OTel metrics: {collector_initial['otel_count']}")
    
    # Step 2: Trigger requests
    print("\n🚀 Step 2: Triggering test requests...")
    requests_result = trigger_requests(app_url, 5)
    print(f"  Requests: {requests_result['successful']}/{requests_result['total']} successful")
    
    # Step 3: Wait for metrics export
    print("\n⏳ Step 3: Waiting for metrics export (15 seconds)...")
    time.sleep(15)
    
    # Step 4: Check final state
    print("\n📈 Step 4: Checking final metrics state...")
    app_final = check_endpoint(f"{app_url}/metrics", "App /metrics")
    collector_final = check_endpoint(f"{collector_url}/metrics", "Collector /metrics")
    
    print(f"  App /metrics: {app_final['status']}")
    if app_final['status'] == 'success':
        print(f"    Custom metrics: {app_final['custom_count']}")
        print(f"    OTel metrics: {app_final['otel_count']}")
        if app_final['custom_metrics']:
            print("    Sample custom metrics:")
            for metric in app_final['custom_metrics'][:3]:
                print(f"      {metric}")
    
    print(f"  Collector /metrics: {collector_final['status']}")
    if collector_final['status'] == 'success':
        print(f"    Custom metrics: {collector_final['custom_count']}")
        print(f"    OTel metrics: {collector_final['otel_count']}")
        if collector_final['otel_metrics']:
            print("    Sample OTel metrics:")
            for metric in collector_final['otel_metrics'][:3]:
                print(f"      {metric}")
    
    # Step 5: Diagnosis
    print("\n🔍 DIAGNOSIS:")
    
    if app_final['status'] != 'success':
        print("  ❌ CRITICAL: Cannot access app /metrics endpoint")
        print("     - Check if the application is running")
        print("     - Verify the app URL is correct")
        return 1
    
    if collector_final['status'] != 'success':
        print("  ❌ CRITICAL: Cannot access collector /metrics endpoint")
        print("     - Check if the OpenTelemetry collector is running")
        print("     - Verify the collector URL is correct")
        print("     - Check if port 8889 is accessible")
        return 1
    
    if app_final['custom_count'] == 0:
        print("  ❌ ISSUE: No custom metrics found in app")
        print("     - Check if metrics middleware is enabled")
        print("     - Verify ENABLE_METRICS=true in environment")
        return 1
    
    if collector_final['otel_count'] == 0:
        print("  ❌ ISSUE: Custom metrics not reaching collector")
        print("     - Check OpenTelemetry exporter configuration")
        print("     - Verify collector endpoint connectivity")
        print("     - Check collector logs for errors")
        print("     - Ensure OTEL_EXPORTER_OTLP_METRICS_ENDPOINT is correct")
        return 1
    
    print("  ✅ SUCCESS: Custom metrics are flowing correctly!")
    print("     - Metrics should now appear in Prometheus")
    print("     - Look for metrics with 'otel_' prefix in Prometheus")
    return 0

if __name__ == "__main__":
    sys.exit(main())