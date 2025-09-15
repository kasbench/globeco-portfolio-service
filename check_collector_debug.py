#!/usr/bin/env python3
"""
Check collector debug output and logs to see what's happening with metrics.
"""

import subprocess
import time
import sys

def check_collector_debug():
    """Check collector debug output and logs."""
    
    print("🔍 Checking OpenTelemetry collector debug output...")
    
    # Step 1: Check if we can access collector logs
    print("\n📋 Step 1: Checking collector logs...")
    
    try:
        # Try to get collector pod logs
        result = subprocess.run([
            "kubectl", "logs", "-n", "monitor", 
            "-l", "app=otel-collector", 
            "--tail=50"
        ], capture_output=True, text=True, timeout=30)
        
        if result.returncode == 0:
            logs = result.stdout
            print("✅ Successfully retrieved collector logs")
            
            # Look for metrics-related log entries
            metrics_lines = [line for line in logs.split('\n') if 'metric' in line.lower()]
            error_lines = [line for line in logs.split('\n') if 'error' in line.lower()]
            
            print(f"   Found {len(metrics_lines)} metrics-related log lines")
            print(f"   Found {len(error_lines)} error log lines")
            
            if error_lines:
                print("   Recent errors:")
                for line in error_lines[-3:]:
                    print(f"     {line}")
            
            if metrics_lines:
                print("   Recent metrics activity:")
                for line in metrics_lines[-5:]:
                    print(f"     {line}")
            
        else:
            print(f"❌ Failed to get collector logs: {result.stderr}")
            return False
            
    except Exception as e:
        print(f"❌ Error getting collector logs: {e}")
        return False
    
    # Step 2: Send a test metric and watch for debug output
    print("\n🧪 Step 2: Sending test metric and monitoring debug output...")
    
    try:
        # Start monitoring collector logs in the background
        log_process = subprocess.Popen([
            "kubectl", "logs", "-n", "monitor",
            "-l", "app=otel-collector",
            "-f", "--tail=10"
        ], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        
        print("   Started log monitoring...")
        time.sleep(2)
        
        # Send a simple test metric using curl
        test_payload = '''
{
  "resourceMetrics": [
    {
      "resource": {
        "attributes": [
          {
            "key": "service.name",
            "value": {
              "stringValue": "test-service"
            }
          }
        ]
      },
      "scopeMetrics": [
        {
          "scope": {
            "name": "test"
          },
          "metrics": [
            {
              "name": "test_counter",
              "description": "A test counter",
              "unit": "1",
              "sum": {
                "dataPoints": [
                  {
                    "attributes": [
                      {
                        "key": "test_label",
                        "value": {
                          "stringValue": "test_value"
                        }
                      }
                    ],
                    "timeUnixNano": "1640995200000000000",
                    "asInt": "1"
                  }
                ]
              }
            }
          ]
        }
      ]
    }
  ]
}
'''
        
        # Send test metric
        curl_result = subprocess.run([
            "curl", "-X", "POST",
            "http://192.168.0.101:4318/v1/metrics",
            "-H", "Content-Type: application/json",
            "-d", test_payload
        ], capture_output=True, text=True, timeout=10)
        
        print(f"   Test metric sent: HTTP response code {curl_result.returncode}")
        if curl_result.stdout:
            print(f"   Response: {curl_result.stdout}")
        
        # Wait for logs and check output
        time.sleep(5)
        
        # Stop log monitoring and get output
        log_process.terminate()
        try:
            stdout, stderr = log_process.communicate(timeout=5)
            if stdout:
                print("   Collector debug output after test metric:")
                for line in stdout.split('\n')[-10:]:
                    if line.strip():
                        print(f"     {line}")
        except subprocess.TimeoutExpired:
            log_process.kill()
        
    except Exception as e:
        print(f"❌ Error testing metric send: {e}")
        return False
    
    # Step 3: Check collector configuration
    print("\n⚙️  Step 3: Checking collector configuration...")
    
    try:
        config_result = subprocess.run([
            "kubectl", "get", "configmap", "-n", "monitor",
            "otel-collector-config", "-o", "yaml"
        ], capture_output=True, text=True, timeout=30)
        
        if config_result.returncode == 0:
            config = config_result.stdout
            
            # Check for key configuration elements
            has_otlp_receiver = "otlp:" in config
            has_prometheus_exporter = "prometheus:" in config
            has_debug_exporter = "debug:" in config
            has_metrics_pipeline = "metrics:" in config
            
            print(f"   OTLP receiver configured: {has_otlp_receiver}")
            print(f"   Prometheus exporter configured: {has_prometheus_exporter}")
            print(f"   Debug exporter configured: {has_debug_exporter}")
            print(f"   Metrics pipeline configured: {has_metrics_pipeline}")
            
            if all([has_otlp_receiver, has_prometheus_exporter, has_debug_exporter, has_metrics_pipeline]):
                print("✅ Collector configuration appears correct")
            else:
                print("❌ Collector configuration may have issues")
                return False
                
        else:
            print(f"❌ Failed to get collector config: {config_result.stderr}")
            return False
            
    except Exception as e:
        print(f"❌ Error checking collector config: {e}")
        return False
    
    print("\n🔍 Summary:")
    print("1. Collector logs retrieved successfully")
    print("2. Test metric sent to collector")
    print("3. Configuration appears correct")
    print("\nIf metrics still aren't appearing, the issue might be:")
    print("- Collector not processing metrics properly")
    print("- Prometheus exporter configuration issue")
    print("- Resource attribute processing issue")
    print("- Timing/batching issue")
    
    return True

if __name__ == "__main__":
    success = check_collector_debug()
    if success:
        print("\n✅ Collector debug check completed")
        sys.exit(0)
    else:
        print("\n❌ Issues found with collector")
        sys.exit(1)