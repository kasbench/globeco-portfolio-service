#!/usr/bin/env python3
"""
Test script to verify if the middleware is actually recording OpenTelemetry metrics.
This focuses on the specific issue: metrics visible in /metrics but not exported via OpenTelemetry.
"""

import requests
import time
import sys
import json

def test_middleware_recording():
    """Test if the middleware is recording OpenTelemetry metrics by making actual requests."""
    
    print("🔍 Testing middleware OpenTelemetry metrics recording...")
    
    # Configuration - adjust these if needed
    app_url = "http://localhost:8000"  # Local port-forward or direct access
    
    # Step 1: Check if app is accessible
    print(f"\n🌐 Step 1: Testing app accessibility at {app_url}...")
    try:
        response = requests.get(f"{app_url}/health", timeout=5)
        if response.status_code == 200:
            print("✅ App is accessible")
        else:
            print(f"⚠️  App responded with HTTP {response.status_code}")
    except Exception as e:
        print(f"❌ Cannot access app: {e}")
        print("💡 Try: kubectl port-forward -n globeco svc/globeco-portfolio-service 8000:8000")
        return False
    
    # Step 2: Check /metrics endpoint before requests
    print(f"\n📊 Step 2: Checking /metrics endpoint before test requests...")
    try:
        response = requests.get(f"{app_url}/metrics", timeout=10)
        if response.status_code == 200:
            initial_metrics = response.text
            
            # Count initial HTTP metrics
            initial_total_lines = [line for line in initial_metrics.split('\n') 
                                 if line.startswith('http_requests_total{') and 'service_namespace="globeco"' in line]
            initial_duration_lines = [line for line in initial_metrics.split('\n')
                                    if line.startswith('http_request_duration_bucket{') and 'service_namespace="globeco"' in line]
            
            print(f"   Initial http_requests_total metrics: {len(initial_total_lines)}")
            print(f"   Initial http_request_duration metrics: {len(initial_duration_lines)}")
            
            if initial_total_lines:
                print("   Sample initial metrics:")
                for line in initial_total_lines[:2]:
                    print(f"     {line}")
        else:
            print(f"❌ Cannot access /metrics endpoint: HTTP {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ Error accessing /metrics: {e}")
        return False
    
    # Step 3: Make test requests to trigger middleware
    print(f"\n🚀 Step 3: Making test requests to trigger middleware...")
    
    test_requests = [
        "/",
        "/health", 
        "/api/v1/portfolios",
        "/api/v2/portfolios",
        "/nonexistent"  # This should generate a 404
    ]
    
    successful_requests = 0
    for i, endpoint in enumerate(test_requests):
        try:
            response = requests.get(f"{app_url}{endpoint}", timeout=5)
            print(f"   Request {i+1}: {endpoint} -> HTTP {response.status_code}")
            successful_requests += 1
            time.sleep(0.5)  # Small delay between requests
        except Exception as e:
            print(f"   Request {i+1}: {endpoint} -> Error: {e}")
    
    print(f"   Completed {successful_requests}/{len(test_requests)} requests")
    
    # Step 4: Check /metrics endpoint after requests
    print(f"\n📈 Step 4: Checking /metrics endpoint after test requests...")
    time.sleep(2)  # Wait for metrics to be recorded
    
    try:
        response = requests.get(f"{app_url}/metrics", timeout=10)
        if response.status_code == 200:
            final_metrics = response.text
            
            # Count final HTTP metrics
            final_total_lines = [line for line in final_metrics.split('\n') 
                               if line.startswith('http_requests_total{') and 'service_namespace="globeco"' in line]
            final_duration_lines = [line for line in final_metrics.split('\n')
                                  if line.startswith('http_request_duration_bucket{') and 'service_namespace="globeco"' in line]
            
            print(f"   Final http_requests_total metrics: {len(final_total_lines)}")
            print(f"   Final http_request_duration metrics: {len(final_duration_lines)}")
            
            # Check if metrics increased
            total_increase = len(final_total_lines) - len(initial_total_lines)
            duration_increase = len(final_duration_lines) - len(initial_duration_lines)
            
            print(f"   Metrics increase - total: +{total_increase}, duration: +{duration_increase}")
            
            if total_increase > 0 or duration_increase > 0:
                print("✅ Prometheus metrics are being recorded by middleware")
                
                # Show some sample new metrics
                if final_total_lines:
                    print("   Sample final metrics:")
                    for line in final_total_lines[-3:]:
                        print(f"     {line}")
            else:
                print("❌ No increase in Prometheus metrics - middleware may not be working")
                return False
                
        else:
            print(f"❌ Cannot access /metrics endpoint: HTTP {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ Error accessing /metrics: {e}")
        return False
    
    # Step 5: Check application logs for OpenTelemetry recording
    print(f"\n📋 Step 5: Checking application logs for OpenTelemetry metrics recording...")
    
    try:
        import subprocess
        
        # Get recent application logs
        result = subprocess.run([
            "kubectl", "logs", "-n", "globeco",
            "-l", "app=globeco-portfolio-service",
            "--tail=50"
        ], capture_output=True, text=True, timeout=30)
        
        if result.returncode == 0:
            logs = result.stdout
            
            # Look for metrics-related log entries
            otel_lines = [line for line in logs.split('\n') if 'OpenTelemetry' in line and 'metric' in line.lower()]
            recording_lines = [line for line in logs.split('\n') if 'recorded' in line.lower() and 'metric' in line.lower()]
            error_lines = [line for line in logs.split('\n') if 'error' in line.lower() and 'metric' in line.lower()]
            
            print(f"   Found {len(otel_lines)} OpenTelemetry metrics log lines")
            print(f"   Found {len(recording_lines)} metrics recording log lines")
            print(f"   Found {len(error_lines)} metrics error log lines")
            
            if error_lines:
                print("   Recent metrics errors:")
                for line in error_lines[-3:]:
                    print(f"     {line}")
            
            if recording_lines:
                print("   Recent metrics recording activity:")
                for line in recording_lines[-3:]:
                    print(f"     {line}")
            elif otel_lines:
                print("   Recent OpenTelemetry activity:")
                for line in otel_lines[-3:]:
                    print(f"     {line}")
            else:
                print("   ⚠️  No OpenTelemetry metrics activity found in logs")
                print("   This suggests OpenTelemetry metrics may not be recording")
                
        else:
            print(f"❌ Failed to get application logs: {result.stderr}")
            
    except Exception as e:
        print(f"❌ Error getting application logs: {e}")
    
    # Summary
    print(f"\n🔍 DIAGNOSIS:")
    print("✅ Prometheus client metrics are working (visible in /metrics)")
    print("❓ OpenTelemetry metrics recording status unclear")
    print("\nMost likely issues:")
    print("1. OpenTelemetry metrics are None in the middleware (initialization failed)")
    print("2. OpenTelemetry metrics are recording but export is failing")
    print("3. Export configuration issue (endpoint, timing, format)")
    
    return True

if __name__ == "__main__":
    success = test_middleware_recording()
    if success:
        print("\n✅ Middleware recording test completed")
        print("\nNext steps:")
        print("1. Check if OpenTelemetry metrics are None in the running app")
        print("2. Verify export configuration and connectivity")
        print("3. Check collector logs for incoming metrics")
        sys.exit(0)
    else:
        print("\n❌ Issues found with middleware recording")
        sys.exit(1)