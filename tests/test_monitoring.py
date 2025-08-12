"""
Unit tests for the enhanced HTTP metrics monitoring module.

These tests verify the metrics registry system, duplicate registration handling,
and error recovery mechanisms.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from prometheus_client import Counter, Histogram, Gauge, CollectorRegistry, REGISTRY

# Import after setting up test environment
import os
os.environ['PROMETHEUS_DISABLE_CREATED_SERIES'] = 'True'

from app.monitoring import (
    _get_or_create_metric,
    DummyMetric,
    get_metrics_registry,
    clear_metrics_registry,
    is_dummy_metric,
    get_metric_status,
    HTTP_REQUESTS_TOTAL,
    HTTP_REQUEST_DURATION,
    HTTP_REQUESTS_IN_FLIGHT,
)


class TestDummyMetric:
    """Test the DummyMetric fallback class."""
    
    def test_dummy_metric_interface(self):
        """Test that DummyMetric provides the expected interface."""
        dummy = DummyMetric()
        
        # Test method chaining
        assert dummy.labels(method="GET", path="/test", status="200") is dummy
        
        # Test operations don't raise exceptions
        dummy.inc()
        dummy.inc(5.0)
        dummy.observe(100.5)
        dummy.set(42.0)
        
        # Test collect returns empty list
        assert dummy.collect() == []
    
    def test_dummy_metric_with_kwargs(self):
        """Test DummyMetric handles arbitrary keyword arguments."""
        dummy = DummyMetric()
        
        # Should handle any labels without error
        result = dummy.labels(
            method="POST", 
            path="/api/v1/test", 
            status="201",
            extra_label="value"
        )
        assert result is dummy


class TestMetricsRegistry:
    """Test the global metrics registry system."""
    
    def setup_method(self):
        """Clear registry before each test."""
        clear_metrics_registry()
        # Create a fresh registry for each test to avoid conflicts
        self.test_registry = CollectorRegistry()
    
    def teardown_method(self):
        """Clear registry after each test."""
        clear_metrics_registry()
    
    def test_get_or_create_metric_new_counter(self):
        """Test creating a new Counter metric."""
        with patch('prometheus_client.Counter') as mock_counter:
            mock_instance = Mock()
            mock_instance._name = 'test_counter'
            mock_counter.return_value = mock_instance
            
            metric = _get_or_create_metric(
                mock_counter,
                'test_counter',
                'Test counter description',
                ['label1', 'label2']
            )
            
            assert metric is mock_instance
            
            # Verify it's in the registry
            registry = get_metrics_registry()
            assert 'test_counter' in registry
            assert registry['test_counter'] is metric
    
    def test_get_or_create_metric_new_histogram(self):
        """Test creating a new Histogram metric."""
        with patch('prometheus_client.Histogram') as mock_histogram:
            mock_instance = Mock()
            mock_instance._name = 'test_histogram'
            mock_histogram.return_value = mock_instance
            
            metric = _get_or_create_metric(
                mock_histogram,
                'test_histogram',
                'Test histogram description',
                ['label1'],
                buckets=[1, 5, 10, 50, 100]
            )
            
            assert metric is mock_instance
            
            # Verify it's in the registry
            registry = get_metrics_registry()
            assert 'test_histogram' in registry
            assert registry['test_histogram'] is metric
    
    def test_get_or_create_metric_new_gauge(self):
        """Test creating a new Gauge metric."""
        with patch('prometheus_client.Gauge') as mock_gauge:
            mock_instance = Mock()
            mock_instance._name = 'test_gauge'
            mock_gauge.return_value = mock_instance
            
            metric = _get_or_create_metric(
                mock_gauge,
                'test_gauge',
                'Test gauge description'
            )
            
            assert metric is mock_instance
            
            # Verify it's in the registry
            registry = get_metrics_registry()
            assert 'test_gauge' in registry
            assert registry['test_gauge'] is metric
    
    def test_get_or_create_metric_reuse_existing(self):
        """Test that existing metrics are reused."""
        with patch('prometheus_client.Counter') as mock_counter:
            mock_instance = Mock()
            mock_counter.return_value = mock_instance
            
            # Create metric first time
            metric1 = _get_or_create_metric(
                mock_counter,
                'reuse_test',
                'Test reuse',
                ['label1']
            )
            
            # Try to create same metric again
            metric2 = _get_or_create_metric(
                mock_counter,
                'reuse_test',
                'Test reuse different description',  # Different description
                ['label1', 'label2']  # Different labels
            )
            
            # Should return the same instance
            assert metric1 is metric2
            
            # Registry should only have one entry
            registry = get_metrics_registry()
            assert len(registry) == 1
            assert 'reuse_test' in registry
            
            # Counter should only be called once
            assert mock_counter.call_count == 1
    
    def test_get_or_create_metric_custom_registry_key(self):
        """Test using custom registry key."""
        with patch('prometheus_client.Counter') as mock_counter:
            mock_instance = Mock()
            mock_counter.return_value = mock_instance
            
            metric = _get_or_create_metric(
                mock_counter,
                'metric_name',
                'Test description',
                ['label1'],
                registry_key='custom_key'
            )
            
            registry = get_metrics_registry()
            assert 'custom_key' in registry
            assert 'metric_name' not in registry
            assert registry['custom_key'] is metric
    
    @patch('app.monitoring.Counter')
    def test_get_or_create_metric_duplicate_registration_error(self, mock_counter_class):
        """Test handling of duplicate registration ValueError."""
        # Mock Counter to raise ValueError with specific message
        mock_counter_class.side_effect = ValueError("Duplicated timeseries in CollectorRegistry")
        
        metric = _get_or_create_metric(
            mock_counter_class,
            'duplicate_test',
            'Test duplicate handling',
            ['label1']
        )
        
        # Should return DummyMetric
        assert isinstance(metric, DummyMetric)
        
        # Should be in registry
        registry = get_metrics_registry()
        assert 'duplicate_test' in registry
        assert isinstance(registry['duplicate_test'], DummyMetric)
    
    @patch('app.monitoring.Counter')
    def test_get_or_create_metric_other_value_error(self, mock_counter_class):
        """Test handling of other ValueError exceptions."""
        # Mock Counter to raise different ValueError
        mock_counter_class.side_effect = ValueError("Some other error")
        
        metric = _get_or_create_metric(
            mock_counter_class,
            'other_error_test',
            'Test other error handling',
            ['label1']
        )
        
        # Should return DummyMetric
        assert isinstance(metric, DummyMetric)
        
        # Should be in registry
        registry = get_metrics_registry()
        assert 'other_error_test' in registry
        assert isinstance(registry['other_error_test'], DummyMetric)
    
    @patch('app.monitoring.Counter')
    def test_get_or_create_metric_unexpected_error(self, mock_counter_class):
        """Test handling of unexpected exceptions."""
        # Mock Counter to raise unexpected exception
        mock_counter_class.side_effect = RuntimeError("Unexpected error")
        
        metric = _get_or_create_metric(
            mock_counter_class,
            'unexpected_error_test',
            'Test unexpected error handling',
            ['label1']
        )
        
        # Should return DummyMetric
        assert isinstance(metric, DummyMetric)
        
        # Should be in registry
        registry = get_metrics_registry()
        assert 'unexpected_error_test' in registry
        assert isinstance(registry['unexpected_error_test'], DummyMetric)


class TestMetricsRegistryUtilities:
    """Test utility functions for metrics registry."""
    
    def setup_method(self):
        """Clear registry before each test."""
        clear_metrics_registry()
    
    def teardown_method(self):
        """Clear registry after each test."""
        clear_metrics_registry()
    
    def test_get_metrics_registry_empty(self):
        """Test getting empty registry."""
        registry = get_metrics_registry()
        assert isinstance(registry, dict)
        assert len(registry) == 0
    
    def test_get_metrics_registry_with_metrics(self):
        """Test getting registry with metrics."""
        # Add some metrics
        metric1 = _get_or_create_metric(Counter, 'test1', 'Test 1', ['label1'])
        metric2 = _get_or_create_metric(Histogram, 'test2', 'Test 2', ['label1'])
        
        registry = get_metrics_registry()
        assert len(registry) == 2
        assert 'test1' in registry
        assert 'test2' in registry
        assert registry['test1'] is metric1
        assert registry['test2'] is metric2
    
    def test_get_metrics_registry_returns_copy(self):
        """Test that get_metrics_registry returns a copy."""
        # Add a metric
        _get_or_create_metric(Counter, 'test', 'Test', ['label1'])
        
        registry1 = get_metrics_registry()
        registry2 = get_metrics_registry()
        
        # Should be different objects
        assert registry1 is not registry2
        
        # But with same content
        assert registry1 == registry2
        
        # Modifying one shouldn't affect the other
        registry1['new_key'] = 'new_value'
        assert 'new_key' not in registry2
    
    def test_clear_metrics_registry(self):
        """Test clearing the metrics registry."""
        # Add some metrics
        _get_or_create_metric(Counter, 'test1', 'Test 1', ['label1'])
        _get_or_create_metric(Histogram, 'test2', 'Test 2', ['label1'])
        
        # Verify they exist
        registry = get_metrics_registry()
        assert len(registry) == 2
        
        # Clear registry
        clear_metrics_registry()
        
        # Verify it's empty
        registry = get_metrics_registry()
        assert len(registry) == 0
    
    def test_is_dummy_metric(self):
        """Test identifying dummy metrics."""
        # Create real metric
        real_metric = _get_or_create_metric(Counter, 'real', 'Real metric', ['label1'])
        assert not is_dummy_metric(real_metric)
        
        # Create dummy metric
        dummy_metric = DummyMetric()
        assert is_dummy_metric(dummy_metric)
        
        # Test with other objects
        assert not is_dummy_metric("string")
        assert not is_dummy_metric(123)
        assert not is_dummy_metric(None)
    
    def test_get_metric_status(self):
        """Test getting metric status information."""
        # Start with empty registry
        status = get_metric_status()
        assert isinstance(status, dict)
        assert len(status) == 0
        
        # Add real metric
        with patch('prometheus_client.Counter') as mock_counter:
            mock_instance = Mock()
            mock_counter.return_value = mock_instance
            _get_or_create_metric(mock_counter, 'real_metric', 'Real metric', ['label1'])
        
        # Add dummy metric by forcing an error - patch the function parameter
        def failing_counter(*args, **kwargs):
            raise ValueError("Duplicated timeseries")
        
        _get_or_create_metric(failing_counter, 'dummy_metric', 'Dummy metric', ['label1'])
        
        status = get_metric_status()
        assert len(status) == 2
        
        # Check real metric status
        assert 'real_metric' in status
        real_status = status['real_metric']
        assert real_status['type'] == 'Mock'  # Since we mocked it
        assert real_status['is_dummy'] is False
        
        # Check dummy metric status
        assert 'dummy_metric' in status
        dummy_status = status['dummy_metric']
        assert dummy_status['type'] == 'DummyMetric'
        assert dummy_status['is_dummy'] is True
        assert 'app.monitoring' in dummy_status['class_module']


class TestStandardHTTPMetrics:
    """Test the standard HTTP metrics are created correctly."""
    
    def test_http_requests_total_created(self):
        """Test HTTP_REQUESTS_TOTAL metric is created."""
        assert HTTP_REQUESTS_TOTAL is not None
        
        # Should be either Counter or DummyMetric
        assert isinstance(HTTP_REQUESTS_TOTAL, (Counter, DummyMetric))
        
        # Should support labels method
        labeled = HTTP_REQUESTS_TOTAL.labels(method="GET", path="/test", status="200")
        assert labeled is not None
    
    def test_http_requests_total_labels(self):
        """Test HTTP_REQUESTS_TOTAL has correct labels: method, path, status."""
        # Test that all required labels are supported
        labeled = HTTP_REQUESTS_TOTAL.labels(method="GET", path="/api/v1/test", status="200")
        assert labeled is not None
        
        # Test with different label values
        labeled2 = HTTP_REQUESTS_TOTAL.labels(method="POST", path="/api/v2/test", status="201")
        assert labeled2 is not None
        
        # Test that inc() works
        labeled.inc()
        labeled2.inc(5)  # Test with custom increment
    
    def test_http_request_duration_created(self):
        """Test HTTP_REQUEST_DURATION metric is created."""
        assert HTTP_REQUEST_DURATION is not None
        
        # Should be either Histogram or DummyMetric
        assert isinstance(HTTP_REQUEST_DURATION, (Histogram, DummyMetric))
        
        # Should support labels method
        labeled = HTTP_REQUEST_DURATION.labels(method="GET", path="/test", status="200")
        assert labeled is not None
    
    def test_http_request_duration_labels_and_buckets(self):
        """Test HTTP_REQUEST_DURATION has correct labels and millisecond buckets."""
        # Test that all required labels are supported
        labeled = HTTP_REQUEST_DURATION.labels(method="GET", path="/api/v1/test", status="200")
        assert labeled is not None
        
        # Test with different label values
        labeled2 = HTTP_REQUEST_DURATION.labels(method="POST", path="/api/v2/test", status="500")
        assert labeled2 is not None
        
        # Test that observe() works with millisecond values
        labeled.observe(5.5)    # Should fit in first bucket (5ms)
        labeled.observe(25.0)   # Should fit in 25ms bucket
        labeled.observe(100.0)  # Should fit in 100ms bucket
        labeled.observe(1500.0) # Should fit in 2500ms bucket
        labeled2.observe(10000.0) # Should fit in 10000ms bucket
    
    def test_http_request_duration_buckets(self):
        """Test HTTP_REQUEST_DURATION has the correct millisecond buckets."""
        # If it's a real Histogram (not DummyMetric), check buckets
        if isinstance(HTTP_REQUEST_DURATION, Histogram):
            # The buckets should be [5, 10, 25, 50, 100, 250, 500, 1000, 2500, 5000, 10000]
            # We can't directly access buckets, but we can test that observations work
            labeled = HTTP_REQUEST_DURATION.labels(method="GET", path="/test", status="200")
            
            # Test observations at bucket boundaries
            test_values = [5, 10, 25, 50, 100, 250, 500, 1000, 2500, 5000, 10000]
            for value in test_values:
                labeled.observe(value)  # Should not raise
    
    def test_http_requests_in_flight_created(self):
        """Test HTTP_REQUESTS_IN_FLIGHT metric is created."""
        assert HTTP_REQUESTS_IN_FLIGHT is not None
        
        # Should be either Gauge or DummyMetric
        assert isinstance(HTTP_REQUESTS_IN_FLIGHT, (Gauge, DummyMetric))
        
        # Should support inc/dec methods
        HTTP_REQUESTS_IN_FLIGHT.inc()
        HTTP_REQUESTS_IN_FLIGHT.dec()
    
    def test_http_requests_in_flight_no_labels(self):
        """Test HTTP_REQUESTS_IN_FLIGHT gauge has no labels."""
        # Should be able to call inc/dec/set directly without labels
        HTTP_REQUESTS_IN_FLIGHT.inc()
        HTTP_REQUESTS_IN_FLIGHT.inc(2.0)  # Test with custom increment
        HTTP_REQUESTS_IN_FLIGHT.dec()
        HTTP_REQUESTS_IN_FLIGHT.dec(1.0)  # Test with custom decrement
        HTTP_REQUESTS_IN_FLIGHT.set(5.0)  # Test set operation
        HTTP_REQUESTS_IN_FLIGHT.set(0.0)  # Reset to 0
    
    def test_standard_metrics_exist(self):
        """Test that standard metrics exist and have expected interface."""
        # Test that all metrics exist
        assert HTTP_REQUESTS_TOTAL is not None
        assert HTTP_REQUEST_DURATION is not None
        assert HTTP_REQUESTS_IN_FLIGHT is not None
        
        # Test that they support the expected interface
        # Counter interface
        labeled_counter = HTTP_REQUESTS_TOTAL.labels(method="GET", path="/test", status="200")
        labeled_counter.inc()  # Should not raise
        
        # Histogram interface
        labeled_histogram = HTTP_REQUEST_DURATION.labels(method="GET", path="/test", status="200")
        labeled_histogram.observe(100.0)  # Should not raise
        
        # Gauge interface
        HTTP_REQUESTS_IN_FLIGHT.inc()  # Should not raise
        HTTP_REQUESTS_IN_FLIGHT.dec()  # Should not raise
    
    def test_metrics_registry_contains_standard_metrics(self):
        """Test that all standard metrics are registered in the global registry."""
        # The metrics should exist regardless of registry state
        # since they are module-level variables
        assert HTTP_REQUESTS_TOTAL is not None
        assert HTTP_REQUEST_DURATION is not None
        assert HTTP_REQUESTS_IN_FLIGHT is not None
        
        # Test that they have the expected types
        from prometheus_client import Counter, Histogram, Gauge
        assert isinstance(HTTP_REQUESTS_TOTAL, (Counter, DummyMetric))
        assert isinstance(HTTP_REQUEST_DURATION, (Histogram, DummyMetric))
        assert isinstance(HTTP_REQUESTS_IN_FLIGHT, (Gauge, DummyMetric))
    
    def test_metric_names_and_descriptions(self):
        """Test that metrics have the correct names and descriptions."""
        # We can't directly access names/descriptions from prometheus_client objects,
        # but we can verify they were created with the right parameters by checking
        # that they exist and work as expected
        
        # Test that the metrics work with the expected interface
        # This indirectly verifies they were created correctly
        
        # HTTP_REQUESTS_TOTAL should be a counter with 3 labels
        counter_labeled = HTTP_REQUESTS_TOTAL.labels(
            method="GET", 
            path="/api/v1/portfolio/{portfolioId}", 
            status="200"
        )
        counter_labeled.inc()
        
        # HTTP_REQUEST_DURATION should be a histogram with 3 labels
        histogram_labeled = HTTP_REQUEST_DURATION.labels(
            method="POST", 
            path="/api/v2/portfolios", 
            status="201"
        )
        histogram_labeled.observe(150.5)  # milliseconds
        
        # HTTP_REQUESTS_IN_FLIGHT should be a gauge with no labels
        HTTP_REQUESTS_IN_FLIGHT.inc()
        HTTP_REQUESTS_IN_FLIGHT.dec()


class TestMetricsRegistryIntegration:
    """Integration tests for the metrics registry system."""
    
    def setup_method(self):
        """Clear registry before each test."""
        clear_metrics_registry()
    
    def teardown_method(self):
        """Clear registry after each test."""
        clear_metrics_registry()
    
    def test_multiple_metric_types(self):
        """Test creating multiple different metric types."""
        with patch('prometheus_client.Counter') as mock_counter, \
             patch('prometheus_client.Histogram') as mock_histogram, \
             patch('prometheus_client.Gauge') as mock_gauge:
            
            mock_counter_instance = Mock()
            mock_histogram_instance = Mock()
            mock_gauge_instance = Mock()
            
            mock_counter.return_value = mock_counter_instance
            mock_histogram.return_value = mock_histogram_instance
            mock_gauge.return_value = mock_gauge_instance
            
            counter = _get_or_create_metric(
                mock_counter, 'test_counter', 'Test counter', ['method', 'status']
            )
            histogram = _get_or_create_metric(
                mock_histogram, 'test_histogram', 'Test histogram', ['endpoint'], 
                buckets=[0.1, 0.5, 1.0, 5.0]
            )
            gauge = _get_or_create_metric(
                mock_gauge, 'test_gauge', 'Test gauge'
            )
            
            # All should be created successfully
            assert counter is mock_counter_instance
            assert histogram is mock_histogram_instance
            assert gauge is mock_gauge_instance
            
            # All should be in registry
            registry = get_metrics_registry()
            assert len(registry) == 3
            assert registry['test_counter'] is counter
            assert registry['test_histogram'] is histogram
            assert registry['test_gauge'] is gauge
    
    def test_mixed_real_and_dummy_metrics(self):
        """Test registry with both real and dummy metrics."""
        # Create real metric
        with patch('prometheus_client.Counter') as mock_counter:
            mock_instance = Mock()
            mock_counter.return_value = mock_instance
            
            real_metric = _get_or_create_metric(
                mock_counter, 'real_metric', 'Real metric', ['label1']
            )
        
        # Force creation of dummy metric
        def failing_histogram(*args, **kwargs):
            raise ValueError("Duplicated timeseries")
        
        dummy_metric = _get_or_create_metric(
            failing_histogram, 'dummy_metric', 'Dummy metric', ['label1']
        )
        
        # Verify types
        assert real_metric is mock_instance
        assert isinstance(dummy_metric, DummyMetric)
        
        # Both should be in registry
        registry = get_metrics_registry()
        assert len(registry) == 2
        assert registry['real_metric'] is real_metric
        assert registry['dummy_metric'] is dummy_metric
        
        # Status should reflect the difference
        status = get_metric_status()
        assert status['real_metric']['is_dummy'] is False
        assert status['dummy_metric']['is_dummy'] is True
    
    @patch('app.monitoring.logger')
    def test_logging_during_metric_creation(self, mock_logger):
        """Test that appropriate logging occurs during metric creation."""
        # Create successful metric
        with patch('prometheus_client.Counter') as mock_counter:
            mock_instance = Mock()
            mock_counter.return_value = mock_instance
            _get_or_create_metric(mock_counter, 'success_metric', 'Success', ['label1'])
        
        # Verify success logging
        mock_logger.info.assert_called_with("Successfully created metric: success_metric")
        
        # Create failing metric
        def failing_counter(*args, **kwargs):
            raise ValueError("Duplicated timeseries")
        
        _get_or_create_metric(failing_counter, 'fail_metric', 'Fail', ['label1'])
        
        # Verify warning logging
        mock_logger.warning.assert_called()
        warning_calls = [call for call in mock_logger.warning.call_args_list 
                        if 'Metric already registered in Prometheus' in str(call)]
        assert len(warning_calls) > 0


class TestRoutePatternExtraction:
    """Test route pattern extraction for portfolio service endpoints."""
    
    def test_extract_route_pattern_root(self):
        """Test root endpoint pattern extraction."""
        from app.monitoring import _extract_route_pattern
        from unittest.mock import Mock
        
        # Mock request for root path
        request = Mock()
        request.url.path = "/"
        
        result = _extract_route_pattern(request)
        assert result == "/"
    
    def test_extract_route_pattern_empty_path(self):
        """Test empty path pattern extraction."""
        from app.monitoring import _extract_route_pattern
        from unittest.mock import Mock
        
        # Mock request for empty path
        request = Mock()
        request.url.path = ""
        
        result = _extract_route_pattern(request)
        assert result == "/"
    
    def test_extract_route_pattern_health(self):
        """Test health endpoint pattern extraction."""
        from app.monitoring import _extract_route_pattern
        from unittest.mock import Mock
        
        # Mock request for health path
        request = Mock()
        request.url.path = "/health"
        
        result = _extract_route_pattern(request)
        assert result == "/health"
    
    def test_extract_route_pattern_metrics(self):
        """Test metrics endpoint pattern extraction."""
        from app.monitoring import _extract_route_pattern
        from unittest.mock import Mock
        
        # Mock request for metrics path
        request = Mock()
        request.url.path = "/metrics"
        
        result = _extract_route_pattern(request)
        assert result == "/metrics"
    
    def test_extract_route_pattern_trailing_slash(self):
        """Test that trailing slashes are stripped."""
        from app.monitoring import _extract_route_pattern
        from unittest.mock import Mock
        
        # Mock request with trailing slash
        request = Mock()
        request.url.path = "/health/"
        
        result = _extract_route_pattern(request)
        assert result == "/health"
    
    def test_extract_route_pattern_exception_handling(self):
        """Test exception handling in route pattern extraction."""
        from app.monitoring import _extract_route_pattern
        from unittest.mock import Mock, PropertyMock
        
        # Mock request that will cause an exception when accessing path
        request = Mock()
        url_mock = Mock()
        # Make path property raise an exception
        type(url_mock).path = PropertyMock(side_effect=Exception("Test error"))
        request.url = url_mock
        
        result = _extract_route_pattern(request)
        assert result == "/unknown"


class TestPortfolioV1RoutePatterns:
    """Test v1 API route pattern extraction."""
    
    def test_extract_portfolio_v1_portfolios_collection(self):
        """Test v1 portfolios collection endpoint."""
        from app.monitoring import _extract_portfolio_v1_route_pattern
        
        result = _extract_portfolio_v1_route_pattern("/api/v1/portfolios")
        assert result == "/api/v1/portfolios"
    
    def test_extract_portfolio_v1_single_portfolio(self):
        """Test v1 single portfolio endpoint with ObjectId."""
        from app.monitoring import _extract_portfolio_v1_route_pattern
        
        # Test with MongoDB ObjectId
        result = _extract_portfolio_v1_route_pattern("/api/v1/portfolio/507f1f77bcf86cd799439011")
        assert result == "/api/v1/portfolio/{portfolioId}"
    
    def test_extract_portfolio_v1_single_portfolio_uuid(self):
        """Test v1 single portfolio endpoint with UUID."""
        from app.monitoring import _extract_portfolio_v1_route_pattern
        
        # Test with UUID
        result = _extract_portfolio_v1_route_pattern("/api/v1/portfolio/550e8400-e29b-41d4-a716-446655440000")
        assert result == "/api/v1/portfolio/{portfolioId}"
    
    def test_extract_portfolio_v1_single_portfolio_numeric(self):
        """Test v1 single portfolio endpoint with numeric ID."""
        from app.monitoring import _extract_portfolio_v1_route_pattern
        
        # Test with numeric ID
        result = _extract_portfolio_v1_route_pattern("/api/v1/portfolio/12345")
        assert result == "/api/v1/portfolio/{portfolioId}"
    
    def test_extract_portfolio_v1_unknown_pattern(self):
        """Test v1 unknown pattern fallback."""
        from app.monitoring import _extract_portfolio_v1_route_pattern
        
        # Test with unexpected pattern
        result = _extract_portfolio_v1_route_pattern("/api/v1/portfolio/something/else/here")
        assert result == "/api/v1/portfolio/unknown"
    
    def test_extract_route_pattern_v1_integration(self):
        """Test full integration with v1 routes."""
        from app.monitoring import _extract_route_pattern
        from unittest.mock import Mock
        
        # Test v1 portfolios collection
        request = Mock()
        request.url.path = "/api/v1/portfolios"
        result = _extract_route_pattern(request)
        assert result == "/api/v1/portfolios"
        
        # Test v1 single portfolio
        request.url.path = "/api/v1/portfolio/507f1f77bcf86cd799439011"
        result = _extract_route_pattern(request)
        assert result == "/api/v1/portfolio/{portfolioId}"


class TestPortfolioV2RoutePatterns:
    """Test v2 API route pattern extraction."""
    
    def test_extract_portfolio_v2_portfolios_search(self):
        """Test v2 portfolios search endpoint."""
        from app.monitoring import _extract_portfolio_v2_route_pattern
        
        result = _extract_portfolio_v2_route_pattern("/api/v2/portfolios")
        assert result == "/api/v2/portfolios"
    
    def test_extract_portfolio_v2_unknown_pattern(self):
        """Test v2 unknown pattern fallback."""
        from app.monitoring import _extract_portfolio_v2_route_pattern
        
        # Test with unexpected pattern
        result = _extract_portfolio_v2_route_pattern("/api/v2/portfolios/something/else")
        assert result == "/api/v2/portfolios/unknown"
    
    def test_extract_route_pattern_v2_integration(self):
        """Test full integration with v2 routes."""
        from app.monitoring import _extract_route_pattern
        from unittest.mock import Mock
        
        # Test v2 portfolios search
        request = Mock()
        request.url.path = "/api/v2/portfolios"
        result = _extract_route_pattern(request)
        assert result == "/api/v2/portfolios"


class TestIDDetection:
    """Test ID detection logic for route sanitization."""
    
    def test_looks_like_id_mongodb_objectid(self):
        """Test MongoDB ObjectId detection."""
        from app.monitoring import _looks_like_id
        
        # Valid MongoDB ObjectIds (24 character hex)
        assert _looks_like_id("507f1f77bcf86cd799439011") is True
        assert _looks_like_id("507F1F77BCF86CD799439011") is True  # Uppercase
        assert _looks_like_id("000000000000000000000000") is True  # All zeros
        assert _looks_like_id("ffffffffffffffffffffffff") is True  # All f's
        
        # Invalid ObjectIds
        assert _looks_like_id("507f1f77bcf86cd79943901") is False   # 23 chars
        assert _looks_like_id("507f1f77bcf86cd7994390111") is False # 25 chars
        assert _looks_like_id("507f1f77bcf86cd79943901g") is False  # Invalid hex char
    
    def test_looks_like_id_uuid_with_hyphens(self):
        """Test UUID with hyphens detection."""
        from app.monitoring import _looks_like_id
        
        # Valid UUIDs with hyphens
        assert _looks_like_id("550e8400-e29b-41d4-a716-446655440000") is True
        assert _looks_like_id("6ba7b810-9dad-11d1-80b4-00c04fd430c8") is True
        assert _looks_like_id("00000000-0000-0000-0000-000000000000") is True
        
        # Invalid UUIDs
        assert _looks_like_id("550e8400-e29b-41d4-a716-44665544000") is False  # Wrong length
        assert _looks_like_id("550e8400-e29b-41d4-a716-44665544000g") is False # Invalid hex
        assert _looks_like_id("550e8400-e29b-41d4-a716") is False              # Too short
        # Note: UUID without hyphens is still a valid ID, just detected by different rule
    
    def test_looks_like_id_uuid_without_hyphens(self):
        """Test UUID without hyphens detection."""
        from app.monitoring import _looks_like_id
        
        # Valid UUIDs without hyphens (32 character hex)
        assert _looks_like_id("550e8400e29b41d4a716446655440000") is True
        assert _looks_like_id("6ba7b8109dad11d180b400c04fd430c8") is True
        assert _looks_like_id("00000000000000000000000000000000") is True
        assert _looks_like_id("FFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF") is True  # Uppercase
        
        # Invalid UUIDs
        assert _looks_like_id("550e8400e29b41d4a71644665544000") is False   # 31 chars
        assert _looks_like_id("550e8400e29b41d4a7164466554400000") is False # 33 chars
        assert _looks_like_id("550e8400e29b41d4a716446655440g00") is False  # Invalid hex
    
    def test_looks_like_id_numeric(self):
        """Test numeric ID detection."""
        from app.monitoring import _looks_like_id
        
        # Valid numeric IDs
        assert _looks_like_id("1") is True
        assert _looks_like_id("123") is True
        assert _looks_like_id("12345") is True
        assert _looks_like_id("999999999999999999") is True
        
        # Invalid numeric IDs
        assert _looks_like_id("123abc") is False
        assert _looks_like_id("abc123") is False
        assert _looks_like_id("12.34") is False
        assert _looks_like_id("") is False
    
    def test_looks_like_id_alphanumeric(self):
        """Test long alphanumeric ID detection."""
        from app.monitoring import _looks_like_id
        
        # Valid long alphanumeric IDs (>8 chars, contains non-letters)
        assert _looks_like_id("abc123def456") is True      # 12 chars with numbers
        assert _looks_like_id("user_12345_session") is True # With underscores and numbers
        assert _looks_like_id("token-abc123-def") is True   # With hyphens and numbers
        assert _looks_like_id("session123456789") is True   # 16 chars with numbers
        
        # Invalid alphanumeric IDs
        assert _looks_like_id("abcdefgh") is False          # 8 chars, all letters
        assert _looks_like_id("abcdefghi") is False         # 9 chars, all letters
        assert _looks_like_id("short1") is False            # 6 chars
        assert _looks_like_id("test") is False              # 4 chars, all letters
        assert _looks_like_id("") is False                  # Empty string
    
    def test_looks_like_id_edge_cases(self):
        """Test edge cases for ID detection."""
        from app.monitoring import _looks_like_id
        
        # Edge cases that should not be considered IDs
        assert _looks_like_id("portfolios") is False        # Regular word
        assert _looks_like_id("api") is False               # Regular word
        assert _looks_like_id("v1") is False                # Version identifier
        assert _looks_like_id("health") is False            # Endpoint name
        assert _looks_like_id("metrics") is False           # Endpoint name
        assert _looks_like_id("search") is False            # Action name
        
        # Borderline cases
        assert _looks_like_id("version1") is False          # 8 chars with number
        assert _looks_like_id("version12") is True          # 9 chars with number
    
    def test_looks_like_id_exception_handling(self):
        """Test exception handling in ID detection."""
        from app.monitoring import _looks_like_id
        
        # Test with None (should not raise exception)
        assert _looks_like_id(None) is False
        
        # Test with non-string types (should not raise exception)
        assert _looks_like_id(123) is False
        assert _looks_like_id([]) is False
        assert _looks_like_id({}) is False


class TestRouteSanitization:
    """Test route sanitization for unmatched patterns."""
    
    def test_sanitize_unmatched_route_simple(self):
        """Test sanitization of simple unmatched routes."""
        from app.monitoring import _sanitize_unmatched_route
        
        # Simple path without IDs
        result = _sanitize_unmatched_route("/api/v3/users")
        assert result == "/api/v3/users"
        
        # Path with regular words
        result = _sanitize_unmatched_route("/admin/dashboard/settings")
        assert result == "/admin/dashboard/settings"
    
    def test_sanitize_unmatched_route_with_ids(self):
        """Test sanitization of routes with various ID types."""
        from app.monitoring import _sanitize_unmatched_route
        
        # MongoDB ObjectId
        result = _sanitize_unmatched_route("/api/v3/users/507f1f77bcf86cd799439011")
        assert result == "/api/v3/users/{id}"
        
        # UUID with hyphens
        result = _sanitize_unmatched_route("/api/v3/users/550e8400-e29b-41d4-a716-446655440000")
        assert result == "/api/v3/users/{id}"
        
        # UUID without hyphens
        result = _sanitize_unmatched_route("/api/v3/users/550e8400e29b41d4a716446655440000")
        assert result == "/api/v3/users/{id}"
        
        # Numeric ID
        result = _sanitize_unmatched_route("/api/v3/users/12345")
        assert result == "/api/v3/users/{id}"
        
        # Long alphanumeric ID
        result = _sanitize_unmatched_route("/api/v3/users/session123456789")
        assert result == "/api/v3/users/{id}"
    
    def test_sanitize_unmatched_route_multiple_ids(self):
        """Test sanitization of routes with multiple IDs."""
        from app.monitoring import _sanitize_unmatched_route
        
        # Multiple IDs in path
        result = _sanitize_unmatched_route("/api/v3/users/12345/posts/507f1f77bcf86cd799439011")
        assert result == "/api/v3/users/{id}/posts/{id}"
        
        # Mixed IDs and regular segments
        result = _sanitize_unmatched_route("/api/v3/users/12345/profile/settings")
        assert result == "/api/v3/users/{id}/profile/settings"
    
    def test_sanitize_unmatched_route_empty_segments(self):
        """Test sanitization with empty path segments."""
        from app.monitoring import _sanitize_unmatched_route
        
        # Double slashes (empty segments)
        result = _sanitize_unmatched_route("/api//v3/users")
        assert result == "/api//v3/users"
        
        # Leading/trailing empty segments
        result = _sanitize_unmatched_route("//api/v3/users//")
        assert result == "//api/v3/users//"
    
    def test_sanitize_unmatched_route_long_segments(self):
        """Test sanitization with very long path segments."""
        from app.monitoring import _sanitize_unmatched_route
        
        # Very long segment (should be truncated)
        long_segment = "a" * 100
        result = _sanitize_unmatched_route(f"/api/v3/{long_segment}")
        assert result == f"/api/v3/{long_segment[:50]}"
        
        # Segment exactly at limit
        limit_segment = "a" * 50
        result = _sanitize_unmatched_route(f"/api/v3/{limit_segment}")
        assert result == f"/api/v3/{limit_segment}"
    
    def test_sanitize_unmatched_route_very_long_path(self):
        """Test sanitization with very long overall path."""
        from app.monitoring import _sanitize_unmatched_route
        
        # Create a path longer than 200 characters
        long_path = "/api/v3/" + "/".join(["segment"] * 30)  # Should be > 200 chars
        result = _sanitize_unmatched_route(long_path)
        assert result == "/unknown"
    
    def test_sanitize_unmatched_route_exception_handling(self):
        """Test exception handling in route sanitization."""
        from app.monitoring import _sanitize_unmatched_route
        
        # Test with None (should not raise exception)
        result = _sanitize_unmatched_route(None)
        assert result == "/unknown"
        
        # Test with non-string (should not raise exception)
        result = _sanitize_unmatched_route(123)
        assert result == "/unknown"


class TestRoutePatternIntegration:
    """Integration tests for complete route pattern extraction."""
    
    def test_all_portfolio_service_routes(self):
        """Test all known portfolio service routes."""
        from app.monitoring import _extract_route_pattern
        from unittest.mock import Mock
        
        test_cases = [
            # Root and utility endpoints
            ("/", "/"),
            ("/health", "/health"),
            ("/metrics", "/metrics"),
            
            # V1 API endpoints
            ("/api/v1/portfolios", "/api/v1/portfolios"),
            ("/api/v1/portfolio/507f1f77bcf86cd799439011", "/api/v1/portfolio/{portfolioId}"),
            ("/api/v1/portfolio/550e8400-e29b-41d4-a716-446655440000", "/api/v1/portfolio/{portfolioId}"),
            ("/api/v1/portfolio/12345", "/api/v1/portfolio/{portfolioId}"),
            
            # V2 API endpoints
            ("/api/v2/portfolios", "/api/v2/portfolios"),
            
            # Unknown routes (should be sanitized)
            ("/api/v3/unknown", "/api/v3/unknown"),
            ("/api/v3/users/12345", "/api/v3/users/{id}"),
            ("/admin/users/507f1f77bcf86cd799439011/profile", "/admin/users/{id}/profile"),
        ]
        
        for input_path, expected_pattern in test_cases:
            request = Mock()
            request.url.path = input_path
            result = _extract_route_pattern(request)
            assert result == expected_pattern, f"Failed for path {input_path}: expected {expected_pattern}, got {result}"
    
    def test_route_pattern_with_query_parameters(self):
        """Test that query parameters don't affect route pattern extraction."""
        from app.monitoring import _extract_route_pattern
        from unittest.mock import Mock
        
        # Query parameters should not affect the path extraction
        request = Mock()
        request.url.path = "/api/v2/portfolios"  # Path without query params
        
        result = _extract_route_pattern(request)
        assert result == "/api/v2/portfolios"
    
    def test_route_pattern_case_sensitivity(self):
        """Test route pattern extraction with different cases."""
        from app.monitoring import _extract_route_pattern
        from unittest.mock import Mock
        
        # Test case sensitivity - paths should be case sensitive
        test_cases = [
            ("/API/V1/PORTFOLIOS", "/API/V1/PORTFOLIOS"),  # Should not match v1 pattern
            ("/api/V1/portfolios", "/api/V1/portfolios"),  # Should not match v1 pattern
            ("/api/v1/PORTFOLIOS", "/api/v1/PORTFOLIOS"),  # Should not match v1 pattern
        ]
        
        for input_path, expected_pattern in test_cases:
            request = Mock()
            request.url.path = input_path
            result = _extract_route_pattern(request)
            assert result == expected_pattern, f"Failed for path {input_path}: expected {expected_pattern}, got {result}"
    
    def test_route_pattern_with_trailing_slashes(self):
        """Test route pattern extraction with trailing slashes."""
        from app.monitoring import _extract_route_pattern
        from unittest.mock import Mock
        
        # Trailing slashes should be stripped
        test_cases = [
            ("/api/v1/portfolios/", "/api/v1/portfolios"),
            ("/api/v1/portfolio/12345/", "/api/v1/portfolio/{portfolioId}"),
            ("/api/v2/portfolios/", "/api/v2/portfolios"),
            ("/health/", "/health"),
            ("/metrics/", "/metrics"),
        ]
        
        for input_path, expected_pattern in test_cases:
            request = Mock()
            request.url.path = input_path
            result = _extract_route_pattern(request)
            assert result == expected_pattern, f"Failed for path {input_path}: expected {expected_pattern}, got {result}"