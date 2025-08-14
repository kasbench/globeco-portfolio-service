"""
Unit tests for comprehensive error handling and logging in the enhanced HTTP metrics monitoring module.

These tests verify that all error scenarios are properly logged with appropriate context,
debug logging works correctly, and slow request detection functions as expected.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock, call
import time
from fastapi import Request, Response
from starlette.responses import Response as StarletteResponse

# Import after setting up test environment
import os
os.environ['PROMETHEUS_DISABLE_CREATED_SERIES'] = 'True'

from app.monitoring import (
    EnhancedHTTPMetricsMiddleware,
    _get_or_create_metric,
    _extract_route_pattern,
    _get_method_label,
    _format_status_code,
    _sanitize_unmatched_route,
    DummyMetric,
    clear_metrics_registry,
    HTTP_REQUESTS_TOTAL,
    HTTP_REQUEST_DURATION,
    HTTP_REQUESTS_IN_FLIGHT,
)


class TestComprehensiveErrorLogging:
    """Test comprehensive error logging throughout the monitoring module."""
    
    def setup_method(self):
        """Clear registry before each test."""
        clear_metrics_registry()
    
    def teardown_method(self):
        """Clear registry after each test."""
        clear_metrics_registry()
    
    @patch('app.monitoring.logger')
    def test_metric_creation_success_logging(self, mock_logger):
        """Test that successful metric creation is logged appropriately."""
        with patch('prometheus_client.Counter') as mock_counter:
            mock_instance = Mock()
            mock_counter.return_value = mock_instance
            
            metric = _get_or_create_metric(
                mock_counter,
                'test_success_metric',
                'Test success metric',
                ['method', 'path', 'status']
            )
            
            # Verify debug logging for creation attempt
            debug_calls = [call for call in mock_logger.debug.call_args_list 
                          if 'Attempting to create new metric' in str(call)]
            assert len(debug_calls) > 0
            
            # Verify info logging for successful creation
            info_calls = [call for call in mock_logger.info.call_args_list 
                         if 'Successfully created and registered metric' in str(call)]
            assert len(info_calls) > 0
            
            # Verify structured logging includes all expected fields
            info_call = info_calls[0]
            call_kwargs = info_call[1]  # Get keyword arguments
            assert 'metric_name' in call_kwargs
            assert 'metric_type' in call_kwargs
            assert 'registry_key' in call_kwargs
            assert 'has_labels' in call_kwargs
            assert 'label_count' in call_kwargs
            assert 'registry_size' in call_kwargs
    
    @patch('app.monitoring.logger')
    def test_metric_creation_duplicate_error_logging(self, mock_logger):
        """Test logging when duplicate metric registration occurs."""
        def failing_counter(*args, **kwargs):
            raise ValueError("Duplicated timeseries in CollectorRegistry")
        
        metric = _get_or_create_metric(
            failing_counter,
            'duplicate_metric',
            'Duplicate test metric',
            ['label1']
        )
        
        # Should return DummyMetric
        assert isinstance(metric, DummyMetric)
        
        # Verify warning logging for duplicate registration
        warning_calls = [call for call in mock_logger.warning.call_args_list 
                        if 'Metric already registered in Prometheus registry' in str(call)]
        assert len(warning_calls) > 0
        
        # Verify structured logging includes error context
        warning_call = warning_calls[0]
        call_kwargs = warning_call[1]
        assert 'metric_name' in call_kwargs
        assert 'registry_key' in call_kwargs
        assert 'error' in call_kwargs
        assert 'error_type' in call_kwargs
        assert 'prometheus_registry_conflict' in call_kwargs
        assert call_kwargs['prometheus_registry_conflict'] is True
    
    @patch('app.monitoring.logger')
    def test_metric_creation_unexpected_error_logging(self, mock_logger):
        """Test logging when unexpected errors occur during metric creation."""
        def failing_counter(*args, **kwargs):
            raise RuntimeError("Unexpected database connection error")
        
        metric = _get_or_create_metric(
            failing_counter,
            'error_metric',
            'Error test metric',
            ['label1']
        )
        
        # Should return DummyMetric
        assert isinstance(metric, DummyMetric)
        
        # Verify error logging for unexpected error
        error_calls = [call for call in mock_logger.error.call_args_list 
                      if 'Unexpected error during metric creation' in str(call)]
        assert len(error_calls) > 0
        
        # Verify structured logging includes comprehensive error context
        error_call = error_calls[0]
        call_kwargs = error_call[1]
        assert 'metric_name' in call_kwargs
        assert 'registry_key' in call_kwargs
        assert 'error' in call_kwargs
        assert 'error_type' in call_kwargs
        assert 'metric_class' in call_kwargs
        assert 'exc_info' in call_kwargs
        assert call_kwargs['exc_info'] is True
    
    @patch('app.monitoring.logger')
    def test_route_pattern_extraction_error_logging(self, mock_logger):
        """Test logging when route pattern extraction fails."""
        # Create a mock request that will cause an exception
        request = Mock()
        url_mock = Mock()
        url_mock.path = Mock(side_effect=Exception("URL parsing error"))
        request.url = url_mock
        
        result = _extract_route_pattern(request)
        
        # Should return fallback pattern
        assert result == "/unknown"
        
        # Verify error logging
        error_calls = [call for call in mock_logger.error.call_args_list 
                      if 'Critical error in route pattern extraction' in str(call)]
        assert len(error_calls) > 0
        
        # Verify structured logging includes error context
        error_call = error_calls[0]
        call_kwargs = error_call[1]
        assert 'error' in call_kwargs
        assert 'error_type' in call_kwargs
        assert 'fallback_pattern' in call_kwargs
        assert 'impact' in call_kwargs
        assert call_kwargs['fallback_pattern'] == "/unknown"
        assert call_kwargs['impact'] == "metrics_cardinality_protection"
    
    @patch('app.monitoring.logger')
    def test_method_label_formatting_error_logging(self, mock_logger):
        """Test logging when method label formatting encounters errors."""
        # Test with None method
        result = _get_method_label(None)
        assert result == "UNKNOWN"
        
        # Verify warning logging for invalid method type
        warning_calls = [call for call in mock_logger.warning.call_args_list 
                        if 'Invalid method type for label formatting' in str(call)]
        assert len(warning_calls) > 0
        
        # The function is very robust and hard to make fail in normal circumstances
        # This is actually a good thing - it means our error handling is comprehensive
        # Let's verify that the function handles edge cases gracefully
        
        # Test with various edge cases that should all return "UNKNOWN" safely
        edge_cases = [float('inf'), float('-inf'), complex(1, 2), [], {}, set()]
        for edge_case in edge_cases:
            result = _get_method_label(edge_case)
            assert result == "UNKNOWN"
        
        # Verify that warning logging occurred for non-string types
        warning_calls = [call for call in mock_logger.warning.call_args_list 
                        if 'Invalid method type for label formatting' in str(call)]
        # Should have at least one warning for None, plus warnings for edge cases
        assert len(warning_calls) >= 7  # 1 for None + 6 edge cases
    
    @patch('app.monitoring.logger')
    def test_status_code_formatting_error_logging(self, mock_logger):
        """Test logging when status code formatting encounters errors."""
        # Test with invalid status code
        result = _format_status_code(999)
        assert result == "unknown"
        
        # Verify warning logging for out-of-range status code
        warning_calls = [call for call in mock_logger.warning.call_args_list 
                        if 'HTTP status code outside valid range' in str(call)]
        assert len(warning_calls) > 0
        
        # Verify structured logging includes context
        warning_call = warning_calls[0]
        call_kwargs = warning_call[1]
        assert 'status_code' in call_kwargs
        assert 'valid_range' in call_kwargs
        assert 'fallback_value' in call_kwargs
        assert 'rfc_reference' in call_kwargs
        assert call_kwargs['status_code'] == 999
        assert call_kwargs['valid_range'] == "100-599"
        assert call_kwargs['fallback_value'] == "unknown"
    
    @patch('app.monitoring.logger')
    def test_route_sanitization_error_logging(self, mock_logger):
        """Test logging during route sanitization process."""
        # Test with path that has many long segments that won't be detected as IDs
        # Create segments that are long but don't contain digits (so not alphanumeric IDs)
        segments = [f"very-long-segment-name-that-contains-no-digits-part-{chr(ord('a') + i)}" for i in range(6)]
        long_path = "/" + "/".join(segments)
        result = _sanitize_unmatched_route(long_path)
        
        # Should return fallback due to length (the path will be over 200 chars)
        assert result == "/unknown"
        
        # Verify warning logging for length protection
        warning_calls = [call for call in mock_logger.warning.call_args_list 
                        if 'Route pattern exceeds maximum length' in str(call)]
        assert len(warning_calls) > 0
        
        # Verify structured logging includes length context
        warning_call = warning_calls[0]
        call_kwargs = warning_call[1]
        assert 'original_path' in call_kwargs
        assert 'sanitized_length' in call_kwargs
        assert 'max_allowed_length' in call_kwargs
        assert 'fallback_pattern' in call_kwargs
        assert 'reason' in call_kwargs
        assert call_kwargs['max_allowed_length'] == 200
        assert call_kwargs['fallback_pattern'] == "/unknown"
        assert call_kwargs['reason'] == "length_protection"


class TestDebugLogging:
    """Test debug logging functionality throughout the monitoring module."""
    
    def setup_method(self):
        """Clear registry before each test."""
        clear_metrics_registry()
    
    def teardown_method(self):
        """Clear registry after each test."""
        clear_metrics_registry()
    
    @patch('app.monitoring.logger')
    def test_middleware_debug_logging_enabled(self, mock_logger):
        """Test that debug logging works when enabled in middleware."""
        app = Mock()
        middleware = EnhancedHTTPMetricsMiddleware(app, debug_logging=True)
        
        # Verify initialization logging includes debug status
        info_calls = [call for call in mock_logger.info.call_args_list 
                     if 'EnhancedHTTPMetricsMiddleware initialized successfully' in str(call)]
        assert len(info_calls) > 0
        
        info_call = info_calls[0]
        call_kwargs = info_call[1]
        assert 'debug_logging_enabled' in call_kwargs
        assert call_kwargs['debug_logging_enabled'] is True
        
        # Verify debug logging message
        debug_calls = [call for call in mock_logger.debug.call_args_list 
                      if 'Debug logging enabled for HTTP metrics middleware' in str(call)]
        assert len(debug_calls) > 0
    
    @patch('app.monitoring.logger')
    def test_middleware_debug_logging_disabled(self, mock_logger):
        """Test that debug logging is properly disabled when not requested."""
        app = Mock()
        middleware = EnhancedHTTPMetricsMiddleware(app, debug_logging=False)
        
        # Verify initialization logging shows debug disabled
        info_calls = [call for call in mock_logger.info.call_args_list 
                     if 'EnhancedHTTPMetricsMiddleware initialized successfully' in str(call)]
        assert len(info_calls) > 0
        
        info_call = info_calls[0]
        call_kwargs = info_call[1]
        assert 'debug_logging_enabled' in call_kwargs
        assert call_kwargs['debug_logging_enabled'] is False
        
        # Verify no debug logging message for middleware setup
        debug_calls = [call for call in mock_logger.debug.call_args_list 
                      if 'Debug logging enabled for HTTP metrics middleware' in str(call)]
        assert len(debug_calls) == 0
    
    @patch('app.monitoring.logger')
    def test_debug_logging_in_metric_recording(self, mock_logger):
        """Test debug logging during metric recording operations."""
        app = Mock()
        middleware = EnhancedHTTPMetricsMiddleware(app, debug_logging=True)
        
        # Mock the actual metrics to avoid recording but allow the method to run
        with patch('app.monitoring.HTTP_REQUESTS_TOTAL'), \
             patch('app.monitoring.HTTP_REQUEST_DURATION'), \
             patch('app.monitoring.otel_http_requests_total'), \
             patch('app.monitoring.otel_http_request_duration'):
            
            # Call the real method to test debug logging
            middleware._record_metrics("GET", "/test", "200", 150.5)
        
        # Verify debug logging for metric recording
        debug_calls = [call for call in mock_logger.debug.call_args_list 
                      if 'Recording HTTP metrics to both Prometheus and OpenTelemetry' in str(call)]
        assert len(debug_calls) > 0
        
        # Verify structured debug logging includes metric details
        debug_call = debug_calls[0]
        call_kwargs = debug_call[1]
        assert 'method' in call_kwargs
        assert 'path' in call_kwargs
        assert 'status' in call_kwargs
        assert 'duration_ms' in call_kwargs


class TestSlowRequestDetection:
    """Test slow request detection and logging functionality."""
    
    def setup_method(self):
        """Clear registry before each test."""
        clear_metrics_registry()
    
    def teardown_method(self):
        """Clear registry after each test."""
        clear_metrics_registry()
    
    @pytest.mark.asyncio
    @patch('app.monitoring.logger')
    async def test_slow_request_detection_and_logging(self, mock_logger):
        """Test that slow requests (>1000ms) are detected and logged."""
        app = Mock()
        middleware = EnhancedHTTPMetricsMiddleware(app, debug_logging=False)
        
        # Mock request and response
        request = Mock()
        request.method = "GET"
        request.url.path = "/api/v1/slow-endpoint"
        request.url.query = "param=value"
        request.headers = {"user-agent": "test-client"}
        request.client.host = "127.0.0.1"
        
        response = Mock()
        response.status_code = 200
        
        # Mock call_next to simulate slow processing (>1000ms)
        async def slow_call_next(req):
            await asyncio.sleep(0.001)  # Small actual sleep
            return response
        
        # Mock time.perf_counter to simulate 1500ms duration
        with patch('time.perf_counter') as mock_perf_counter:
            mock_perf_counter.side_effect = [0.0, 1.5]  # 1500ms duration
            
            # Mock the metrics to avoid actual recording
            with patch('app.monitoring.HTTP_REQUESTS_TOTAL'), \
                 patch('app.monitoring.HTTP_REQUEST_DURATION'), \
                 patch('app.monitoring.HTTP_REQUESTS_IN_FLIGHT'), \
                 patch('app.monitoring.otel_http_requests_total'), \
                 patch('app.monitoring.otel_http_request_duration'), \
                 patch('app.monitoring.otel_http_requests_in_flight'):
                
                import asyncio
                result = await middleware.dispatch(request, slow_call_next)
        
        # Verify slow request warning was logged
        warning_calls = [call for call in mock_logger.warning.call_args_list 
                        if 'Slow request detected - performance monitoring alert' in str(call)]
        assert len(warning_calls) > 0
        
        # Verify structured logging includes comprehensive slow request context
        warning_call = warning_calls[0]
        call_kwargs = warning_call[1]
        assert 'method' in call_kwargs
        assert 'path' in call_kwargs
        assert 'duration_ms' in call_kwargs
        assert 'status' in call_kwargs
        assert 'request_url' in call_kwargs
        assert 'slow_request_threshold_ms' in call_kwargs
        assert 'performance_impact' in call_kwargs
        
        assert call_kwargs['method'] == "GET"
        assert call_kwargs['path'] == "/api/v1/slow-endpoint"  # This path doesn't match portfolio patterns
        assert call_kwargs['duration_ms'] == 1500.0
        assert call_kwargs['status'] == "200"
        assert call_kwargs['slow_request_threshold_ms'] == 1000
        assert call_kwargs['performance_impact'] == "high"
    
    @pytest.mark.asyncio
    @patch('app.monitoring.logger')
    async def test_slow_request_debug_logging(self, mock_logger):
        """Test that slow requests generate additional debug information when debug logging is enabled."""
        app = Mock()
        middleware = EnhancedHTTPMetricsMiddleware(app, debug_logging=True)
        
        # Mock request with comprehensive details
        request = Mock()
        request.method = "POST"
        request.url.path = "/api/v2/portfolios"
        request.url.query = "name=test&limit=10"
        request.headers = {"user-agent": "test-client", "authorization": "Bearer token"}
        request.client.host = "192.168.1.100"
        
        response = Mock()
        response.status_code = 201
        
        async def slow_call_next(req):
            return response
        
        # Mock time.perf_counter to simulate 2000ms duration
        with patch('time.perf_counter') as mock_perf_counter:
            mock_perf_counter.side_effect = [0.0, 2.0]  # 2000ms duration
            
            # Mock the metrics to avoid actual recording
            with patch('app.monitoring.HTTP_REQUESTS_TOTAL'), \
                 patch('app.monitoring.HTTP_REQUEST_DURATION'), \
                 patch('app.monitoring.HTTP_REQUESTS_IN_FLIGHT'), \
                 patch('app.monitoring.otel_http_requests_total'), \
                 patch('app.monitoring.otel_http_request_duration'), \
                 patch('app.monitoring.otel_http_requests_in_flight'):
                
                import asyncio
                result = await middleware.dispatch(request, slow_call_next)
        
        # Verify slow request warning was logged
        warning_calls = [call for call in mock_logger.warning.call_args_list 
                        if 'Slow request detected - performance monitoring alert' in str(call)]
        assert len(warning_calls) > 0
        
        # Verify additional debug information was logged for slow request
        debug_calls = [call for call in mock_logger.debug.call_args_list 
                      if 'Slow request debug information' in str(call)]
        assert len(debug_calls) > 0
        
        # Verify debug logging includes comprehensive request details
        debug_call = debug_calls[0]
        call_kwargs = debug_call[1]
        assert 'method' in call_kwargs
        assert 'path' in call_kwargs
        assert 'duration_ms' in call_kwargs
        assert 'status' in call_kwargs
        assert 'request_headers' in call_kwargs
        assert 'client_host' in call_kwargs
        assert 'query_params' in call_kwargs
        
        assert call_kwargs['method'] == "POST"
        assert call_kwargs['duration_ms'] == 2000.0
        assert call_kwargs['status'] == "201"
        assert call_kwargs['client_host'] == "192.168.1.100"
        assert call_kwargs['query_params'] == "name=test&limit=10"
    
    @pytest.mark.asyncio
    @patch('app.monitoring.logger')
    async def test_fast_request_no_slow_logging(self, mock_logger):
        """Test that fast requests (<1000ms) do not trigger slow request logging."""
        app = Mock()
        middleware = EnhancedHTTPMetricsMiddleware(app, debug_logging=True)
        
        # Mock request
        request = Mock()
        request.method = "GET"
        request.url.path = "/health"
        
        response = Mock()
        response.status_code = 200
        
        async def fast_call_next(req):
            return response
        
        # Mock time.perf_counter to simulate 50ms duration (fast)
        with patch('time.perf_counter') as mock_perf_counter:
            mock_perf_counter.side_effect = [0.0, 0.05]  # 50ms duration
            
            # Mock the metrics to avoid actual recording
            with patch('app.monitoring.HTTP_REQUESTS_TOTAL'), \
                 patch('app.monitoring.HTTP_REQUEST_DURATION'), \
                 patch('app.monitoring.HTTP_REQUESTS_IN_FLIGHT'), \
                 patch('app.monitoring.otel_http_requests_total'), \
                 patch('app.monitoring.otel_http_request_duration'), \
                 patch('app.monitoring.otel_http_requests_in_flight'):
                
                import asyncio
                result = await middleware.dispatch(request, fast_call_next)
        
        # Verify no slow request warning was logged
        warning_calls = [call for call in mock_logger.warning.call_args_list 
                        if 'Slow request detected' in str(call)]
        assert len(warning_calls) == 0
        
        # Verify no slow request debug information was logged
        debug_calls = [call for call in mock_logger.debug.call_args_list 
                      if 'Slow request debug information' in str(call)]
        assert len(debug_calls) == 0


class TestMiddlewareErrorHandling:
    """Test comprehensive error handling in middleware operations."""
    
    def setup_method(self):
        """Clear registry before each test."""
        clear_metrics_registry()
    
    def teardown_method(self):
        """Clear registry after each test."""
        clear_metrics_registry()
    
    @patch('app.monitoring.logger')
    def test_middleware_initialization_with_dummy_metrics_logging(self, mock_logger):
        """Test that middleware initialization logs warnings when dummy metrics are detected."""
        # Force creation of dummy metrics
        with patch('app.monitoring.HTTP_REQUESTS_TOTAL', new=DummyMetric()), \
             patch('app.monitoring.HTTP_REQUEST_DURATION', new=DummyMetric()), \
             patch('app.monitoring.HTTP_REQUESTS_IN_FLIGHT', new=DummyMetric()):
            
            app = Mock()
            middleware = EnhancedHTTPMetricsMiddleware(app, debug_logging=False)
        
        # Verify warnings were logged for each dummy metric
        warning_calls = mock_logger.warning.call_args_list
        
        counter_warnings = [call for call in warning_calls 
                           if 'HTTP requests total counter is using dummy metric' in str(call)]
        assert len(counter_warnings) > 0
        
        histogram_warnings = [call for call in warning_calls 
                             if 'HTTP request duration histogram is using dummy metric' in str(call)]
        assert len(histogram_warnings) > 0
        
        gauge_warnings = [call for call in warning_calls 
                         if 'HTTP requests in-flight gauge is using dummy metric' in str(call)]
        assert len(gauge_warnings) > 0
    
    @pytest.mark.asyncio
    @patch('app.monitoring.logger')
    async def test_in_flight_gauge_error_handling(self, mock_logger):
        """Test error handling when in-flight gauge operations fail."""
        app = Mock()
        middleware = EnhancedHTTPMetricsMiddleware(app, debug_logging=True)
        
        # Mock request
        request = Mock()
        request.method = "GET"
        request.url.path = "/test"
        
        response = Mock()
        response.status_code = 200
        
        async def call_next(req):
            return response
        
        # Mock in-flight gauge to succeed on increment but fail on decrement
        with patch('app.monitoring.HTTP_REQUESTS_IN_FLIGHT') as mock_gauge:
            mock_gauge.inc.return_value = None  # Succeed on increment
            mock_gauge.dec.side_effect = Exception("Gauge decrement failed")  # Fail on decrement
            
            # Mock other metrics to avoid interference
            with patch('app.monitoring.HTTP_REQUESTS_TOTAL'), \
                 patch('app.monitoring.HTTP_REQUEST_DURATION'), \
                 patch('app.monitoring.otel_http_requests_total'), \
                 patch('app.monitoring.otel_http_request_duration'), \
                 patch('app.monitoring.otel_http_requests_in_flight'):
                
                result = await middleware.dispatch(request, call_next)
        
        # Since increment succeeds, there should be no increment error logging
        increment_errors = [call for call in mock_logger.error.call_args_list 
                           if 'Failed to increment Prometheus in-flight requests gauge' in str(call)]
        assert len(increment_errors) == 0
        
        # Verify error logging for decrement failure
        decrement_errors = [call for call in mock_logger.error.call_args_list 
                           if 'Critical error decrementing Prometheus in-flight requests gauge' in str(call)]
        assert len(decrement_errors) > 0
        
        # Verify structured logging includes comprehensive error context for decrement error
        decrement_error = decrement_errors[0]
        call_kwargs = decrement_error[1]
        assert 'error' in call_kwargs
        assert 'error_type' in call_kwargs
        assert 'method' in call_kwargs
        assert 'path' in call_kwargs
        assert 'gauge_operation' in call_kwargs
        assert 'impact' in call_kwargs
        assert call_kwargs['gauge_operation'] == "decrement"
        assert call_kwargs['impact'] == "prometheus_gauge_accuracy_compromised"
    
    @pytest.mark.asyncio
    @patch('app.monitoring.logger')
    async def test_metrics_recording_error_handling(self, mock_logger):
        """Test error handling when metrics recording fails."""
        app = Mock()
        middleware = EnhancedHTTPMetricsMiddleware(app, debug_logging=False)
        
        # Mock request
        request = Mock()
        request.method = "POST"
        request.url.path = "/api/test"
        
        response = Mock()
        response.status_code = 201
        
        async def call_next(req):
            return response
        
        # Mock metrics recording to fail
        with patch.object(middleware, '_record_metrics') as mock_record:
            mock_record.side_effect = Exception("Metrics recording failed")
            
            # Mock in-flight gauges to work normally
            with patch('app.monitoring.HTTP_REQUESTS_IN_FLIGHT'), \
                 patch('app.monitoring.otel_http_requests_in_flight'):
                
                # Should not raise exception despite metrics recording failure
                result = await middleware.dispatch(request, call_next)
                assert result is response
        
        # Verify that metrics recording was attempted
        assert mock_record.called
    
    @pytest.mark.asyncio
    @patch('app.monitoring.logger')
    async def test_request_processing_exception_logging(self, mock_logger):
        """Test comprehensive logging when request processing raises an exception."""
        app = Mock()
        middleware = EnhancedHTTPMetricsMiddleware(app, debug_logging=True)
        
        # Mock request
        request = Mock()
        request.method = "DELETE"
        request.url.path = "/api/v1/portfolio/test123"
        request.url = Mock()
        request.url.__str__ = Mock(return_value="http://localhost/api/v1/portfolio/test123")
        
        # Mock call_next to raise an exception
        async def failing_call_next(req):
            raise ValueError("Database connection failed")
        
        # Mock metrics recording to work
        with patch.object(middleware, '_record_metrics') as mock_record, \
             patch('app.monitoring.HTTP_REQUESTS_IN_FLIGHT'), \
             patch('app.monitoring.otel_http_requests_in_flight'):
            
            # Should re-raise the exception
            with pytest.raises(ValueError, match="Database connection failed"):
                await middleware.dispatch(request, failing_call_next)
        
        # Verify error logging for request processing failure
        error_calls = [call for call in mock_logger.error.call_args_list 
                      if 'Request processing failed - attempted metrics collection for error case' in str(call)]
        assert len(error_calls) > 0
        
        # Verify structured logging includes comprehensive error context
        error_call = error_calls[0]
        call_kwargs = error_call[1]
        assert 'error' in call_kwargs
        assert 'error_type' in call_kwargs
        assert 'method' in call_kwargs
        assert 'path' in call_kwargs
        assert 'status' in call_kwargs
        assert 'duration_ms' in call_kwargs
        assert 'request_url' in call_kwargs
        assert 'error_handling' in call_kwargs
        
        assert call_kwargs['error'] == "Database connection failed"
        assert call_kwargs['error_type'] == "ValueError"
        assert call_kwargs['method'] == "DELETE"
        assert call_kwargs['status'] == "500"
        assert call_kwargs['error_handling'] == "metrics_recorded_for_500_status"
        
        # Verify metrics were recorded for the failed request
        assert mock_record.called
        record_call = mock_record.call_args
        assert record_call[0][0] == "DELETE"  # method
        assert record_call[0][2] == "500"     # status (error)


class TestLoggingConfiguration:
    """Test logging configuration and settings integration."""
    
    @patch('app.monitoring.logger')
    def test_debug_logging_configuration_from_settings(self, mock_logger):
        """Test that debug logging configuration is properly read from settings."""
        # This test verifies that the middleware respects the debug_logging parameter
        # In the actual application, this comes from settings.metrics_debug_logging
        
        app = Mock()
        
        # Test with debug logging enabled
        middleware_debug = EnhancedHTTPMetricsMiddleware(app, debug_logging=True)
        assert middleware_debug.debug_logging is True
        
        # Test with debug logging disabled
        middleware_no_debug = EnhancedHTTPMetricsMiddleware(app, debug_logging=False)
        assert middleware_no_debug.debug_logging is False
        
        # Verify initialization logging reflects the configuration
        info_calls = mock_logger.info.call_args_list
        
        # Find calls for both middleware instances
        debug_enabled_calls = [call for call in info_calls 
                              if 'EnhancedHTTPMetricsMiddleware initialized successfully' in str(call)
                              and call[1].get('debug_logging_enabled') is True]
        assert len(debug_enabled_calls) > 0
        
        debug_disabled_calls = [call for call in info_calls 
                               if 'EnhancedHTTPMetricsMiddleware initialized successfully' in str(call)
                               and call[1].get('debug_logging_enabled') is False]
        assert len(debug_disabled_calls) > 0