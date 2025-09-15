#!/usr/bin/env python3
"""
Test script to verify OpenTelemetry export connectivity and timing.
This script tests the actual export pipeline used by the application.
"""

import sys
import os
import time
import requests
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def test_export_connectivity():
    """Test the OpenTelemetry export connectivity and configuration."""
    
    print("🔍 Testing OpenTelemetry export connectivity...")
    
    # Step 1: Test collector endpoint accessibility
    print("\n🌐 Step 1: Testing collector endpoint accessibility...")
    
    # Try different possible endpoints
    possible_endpoints = [
        "http://localhost:4318/v1/metrics",
        "http://192.168.0.101:4318/v1/metrics",  # Based on your logs
        "http://otel-collector.monitor.svc.cluster.local:4318/v1/metrics"
    ]
    
    accessible_endpoint = None
    for endpoint in possible_endpoints:
        try:
            # Try to make a simple HTTP request to the endpoint
            response = requests.post(endpoint, 
                                   headers={"Content-Type": "application/x-protobuf"},
                                   data=b"", 
                                   timeout=5)
            print(f"   {endpoint}: HTTP {response.status_code}")
            if response.status_code in [200, 400, 405]:  # 400/405 are OK - means endpoint exists
                accessible_endpoint = endpoint
                break
        except Exception as e:
            print(f"   {endpoint}: Error - {e}")
    
    if not accessible_endpoint:
        print("❌ No accessible collector endpoint found")
        return False
    
    print(f"✅ Found accessible endpoint: {accessible_endpoint}")
    
    # Step 2: Test with the same configuration as the app
    print("\n🔧 Step 2: Testing with application configuration...")
    
    try:
        from opentelemetry import metrics
        from opentelemetry.sdk.metrics import MeterProvider
        from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
        from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
        from opentelemetry.sdk.resources import Resource
        
        # Use the same resource as the app
        resource = Resource.create({
            "service.name": "globeco-portfolio-service",
            "service.version": "1.0.0",
            "service.namespace": "globeco",
            "k8s.namespace.name": "globeco",
            "k8s.deployment.name": "globeco-portfolio-service"
        })
        
        # Create exporter with the accessible endpoint
        metric_exporter = OTLPMetricExporter(endpoint=accessible_endpoint)
        
        # Use shorter intervals for testing
        metric_reader = PeriodicExportingMetricReader(
            exporter=metric_exporter,
            export_interval_millis=2000,  # 2 seconds instead of 10
            export_timeout_millis=5000    # 5 seconds timeout
        )
        
        meter_provider = MeterProvider(
            resource=resource,
            metric_readers=[metric_reader]
        )
        metrics.set_meter_provider(meter_provider)
        
        print("✅ Meter provider configured successfully")
        
    except Exception as e:
        print(f"❌ Failed to configure meter provider: {e}")
        return False
    
    # Step 3: Create and record test metrics
    print("\n📊 Step 3: Creating and recording test metrics...")
    
    try:
        meter = metrics.get_meter("test.export")
        
        # Create the same metrics as the app
        test_counter = meter.create_counter(
            name="http_requests_total",
            description="Test HTTP requests total",
            unit="1"
        )
        
        test_histogram = meter.create_histogram(
            name="http_request_duration", 
            description="Test HTTP request duration",
            unit="ms"
        )
        
        test_gauge = meter.create_up_down_counter(
            name="http_requests_in_flight",
            description="Test HTTP requests in flight",
            unit="1"
        )
        
        print("✅ Test metrics created successfully")
        
        # Record some test data
        for i in range(5):
            test_counter.add(1, attributes={
                "method": "GET",
                "path": f"/test/{i}",
                "status": "200",
                "service_name": "globeco-portfolio-service"
            })
            
            test_histogram.record(100 + i * 10, attributes={
                "method": "GET", 
                "path": f"/test/{i}",
                "status": "200",
                "service_name": "globeco-portfolio-service"
            })
            
            test_gauge.add(1, attributes={
                "service_name": "globeco-portfolio-service"
            })
            
            print(f"   Recorded test metrics batch {i+1}")
            time.sleep(0.5)
        
        print("✅ Test metrics recorded successfully")
        
    except Exception as e:
        print(f"❌ Failed to record test metrics: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    # Step 4: Wait for export and check collector
    print("\n⏳ Step 4: Waiting for export (10 seconds)...")
    time.sleep(10)
    
    # Step 5: Check if metrics appeared in collector
    print("\n📈 Step 5: Checking collector for exported metrics...")
    
    try:
        # Check collector metrics endpoint
        collector_metrics_url = accessible_endpoint.replace(":4318/v1/metrics", ":8889/metrics")
        response = requests.get(collector_metrics_url, timeout=10)
        
        if response.status_code == 200:
            metrics_text = response.text
            
            # Look for our test metrics
            http_requests_total_lines = [line for line in metrics_text.split('\n') 
                                       if 'http_requests_total' in line and 'globeco-portfolio-service' in line]
            http_request_duration_lines = [line for line in metrics_text.split('\n')
                                         if 'http_request_duration' in line and 'globeco-portfolio-service' in line]
            
            print(f"   Found http_requests_total metrics: {len(http_requests_total_lines)}")
            print(f"   Found http_request_duration metrics: {len(http_request_duration_lines)}")
            
            if http_requests_total_lines:
                print("   Sample metrics found:")
                for line in http_requests_total_lines[:2]:
                    print(f"     {line}")
                print("✅ Export is working - metrics found in collector!")
                return True
            else:
                print("❌ No test metrics found in collector")
                return False
        else:
            print(f"❌ Cannot access collector metrics endpoint: HTTP {response.status_code}")
            return False
            
    except Exception as e:
        print(f"❌ Error checking collector: {e}")
        return False

if __name__ == "__main__":
    success = test_export_connectivity()
    if success:
        print("\n🎉 Export connectivity is working!")
        print("\nThe issue might be:")
        print("1. Export interval too long in the app (currently 10 seconds)")
        print("2. Metrics not being recorded due to middleware issues")
        print("3. Different endpoint being used in production")
        sys.exit(0)
    else:
        print("\n💥 Export connectivity issues found!")
        print("\nTroubleshooting steps:")
        print("1. Check collector is running and accessible")
        print("2. Verify network connectivity from app to collector")
        print("3. Check collector logs for errors")
        print("4. Verify endpoint configuration matches")
        sys.exit(1)