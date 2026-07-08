#!/usr/bin/env python3
"""
Test script to make HTTP requests and monitor logs for OpenTelemetry metrics recording.
"""

import subprocess
import requests
import time
import threading
import sys

def monitor_logs():
    """Monitor application logs in the background."""
    logs = []
    
    def log_reader():
        try:
            process = subprocess.Popen([
                "kubectl", "logs", "-n", "globeco",
                "-l", "app=globeco-portfolio-service",
                "-f", "--tail=0"
            ], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            
            for line in iter(process.stdout.readline, ''):
                if line.strip():
                    logs.append(line.strip())
                    # Print OpenTelemetry related logs immediately
                    if 'OpenTelemetry' in line or 'otel' in line.lower():
                        print(f"📋 LOG: {line.strip()}")
            
        except Exception as e:
            print(f"❌ Log monitoring error: {e}")
    
    thread = threading.Thread(target=log_reader, daemon=True)
    thread.start()
    return logs

def test_live_recording():
    """Test OpenTelemetry recording with live HTTP requests."""
    
    print("🔍 Testing live OpenTelemetry metrics recording...")
    
    # Start log monitoring
    print("\n📋 Starting log monitoring...")
    logs = monitor_logs()
    time.sleep(2)  # Let log monitoring start
    
    # Get pod IP for direct access
    print("\n🔍 Getting pod information...")
    try:
        result = subprocess.run([
            "kubectl", "get", "pods", "-n", "globeco",
            "-l", "app=globeco-portfolio-service",
            "-o", "jsonpath={.items[0].status.podIP}"
        ], capture_output=True, text=True, timeout=30)
        
        if result.returncode == 0 and result.stdout.strip():
            pod_ip = result.stdout.strip()
            app_url = f"http://{pod_ip}:8000"
            print(f"   Using pod IP: {pod_ip}")
        else:
            app_url = "http://localhost:8000"  # Fallback to port-forward
            print("   Using localhost (ensure port-forward is active)")
            
    except Exception as e:
        app_url = "http://localhost:8000"
        print(f"   Error getting pod IP: {e}, using localhost")
    
    # Test app accessibility
    print(f"\n🌐 Testing app accessibility at {app_url}...")
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
    
    # Make test requests
    print(f"\n🚀 Making test HTTP requests...")
    
    test_endpoints = [
        "/",
        "/health", 
        "/api/v1/portfolios",
        "/api/v2/portfolios",
        "/metrics",
        "/nonexistent"  # 404 test
    ]
    
    for i, endpoint in enumerate(test_endpoints):
        try:
            print(f"   Request {i+1}: {endpoint}")
            response = requests.get(f"{app_url}{endpoint}", timeout=5)
            print(f"     → HTTP {response.status_code}")
            time.sleep(1)  # Wait between requests to see individual log entries
        except Exception as e:
            print(f"     → Error: {e}")
    
    # Wait for logs and export
    print(f"\n⏳ Waiting for logs and metrics export (10 seconds)...")
    time.sleep(10)
    
    # Analyze captured logs
    print(f"\n📊 Analyzing captured logs...")
    
    otel_recording_logs = []
    otel_error_logs = []
    middleware_logs = []
    
    for log in logs:
        if 'Successfully recorded OpenTelemetry' in log:
            otel_recording_logs.append(log)
        elif 'Skipping OpenTelemetry' in log:
            otel_error_logs.append(log)
        elif 'middleware' in log.lower() or 'HTTP' in log:
            middleware_logs.append(log)
    
    print(f"   OpenTelemetry recording logs: {len(otel_recording_logs)}")
    print(f"   OpenTelemetry skipping logs: {len(otel_error_logs)}")
    print(f"   Middleware activity logs: {len(middleware_logs)}")
    
    if otel_recording_logs:
        print("   ✅ OpenTelemetry metrics ARE being recorded!")
        print("   Sample recording logs:")
        for log in otel_recording_logs[:3]:
            print(f"     {log}")
    elif otel_error_logs:
        print("   ❌ OpenTelemetry metrics are being SKIPPED!")
        print("   Sample skipping logs:")
        for log in otel_error_logs[:3]:
            print(f"     {log}")
    else:
        print("   ❓ No OpenTelemetry recording activity found in logs")
        print("   This could mean:")
        print("     - Debug logging is not enabled")
        print("     - Middleware is not being triggered")
        print("     - OpenTelemetry metrics are still None")
    
    # Check collector for metrics
    print(f"\n📈 Checking collector for custom metrics...")
    
    try:
        response = requests.get("http://localhost:8889/metrics", timeout=10)
        if response.status_code == 200:
            metrics_text = response.text
            
            # Look for our custom metrics with app.monitoring scope
            custom_metrics = [line for line in metrics_text.split('\n')
                            if 'http_request' in line 
                            and 'globeco-portfolio-service' in line
                            and 'otel_scope_name="app.monitoring"' in line]
            
            print(f"   Custom metrics found: {len(custom_metrics)}")
            
            if custom_metrics:
                print("   ✅ SUCCESS: Custom OpenTelemetry metrics found in collector!")
                print("   Sample metrics:")
                for metric in custom_metrics[:3]:
                    print(f"     {metric}")
                return True
            else:
                print("   ❌ No custom metrics found in collector")
                
                # Check for any app.monitoring scope metrics
                app_monitoring_metrics = [line for line in metrics_text.split('\n')
                                        if 'otel_scope_name="app.monitoring"' in line
                                        and 'globeco-portfolio-service' in line]
                
                print(f"   Total app.monitoring metrics: {len(app_monitoring_metrics)}")
                
                if app_monitoring_metrics:
                    print("   Found other app.monitoring metrics:")
                    for metric in app_monitoring_metrics[:3]:
                        print(f"     {metric}")
                else:
                    print("   No app.monitoring scope metrics found at all")
                    print("   This confirms OpenTelemetry metrics are not being exported")
                
        else:
            print(f"   ❌ Cannot access collector: HTTP {response.status_code}")
            
    except Exception as e:
        print(f"   ❌ Error checking collector: {e}")
    
    return False

if __name__ == "__main__":
    success = test_live_recording()
    
    if success:
        print("\n🎉 OpenTelemetry metrics are working correctly!")
    else:
        print("\n💥 OpenTelemetry metrics are still not working.")
        print("\nNext debugging steps:")
        print("1. Check if debug logging is actually enabled")
        print("2. Verify middleware is being triggered")
        print("3. Check if OpenTelemetry metrics are still None")
        print("4. Verify export configuration and connectivity")
    
    sys.exit(0 if success else 1)