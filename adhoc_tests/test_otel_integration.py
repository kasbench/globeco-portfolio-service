#!/usr/bin/env python3
"""
Quick test to verify OpenTelemetry metrics are being created and exported.
This script can be run locally to test the metrics integration.
"""

import asyncio
import sys
import os
from unittest.mock import Mock, patch
import logging

# Add the app directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'app'))

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class MockOTelMetric:
    """Mock OpenTelemetry metric for testing."""
    def __init__(self, name):
        self.name = name
        self.calls = []
    
    def add(self, value, attributes=None):
        self.calls.append(('add', value, attributes))
        logger.info(f"OTel {self.name}: add({value}) with attributes {attributes}")
    
    def record(self, value, attributes=None):
        self.calls.append(('record', value, attributes))
        logger.info(f"OTel {self.name}: record({value}) with attributes {attributes}")

class MockMeter:
    """Mock OpenTelemetry meter for testing."""
    def __init__(self):
        self.metrics = {}
    
    def create_counter(self, name, description=None, unit=None):
        metric = MockOTelMetric(name)
        self.metrics[name] = metric
        logger.info(f"Created OTel counter: {name}")
        return metric
    
    def create_histogram(self, name, description=None, unit=None):
        metric = MockOTelMetric(name)
        self.metrics[name] = metric
        logger.info(f"Created OTel histogram: {name}")
        return metric
    
    def create_up_down_counter(self, name, description=None, unit=None):
        metric = MockOTelMetric(name)
        self.metrics[name] = metric
        logger.info(f"Created OTel up_down_counter: {name}")
        return metric

async def test_metrics_integration():
    """Test the OpenTelemetry metrics integration."""
    logger.info("Starting OpenTelemetry metrics integration test...")
    
    # Mock the OpenTelemetry metrics module
    mock_meter = MockMeter()
    
    with patch('opentelemetry.metrics.get_meter', return_value=mock_meter):
        # Import the monitoring module (this will create the metrics)
        try:
            from app import monitoring
            logger.info("✅ Successfully imported monitoring module")
        except Exception as e:
            logger.error(f"❌ Failed to import monitoring module: {e}")
            return False
        
        # Check if OpenTelemetry metrics were created
        expected_metrics = [
            'http_requests_total',
            'http_request_duration', 
            'http_requests_in_flight',
            'http_workers_active',
            'http_workers_total',
            'http_workers_max_configured',
            'http_requests_queued'
        ]
        
        created_metrics = list(mock_meter.metrics.keys())
        logger.info(f"Created OTel metrics: {created_metrics}")
        
        missing_metrics = [m for m in expected_metrics if m not in created_metrics]
        if missing_metrics:
            logger.error(f"❌ Missing OTel metrics: {missing_metrics}")
            return False
        else:
            logger.info("✅ All expected OTel metrics were created")
        
        # Test the middleware
        try:
            from fastapi import FastAPI, Request, Response
            from fastapi.testclient import TestClient
            
            # Create a test app
            app = FastAPI()
            
            # Add the monitoring middleware
            app.add_middleware(
                monitoring.EnhancedHTTPMetricsMiddleware,
                debug_logging=True
            )
            
            @app.get("/test")
            async def test_endpoint():
                return {"message": "test"}
            
            # Create test client
            client = TestClient(app)
            
            # Make a test request
            logger.info("Making test request to trigger metrics...")
            response = client.get("/test")
            
            if response.status_code == 200:
                logger.info("✅ Test request successful")
                
                # Check if metrics were recorded
                http_requests_total = mock_meter.metrics.get('http_requests_total')
                http_request_duration = mock_meter.metrics.get('http_request_duration')
                http_requests_in_flight = mock_meter.metrics.get('http_requests_in_flight')
                
                if http_requests_total and http_requests_total.calls:
                    logger.info(f"✅ http_requests_total recorded: {http_requests_total.calls}")
                else:
                    logger.error("❌ http_requests_total not recorded")
                    return False
                
                if http_request_duration and http_request_duration.calls:
                    logger.info(f"✅ http_request_duration recorded: {http_request_duration.calls}")
                else:
                    logger.error("❌ http_request_duration not recorded")
                    return False
                
                if http_requests_in_flight and http_requests_in_flight.calls:
                    logger.info(f"✅ http_requests_in_flight recorded: {http_requests_in_flight.calls}")
                else:
                    logger.error("❌ http_requests_in_flight not recorded")
                    return False
                
                logger.info("✅ All HTTP metrics were recorded successfully")
                return True
            else:
                logger.error(f"❌ Test request failed: {response.status_code}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Error testing middleware: {e}")
            return False

def main():
    """Main test function."""
    logger.info("🧪 OpenTelemetry Metrics Integration Test")
    logger.info("=" * 50)
    
    # Set environment variables for testing
    os.environ['ENABLE_METRICS'] = 'true'
    os.environ['METRICS_DEBUG_LOGGING'] = 'true'
    os.environ['OTEL_METRICS_LOGGING_ENABLED'] = 'true'
    
    # Run the test
    success = asyncio.run(test_metrics_integration())
    
    if success:
        logger.info("🎉 All tests passed! OpenTelemetry metrics integration is working.")
        print("\n✅ RESULT: OpenTelemetry metrics integration is working correctly")
        print("📝 The custom metrics should now be sent to the OpenTelemetry collector")
        print("🔍 Next steps:")
        print("   1. Deploy the updated configuration")
        print("   2. Check collector logs for incoming metrics")
        print("   3. Verify metrics appear in Prometheus")
        return 0
    else:
        logger.error("❌ Tests failed! There are issues with the OpenTelemetry metrics integration.")
        print("\n❌ RESULT: OpenTelemetry metrics integration has issues")
        print("🔧 Check the logs above for specific error details")
        return 1

if __name__ == "__main__":
    sys.exit(main())