#!/usr/bin/env python3
"""
Test script to verify the metrics initialization fix.
This script tests that OpenTelemetry metrics are properly initialized after the meter provider is set up.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from opentelemetry import metrics
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader, ConsoleMetricExporter
from opentelemetry.sdk.resources import Resource

def test_metrics_initialization():
    """Test that metrics are properly initialized after meter provider setup."""
    
    print("🔧 Testing OpenTelemetry metrics initialization fix...")
    
    # Step 1: Import monitoring module (this should not create metrics yet)
    print("📦 Importing monitoring module...")
    from app.monitoring import (
        otel_http_requests_total, 
        otel_http_request_duration, 
        otel_http_requests_in_flight,
        initialize_otel_metrics
    )
    
    # Check that metrics are None initially
    print(f"   otel_http_requests_total: {otel_http_requests_total}")
    print(f"   otel_http_request_duration: {otel_http_request_duration}")
    print(f"   otel_http_requests_in_flight: {otel_http_requests_in_flight}")
    
    if otel_http_requests_total is None:
        print("✅ Metrics are None before meter provider setup (correct)")
    else:
        print("❌ Metrics are not None before meter provider setup (incorrect)")
        return False
    
    # Step 2: Set up meter provider (like in main.py)
    print("\n🔧 Setting up meter provider...")
    resource = Resource.create({
        "service.name": "test-service",
        "service.namespace": "test"
    })
    
    # Use console exporter for testing
    reader = PeriodicExportingMetricReader(
        exporter=ConsoleMetricExporter(),
        export_interval_millis=5000
    )
    
    meter_provider = MeterProvider(resource=resource, metric_readers=[reader])
    metrics.set_meter_provider(meter_provider)
    print("✅ Meter provider set up")
    
    # Step 3: Initialize OpenTelemetry metrics
    print("\n📊 Initializing OpenTelemetry metrics...")
    success = initialize_otel_metrics()
    
    if success:
        print("✅ OpenTelemetry metrics initialized successfully")
    else:
        print("❌ OpenTelemetry metrics initialization failed")
        return False
    
    # Step 4: Check that metrics are now available
    from app.monitoring import (
        otel_http_requests_total, 
        otel_http_request_duration, 
        otel_http_requests_in_flight
    )
    
    print(f"   otel_http_requests_total: {type(otel_http_requests_total)}")
    print(f"   otel_http_request_duration: {type(otel_http_request_duration)}")
    print(f"   otel_http_requests_in_flight: {type(otel_http_requests_in_flight)}")
    
    if otel_http_requests_total is not None:
        print("✅ Metrics are available after initialization (correct)")
    else:
        print("❌ Metrics are still None after initialization (incorrect)")
        return False
    
    # Step 5: Test recording metrics
    print("\n📈 Testing metric recording...")
    try:
        # Test counter
        otel_http_requests_total.add(1, attributes={
            "method": "GET",
            "path": "/test",
            "status": "200",
            "service_name": "test-service"
        })
        print("✅ Counter metric recorded successfully")
        
        # Test histogram
        otel_http_request_duration.record(123.45, attributes={
            "method": "GET", 
            "path": "/test",
            "status": "200",
            "service_name": "test-service"
        })
        print("✅ Histogram metric recorded successfully")
        
        # Test up-down counter
        otel_http_requests_in_flight.add(1, attributes={
            "service_name": "test-service"
        })
        print("✅ Up-down counter metric recorded successfully")
        
        return True
        
    except Exception as e:
        print(f"❌ Error recording metrics: {e}")
        return False

if __name__ == "__main__":
    success = test_metrics_initialization()
    if success:
        print("\n🎉 All tests passed! The metrics initialization fix is working correctly.")
        sys.exit(0)
    else:
        print("\n💥 Tests failed! There are still issues with metrics initialization.")
        sys.exit(1)