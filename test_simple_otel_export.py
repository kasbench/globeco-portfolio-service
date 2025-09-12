#!/usr/bin/env python3
"""
Simple test to verify OpenTelemetry metrics export is working.
This creates a minimal setup to test metric export to the collector.
"""

import os
import time
import logging
from opentelemetry import metrics
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def test_otel_export():
    """Test OpenTelemetry metrics export."""
    
    # Get collector endpoint
    collector_endpoint = os.getenv("OTEL_EXPORTER_OTLP_METRICS_ENDPOINT", "http://localhost:4318/v1/metrics")
    
    logger.info(f"Testing OpenTelemetry export to: {collector_endpoint}")
    
    # Create resource
    resource = Resource.create({
        "service.name": "test-service",
        "service.version": "1.0.0",
        "service.namespace": "globeco",
    })
    
    # Create exporter
    exporter = OTLPMetricExporter(endpoint=collector_endpoint)
    
    # Create metric reader with short export interval for testing
    reader = PeriodicExportingMetricReader(
        exporter=exporter,
        export_interval_millis=5000,  # 5 seconds
        export_timeout_millis=3000    # 3 seconds
    )
    
    # Create meter provider
    meter_provider = MeterProvider(resource=resource, metric_readers=[reader])
    metrics.set_meter_provider(meter_provider)
    
    # Create meter and metrics
    meter = metrics.get_meter(__name__)
    
    test_counter = meter.create_counter(
        name="test_requests_total",
        description="Test counter for debugging",
        unit="1"
    )
    
    test_histogram = meter.create_histogram(
        name="test_request_duration",
        description="Test histogram for debugging",
        unit="ms"
    )
    
    logger.info("Created test metrics, starting to record data...")
    
    # Record some test data
    for i in range(10):
        test_counter.add(1, attributes={
            "method": "GET",
            "status": "200",
            "service_namespace": "globeco"
        })
        
        test_histogram.record(100 + i * 10, attributes={
            "method": "GET", 
            "status": "200",
            "service_namespace": "globeco"
        })
        
        logger.info(f"Recorded test data point {i+1}/10")
        time.sleep(1)
    
    logger.info("Waiting for final export...")
    time.sleep(10)  # Wait for final export
    
    logger.info("Test completed. Check collector logs and Prometheus for test_requests_total and test_request_duration metrics.")

if __name__ == "__main__":
    test_otel_export()