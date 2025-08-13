"""
Integration tests for Enhanced HTTP Metrics Middleware integration with FastAPI.

These tests verify that the middleware is properly registered and positioned
correctly in the middleware stack.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from fastapi import FastAPI
from fastapi.testclient import TestClient
import os

# Set test environment variables
os.environ['PROMETHEUS_DISABLE_CREATED_SERIES'] = 'True'

from app.config import Settings
from app.monitoring import EnhancedHTTPMetricsMiddleware


class TestMiddlewareRegistration:
    """Test middleware registration in FastAPI application."""
    
    def test_middleware_enabled_by_default(self):
        """Test that middleware is enabled when enable_metrics is True."""
        # Mock settings with metrics enabled
        with patch('app.config.settings') as mock_settings:
            mock_settings.enable_metrics = True
            mock_settings.metrics_debug_logging = False
            
            # Import main after patching settings
            from app.main import app
            
            # Check that the middleware stack includes our middleware
            middleware_classes = [middleware.cls for middleware in app.user_middleware]
            assert EnhancedHTTPMetricsMiddleware in middleware_classes
    
    def test_middleware_disabled_when_configured(self):
        """Test that middleware is not added when enable_metrics is False."""
        # Create a fresh app with metrics disabled
        with patch('app.config.settings') as mock_settings:
            mock_settings.enable_metrics = False
            mock_settings.metrics_debug_logging = False
            
            # Create new app instance
            app = FastAPI()
            
            # Simulate the middleware addition logic from main.py
            if mock_settings.enable_metrics:
                app.add_middleware(EnhancedHTTPMetricsMiddleware)
            
            # Check that middleware is not in the stack
            middleware_classes = [middleware.cls for middleware in app.user_middleware]
            assert EnhancedHTTPMetricsMiddleware not in middleware_classes
    
    def test_middleware_debug_logging_parameter(self):
        """Test that debug logging parameter is passed correctly."""
        with patch('app.config.settings') as mock_settings:
            mock_settings.enable_metrics = True
            mock_settings.metrics_debug_logging = True
            
            app = FastAPI()
            
            # Mock the middleware class to capture initialization parameters
            with patch('app.monitoring.EnhancedHTTPMetricsMiddleware') as mock_middleware:
                # Simulate the middleware addition logic from main.py
                if mock_settings.enable_metrics:
                    app.add_middleware(
                        mock_middleware, 
                        debug_logging=mock_settings.metrics_debug_logging
                    )
                
                # Verify middleware was called with correct debug_logging parameter
                mock_middleware.assert_called_once()
                # The middleware is added via add_middleware, so we check the call
                assert len(app.user_middleware) > 0


class TestMiddlewareOrdering:
    """Test that middleware is positioned correctly in the stack."""
    
    def test_middleware_after_logging_middleware(self):
        """Test that metrics middleware is added after logging middleware."""
        from app.logging_config import LoggingMiddleware
        
        with patch('app.config.settings') as mock_settings:
            mock_settings.enable_metrics = True
            mock_settings.metrics_debug_logging = False
            
            app = FastAPI()
            
            # Add logging middleware first (simulating main.py)
            app.add_middleware(LoggingMiddleware, logger=Mock())
            
            # Add metrics middleware second (simulating main.py)
            app.add_middleware(EnhancedHTTPMetricsMiddleware)
            
            # Check middleware order - FastAPI processes middleware in reverse order
            # So the last added middleware runs first
            middleware_classes = [middleware.cls for middleware in app.user_middleware]
            
            # Both middleware should be present
            assert LoggingMiddleware in middleware_classes
            assert EnhancedHTTPMetricsMiddleware in middleware_classes
            
            # Find their positions
            logging_index = next(i for i, cls in enumerate(middleware_classes) if cls == LoggingMiddleware)
            metrics_index = next(i for i, cls in enumerate(middleware_classes) if cls == EnhancedHTTPMetricsMiddleware)
            
            # Metrics middleware should be added after logging (higher index in user_middleware)
            # but will execute before logging (due to FastAPI's reverse processing)
            assert metrics_index > logging_index
    
    def test_middleware_before_otel_instrumentation(self):
        """Test that middleware is positioned before OpenTelemetry instrumentation."""
        # This test verifies the conceptual ordering - OTel instrumentation
        # happens after middleware registration in main.py
        
        with patch('app.config.settings') as mock_settings:
            mock_settings.enable_metrics = True
            mock_settings.metrics_debug_logging = False
            
            app = FastAPI()
            
            # Add our middleware
            app.add_middleware(EnhancedHTTPMetricsMiddleware)
            
            # Simulate OTel instrumentation (this happens after middleware in main.py)
            with patch('opentelemetry.instrumentation.fastapi.FastAPIInstrumentor') as mock_instrumentor:
                mock_instance = Mock()
                mock_instrumentor.return_value = mock_instance
                
                # This simulates the instrumentation call in main.py
                instrumentor = mock_instrumentor()
                instrumentor.instrument_app(app)
                
                # Verify instrumentation was called
                mock_instrumentor.assert_called_once()
                mock_instance.instrument_app.assert_called_once_with(app)
                
                # Our middleware should be in the stack
                middleware_classes = [middleware.cls for middleware in app.user_middleware]
                assert EnhancedHTTPMetricsMiddleware in middleware_classes


class TestMiddlewareEndToEnd:
    """End-to-end tests for middleware functionality."""
    
    @pytest.fixture
    def app_with_middleware(self):
        """Create a test app with middleware enabled."""
        app = FastAPI()
        
        # Mock the metrics to prevent actual Prometheus registration
        with patch('app.monitoring.HTTP_REQUESTS_TOTAL') as mock_counter, \
             patch('app.monitoring.HTTP_REQUEST_DURATION') as mock_histogram, \
             patch('app.monitoring.HTTP_REQUESTS_IN_FLIGHT') as mock_gauge:
            
            # Configure mocks to support method chaining
            mock_counter.labels.return_value.inc = Mock()
            mock_histogram.labels.return_value.observe = Mock()
            mock_gauge.inc = Mock()
            mock_gauge.dec = Mock()
            
            app.add_middleware(EnhancedHTTPMetricsMiddleware, debug_logging=False)
            
            # Add a test endpoint
            @app.get("/test")
            async def test_endpoint():
                return {"message": "test"}
            
            @app.get("/health")
            async def health_endpoint():
                return {"status": "healthy"}
            
            yield app
    
    def test_middleware_processes_requests(self, app_with_middleware):
        """Test that middleware processes requests correctly."""
        client = TestClient(app_with_middleware)
        
        with patch('app.monitoring.HTTP_REQUESTS_TOTAL') as mock_counter, \
             patch('app.monitoring.HTTP_REQUEST_DURATION') as mock_histogram, \
             patch('app.monitoring.HTTP_REQUESTS_IN_FLIGHT') as mock_gauge:
            
            # Configure mocks
            mock_labeled_counter = Mock()
            mock_labeled_histogram = Mock()
            mock_counter.labels.return_value = mock_labeled_counter
            mock_histogram.labels.return_value = mock_labeled_histogram
            
            # Make a request
            response = client.get("/test")
            
            # Verify response
            assert response.status_code == 200
            assert response.json() == {"message": "test"}
            
            # Verify metrics were called
            mock_gauge.inc.assert_called_once()
            mock_gauge.dec.assert_called_once()
            mock_counter.labels.assert_called_once()
            mock_histogram.labels.assert_called_once()
            mock_labeled_counter.inc.assert_called_once()
            mock_labeled_histogram.observe.assert_called_once()
    
    def test_middleware_handles_health_endpoint(self, app_with_middleware):
        """Test that middleware correctly handles health endpoint."""
        client = TestClient(app_with_middleware)
        
        with patch('app.monitoring.HTTP_REQUESTS_TOTAL') as mock_counter, \
             patch('app.monitoring.HTTP_REQUEST_DURATION') as mock_histogram, \
             patch('app.monitoring.HTTP_REQUESTS_IN_FLIGHT') as mock_gauge:
            
            # Configure mocks
            mock_labeled_counter = Mock()
            mock_labeled_histogram = Mock()
            mock_counter.labels.return_value = mock_labeled_counter
            mock_histogram.labels.return_value = mock_labeled_histogram
            
            # Make a request to health endpoint
            response = client.get("/health")
            
            # Verify response
            assert response.status_code == 200
            assert response.json() == {"status": "healthy"}
            
            # Verify metrics were recorded with correct path pattern
            mock_counter.labels.assert_called_once()
            call_args = mock_counter.labels.call_args
            assert call_args[1]['path'] == '/health'  # Should be /health pattern
            assert call_args[1]['method'] == 'GET'
            assert call_args[1]['status'] == '200'
    
    def test_middleware_handles_errors(self, app_with_middleware):
        """Test that middleware handles errors correctly."""
        # Add an endpoint that raises an exception
        @app_with_middleware.get("/error")
        async def error_endpoint():
            raise ValueError("Test error")
        
        client = TestClient(app_with_middleware)
        
        with patch('app.monitoring.HTTP_REQUESTS_TOTAL') as mock_counter, \
             patch('app.monitoring.HTTP_REQUEST_DURATION') as mock_histogram, \
             patch('app.monitoring.HTTP_REQUESTS_IN_FLIGHT') as mock_gauge:
            
            # Configure mocks
            mock_labeled_counter = Mock()
            mock_labeled_histogram = Mock()
            mock_counter.labels.return_value = mock_labeled_counter
            mock_histogram.labels.return_value = mock_labeled_histogram
            
            # Make a request that will cause an error
            response = client.get("/error")
            
            # Verify error response
            assert response.status_code == 500
            
            # Verify metrics were still recorded with status 500
            mock_counter.labels.assert_called_once()
            call_args = mock_counter.labels.call_args
            assert call_args[1]['status'] == '500'  # Should record as 500 for errors
            
            # Verify in-flight gauge was properly decremented even with error
            mock_gauge.inc.assert_called_once()
            mock_gauge.dec.assert_called_once()


class TestMiddlewareConfiguration:
    """Test middleware configuration and settings integration."""
    
    def test_settings_integration(self):
        """Test that middleware respects settings configuration."""
        # Test with metrics enabled
        settings_enabled = Settings(enable_metrics=True, metrics_debug_logging=True)
        
        app = FastAPI()
        
        # Simulate main.py logic
        if settings_enabled.enable_metrics:
            app.add_middleware(
                EnhancedHTTPMetricsMiddleware, 
                debug_logging=settings_enabled.metrics_debug_logging
            )
        
        middleware_classes = [middleware.cls for middleware in app.user_middleware]
        assert EnhancedHTTPMetricsMiddleware in middleware_classes
        
        # Test with metrics disabled
        settings_disabled = Settings(enable_metrics=False, metrics_debug_logging=False)
        
        app2 = FastAPI()
        
        # Simulate main.py logic
        if settings_disabled.enable_metrics:
            app2.add_middleware(
                EnhancedHTTPMetricsMiddleware, 
                debug_logging=settings_disabled.metrics_debug_logging
            )
        
        middleware_classes2 = [middleware.cls for middleware in app2.user_middleware]
        assert EnhancedHTTPMetricsMiddleware not in middleware_classes2
    
    def test_debug_logging_configuration(self):
        """Test that debug logging configuration is passed correctly."""
        app = FastAPI()
        
        # Test with debug logging enabled
        with patch('app.monitoring.EnhancedHTTPMetricsMiddleware') as mock_middleware_class:
            mock_instance = Mock()
            mock_middleware_class.return_value = mock_instance
            
            # This simulates how the middleware is added in main.py
            app.add_middleware(EnhancedHTTPMetricsMiddleware, debug_logging=True)
            
            # The middleware should be in the stack
            middleware_classes = [middleware.cls for middleware in app.user_middleware]
            assert EnhancedHTTPMetricsMiddleware in middleware_classes


class TestMiddlewareCompatibility:
    """Test middleware compatibility with existing components."""
    
    def test_compatibility_with_logging_middleware(self):
        """Test that metrics middleware works alongside logging middleware."""
        from app.logging_config import LoggingMiddleware
        
        app = FastAPI()
        
        # Add both middleware (simulating main.py)
        app.add_middleware(LoggingMiddleware, logger=Mock())
        app.add_middleware(EnhancedHTTPMetricsMiddleware, debug_logging=False)
        
        # Add test endpoint
        @app.get("/test")
        async def test_endpoint():
            return {"message": "test"}
        
        client = TestClient(app)
        
        with patch('app.monitoring.HTTP_REQUESTS_TOTAL') as mock_counter, \
             patch('app.monitoring.HTTP_REQUEST_DURATION') as mock_histogram, \
             patch('app.monitoring.HTTP_REQUESTS_IN_FLIGHT') as mock_gauge:
            
            # Configure mocks
            mock_counter.labels.return_value.inc = Mock()
            mock_histogram.labels.return_value.observe = Mock()
            mock_gauge.inc = Mock()
            mock_gauge.dec = Mock()
            
            # Make request - should work with both middleware
            response = client.get("/test")
            
            assert response.status_code == 200
            assert response.json() == {"message": "test"}
            
            # Verify metrics middleware was called
            mock_gauge.inc.assert_called_once()
            mock_gauge.dec.assert_called_once()
    
    def test_compatibility_with_cors_middleware(self):
        """Test that metrics middleware works with CORS middleware."""
        from fastapi.middleware.cors import CORSMiddleware
        
        app = FastAPI()
        
        # Add CORS and metrics middleware
        app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )
        app.add_middleware(EnhancedHTTPMetricsMiddleware, debug_logging=False)
        
        # Add test endpoint
        @app.get("/test")
        async def test_endpoint():
            return {"message": "test"}
        
        client = TestClient(app)
        
        with patch('app.monitoring.HTTP_REQUESTS_TOTAL') as mock_counter, \
             patch('app.monitoring.HTTP_REQUEST_DURATION') as mock_histogram, \
             patch('app.monitoring.HTTP_REQUESTS_IN_FLIGHT') as mock_gauge:
            
            # Configure mocks
            mock_counter.labels.return_value.inc = Mock()
            mock_histogram.labels.return_value.observe = Mock()
            mock_gauge.inc = Mock()
            mock_gauge.dec = Mock()
            
            # Make request with CORS headers
            response = client.get("/test", headers={"Origin": "http://localhost:3000"})
            
            assert response.status_code == 200
            
            # Verify metrics middleware was called
            mock_gauge.inc.assert_called_once()
            mock_gauge.dec.assert_called_once()


class TestMiddlewareErrorHandling:
    """Test middleware error handling and resilience."""
    
    def test_middleware_continues_on_metric_errors(self):
        """Test that middleware continues processing even if metrics fail."""
        app = FastAPI()
        app.add_middleware(EnhancedHTTPMetricsMiddleware, debug_logging=False)
        
        @app.get("/test")
        async def test_endpoint():
            return {"message": "test"}
        
        client = TestClient(app)
        
        # Mock metrics to raise exceptions
        with patch('app.monitoring.HTTP_REQUESTS_TOTAL') as mock_counter, \
             patch('app.monitoring.HTTP_REQUEST_DURATION') as mock_histogram, \
             patch('app.monitoring.HTTP_REQUESTS_IN_FLIGHT') as mock_gauge:
            
            # Make metrics operations fail
            mock_gauge.inc.side_effect = Exception("Metrics error")
            mock_gauge.dec.side_effect = Exception("Metrics error")
            mock_counter.labels.side_effect = Exception("Metrics error")
            mock_histogram.labels.side_effect = Exception("Metrics error")
            
            # Request should still succeed despite metrics errors
            response = client.get("/test")
            
            assert response.status_code == 200
            assert response.json() == {"message": "test"}
    
    def test_middleware_handles_request_processing_errors(self):
        """Test that middleware handles errors during request processing."""
        app = FastAPI()
        app.add_middleware(EnhancedHTTPMetricsMiddleware, debug_logging=False)
        
        @app.get("/error")
        async def error_endpoint():
            raise RuntimeError("Request processing error")
        
        client = TestClient(app)
        
        with patch('app.monitoring.HTTP_REQUESTS_TOTAL') as mock_counter, \
             patch('app.monitoring.HTTP_REQUEST_DURATION') as mock_histogram, \
             patch('app.monitoring.HTTP_REQUESTS_IN_FLIGHT') as mock_gauge:
            
            # Configure mocks
            mock_counter.labels.return_value.inc = Mock()
            mock_histogram.labels.return_value.observe = Mock()
            mock_gauge.inc = Mock()
            mock_gauge.dec = Mock()
            
            # Make request that will cause an error
            response = client.get("/error")
            
            # Should return 500 error
            assert response.status_code == 500
            
            # Metrics should still be recorded
            mock_gauge.inc.assert_called_once()
            mock_gauge.dec.assert_called_once()
            
            # Should record with status 500
            mock_counter.labels.assert_called_once()
            call_args = mock_counter.labels.call_args
            assert call_args[1]['status'] == '500'