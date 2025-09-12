#!/usr/bin/env python3
"""
Debug script to check what's happening with metrics export.
This helps identify if the issue is in creation, export, or collection.
"""

import requests
import json
import time
import sys

def check_app_metrics():
    """Check what metrics the app is exposing on /metrics endpoint."""
    try:
        response = requests.get("http://localhost:8000/metrics", timeout=10)
        if response.status_code == 200:
            content = response.text
            
            # Look for custom metrics
            custom_metrics = []
            for line in content.split('\n'):
                if any(metric in line for metric in ['http_requests_total', 'http_request_duration', 'http_requests_in_flight']):
                    if not line.startswith('#') and line.strip():
                        custom_metrics.append(line.strip())
            
            print(f"✅ App /metrics endpoint accessible")
            print(f"📊 Found {len(custom_metrics)} custom metric lines")
            if custom_metrics:
                print("📋 Sample custom metrics:")
                for metric in custom_metrics[:3]:
                    print(f"   {metric}")
            return True
        else:
            print(f"❌ App /metrics returned HTTP {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ Cannot access app /metrics: {e}")
        return False

def check_collector_metrics():
    """Check what metrics the collector is exposing."""
    try:
        response = requests.get("http://localhost:8889/metrics", timeout=10)
        if response.status_code == 200:
            content = response.text
            
            # Look for our custom metrics
            custom_metrics = []
            otel_metrics = []
            
            for line in content.split('\n'):
                if any(metric in line for metric in ['http_requests_total', 'http_request_duration', 'http_requests_in_flight']):
                    if not line.startswith('#') and line.strip():
                        if 'service_namespace="globeco"' in line:
                            custom_metrics.append(line.strip())
                        elif 'otel_' in line:
                            otel_metrics.append(line.strip())
            
            print(f"✅ Collector /metrics endpoint accessible")
            print(f"📊 Found {len(custom_metrics)} custom metrics with service_namespace=globeco")
            print(f"📊 Found {len(otel_metrics)} otel_ prefixed metrics")
            
            if custom_metrics:
                print("📋 Sample custom metrics from collector:")
                for metric in custom_metrics[:3]:
                    print(f"   {metric}")
            elif otel_metrics:
                print("📋 Sample otel_ metrics from collector:")
                for metric in otel_metrics[:3]:
                    print(f"   {metric}")
            else:
                print("❌ No custom metrics found in collector")
                
            return len(custom_metrics) > 0 or len(otel_metrics) > 0
        else:
            print(f"❌ Collector /metrics returned HTTP {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ Cannot access collector /metrics: {e}")
        return False

def trigger_app_requests():
    """Trigger some requests to generate metrics."""
    print("🚀 Triggering test requests...")
    successful = 0
    for i in range(5):
        try:
            response = requests.get("http://localhost:8000/", timeout=5)
            if response.status_code == 200:
                successful += 1
            print(f"   Request {i+1}: HTTP {response.status_code}")
        except Exception as e:
            print(f"   Request {i+1}: Error - {e}")
        time.sleep(1)
    
    print(f"✅ Completed {successful}/5 successful requests")
    return successful > 0

def main():
    """Main diagnostic function."""
    print("🔍 OpenTelemetry Metrics Export Debug")
    print("=" * 40)
    
    # Step 1: Check initial state
    print("\n📊 Step 1: Checking initial metrics state...")
    app_working = check_app_metrics()
    collector_working = check_collector_metrics()
    
    if not app_working:
        print("❌ Cannot proceed - app not accessible")
        return 1
    
    if not collector_working:
        print("❌ Cannot proceed - collector not accessible")
        return 1
    
    # Step 2: Trigger requests
    print("\n🚀 Step 2: Triggering test requests...")
    if not trigger_app_requests():
        print("❌ No successful requests - cannot generate metrics")
        return 1
    
    # Step 3: Wait for export
    print("\n⏳ Step 3: Waiting 15 seconds for metrics export...")
    time.sleep(15)
    
    # Step 4: Check final state
    print("\n📈 Step 4: Checking final metrics state...")
    app_final = check_app_metrics()
    collector_final = check_collector_metrics()
    
    # Step 5: Diagnosis
    print("\n🔍 DIAGNOSIS:")
    
    if app_final and not collector_final:
        print("❌ ISSUE: Metrics visible in app but not in collector")
        print("   Possible causes:")
        print("   1. OpenTelemetry exporter not sending metrics")
        print("   2. Collector not receiving/processing metrics")
        print("   3. Network connectivity issues")
        print("   4. Metric name conflicts causing drops")
        print("\n🔧 Troubleshooting steps:")
        print("   1. Check app logs for OpenTelemetry export errors")
        print("   2. Check collector logs for incoming metrics")
        print("   3. Verify OTEL_EXPORTER_OTLP_METRICS_ENDPOINT setting")
        return 1
    elif collector_final:
        print("✅ SUCCESS: Metrics are flowing to collector")
        print("   If not visible in Prometheus, check:")
        print("   1. Prometheus scraping configuration")
        print("   2. Metric label matching in Prometheus queries")
        return 0
    else:
        print("❌ ISSUE: No metrics found anywhere")
        print("   Check if metrics middleware is enabled")
        return 1

if __name__ == "__main__":
    sys.exit(main())