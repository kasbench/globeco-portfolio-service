#!/usr/bin/env python3
"""
Debug script to check if metrics are being recorded properly.
This script simulates the metrics recording process to identify issues.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def debug_metrics_recording():
    """Debug the metrics recording process step by step."""
    
    print("🔍 Debugging metrics recording process...")
    
    # Step 1: Check if we can import the monitoring module
    print("\n📦 Step 1: Importing monitoring module...")
    try:
        from app.monitoring import (
            otel_http_requests_total,
            otel_http_request_duration, 
            otel_http_requests_in_flight,
            HTTP_REQUESTS_TOTAL,
            HTTP_REQUEST_DURATION,
            HTTP_REQUESTS_IN_FLIGHT
        )
        print("✅ Successfully imported monitoring module")
    except Exception as e:
        print(f"❌ Failed to import monitoring module: {e}")
        return False
    
    # Step 2: Check initial state of metrics
    print("\n📊 Step 2: Checking initial state of metrics...")
    print(f"   Prometheus HTTP_REQUESTS_TOTAL: {type(HTTP_REQUESTS_TOTAL)}")
    print(f"   Prometheus HTTP_REQUEST_DURATION: {type(HTTP_REQUEST_DURATION)}")
    print(f"   Prometheus HTTP_REQUESTS_IN_FLIGHT: {type(HTTP_REQUESTS_IN_FLIGHT)}")
    print(f"   OpenTelemetry otel_http_requests_total: {type(otel_http_requests_total)}")
    print(f"   OpenTelemetry otel_http_request_duration: {type(otel_http_request_duration)}")
    print(f"   OpenTelemetry otel_http_requests_in_flight: {type(otel_http_requests_in_flight)}")
    
    # Check if OpenTelemetry metrics are None
    if otel_http_requests_total is None:
        print("⚠️  OpenTelemetry metrics are None - they need to be initialized")
        
        # Step 3: Try to initialize OpenTelemetry metrics
        print("\n🔧 Step 3: Attempting to initialize OpenTelemetry metrics...")
        try:
            # Set up a basic meter provider for testing
            from opentelemetry import metrics
            from opentelemetry.sdk.metrics import MeterProvider
            from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader, ConsoleMetricExporter
            from opentelemetry.sdk.resources import Resource
            
            resource = Resource.create({
                "service.name": "debug-test",
                "service.namespace": "debug"
            })
            
            reader = PeriodicExportingMetricReader(
                exporter=ConsoleMetricExporter(),
                export_interval_millis=5000
            )
            
            meter_provider = MeterProvider(resource=resource, metric_readers=[reader])
            metrics.set_meter_provider(meter_provider)
            
            # Now initialize the metrics
            from app.monitoring import initialize_otel_metrics
            success = initialize_otel_metrics()
            
            if success:
                print("✅ OpenTelemetry metrics initialized successfully")
            else:
                print("❌ OpenTelemetry metrics initialization failed")
                return False
                
        except Exception as e:
            print(f"❌ Failed to initialize OpenTelemetry metrics: {e}")
            return False
    else:
        print("✅ OpenTelemetry metrics are already initialized")
    
    # Step 4: Test recording metrics
    print("\n📈 Step 4: Testing metrics recording...")
    
    # Re-import to get updated references
    from app.monitoring import (
        otel_http_requests_total,
        otel_http_request_duration, 
        otel_http_requests_in_flight
    )
    
    try:
        # Test Prometheus metrics
        print("   Testing Prometheus metrics...")
        HTTP_REQUESTS_TOTAL.labels(method="GET", path="/debug", status="200").inc()
        HTTP_REQUEST_DURATION.labels(method="GET", path="/debug", status="200").observe(123.45)
        HTTP_REQUESTS_IN_FLIGHT.inc()
        print("   ✅ Prometheus metrics recorded successfully")
        
        # Test OpenTelemetry metrics
        print("   Testing OpenTelemetry metrics...")
        if otel_http_requests_total is not None:
            otel_http_requests_total.add(1, attributes={
                "method": "GET",
                "path": "/debug", 
                "status": "200",
                "service_name": "debug-test"
            })
            print("   ✅ OpenTelemetry counter recorded successfully")
        else:
            print("   ❌ OpenTelemetry counter is None")
            return False
            
        if otel_http_request_duration is not None:
            otel_http_request_duration.record(123.45, attributes={
                "method": "GET",
                "path": "/debug",
                "status": "200", 
                "service_name": "debug-test"
            })
            print("   ✅ OpenTelemetry histogram recorded successfully")
        else:
            print("   ❌ OpenTelemetry histogram is None")
            return False
            
        if otel_http_requests_in_flight is not None:
            otel_http_requests_in_flight.add(1, attributes={
                "service_name": "debug-test"
            })
            print("   ✅ OpenTelemetry up-down counter recorded successfully")
        else:
            print("   ❌ OpenTelemetry up-down counter is None")
            return False
            
    except Exception as e:
        print(f"   ❌ Error recording metrics: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    # Step 5: Test the middleware recording function
    print("\n🔧 Step 5: Testing middleware recording function...")
    try:
        from app.monitoring import EnhancedHTTPMetricsMiddleware
        
        # Create a dummy middleware instance
        class DummyApp:
            pass
        
        middleware = EnhancedHTTPMetricsMiddleware(DummyApp(), debug_logging=True)
        
        # Test the _record_metrics method directly
        middleware._record_metrics("GET", "/debug", "200", 123.45)
        print("   ✅ Middleware _record_metrics method executed successfully")
        
    except Exception as e:
        print(f"   ❌ Error testing middleware recording: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    print("\n🎉 All debugging steps completed successfully!")
    print("\nIf metrics are still not appearing in the collector, the issue is likely:")
    print("1. Metrics export configuration (endpoint, timing)")
    print("2. Network connectivity to collector")
    print("3. Collector processing/export configuration")
    
    return True

if __name__ == "__main__":
    success = debug_metrics_recording()
    if success:
        print("\n✅ Metrics recording appears to be working correctly.")
        sys.exit(0)
    else:
        print("\n❌ Issues found with metrics recording.")
        sys.exit(1)