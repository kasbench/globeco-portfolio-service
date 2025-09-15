#!/usr/bin/env python3
"""
Test OpenTelemetry metrics recording directly by checking if they're being recorded
when HTTP requests are made to the application.
"""

import requests
import time
import subprocess
import sys

def test_otel_recording():
    """Test if OpenTelemetry metrics are being recorded by monitoring app logs during requests."""
    
    print("🔍 Testing OpenTelemetry metrics recording in live application...")
    
    # Step 1: Enable debug logging if not already enabled
    print("\n🔧 Step 1: Checking if debug logging is enabled...")
    
    try:
        # Check current deployment environment variables
        result = subprocess.run([
            "kubectl", "get", "deployment", "-n", "globeco", 
            "globeco-portfolio-service", "-o", "yaml"
        ], capture_output=True, text=True, timeout=30)
        
        if result.returncode == 0:
            deployment_yaml = result.stdout
            debug_enabled = "METRICS_DEBUG_LOGGING" in deployment_yaml and "true" in deployment_yaml
            print(f"   Debug logging enabled: {debug_enabled}")
            
            if not debug_enabled:
                print("   ⚠️  Debug logging not enabled - may have limited visibility")
        else:
            print(f"   ❌ Failed to check deployment: {result.stderr}")
            
    except Exception as e:
        print(f"   ❌ Error checking deployment: {e}")
    
    # Step 2: Start monitoring application logs
    print("\n📋 Step 2: Starting application log monitoring...")
    
    try:
        # Start log monitoring in background
        log_process = subprocess.Popen([
            "kubectl", "logs", "-n", "globeco",
            "-l", "app=globeco-portfolio-service",
            "-f", "--tail=5"
        ], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        
        print("   Log monitoring started...")
        time.sleep(2)
        
        # Step 3: Make test requests while monitoring logs
        print("\n🚀 Step 3: Making test requests while monitoring logs...")
        
        # Use port-forward or direct access - adjust as needed
        app_endpoints = [
            "http://localhost:8000",  # If port-forwarded
            # Add other possible endpoints if needed
        ]
        
        app_url = None
        for endpoint in app_endpoints:
            try:
                response = requests.get(f"{endpoint}/health", timeout=3)
                if response.status_code == 200:
                    app_url = endpoint
                    print(f"   Using app endpoint: {app_url}")
                    break
            except:
                continue
        
        if not app_url:
            print("   ❌ Cannot access application - try: kubectl port-forward -n globeco svc/globeco-portfolio-service 8000:8000")
            log_process.terminate()
            return False
        
        # Make several test requests
        test_paths = ["/", "/health", "/api/v1/portfolios", "/metrics"]
        
        for i, path in enumerate(test_paths):
            try:
                print(f"   Making request {i+1}: {path}")
                response = requests.get(f"{app_url}{path}", timeout=5)
                print(f"     Response: HTTP {response.status_code}")
                time.sleep(1)  # Wait between requests
            except Exception as e:
                print(f"     Error: {e}")
        
        # Wait for logs to be generated
        print("   Waiting for log output...")
        time.sleep(5)
        
        # Step 4: Stop log monitoring and analyze output
        print("\n📊 Step 4: Analyzing log output...")
        
        log_process.terminate()
        try:
            stdout, stderr = log_process.communicate(timeout=10)
            
            if stdout:
                log_lines = stdout.strip().split('\n')
                print(f"   Captured {len(log_lines)} log lines")
                
                # Look for specific OpenTelemetry metrics activity
                otel_recording_lines = []
                otel_error_lines = []
                middleware_lines = []
                
                for line in log_lines:
                    if line.strip():
                        if 'OpenTelemetry' in line and ('record' in line.lower() or 'add' in line.lower()):
                            otel_recording_lines.append(line)
                        elif 'error' in line.lower() and ('otel' in line.lower() or 'metric' in line.lower()):
                            otel_error_lines.append(line)
                        elif 'middleware' in line.lower() or 'HTTP' in line:
                            middleware_lines.append(line)
                
                print(f"   OpenTelemetry recording lines: {len(otel_recording_lines)}")
                print(f"   OpenTelemetry error lines: {len(otel_error_lines)}")
                print(f"   Middleware activity lines: {len(middleware_lines)}")
                
                # Show relevant log entries
                if otel_error_lines:
                    print("   🚨 OpenTelemetry errors found:")
                    for line in otel_error_lines:
                        print(f"     {line}")
                
                if otel_recording_lines:
                    print("   ✅ OpenTelemetry recording activity found:")
                    for line in otel_recording_lines[:3]:
                        print(f"     {line}")
                elif middleware_lines:
                    print("   📝 Middleware activity found (but no OpenTelemetry recording):")
                    for line in middleware_lines[:3]:
                        print(f"     {line}")
                else:
                    print("   ❌ No relevant activity found in logs")
                    print("   This suggests either:")
                    print("     - Debug logging is not enabled")
                    print("     - OpenTelemetry metrics are not being recorded")
                    print("     - Middleware is not processing requests")
                
                # Show all captured logs for debugging
                if len(log_lines) > 0:
                    print("   📋 All captured logs:")
                    for line in log_lines:
                        if line.strip():
                            print(f"     {line}")
                
            else:
                print("   ❌ No log output captured")
                
        except subprocess.TimeoutExpired:
            log_process.kill()
            print("   ⚠️  Log process timeout")
            
    except Exception as e:
        print(f"   ❌ Error during log monitoring: {e}")
        return False
    
    # Step 5: Check current metrics state
    print("\n📈 Step 5: Checking current metrics state...")
    
    if app_url:
        try:
            response = requests.get(f"{app_url}/metrics", timeout=10)
            if response.status_code == 200:
                metrics_text = response.text
                
                # Count current metrics
                total_lines = [line for line in metrics_text.split('\n') 
                             if line.startswith('http_requests_total{') and 'service_namespace="globeco"' in line]
                duration_lines = [line for line in metrics_text.split('\n')
                                if line.startswith('http_request_duration_bucket{') and 'service_namespace="globeco"' in line]
                
                print(f"   Current http_requests_total metrics: {len(total_lines)}")
                print(f"   Current http_request_duration metrics: {len(duration_lines)}")
                
                if total_lines:
                    print("   ✅ Prometheus metrics are being recorded")
                    print("   Sample metrics:")
                    for line in total_lines[:2]:
                        print(f"     {line}")
                else:
                    print("   ❌ No Prometheus metrics found")
                    
            else:
                print(f"   ❌ Cannot access /metrics: HTTP {response.status_code}")
                
        except Exception as e:
            print(f"   ❌ Error checking metrics: {e}")
    
    print("\n🔍 CONCLUSION:")
    print("Based on the log analysis:")
    
    if len(otel_recording_lines) > 0:
        print("✅ OpenTelemetry metrics ARE being recorded")
        print("   → Issue is likely with export configuration or collector connectivity")
    elif len(otel_error_lines) > 0:
        print("❌ OpenTelemetry metrics have ERRORS during recording")
        print("   → Check the error messages above for specific issues")
    else:
        print("❓ OpenTelemetry metrics recording status UNCLEAR")
        print("   → May need to enable debug logging or check initialization")
    
    return True

if __name__ == "__main__":
    success = test_otel_recording()
    if success:
        print("\n✅ OpenTelemetry recording test completed")
        sys.exit(0)
    else:
        print("\n❌ Test failed")
        sys.exit(1)