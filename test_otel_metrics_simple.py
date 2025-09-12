#!/usr/bin/env python3
"""
Simple test to verify OpenTelemetry metrics are being created and sent.
This creates a minimal test to isolate the issue.
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

def test_otel_metrics():
    """Test OpenTelemetry metrics creation and export."""
    
    # Use the same configuration as your app
    collector_endpoint = os.getenv("OTEL_EXPORTER_OTLP_METRICS_ENDPOINT", "http://localhost:4318/v1/metrics")
    
    logger.info(f"Testing OpenTelemetry metrics export to: {collector_endpoint}")
    
    # Create resource with same attributes as your app
    resource = Resource.create({
        "service.name": "globeco-portfolio-service",
        "service.version": "1.0.0",
        "service.namespace": "globeco",
        "k8s.pod.name": "test-pod",
        "k8s.namespace.name": "globeco",
        "k8s.deployment.name": "globeco-portfolio-service",
    })
    
    # Create exporter
    exporter = OTLPMetricExporter(endpoint=collector_endpoint)
    
    # Create metric reader
    reader = PeriodicExportingMetricReader(
        exporter=exporter,
        export_interval_millis=5000,  # 5 seconds for testing
        export_timeout_millis=3000    # 3 seconds timeout
    )
    
    # Create meter provider
    meter_provider = MeterProvider(resource=resource, metric_readers=[reader])
    metrics.set_meter_provider(meter_provider)
    
    # Create meter and test metrics
    meter = metrics.get_meter(__name__)
    
    # Create the same metrics as your app
    http_requests_total = meter.create_counter(
        name="http_requests_total",
        description="Total number of HTTP requests",
        unit="1"
    )
    
    http_request_duration = meter.create_histogram(
        name="http_request_duration",
        description="HTTP request duration in milliseconds",
        unit="ms"
    )
    
    http_requests_in_flight = meter.create_up_down_counter(
        name="http_requests_in_flight",
        description="Number of HTTP requests currently being processed",
        unit="1"
    )
    
    logger.info("Created test metrics, recording data...")
    
    # Record test data with same attributes as your app
    test_attributes = {
        "method": "GET",
        "path": "/",
        "status": "200",
        "service_namespace": "globeco"
    }
    
    for i in range(5):
        # Simulate request processing
        http_requests_in_flight.add(1, attributes={"service_namespace": "globeco"})
        
        http_requests_total.add(1, attributes=test_attributes)
        http_request_duration.record(50 + i * 10, attributes=test_attributes)
        
        logger.info(f"Recorded test data point {i+1}/5")
        time.sleep(2)
        
        http_requests_in_flight.add(-1, attributes={"service_namespace": "globeco"})
    
    logger.info("Waiting for final export...")
    time.sleep(10)  # Wait for final export
    
    logger.info("Test completed. Check collector logs and Prometheus for metrics.")
    logger.info("Expected metrics in Prometheus:")
    logger.info("- http_requests_total{service_namespace=\"globeco\",method=\"GET\",path=\"/\",status=\"200\"}")
    logger.info("- http_request_duration_bucket{service_namespace=\"globeco\",method=\"GET\",path=\"/\",status=\"200\"}")

if __name__ == "__main__":
    test_otel_metrics()