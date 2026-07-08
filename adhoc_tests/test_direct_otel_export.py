#!/usr/bin/env python3
"""
Direct test of OpenTelemetry export to verify if custom metrics can be exported.
This bypasses the middleware and directly tests the export pipeline.
"""

import time
import os
import sys

# Add the app directory to the path
sys.path.insert(0, '/app')

def test_direct_export():
    """Test direct OpenTelemetry export using the same configuration as the app."""
    
    print("🔍 Testing direct OpenTelemetry export...")
    
    # Import the same modules as the app
    from opentelemetry import metrics
    from opentelemetry.sdk.metrics import MeterProvider
    from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
    from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
    from opentelemetry.sdk.resources import Resource
    
    # Use the same configuration as the app
    resource = Resource.create({
        "service.name": "globeco-portfolio-service",
        "service.version": "1.0.0",
        "service.namespace": "globeco",
        "k8s.namespace.name": "globeco",
        "k8s.deployment.name": "globeco-portfolio-service"
    })
    
    # Use the same endpoint as the app
    endpoint = os.getenv("OTEL_EXPORTER_OTLP_METRICS_ENDPOINT", "http://192.168.0.101:4318/v1/metrics")
    print(f"   Using endpoint: {endpoint}")
    
    # Create the same exporter configuration
    metric_exporter = OTLPMetricExporter(endpoint=endpoint)
    
    # Use shorter intervals for testing
    metric_reader = PeriodicExportingMetricReader(
        exporter=metric_exporter,
        export_interval_millis=2000,  # 2 seconds
        export_timeout_millis=5000    # 5 seconds
    )
    
    meter_provider = MeterProvider(
        resource=resource,
        metric_readers=[metric_reader]
    )
    metrics.set_meter_provider(meter_provider)
    
    print("✅ Meter provider configured")
    
    # Create a test meter with the same name as the app
    meter = metrics.get_meter("app.monitoring")
    
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
    
    print("✅ Test metrics created")
    
    # Record test data with the same attributes as the app
    print("📊 Recording test metrics...")
    
    for i in range(5):
        # Use the same attribute structure as the app
        attributes = {
            "method": "GET",
            "path": f"/test/{i}",
            "status": "200",
            "service_name": "globeco-portfolio-service"
        }
        
        test_counter.add(1, attributes=attributes)
        test_histogram.record(100 + i * 10, attributes=attributes)
        test_gauge.add(1, attributes={"service_name": "globeco-portfolio-service"})
        
        print(f"   Recorded test batch {i+1}")
        time.sleep(0.5)
    
    print("✅ Test metrics recorded")
    
    # Wait for export
    print("⏳ Waiting for export (10 seconds)...")
    time.sleep(10)
    
    print("✅ Direct export test completed")
    print("\nNow check the collector for metrics with:")
    print('curl "http://localhost:8889/metrics" | grep "app\\.monitoring"')
    
    return True

if __name__ == "__main__":
    try:
        test_direct_export()
        print("\n🎉 Direct export test completed successfully")
    except Exception as e:
        print(f"\n💥 Direct export test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)