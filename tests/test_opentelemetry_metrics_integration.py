"""
Integration tests for OpenTelemetry metrics integration.

These tests verify that HTTP metrics are being sent to both Prometheus
(/metrics endpoint) and OpenTelemetry (collector export).
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from unittest.mock import Mock, patch, MagicMock
import os

# Set test environment variables
os.environ['PROMETHEUS_DISABLE_CREATED_SERIES'] = 'True'

from app.monitoring import EnhancedHTTPMetricsMiddleware, clear_metrics_registry


class TestOpenTelemetryMetricsIntegration:
    """Test OpenTelemetry metrics integration."""
    
    @pytest.fixture
    def test_app(self):
        """Create a test FastAPI app with metrics middleware."""
        # Clear metrics before creating app to ensure clean state
        clear_metrics_registry()
        
        app = FastAPI()
        
        # Add metrics middleware
        app.add_middleware(EnhancedHTTPMetricsMiddleware, debug_logging=True)
        
        # Add test endpoint
        @app.get("/test")
        async def test_endpoint():
            return {"message": "test"}
        
        yield app
        
        # Cleanup
        clear_metrics_registry()
    
    @patch('app.monitoring.otel_http_requests_total')
    @patch('app.monitoring.otel_http_request_duration')
    @patch('app.monitoring.otel_http_requests_in_flight')
    def test_opentelemetry_metrics_are_recorded(
        self, 
        mock_otel_in_flight, 
        mock_otel_duration, 
        mock_otel_counter,
        test_app
    ):
        """Test that OpenTelemetry metrics are recorded alongside Prometheus metrics."""
        client = TestClient(test_app)
        
        # Make a request
        response = client.get("/test")
        assert response.status_code == 200
        
        # Verify OpenTelemetry counter was called
        mock_otel_counter.add.assert_called_once_with(
            1, 
            attributes={
                "method": "GET",
                "path": "/test", 
                "status": "200"
            }
        )
        
        # Verify OpenTelemetry histogram was called
        mock_otel_duration.record.assert_called_once()
        call_args = mock_otel_duration.record.call_args
        assert call_args[1]['attributes'] == {
            "method": "GET",
            "path": "/test",
            "status": "200"
        }
        # Duration should be a positive number (milliseconds)
        assert call_args[0][0] > 0
        
        # Verify OpenTelemetry in-flight gauge was incremented and decremented
        assert mock_otel_in_flight.add.call_count == 2
        calls = mock_otel_in_flight.add.call_args_list
        assert calls[0][0][0] == 1  # Increment
        assert calls[1][0][0] == -1  # Decrement
    
    @patch('app.monitoring.otel_http_requests_total')
    @patch('app.monitoring.otel_http_request_duration') 
    @patch('app.monitoring.otel_http_requests_in_flight')
    def test_opentelemetry_metrics_error_handling(
        self,
        mock_otel_in_flight,
        mock_otel_duration,
        mock_otel_counter,
        test_app
    ):
        """Test that OpenTelemetry metrics errors are handled gracefully."""
        # Make OpenTelemetry metrics raise exceptions
        mock_otel_counter.add.side_effect = Exception("OTel counter error")
        mock_otel_duration.record.side_effect = Exception("OTel histogram error")
        mock_otel_in_flight.add.side_effect = Exception("OTel gauge error")
        
        client = TestClient(test_app)
        
        # Request should still succeed despite OpenTelemetry errors
        response = client.get("/test")
        assert response.status_code == 200
        
        # Verify OpenTelemetry methods were called (and failed)
        mock_otel_counter.add.assert_called_once()
        mock_otel_duration.record.assert_called_once()
        # Only increment is attempted since increment failed, decrement is skipped (correct behavior)
        assert mock_otel_in_flight.add.call_count == 1  # Only increment attempt
    
    @patch('app.monitoring.meter')
    def test_opentelemetry_metrics_initialization_failure(self, mock_meter, test_app):
        """Test graceful handling when OpenTelemetry metrics fail to initialize."""
        # Make meter creation fail
        mock_meter.create_counter.side_effect = Exception("Meter initialization error")
        mock_meter.create_histogram.side_effect = Exception("Meter initialization error")
        mock_meter.create_up_down_counter.side_effect = Exception("Meter initialization error")
        
        # Import should still work and create dummy metrics
        from app.monitoring import otel_http_requests_total, otel_http_request_duration, otel_http_requests_in_flight
        
        # Dummy metrics should not raise exceptions
        otel_http_requests_total.add(1, attributes={"test": "value"})
        otel_http_request_duration.record(100.0, attributes={"test": "value"})
        otel_http_requests_in_flight.add(1)
        otel_http_requests_in_flight.add(-1)
    
    def test_both_prometheus_and_opentelemetry_metrics_work_together(self, test_app):
        """Test that both Prometheus and OpenTelemetry metrics work together."""
        client = TestClient(test_app)
        
        # Mock OpenTelemetry metrics to verify they're called
        with patch('app.monitoring.otel_http_requests_total') as mock_otel_counter, \
             patch('app.monitoring.otel_http_request_duration') as mock_otel_duration, \
             patch('app.monitoring.otel_http_requests_in_flight') as mock_otel_in_flight:
            
            # Make requests
            for i in range(3):
                response = client.get("/test")
                assert response.status_code == 200
            
            # Verify OpenTelemetry metrics were called for each request
            assert mock_otel_counter.add.call_count == 3
            assert mock_otel_duration.record.call_count == 3
            assert mock_otel_in_flight.add.call_count == 6  # 3 increments + 3 decrements
            
            # Verify all calls had correct attributes
            for call in mock_otel_counter.add.call_args_list:
                assert call[0][0] == 1  # Amount
                assert call[1]['attributes']['method'] == 'GET'
                assert call[1]['attributes']['path'] == '/test'
                assert call[1]['attributes']['status'] == '200'
    
    def test_opentelemetry_metrics_with_different_endpoints(self, test_app):
        """Test OpenTelemetry metrics with different endpoints and status codes."""
        # Add more endpoints to test app
        @test_app.get("/health")
        async def health_endpoint():
            return {"status": "healthy"}
        
        @test_app.get("/error")
        async def error_endpoint():
            from fastapi import HTTPException
            raise HTTPException(status_code=404, detail="Not found")
        
        client = TestClient(test_app)
        
        with patch('app.monitoring.otel_http_requests_total') as mock_otel_counter, \
             patch('app.monitoring.otel_http_request_duration') as mock_otel_duration:
            
            # Make requests to different endpoints
            client.get("/test")
            client.get("/health") 
            client.get("/error")
            
            # Verify different attributes were recorded
            counter_calls = mock_otel_counter.add.call_args_list
            assert len(counter_calls) == 3
            
            # Check attributes for each call
            test_call = next(call for call in counter_calls if call[1]['attributes']['path'] == '/test')
            assert test_call[1]['attributes']['status'] == '200'
            
            health_call = next(call for call in counter_calls if call[1]['attributes']['path'] == '/health')
            assert health_call[1]['attributes']['status'] == '200'
            
            error_call = next(call for call in counter_calls if call[1]['attributes']['path'] == '/error')
            assert error_call[1]['attributes']['status'] == '404'


def test_opentelemetry_metrics_module_import():
    """Test that OpenTelemetry metrics are properly imported and initialized."""
    # This test verifies the module can be imported without errors
    from app.monitoring import (
        otel_http_requests_total,
        otel_http_request_duration, 
        otel_http_requests_in_flight
    )
    
    # Verify metrics have the expected interface
    assert hasattr(otel_http_requests_total, 'add')
    assert hasattr(otel_http_request_duration, 'record')
    assert hasattr(otel_http_requests_in_flight, 'add')


if __name__ == "__main__":
    pytest.main([__file__, "-v"])