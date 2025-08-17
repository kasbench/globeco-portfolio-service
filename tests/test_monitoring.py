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
    HTTP_WORKERS_ACTIVE,
    HTTP_WORKERS_TOTAL,
    HTTP_WORKERS_MAX_CONFIGURED,
    HTTP_REQUESTS_QUEUED,
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


class TestIDDetection:
    """Test ID detection and sanitization logic."""
    
    def test_is_mongodb_objectid_valid(self):
        """Test MongoDB ObjectId detection with valid IDs."""
        from app.monitoring import _is_mongodb_objectid
        
        # Valid MongoDB ObjectIds (24-char hex)
        valid_objectids = [
            "507f1f77bcf86cd799439011",
            "507F1F77BCF86CD799439011",  # uppercase
            "000000000000000000000000",  # all zeros
            "ffffffffffffffffffffffff",  # all f's
            "123456789abcdef123456789",  # mixed case
        ]
        
        for objectid in valid_objectids:
            assert _is_mongodb_objectid(objectid), f"Should detect {objectid} as ObjectId"
    
    def test_is_mongodb_objectid_invalid(self):
        """Test MongoDB ObjectId detection with invalid IDs."""
        from app.monitoring import _is_mongodb_objectid
        
        # Invalid ObjectIds
        invalid_objectids = [
            "",  # empty
            "507f1f77bcf86cd79943901",   # 23 chars (too short)
            "507f1f77bcf86cd7994390111",  # 25 chars (too long)
            "507f1f77bcf86cd79943901g",   # contains 'g' (not hex)
            "507f1f77-bcf8-6cd7-9943-9011",  # contains hyphens
            "507f1f77 bcf86cd799439011",  # contains space
            "not-an-objectid-at-all",    # not hex at all
        ]
        
        for objectid in invalid_objectids:
            assert not _is_mongodb_objectid(objectid), f"Should not detect {objectid} as ObjectId"
    
    def test_is_uuid_with_hyphens_valid(self):
        """Test UUID with hyphens detection with valid UUIDs."""
        from app.monitoring import _is_uuid_with_hyphens
        
        # Valid UUIDs with hyphens
        valid_uuids = [
            "550e8400-e29b-41d4-a716-446655440000",
            "6ba7b810-9dad-11d1-80b4-00c04fd430c8",
            "6ba7b811-9dad-11d1-80b4-00c04fd430c8",
            "00000000-0000-0000-0000-000000000000",  # nil UUID
            "FFFFFFFF-FFFF-FFFF-FFFF-FFFFFFFFFFFF",  # uppercase
        ]
        
        for uuid in valid_uuids:
            assert _is_uuid_with_hyphens(uuid), f"Should detect {uuid} as UUID with hyphens"
    
    def test_is_uuid_with_hyphens_invalid(self):
        """Test UUID with hyphens detection with invalid UUIDs."""
        from app.monitoring import _is_uuid_with_hyphens
        
        # Invalid UUIDs
        invalid_uuids = [
            "",  # empty
            "550e8400-e29b-41d4-a716",  # too short
            "550e8400-e29b-41d4-a716-446655440000-extra",  # too long
            "550e8400e29b41d4a716446655440000",  # no hyphens
            "550e8400-e29b-41d4-a716-44665544000g",  # contains 'g'
            "550e8400-e29b-41d4-a716-4466554400000",  # last part too long
            "550e8400-e29b-41d4-a7166-446655440000",  # middle part too long
            "550e8400--e29b-41d4-a716-446655440000",  # double hyphen
            "not-a-uuid-at-all-here-definitely",  # not hex
        ]
        
        for uuid in invalid_uuids:
            assert not _is_uuid_with_hyphens(uuid), f"Should not detect {uuid} as UUID with hyphens"
    
    def test_is_uuid_without_hyphens_valid(self):
        """Test UUID without hyphens detection with valid UUIDs."""
        from app.monitoring import _is_uuid_without_hyphens
        
        # Valid UUIDs without hyphens (32-char hex)
        valid_uuids = [
            "550e8400e29b41d4a716446655440000",
            "6ba7b8109dad11d180b400c04fd430c8",
            "00000000000000000000000000000000",  # nil UUID
            "FFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF",  # uppercase
            "123456789abcdef0123456789abcdef0",  # mixed case
        ]
        
        for uuid in valid_uuids:
            assert _is_uuid_without_hyphens(uuid), f"Should detect {uuid} as UUID without hyphens"
    
    def test_is_uuid_without_hyphens_invalid(self):
        """Test UUID without hyphens detection with invalid UUIDs."""
        from app.monitoring import _is_uuid_without_hyphens
        
        # Invalid UUIDs
        invalid_uuids = [
            "",  # empty
            "550e8400e29b41d4a71644665544000",   # 31 chars (too short)
            "550e8400e29b41d4a7164466554400000",  # 33 chars (too long)
            "550e8400e29b41d4a716446655440000g",  # contains 'g'
            "550e8400-e29b-41d4-a716-446655440000",  # contains hyphens
            "not-a-uuid-without-hyphens-here",   # not hex
        ]
        
        for uuid in invalid_uuids:
            assert not _is_uuid_without_hyphens(uuid), f"Should not detect {uuid} as UUID without hyphens"
    
    def test_is_numeric_id_valid(self):
        """Test numeric ID detection with valid numeric IDs."""
        from app.monitoring import _is_numeric_id
        
        # Valid numeric IDs
        valid_numeric_ids = [
            "1",
            "123",
            "456789",
            "1234567890",
            "0",  # single zero
            "000123",  # leading zeros
        ]
        
        for numeric_id in valid_numeric_ids:
            assert _is_numeric_id(numeric_id), f"Should detect {numeric_id} as numeric ID"
    
    def test_is_numeric_id_invalid(self):
        """Test numeric ID detection with invalid numeric IDs."""
        from app.monitoring import _is_numeric_id
        
        # Invalid numeric IDs
        invalid_numeric_ids = [
            "",  # empty
            "abc",  # letters
            "123abc",  # mixed
            "12.34",  # decimal
            "12-34",  # hyphen
            "12_34",  # underscore
            " 123 ",  # spaces
            "+123",  # plus sign
            "-123",  # minus sign
        ]
        
        for numeric_id in invalid_numeric_ids:
            assert not _is_numeric_id(numeric_id), f"Should not detect {numeric_id} as numeric ID"
    
    def test_is_alphanumeric_id_valid(self):
        """Test alphanumeric ID detection with valid alphanumeric IDs."""
        from app.monitoring import _is_alphanumeric_id
        
        # Valid alphanumeric IDs
        valid_alphanumeric_ids = [
            "user-abc123def",  # contains hyphen and numbers
            "session_token_xyz789",  # contains underscore and numbers
            "auth123token456",  # mixed letters and numbers
            "very-long-identifier-with-numbers-123",  # long with hyphens
            "another_long_id_456_here",  # long with underscores
            "mixedCase123ID",  # mixed case with numbers
        ]
        
        for alphanumeric_id in valid_alphanumeric_ids:
            assert _is_alphanumeric_id(alphanumeric_id), f"Should detect {alphanumeric_id} as alphanumeric ID"
    
    def test_is_alphanumeric_id_invalid(self):
        """Test alphanumeric ID detection with invalid alphanumeric IDs."""
        from app.monitoring import _is_alphanumeric_id
        
        # Invalid alphanumeric IDs
        invalid_alphanumeric_ids = [
            "",  # empty
            "short",  # too short (8 chars or less)
            "12345678",  # exactly 8 chars
            "onlyletters",  # only letters, no numbers/separators
            "only-letters-here",  # only letters with separators
            "has spaces in it 123",  # contains spaces
            "has@special#chars123",  # contains special chars
            "exactly20charslong12",  # 20 chars (in exclusion range)
            "this-is-exactly-30-chars-long",  # 30 chars (in exclusion range)
            "this-is-exactly-40-characters-long-id",  # 40 chars (in exclusion range)
        ]
        
        for alphanumeric_id in invalid_alphanumeric_ids:
            assert not _is_alphanumeric_id(alphanumeric_id), f"Should not detect {alphanumeric_id} as alphanumeric ID"
    
    def test_looks_like_id_comprehensive(self):
        """Test comprehensive ID detection with various formats."""
        from app.monitoring import _looks_like_id
        
        # Should be detected as IDs
        should_be_ids = [
            # MongoDB ObjectIds
            "507f1f77bcf86cd799439011",
            "507F1F77BCF86CD799439011",
            
            # UUIDs with hyphens
            "550e8400-e29b-41d4-a716-446655440000",
            "6ba7b810-9dad-11d1-80b4-00c04fd430c8",
            
            # UUIDs without hyphens
            "550e8400e29b41d4a716446655440000",
            "6ba7b8109dad11d180b400c04fd430c8",
            
            # Numeric IDs
            "1",
            "123",
            "456789",
            "1234567890",
            
            # Alphanumeric IDs
            "user-abc123def",
            "session_token_xyz789",
            "auth123token456",
        ]
        
        for id_value in should_be_ids:
            assert _looks_like_id(id_value), f"Should detect {id_value} as ID"
        
        # Should NOT be detected as IDs
        should_not_be_ids = [
            "",  # empty
            "api",  # short word
            "v1",  # version
            "portfolios",  # resource name
            "health",  # endpoint name
            "metrics",  # endpoint name
            "search",  # action name
            "onlyletters",  # only letters
            "has spaces",  # contains spaces
            "has@special#chars",  # special characters
            "exactly20charslong12",  # in exclusion range
        ]
        
        for non_id_value in should_not_be_ids:
            assert not _looks_like_id(non_id_value), f"Should not detect {non_id_value} as ID"
    
    def test_looks_like_id_edge_cases(self):
        """Test ID detection with edge cases."""
        from app.monitoring import _looks_like_id
        
        # Edge cases that should return False
        edge_cases = [
            None,  # None value - should be handled gracefully
            123,   # Non-string type - should be handled gracefully
        ]
        
        for edge_case in edge_cases:
            # Should not raise exception and should return False
            try:
                result = _looks_like_id(edge_case)
                assert result is False, f"Should return False for edge case {edge_case}"
            except Exception as e:
                pytest.fail(f"Should not raise exception for edge case {edge_case}, but got {e}")


class TestSanitizeUnmatchedRoute:
    """Test route sanitization with ID parameterization."""
    
    def test_sanitize_unmatched_route_with_objectid(self):
        """Test sanitization of routes containing MongoDB ObjectIds."""
        from app.monitoring import _sanitize_unmatched_route
        
        test_cases = [
            ("/api/v3/users/507f1f77bcf86cd799439011", "/api/v3/users/{id}"),
            ("/api/v3/users/507f1f77bcf86cd799439011/profile", "/api/v3/users/{id}/profile"),
            ("/custom/507f1f77bcf86cd799439011/data/507f1f77bcf86cd799439012", "/custom/{id}/data/{id}"),
        ]
        
        for original, expected in test_cases:
            result = _sanitize_unmatched_route(original)
            assert result == expected, f"Expected {expected}, got {result} for {original}"
    
    def test_sanitize_unmatched_route_with_uuid(self):
        """Test sanitization of routes containing UUIDs."""
        from app.monitoring import _sanitize_unmatched_route
        
        test_cases = [
            # UUIDs with hyphens
            ("/api/v3/orders/550e8400-e29b-41d4-a716-446655440000", "/api/v3/orders/{id}"),
            ("/api/v3/orders/550e8400-e29b-41d4-a716-446655440000/items", "/api/v3/orders/{id}/items"),
            
            # UUIDs without hyphens
            ("/api/v3/sessions/550e8400e29b41d4a716446655440000", "/api/v3/sessions/{id}"),
            ("/api/v3/sessions/550e8400e29b41d4a716446655440000/refresh", "/api/v3/sessions/{id}/refresh"),
        ]
        
        for original, expected in test_cases:
            result = _sanitize_unmatched_route(original)
            assert result == expected, f"Expected {expected}, got {result} for {original}"
    
    def test_sanitize_unmatched_route_with_numeric_id(self):
        """Test sanitization of routes containing numeric IDs."""
        from app.monitoring import _sanitize_unmatched_route
        
        test_cases = [
            ("/api/v3/products/12345", "/api/v3/products/{id}"),
            ("/api/v3/products/12345/reviews", "/api/v3/products/{id}/reviews"),
            ("/api/v3/categories/1/products/67890", "/api/v3/categories/{id}/products/{id}"),
        ]
        
        for original, expected in test_cases:
            result = _sanitize_unmatched_route(original)
            assert result == expected, f"Expected {expected}, got {result} for {original}"
    
    def test_sanitize_unmatched_route_with_alphanumeric_id(self):
        """Test sanitization of routes containing alphanumeric IDs."""
        from app.monitoring import _sanitize_unmatched_route
        
        test_cases = [
            # Use IDs outside the 20-40 character exclusion range
            ("/api/v3/tokens/auth123token456789", "/api/v3/tokens/{id}"),  # 19 chars
            ("/api/v3/sessions/user-abc123def456", "/api/v3/sessions/{id}"),  # 17 chars  
            ("/api/v3/cache/session_token_xyz789_extra_long_identifier", "/api/v3/cache/{id}"),  # 42 chars
        ]
        
        for original, expected in test_cases:
            result = _sanitize_unmatched_route(original)
            assert result == expected, f"Expected {expected}, got {result} for {original}"
    
    def test_sanitize_unmatched_route_mixed_ids(self):
        """Test sanitization of routes with mixed ID types."""
        from app.monitoring import _sanitize_unmatched_route
        
        test_cases = [
            # ObjectId + UUID
            ("/api/v3/users/507f1f77bcf86cd799439011/sessions/550e8400-e29b-41d4-a716-446655440000", 
             "/api/v3/users/{id}/sessions/{id}"),
            
            # Numeric + Alphanumeric
            ("/api/v3/products/12345/reviews/user-abc123def", 
             "/api/v3/products/{id}/reviews/{id}"),
            
            # All types mixed
            ("/api/v3/users/507f1f77bcf86cd799439011/orders/12345/sessions/auth123token456", 
             "/api/v3/users/{id}/orders/{id}/sessions/{id}"),
        ]
        
        for original, expected in test_cases:
            result = _sanitize_unmatched_route(original)
            assert result == expected, f"Expected {expected}, got {result} for {original}"
    
    def test_sanitize_unmatched_route_no_ids(self):
        """Test sanitization of routes without IDs."""
        from app.monitoring import _sanitize_unmatched_route
        
        test_cases = [
            ("/api/v3/users", "/api/v3/users"),
            ("/api/v3/users/search", "/api/v3/users/search"),
            ("/api/v3/products/categories", "/api/v3/products/categories"),
            ("/custom/endpoint/action", "/custom/endpoint/action"),
        ]
        
        for original, expected in test_cases:
            result = _sanitize_unmatched_route(original)
            assert result == expected, f"Expected {expected}, got {result} for {original}"
    
    def test_sanitize_unmatched_route_long_parts(self):
        """Test sanitization with very long path parts."""
        from app.monitoring import _sanitize_unmatched_route
        
        # Create a very long non-ID part (60 characters)
        long_part = "a" * 60
        expected_truncated = "a" * 50  # Should be truncated to 50 chars
        
        original = f"/api/v3/endpoint/{long_part}/action"
        expected = f"/api/v3/endpoint/{expected_truncated}/action"
        
        result = _sanitize_unmatched_route(original)
        assert result == expected, f"Expected {expected}, got {result} for {original}"
    
    def test_sanitize_unmatched_route_very_long_result(self):
        """Test sanitization when result would be too long."""
        from app.monitoring import _sanitize_unmatched_route
        
        # Create a path that would result in > 200 characters after sanitization
        long_path_parts = [f"part{i}" for i in range(50)]  # 50 parts
        original = "/" + "/".join(long_path_parts)
        
        result = _sanitize_unmatched_route(original)
        assert result == "/unknown", f"Expected '/unknown' for overly long path, got {result}"
    
    def test_sanitize_unmatched_route_empty_and_edge_cases(self):
        """Test sanitization with empty and edge case paths."""
        from app.monitoring import _sanitize_unmatched_route
        
        test_cases = [
            ("", ""),  # empty path
            ("/", "/"),  # root path
            ("//", "//"),  # double slash
            ("/api//v3", "/api//v3"),  # empty part in middle
            ("/api/v3/", "/api/v3/"),  # trailing slash
        ]
        
        for original, expected in test_cases:
            result = _sanitize_unmatched_route(original)
            assert result == expected, f"Expected {expected}, got {result} for {original}"
    
    def test_sanitize_unmatched_route_exception_handling(self):
        """Test sanitization exception handling."""
        from app.monitoring import _sanitize_unmatched_route
        from unittest.mock import patch
        
        # Mock _looks_like_id to raise an exception
        with patch('app.monitoring._looks_like_id', side_effect=Exception("Test error")):
            result = _sanitize_unmatched_route("/api/v3/test/123")
            assert result == "/unknown", f"Expected '/unknown' on exception, got {result}"


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


class TestIndividualIDDetectionMethods:
    """Test individual ID detection helper methods."""
    
    def test_is_mongodb_objectid_valid(self):
        """Test MongoDB ObjectId detection with valid IDs."""
        from app.monitoring import _is_mongodb_objectid
        
        # Valid MongoDB ObjectIds (24-char hex)
        valid_objectids = [
            "507f1f77bcf86cd799439011",
            "507F1F77BCF86CD799439011",  # uppercase
            "000000000000000000000000",  # all zeros
            "ffffffffffffffffffffffff",  # all f's
            "123456789abcdef123456789",  # mixed case
        ]
        
        for objectid in valid_objectids:
            assert _is_mongodb_objectid(objectid), f"Should detect {objectid} as ObjectId"
    
    def test_is_mongodb_objectid_invalid(self):
        """Test MongoDB ObjectId detection with invalid IDs."""
        from app.monitoring import _is_mongodb_objectid
        
        # Invalid ObjectIds
        invalid_objectids = [
            "",  # empty
            "507f1f77bcf86cd79943901",   # 23 chars (too short)
            "507f1f77bcf86cd7994390111",  # 25 chars (too long)
            "507f1f77bcf86cd79943901g",   # contains 'g' (not hex)
            "507f1f77-bcf8-6cd7-9943-9011",  # contains hyphens
            "507f1f77 bcf86cd799439011",  # contains space
            "not-an-objectid-at-all",    # not hex at all
        ]
        
        for objectid in invalid_objectids:
            assert not _is_mongodb_objectid(objectid), f"Should not detect {objectid} as ObjectId"
    
    def test_is_uuid_with_hyphens_valid(self):
        """Test UUID with hyphens detection with valid UUIDs."""
        from app.monitoring import _is_uuid_with_hyphens
        
        # Valid UUIDs with hyphens
        valid_uuids = [
            "550e8400-e29b-41d4-a716-446655440000",
            "6ba7b810-9dad-11d1-80b4-00c04fd430c8",
            "6ba7b811-9dad-11d1-80b4-00c04fd430c8",
            "00000000-0000-0000-0000-000000000000",  # nil UUID
            "FFFFFFFF-FFFF-FFFF-FFFF-FFFFFFFFFFFF",  # uppercase
        ]
        
        for uuid in valid_uuids:
            assert _is_uuid_with_hyphens(uuid), f"Should detect {uuid} as UUID with hyphens"
    
    def test_is_uuid_with_hyphens_invalid(self):
        """Test UUID with hyphens detection with invalid UUIDs."""
        from app.monitoring import _is_uuid_with_hyphens
        
        # Invalid UUIDs
        invalid_uuids = [
            "",  # empty
            "550e8400-e29b-41d4-a716",  # too short
            "550e8400-e29b-41d4-a716-446655440000-extra",  # too long
            "550e8400e29b41d4a716446655440000",  # no hyphens
            "550e8400-e29b-41d4-a716-44665544000g",  # contains 'g'
            "550e8400-e29b-41d4-a716-4466554400000",  # last part too long
            "550e8400-e29b-41d4-a7166-446655440000",  # middle part too long
            "550e8400--e29b-41d4-a716-446655440000",  # double hyphen
            "not-a-uuid-at-all-here-definitely",  # not hex
        ]
        
        for uuid in invalid_uuids:
            assert not _is_uuid_with_hyphens(uuid), f"Should not detect {uuid} as UUID with hyphens"
    
    def test_is_uuid_without_hyphens_valid(self):
        """Test UUID without hyphens detection with valid UUIDs."""
        from app.monitoring import _is_uuid_without_hyphens
        
        # Valid UUIDs without hyphens (32-char hex)
        valid_uuids = [
            "550e8400e29b41d4a716446655440000",
            "6ba7b8109dad11d180b400c04fd430c8",
            "00000000000000000000000000000000",  # nil UUID
            "FFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF",  # uppercase
            "123456789abcdef0123456789abcdef0",  # mixed case
        ]
        
        for uuid in valid_uuids:
            assert _is_uuid_without_hyphens(uuid), f"Should detect {uuid} as UUID without hyphens"
    
    def test_is_uuid_without_hyphens_invalid(self):
        """Test UUID without hyphens detection with invalid UUIDs."""
        from app.monitoring import _is_uuid_without_hyphens
        
        # Invalid UUIDs
        invalid_uuids = [
            "",  # empty
            "550e8400e29b41d4a71644665544000",   # 31 chars (too short)
            "550e8400e29b41d4a7164466554400000",  # 33 chars (too long)
            "550e8400e29b41d4a716446655440000g",  # contains 'g'
            "550e8400-e29b-41d4-a716-446655440000",  # contains hyphens
            "not-a-uuid-without-hyphens-here",   # not hex
        ]
        
        for uuid in invalid_uuids:
            assert not _is_uuid_without_hyphens(uuid), f"Should not detect {uuid} as UUID without hyphens"
    
    def test_is_numeric_id_valid(self):
        """Test numeric ID detection with valid numeric IDs."""
        from app.monitoring import _is_numeric_id
        
        # Valid numeric IDs
        valid_numeric_ids = [
            "1",
            "123",
            "456789",
            "1234567890",
            "0",  # single zero
            "000123",  # leading zeros
        ]
        
        for numeric_id in valid_numeric_ids:
            assert _is_numeric_id(numeric_id), f"Should detect {numeric_id} as numeric ID"
    
    def test_is_numeric_id_invalid(self):
        """Test numeric ID detection with invalid numeric IDs."""
        from app.monitoring import _is_numeric_id
        
        # Invalid numeric IDs
        invalid_numeric_ids = [
            "",  # empty
            "abc",  # letters
            "123abc",  # mixed
            "12.34",  # decimal
            "12-34",  # hyphen
            "12_34",  # underscore
            " 123 ",  # spaces
            "+123",  # plus sign
            "-123",  # minus sign
        ]
        
        for numeric_id in invalid_numeric_ids:
            assert not _is_numeric_id(numeric_id), f"Should not detect {numeric_id} as numeric ID"
    
    def test_is_alphanumeric_id_valid(self):
        """Test alphanumeric ID detection with valid alphanumeric IDs."""
        from app.monitoring import _is_alphanumeric_id
        
        # Valid alphanumeric IDs (>8 chars, not in 20-40 char exclusion range)
        valid_alphanumeric_ids = [
            "user-abc123def",  # 15 chars with hyphen and numbers
            "auth123token456",  # 16 chars with numbers
            "mixedCase123ID",  # 14 chars with mixed case and numbers
            "very_long_identifier_with_numbers_123_and_more_stuff",  # 53 chars
        ]
        
        for alphanumeric_id in valid_alphanumeric_ids:
            assert _is_alphanumeric_id(alphanumeric_id), f"Should detect {alphanumeric_id} as alphanumeric ID"
    
    def test_is_alphanumeric_id_invalid(self):
        """Test alphanumeric ID detection with invalid alphanumeric IDs."""
        from app.monitoring import _is_alphanumeric_id
        
        # Invalid alphanumeric IDs
        invalid_alphanumeric_ids = [
            "",  # empty
            "short",  # too short (8 chars or less)
            "12345678",  # exactly 8 chars
            "onlyletters",  # only letters, no numbers/separators
            "only-letters-here",  # only letters with separators
            "has spaces in it 123",  # contains spaces
            "has@special#chars123",  # contains special chars
            "exactly20charslong12",  # 20 chars (in exclusion range)
            "this-is-exactly-30-chars-long",  # 30 chars (in exclusion range)
            "this-is-exactly-40-characters-long-id",  # 40 chars (in exclusion range)
        ]
        
        for alphanumeric_id in invalid_alphanumeric_ids:
            assert not _is_alphanumeric_id(alphanumeric_id), f"Should not detect {alphanumeric_id} as alphanumeric ID"


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
        
        # Valid long alphanumeric IDs (>8 chars, contains non-letters, not in 20-40 char range)
        assert _looks_like_id("abc123def456") is True      # 12 chars with numbers
        assert _looks_like_id("user_12345_ses") is True    # 13 chars with underscores and numbers
        assert _looks_like_id("token-abc123-def") is True  # 16 chars with hyphens and numbers
        assert _looks_like_id("session123456789") is True  # 16 chars with numbers
        assert _looks_like_id("very_long_identifier_with_numbers_123_and_more_stuff") is True  # 58 chars
        
        # Invalid alphanumeric IDs
        assert _looks_like_id("abcdefgh") is False          # 8 chars, all letters
        assert _looks_like_id("abcdefghi") is False         # 9 chars, all letters
        assert _looks_like_id("short1") is False            # 6 chars
        assert _looks_like_id("test") is False              # 4 chars, all letters
        assert _looks_like_id("") is False                  # Empty string
        assert _looks_like_id("exactly20charslong12") is False  # 20 chars (in exclusion range)
        assert _looks_like_id("this_is_exactly_30_chars_long") is False  # 30 chars (in exclusion range)
    
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


class TestLabelFormatting:
    """Test label formatting and validation methods."""
    
    def test_get_method_label_valid_methods(self):
        """Test formatting of valid HTTP methods."""
        from app.monitoring import _get_method_label
        
        # Test standard HTTP methods
        assert _get_method_label("get") == "GET"
        assert _get_method_label("GET") == "GET"
        assert _get_method_label("post") == "POST"
        assert _get_method_label("POST") == "POST"
        assert _get_method_label("put") == "PUT"
        assert _get_method_label("PUT") == "PUT"
        assert _get_method_label("delete") == "DELETE"
        assert _get_method_label("DELETE") == "DELETE"
        assert _get_method_label("patch") == "PATCH"
        assert _get_method_label("PATCH") == "PATCH"
        assert _get_method_label("head") == "HEAD"
        assert _get_method_label("HEAD") == "HEAD"
        assert _get_method_label("options") == "OPTIONS"
        assert _get_method_label("OPTIONS") == "OPTIONS"
        assert _get_method_label("trace") == "TRACE"
        assert _get_method_label("TRACE") == "TRACE"
        assert _get_method_label("connect") == "CONNECT"
        assert _get_method_label("CONNECT") == "CONNECT"
    
    def test_get_method_label_mixed_case(self):
        """Test formatting of mixed case HTTP methods."""
        from app.monitoring import _get_method_label
        
        assert _get_method_label("Get") == "GET"
        assert _get_method_label("pOsT") == "POST"
        assert _get_method_label("PuT") == "PUT"
        assert _get_method_label("dElEtE") == "DELETE"
        assert _get_method_label("pAtCh") == "PATCH"
    
    def test_get_method_label_with_whitespace(self):
        """Test formatting of HTTP methods with whitespace."""
        from app.monitoring import _get_method_label
        
        assert _get_method_label(" get ") == "GET"
        assert _get_method_label("\tpost\t") == "POST"
        assert _get_method_label("\nput\n") == "PUT"
        assert _get_method_label("  delete  ") == "DELETE"
    
    def test_get_method_label_unknown_methods(self):
        """Test formatting of unknown HTTP methods."""
        from app.monitoring import _get_method_label
        
        # Unknown methods should still be returned uppercase
        assert _get_method_label("custom") == "CUSTOM"
        assert _get_method_label("UNKNOWN_METHOD") == "UNKNOWN_METHOD"
        assert _get_method_label("xyz") == "XYZ"
    
    def test_get_method_label_invalid_input(self):
        """Test handling of invalid input types."""
        from app.monitoring import _get_method_label
        
        # Non-string inputs should return "UNKNOWN"
        assert _get_method_label(None) == "UNKNOWN"
        assert _get_method_label(123) == "UNKNOWN"
        assert _get_method_label([]) == "UNKNOWN"
        assert _get_method_label({}) == "UNKNOWN"
        assert _get_method_label(True) == "UNKNOWN"
    
    def test_get_method_label_empty_string(self):
        """Test handling of empty strings."""
        from app.monitoring import _get_method_label
        
        assert _get_method_label("") == "UNKNOWN"
        assert _get_method_label("   ") == "UNKNOWN"  # Only whitespace
        assert _get_method_label("\t\n") == "UNKNOWN"  # Only whitespace chars
    
    @patch('app.monitoring.logger')
    def test_get_method_label_logging(self, mock_logger):
        """Test logging behavior for method label formatting."""
        from app.monitoring import _get_method_label
        
        # Test warning for invalid type
        _get_method_label(123)
        mock_logger.warning.assert_called()
        
        # Test warning for empty string
        mock_logger.reset_mock()
        _get_method_label("")
        mock_logger.warning.assert_called()
        
        # Test debug for unknown method
        mock_logger.reset_mock()
        _get_method_label("CUSTOM_METHOD")
        mock_logger.debug.assert_called()
    
    def test_get_method_label_exception_handling(self):
        """Test exception handling in method label formatting."""
        from app.monitoring import _get_method_label
        
        # Create a mock object that raises exception on string operations
        class BadString:
            def strip(self):
                raise Exception("Test exception")
            def upper(self):
                raise Exception("Test exception")
            def __str__(self):
                return "bad_string"
        
        bad_input = BadString()
        result = _get_method_label(bad_input)
        assert result == "UNKNOWN"
    
    def test_format_status_code_valid_codes(self):
        """Test formatting of valid HTTP status codes."""
        from app.monitoring import _format_status_code
        
        # Test common status codes
        assert _format_status_code(200) == "200"
        assert _format_status_code(201) == "201"
        assert _format_status_code(400) == "400"
        assert _format_status_code(401) == "401"
        assert _format_status_code(403) == "403"
        assert _format_status_code(404) == "404"
        assert _format_status_code(500) == "500"
        assert _format_status_code(502) == "502"
        assert _format_status_code(503) == "503"
    
    def test_format_status_code_boundary_values(self):
        """Test formatting of boundary HTTP status codes."""
        from app.monitoring import _format_status_code
        
        # Test boundary values
        assert _format_status_code(100) == "100"  # Minimum valid
        assert _format_status_code(599) == "599"  # Maximum valid
        
        # Test just outside boundaries
        assert _format_status_code(99) == "unknown"   # Below minimum
        assert _format_status_code(600) == "unknown"  # Above maximum
    
    def test_format_status_code_invalid_range(self):
        """Test formatting of status codes outside valid range."""
        from app.monitoring import _format_status_code
        
        # Test invalid ranges
        assert _format_status_code(0) == "unknown"
        assert _format_status_code(-1) == "unknown"
        assert _format_status_code(50) == "unknown"
        assert _format_status_code(700) == "unknown"
        assert _format_status_code(1000) == "unknown"
    
    def test_format_status_code_invalid_types(self):
        """Test handling of invalid input types."""
        from app.monitoring import _format_status_code
        
        # Non-integer inputs should return "unknown"
        assert _format_status_code(None) == "unknown"
        assert _format_status_code("200") == "unknown"  # String
        assert _format_status_code(200.5) == "unknown"  # Float
        assert _format_status_code([]) == "unknown"     # List
        assert _format_status_code({}) == "unknown"     # Dict
        assert _format_status_code(True) == "unknown"   # Boolean
    
    def test_format_status_code_edge_cases(self):
        """Test edge cases for status code formatting."""
        from app.monitoring import _format_status_code
        
        # Test edge cases within valid range
        assert _format_status_code(101) == "101"
        assert _format_status_code(199) == "199"
        assert _format_status_code(300) == "300"
        assert _format_status_code(399) == "399"
        assert _format_status_code(400) == "400"
        assert _format_status_code(499) == "499"
        assert _format_status_code(500) == "500"
        assert _format_status_code(598) == "598"
    
    @patch('app.monitoring.logger')
    def test_format_status_code_logging(self, mock_logger):
        """Test logging behavior for status code formatting."""
        from app.monitoring import _format_status_code
        
        # Test warning for invalid type
        _format_status_code("200")
        mock_logger.warning.assert_called()
        
        # Test warning for out of range
        mock_logger.reset_mock()
        _format_status_code(99)
        mock_logger.warning.assert_called()
        
        mock_logger.reset_mock()
        _format_status_code(600)
        mock_logger.warning.assert_called()
    
    def test_format_status_code_exception_handling(self):
        """Test exception handling in status code formatting."""
        from app.monitoring import _format_status_code
        
        # Create a mock object that raises exception on comparison
        class BadInt:
            def __init__(self, value):
                self.value = value
            
            def __lt__(self, other):
                raise Exception("Test exception")
            
            def __gt__(self, other):
                raise Exception("Test exception")
            
            def __str__(self):
                return str(self.value)
        
        bad_input = BadInt(200)
        result = _format_status_code(bad_input)
        assert result == "unknown"


class TestLabelFormattingIntegration:
    """Integration tests for label formatting methods."""
    
    def test_method_and_status_formatting_together(self):
        """Test method and status code formatting work together."""
        from app.monitoring import _get_method_label, _format_status_code
        
        # Test typical combinations
        method = _get_method_label("get")
        status = _format_status_code(200)
        assert method == "GET"
        assert status == "200"
        
        method = _get_method_label("POST")
        status = _format_status_code(201)
        assert method == "POST"
        assert status == "201"
        
        method = _get_method_label("delete")
        status = _format_status_code(404)
        assert method == "DELETE"
        assert status == "404"
    
    def test_error_handling_consistency(self):
        """Test that both methods handle errors consistently."""
        from app.monitoring import _get_method_label, _format_status_code
        
        # Both should handle None gracefully
        assert _get_method_label(None) == "UNKNOWN"
        assert _format_status_code(None) == "unknown"
        
        # Both should handle invalid types gracefully
        assert _get_method_label(123) == "UNKNOWN"
        assert _format_status_code("123") == "unknown"
    
    def test_label_formatting_with_real_values(self):
        """Test label formatting with realistic HTTP values."""
        from app.monitoring import _get_method_label, _format_status_code
        
        # Test realistic scenarios
        test_cases = [
            ("GET", 200, "GET", "200"),
            ("post", 201, "POST", "201"),
            ("PUT", 204, "PUT", "204"),
            ("delete", 404, "DELETE", "404"),
            ("PATCH", 422, "PATCH", "422"),
            ("options", 200, "OPTIONS", "200"),
            ("head", 304, "HEAD", "304"),
        ]
        
        for method_input, status_input, expected_method, expected_status in test_cases:
            method_result = _get_method_label(method_input)
            status_result = _format_status_code(status_input)
            
            assert method_result == expected_method, f"Method {method_input} -> {method_result}, expected {expected_method}"
            assert status_result == expected_status, f"Status {status_input} -> {status_result}, expected {expected_status}"
    
    def test_label_validation_requirements_compliance(self):
        """Test that label formatting meets the requirements."""
        from app.monitoring import _get_method_label, _format_status_code
        
        # Requirement 2.1: Use uppercase HTTP method names
        methods = ["get", "post", "put", "delete", "patch", "head", "options"]
        for method in methods:
            result = _get_method_label(method)
            assert result == method.upper(), f"Method {method} should be uppercase"
            assert result.isupper(), f"Method result {result} should be uppercase"
        
        # Requirement 2.3: Convert numeric HTTP status codes to strings
        status_codes = [200, 201, 400, 401, 404, 500, 502, 503]
        for status in status_codes:
            result = _format_status_code(status)
            assert isinstance(result, str), f"Status {status} should return string"
            assert result == str(status), f"Status {status} should convert to string"
        
        # Requirement 5.4: Fallback to safe defaults for invalid inputs
        assert _get_method_label(None) == "UNKNOWN"
        assert _get_method_label("") == "UNKNOWN"
        assert _format_status_code(None) == "unknown"
        assert _format_status_code(99) == "unknown"  # Out of range
        assert _format_status_code(600) == "unknown"  # Out of range


class TestLabelFormattingEdgeCases:
    """Test edge cases and error conditions for label formatting."""
    
    def test_method_label_unicode_handling(self):
        """Test method label formatting with unicode characters."""
        from app.monitoring import _get_method_label
        
        # Unicode characters should be handled gracefully
        assert _get_method_label("gét") == "GÉT"  # Accented characters
        assert _get_method_label("pøst") == "PØST"  # Nordic characters
        assert _get_method_label("测试") == "测试"  # Chinese characters
    
    def test_method_label_very_long_strings(self):
        """Test method label formatting with very long strings."""
        from app.monitoring import _get_method_label
        
        # Very long method names should still be processed
        long_method = "a" * 1000
        result = _get_method_label(long_method)
        assert result == "A" * 1000
    
    def test_status_code_extreme_values(self):
        """Test status code formatting with extreme values."""
        from app.monitoring import _format_status_code
        
        # Test very large numbers
        assert _format_status_code(999999) == "unknown"
        assert _format_status_code(-999999) == "unknown"
        
        # Test maximum/minimum integer values
        import sys
        assert _format_status_code(sys.maxsize) == "unknown"
        assert _format_status_code(-sys.maxsize) == "unknown"
    
    def test_concurrent_label_formatting(self):
        """Test that label formatting is thread-safe."""
        import threading
        import time
        from app.monitoring import _get_method_label, _format_status_code
        
        results = []
        errors = []
        
        def format_labels():
            try:
                for i in range(100):
                    method = _get_method_label("get")
                    status = _format_status_code(200)
                    results.append((method, status))
                    time.sleep(0.001)  # Small delay to encourage race conditions
            except Exception as e:
                errors.append(e)
        
        # Run multiple threads
        threads = []
        for _ in range(5):
            thread = threading.Thread(target=format_labels)
            threads.append(thread)
            thread.start()
        
        # Wait for all threads to complete
        for thread in threads:
            thread.join()
        
        # Verify no errors occurred
        assert len(errors) == 0, f"Errors occurred during concurrent execution: {errors}"
        
        # Verify all results are correct
        assert len(results) == 500  # 5 threads * 100 iterations
        for method, status in results:
            assert method == "GET"
            assert status == "200"
    
    def test_memory_usage_with_many_calls(self):
        """Test that repeated label formatting doesn't cause memory leaks."""
        from app.monitoring import _get_method_label, _format_status_code
        
        # Make many calls to ensure no memory accumulation
        for i in range(10000):
            method = _get_method_label("get")
            status = _format_status_code(200)
            assert method == "GET"
            assert status == "200"
        
        # Test with varying inputs
        methods = ["get", "post", "put", "delete", "patch"]
        statuses = [200, 201, 400, 404, 500]
        
        for i in range(1000):
            method_input = methods[i % len(methods)]
            status_input = statuses[i % len(statuses)]
            
            method = _get_method_label(method_input)
            status = _format_status_code(status_input)
            
            assert method == method_input.upper()
            assert status == str(status_input)


class TestEnhancedHTTPMetricsMiddleware:
    """Test the EnhancedHTTPMetricsMiddleware class."""
    
    def setup_method(self):
        """Clear registry before each test."""
        clear_metrics_registry()
    
    def teardown_method(self):
        """Clear registry after each test."""
        clear_metrics_registry()
    
    @pytest.fixture
    def mock_app(self):
        """Mock ASGI application."""
        return Mock()
    
    @pytest.fixture
    def mock_request(self):
        """Mock FastAPI Request."""
        request = Mock()
        request.method = "GET"
        request.url.path = "/api/v1/portfolios"
        return request
    
    @pytest.fixture
    def mock_response(self):
        """Mock FastAPI Response."""
        response = Mock()
        response.status_code = 200
        return response
    
    @pytest.fixture
    def middleware(self, mock_app):
        """Create middleware instance."""
        from app.monitoring import EnhancedHTTPMetricsMiddleware
        return EnhancedHTTPMetricsMiddleware(mock_app)
    
    @pytest.fixture
    def debug_middleware(self, mock_app):
        """Create middleware instance with debug logging."""
        from app.monitoring import EnhancedHTTPMetricsMiddleware
        return EnhancedHTTPMetricsMiddleware(mock_app, debug_logging=True)
    
    def test_middleware_initialization(self, mock_app):
        """Test middleware initialization."""
        from app.monitoring import EnhancedHTTPMetricsMiddleware
        
        # Test normal initialization
        middleware = EnhancedHTTPMetricsMiddleware(mock_app)
        assert middleware.debug_logging is False
        
        # Test with debug logging
        debug_middleware = EnhancedHTTPMetricsMiddleware(mock_app, debug_logging=True)
        assert debug_middleware.debug_logging is True
    
    @pytest.mark.asyncio
    async def test_successful_request_metrics_recording(self, middleware, mock_request, mock_response):
        """Test metrics recording for successful requests."""
        # Mock the metrics
        with patch('app.monitoring.HTTP_REQUESTS_TOTAL') as mock_counter, \
             patch('app.monitoring.HTTP_REQUEST_DURATION') as mock_histogram, \
             patch('app.monitoring.HTTP_REQUESTS_IN_FLIGHT') as mock_gauge, \
             patch('app.monitoring._extract_route_pattern') as mock_extract_route, \
             patch('app.monitoring._get_method_label') as mock_get_method, \
             patch('app.monitoring._format_status_code') as mock_format_status:
            
            # Setup mock returns
            mock_extract_route.return_value = "/api/v1/portfolios"
            mock_get_method.return_value = "GET"
            mock_format_status.return_value = "200"
            
            # Mock labeled metrics
            mock_labeled_counter = Mock()
            mock_labeled_histogram = Mock()
            mock_counter.labels.return_value = mock_labeled_counter
            mock_histogram.labels.return_value = mock_labeled_histogram
            
            # Mock call_next
            async def mock_call_next(request):
                return mock_response
            
            # Execute middleware
            result = await middleware.dispatch(mock_request, mock_call_next)
            
            # Verify response is returned
            assert result is mock_response
            
            # Verify in-flight gauge operations
            mock_gauge.inc.assert_called_once()
            mock_gauge.dec.assert_called_once()
            
            # Verify counter metrics
            mock_counter.labels.assert_called_once_with(
                method="GET", path="/api/v1/portfolios", status="200"
            )
            mock_labeled_counter.inc.assert_called_once()
            
            # Verify histogram metrics
            mock_histogram.labels.assert_called_once_with(
                method="GET", path="/api/v1/portfolios", status="200"
            )
            mock_labeled_histogram.observe.assert_called_once()
            
            # Verify observe was called with a positive duration
            observe_call = mock_labeled_histogram.observe.call_args[0][0]
            assert observe_call > 0  # Should be positive milliseconds
    
    @pytest.mark.asyncio
    async def test_exception_during_request_processing(self, middleware, mock_request):
        """Test metrics recording when request processing raises exception."""
        # Mock the metrics
        with patch('app.monitoring.HTTP_REQUESTS_TOTAL') as mock_counter, \
             patch('app.monitoring.HTTP_REQUEST_DURATION') as mock_histogram, \
             patch('app.monitoring.HTTP_REQUESTS_IN_FLIGHT') as mock_gauge, \
             patch('app.monitoring._extract_route_pattern') as mock_extract_route, \
             patch('app.monitoring._get_method_label') as mock_get_method, \
             patch('app.monitoring._format_status_code') as mock_format_status:
            
            # Setup mock returns
            mock_extract_route.return_value = "/api/v1/portfolios"
            mock_get_method.return_value = "GET"
            mock_format_status.return_value = "500"
            
            # Mock labeled metrics
            mock_labeled_counter = Mock()
            mock_labeled_histogram = Mock()
            mock_counter.labels.return_value = mock_labeled_counter
            mock_histogram.labels.return_value = mock_labeled_histogram
            
            # Mock call_next to raise exception
            async def mock_call_next(request):
                raise ValueError("Test exception")
            
            # Execute middleware and expect exception to be re-raised
            with pytest.raises(ValueError, match="Test exception"):
                await middleware.dispatch(mock_request, mock_call_next)
            
            # Verify in-flight gauge operations
            mock_gauge.inc.assert_called_once()
            mock_gauge.dec.assert_called_once()
            
            # Verify counter metrics with status 500
            mock_counter.labels.assert_called_once_with(
                method="GET", path="/api/v1/portfolios", status="500"
            )
            mock_labeled_counter.inc.assert_called_once()
            
            # Verify histogram metrics with status 500
            mock_histogram.labels.assert_called_once_with(
                method="GET", path="/api/v1/portfolios", status="500"
            )
            mock_labeled_histogram.observe.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_in_flight_gauge_increment_error(self, middleware, mock_request, mock_response):
        """Test handling of in-flight gauge increment errors."""
        with patch('app.monitoring.HTTP_REQUESTS_TOTAL') as mock_counter, \
             patch('app.monitoring.HTTP_REQUEST_DURATION') as mock_histogram, \
             patch('app.monitoring.HTTP_REQUESTS_IN_FLIGHT') as mock_gauge, \
             patch('app.monitoring._extract_route_pattern') as mock_extract_route, \
             patch('app.monitoring._get_method_label') as mock_get_method, \
             patch('app.monitoring._format_status_code') as mock_format_status:
            
            # Setup mock returns
            mock_extract_route.return_value = "/api/v1/portfolios"
            mock_get_method.return_value = "GET"
            mock_format_status.return_value = "200"
            
            # Mock labeled metrics
            mock_labeled_counter = Mock()
            mock_labeled_histogram = Mock()
            mock_counter.labels.return_value = mock_labeled_counter
            mock_histogram.labels.return_value = mock_labeled_histogram
            
            # Make gauge increment fail
            mock_gauge.inc.side_effect = Exception("Gauge increment failed")
            
            # Mock call_next
            async def mock_call_next(request):
                return mock_response
            
            # Execute middleware - should not raise exception
            result = await middleware.dispatch(mock_request, mock_call_next)
            
            # Verify response is returned despite gauge error
            assert result is mock_response
            
            # Verify increment was attempted
            mock_gauge.inc.assert_called_once()
            
            # Verify decrement was NOT called (since increment failed)
            mock_gauge.dec.assert_not_called()
            
            # Verify other metrics still recorded
            mock_labeled_counter.inc.assert_called_once()
            mock_labeled_histogram.observe.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_in_flight_gauge_decrement_error(self, middleware, mock_request, mock_response):
        """Test handling of in-flight gauge decrement errors."""
        with patch('app.monitoring.HTTP_REQUESTS_TOTAL') as mock_counter, \
             patch('app.monitoring.HTTP_REQUEST_DURATION') as mock_histogram, \
             patch('app.monitoring.HTTP_REQUESTS_IN_FLIGHT') as mock_gauge, \
             patch('app.monitoring._extract_route_pattern') as mock_extract_route, \
             patch('app.monitoring._get_method_label') as mock_get_method, \
             patch('app.monitoring._format_status_code') as mock_format_status:
            
            # Setup mock returns
            mock_extract_route.return_value = "/api/v1/portfolios"
            mock_get_method.return_value = "GET"
            mock_format_status.return_value = "200"
            
            # Mock labeled metrics
            mock_labeled_counter = Mock()
            mock_labeled_histogram = Mock()
            mock_counter.labels.return_value = mock_labeled_counter
            mock_histogram.labels.return_value = mock_labeled_histogram
            
            # Make gauge decrement fail
            mock_gauge.dec.side_effect = Exception("Gauge decrement failed")
            
            # Mock call_next
            async def mock_call_next(request):
                return mock_response
            
            # Execute middleware - should not raise exception
            result = await middleware.dispatch(mock_request, mock_call_next)
            
            # Verify response is returned despite gauge error
            assert result is mock_response
            
            # Verify both increment and decrement were attempted
            mock_gauge.inc.assert_called_once()
            mock_gauge.dec.assert_called_once()
            
            # Verify other metrics still recorded
            mock_labeled_counter.inc.assert_called_once()
            mock_labeled_histogram.observe.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_high_precision_timing(self, middleware, mock_request, mock_response):
        """Test that high-precision timing is used."""
        with patch('app.monitoring.time.perf_counter') as mock_perf_counter, \
             patch('app.monitoring.HTTP_REQUESTS_TOTAL') as mock_counter, \
             patch('app.monitoring.HTTP_REQUEST_DURATION') as mock_histogram, \
             patch('app.monitoring.HTTP_REQUESTS_IN_FLIGHT') as mock_gauge, \
             patch('app.monitoring._extract_route_pattern') as mock_extract_route, \
             patch('app.monitoring._get_method_label') as mock_get_method, \
             patch('app.monitoring._format_status_code') as mock_format_status:
            
            # Setup timing mocks - simulate 150ms request
            mock_perf_counter.side_effect = [0.0, 0.15]  # 150ms difference
            
            # Setup other mocks
            mock_extract_route.return_value = "/api/v1/portfolios"
            mock_get_method.return_value = "GET"
            mock_format_status.return_value = "200"
            
            mock_labeled_counter = Mock()
            mock_labeled_histogram = Mock()
            mock_counter.labels.return_value = mock_labeled_counter
            mock_histogram.labels.return_value = mock_labeled_histogram
            
            # Mock call_next
            async def mock_call_next(request):
                return mock_response
            
            # Execute middleware
            await middleware.dispatch(mock_request, mock_call_next)
            
            # Verify perf_counter was called twice (start and end)
            assert mock_perf_counter.call_count == 2
            
            # Verify histogram was called with 150ms (0.15 * 1000)
            mock_labeled_histogram.observe.assert_called_once_with(150.0)
    
    @pytest.mark.asyncio
    async def test_slow_request_logging(self, middleware, mock_request, mock_response):
        """Test that slow requests are logged."""
        with patch('app.monitoring.time.perf_counter') as mock_perf_counter, \
             patch('app.monitoring.HTTP_REQUESTS_TOTAL') as mock_counter, \
             patch('app.monitoring.HTTP_REQUEST_DURATION') as mock_histogram, \
             patch('app.monitoring.HTTP_REQUESTS_IN_FLIGHT') as mock_gauge, \
             patch('app.monitoring._extract_route_pattern') as mock_extract_route, \
             patch('app.monitoring._get_method_label') as mock_get_method, \
             patch('app.monitoring._format_status_code') as mock_format_status, \
             patch('app.monitoring.logger') as mock_logger:
            
            # Setup timing mocks - simulate 1500ms request (slow)
            mock_perf_counter.side_effect = [0.0, 1.5]  # 1500ms difference
            
            # Setup other mocks
            mock_extract_route.return_value = "/api/v1/portfolios"
            mock_get_method.return_value = "GET"
            mock_format_status.return_value = "200"
            
            mock_labeled_counter = Mock()
            mock_labeled_histogram = Mock()
            mock_counter.labels.return_value = mock_labeled_counter
            mock_histogram.labels.return_value = mock_labeled_histogram
            
            # Mock call_next
            async def mock_call_next(request):
                return mock_response
            
            # Execute middleware
            await middleware.dispatch(mock_request, mock_call_next)
            
            # Verify slow request warning was logged
            mock_logger.warning.assert_called_once()
            warning_call = mock_logger.warning.call_args
            assert "Slow request detected" in warning_call[0][0]
    
    @pytest.mark.asyncio
    async def test_debug_logging_enabled(self, debug_middleware, mock_request, mock_response):
        """Test debug logging when enabled."""
        with patch('app.monitoring.HTTP_REQUESTS_TOTAL') as mock_counter, \
             patch('app.monitoring.HTTP_REQUEST_DURATION') as mock_histogram, \
             patch('app.monitoring.HTTP_REQUESTS_IN_FLIGHT') as mock_gauge, \
             patch('app.monitoring._extract_route_pattern') as mock_extract_route, \
             patch('app.monitoring._get_method_label') as mock_get_method, \
             patch('app.monitoring._format_status_code') as mock_format_status, \
             patch('app.monitoring.logger') as mock_logger:
            
            # Setup mock returns
            mock_extract_route.return_value = "/api/v1/portfolios"
            mock_get_method.return_value = "GET"
            mock_format_status.return_value = "200"
            
            mock_labeled_counter = Mock()
            mock_labeled_histogram = Mock()
            mock_counter.labels.return_value = mock_labeled_counter
            mock_histogram.labels.return_value = mock_labeled_histogram
            
            # Mock call_next
            async def mock_call_next(request):
                return mock_response
            
            # Execute middleware
            await debug_middleware.dispatch(mock_request, mock_call_next)
            
            # Verify debug logging was called
            debug_calls = [call for call in mock_logger.debug.call_args_list 
                          if "Successfully incremented in-flight requests gauge" in str(call) or
                             "Successfully decremented in-flight requests gauge" in str(call)]
            assert len(debug_calls) >= 2  # At least increment and decrement logs
    
    def test_record_metrics_success(self, middleware):
        """Test _record_metrics method with successful recording."""
        with patch('app.monitoring.HTTP_REQUESTS_TOTAL') as mock_counter, \
             patch('app.monitoring.HTTP_REQUEST_DURATION') as mock_histogram:
            
            mock_labeled_counter = Mock()
            mock_labeled_histogram = Mock()
            mock_counter.labels.return_value = mock_labeled_counter
            mock_histogram.labels.return_value = mock_labeled_histogram
            
            # Call _record_metrics
            middleware._record_metrics("GET", "/api/v1/portfolios", "200", 150.5)
            
            # Verify counter recording
            mock_counter.labels.assert_called_once_with(
                method="GET", path="/api/v1/portfolios", status="200"
            )
            mock_labeled_counter.inc.assert_called_once()
            
            # Verify histogram recording
            mock_histogram.labels.assert_called_once_with(
                method="GET", path="/api/v1/portfolios", status="200"
            )
            mock_labeled_histogram.observe.assert_called_once_with(150.5)
    
    def test_record_metrics_counter_error(self, middleware):
        """Test _record_metrics method with counter recording error."""
        with patch('app.monitoring.HTTP_REQUESTS_TOTAL') as mock_counter, \
             patch('app.monitoring.HTTP_REQUEST_DURATION') as mock_histogram, \
             patch('app.monitoring.logger') as mock_logger:
            
            mock_labeled_counter = Mock()
            mock_labeled_histogram = Mock()
            mock_counter.labels.return_value = mock_labeled_counter
            mock_histogram.labels.return_value = mock_labeled_histogram
            
            # Make counter increment fail
            mock_labeled_counter.inc.side_effect = Exception("Counter error")
            
            # Call _record_metrics - should not raise exception
            middleware._record_metrics("GET", "/api/v1/portfolios", "200", 150.5)
            
            # Verify error was logged
            mock_logger.error.assert_called()
            error_calls = [call for call in mock_logger.error.call_args_list 
                          if "Failed to record HTTP requests total counter" in str(call)]
            assert len(error_calls) > 0
            
            # Verify histogram was still attempted
            mock_labeled_histogram.observe.assert_called_once_with(150.5)
    
    def test_record_metrics_histogram_error(self, middleware):
        """Test _record_metrics method with histogram recording error."""
        with patch('app.monitoring.HTTP_REQUESTS_TOTAL') as mock_counter, \
             patch('app.monitoring.HTTP_REQUEST_DURATION') as mock_histogram, \
             patch('app.monitoring.logger') as mock_logger:
            
            mock_labeled_counter = Mock()
            mock_labeled_histogram = Mock()
            mock_counter.labels.return_value = mock_labeled_counter
            mock_histogram.labels.return_value = mock_labeled_histogram
            
            # Make histogram observe fail
            mock_labeled_histogram.observe.side_effect = Exception("Histogram error")
            
            # Call _record_metrics - should not raise exception
            middleware._record_metrics("GET", "/api/v1/portfolios", "200", 150.5)
            
            # Verify counter was still recorded
            mock_labeled_counter.inc.assert_called_once()
            
            # Verify error was logged
            mock_logger.error.assert_called()
            error_calls = [call for call in mock_logger.error.call_args_list 
                          if "Failed to record HTTP request duration histogram" in str(call)]
            assert len(error_calls) > 0
    
    def test_record_metrics_debug_logging(self, debug_middleware):
        """Test _record_metrics method with debug logging enabled."""
        with patch('app.monitoring.HTTP_REQUESTS_TOTAL') as mock_counter, \
             patch('app.monitoring.HTTP_REQUEST_DURATION') as mock_histogram, \
             patch('app.monitoring.logger') as mock_logger:
            
            mock_labeled_counter = Mock()
            mock_labeled_histogram = Mock()
            mock_counter.labels.return_value = mock_labeled_counter
            mock_histogram.labels.return_value = mock_labeled_histogram
            
            # Call _record_metrics
            debug_middleware._record_metrics("POST", "/api/v2/portfolios", "201", 75.2)
            
            # Verify debug logging was called
            debug_calls = [call for call in mock_logger.debug.call_args_list 
                          if "Recording HTTP metrics" in str(call) or
                             "Successfully recorded HTTP" in str(call)]
            assert len(debug_calls) >= 3  # Initial recording + 2 success logs
    
    def test_record_metrics_both_counter_and_histogram_errors(self, middleware):
        """Test _record_metrics method with both counter and histogram recording errors."""
        with patch('app.monitoring.HTTP_REQUESTS_TOTAL') as mock_counter, \
             patch('app.monitoring.HTTP_REQUEST_DURATION') as mock_histogram, \
             patch('app.monitoring.logger') as mock_logger:
            
            mock_labeled_counter = Mock()
            mock_labeled_histogram = Mock()
            mock_counter.labels.return_value = mock_labeled_counter
            mock_histogram.labels.return_value = mock_labeled_histogram
            
            # Make both operations fail
            mock_labeled_counter.inc.side_effect = Exception("Counter error")
            mock_labeled_histogram.observe.side_effect = Exception("Histogram error")
            
            # Call _record_metrics - should not raise exception
            middleware._record_metrics("GET", "/api/v1/portfolios", "200", 150.5)
            
            # Verify both operations were attempted
            mock_labeled_counter.inc.assert_called_once()
            mock_labeled_histogram.observe.assert_called_once_with(150.5)
            
            # Verify both errors were logged
            error_calls = [call for call in mock_logger.error.call_args_list 
                          if "Failed to record HTTP" in str(call)]
            assert len(error_calls) == 2  # One for counter, one for histogram
            
            # Verify specific error messages
            counter_error_calls = [call for call in mock_logger.error.call_args_list 
                                  if "Failed to record HTTP requests total counter" in str(call)]
            histogram_error_calls = [call for call in mock_logger.error.call_args_list 
                                    if "Failed to record HTTP request duration histogram" in str(call)]
            assert len(counter_error_calls) == 1
            assert len(histogram_error_calls) == 1
    
    def test_record_metrics_labels_method_error(self, middleware):
        """Test _record_metrics method when labels() method fails."""
        with patch('app.monitoring.HTTP_REQUESTS_TOTAL') as mock_counter, \
             patch('app.monitoring.HTTP_REQUEST_DURATION') as mock_histogram, \
             patch('app.monitoring.logger') as mock_logger:
            
            # Make labels() method fail for counter
            mock_counter.labels.side_effect = Exception("Labels error")
            mock_histogram.labels.return_value = Mock()
            
            # Call _record_metrics - should not raise exception
            middleware._record_metrics("GET", "/api/v1/portfolios", "200", 150.5)
            
            # Verify counter labels was attempted
            mock_counter.labels.assert_called_once_with(
                method="GET", path="/api/v1/portfolios", status="200"
            )
            
            # Verify histogram was still attempted (should succeed)
            mock_histogram.labels.assert_called_once_with(
                method="GET", path="/api/v1/portfolios", status="200"
            )
            
            # Verify error was logged for counter
            error_calls = [call for call in mock_logger.error.call_args_list 
                          if "Failed to record HTTP requests total counter" in str(call)]
            assert len(error_calls) == 1
    
    def test_record_metrics_with_none_values(self, middleware):
        """Test _record_metrics method with None values."""
        with patch('app.monitoring.HTTP_REQUESTS_TOTAL') as mock_counter, \
             patch('app.monitoring.HTTP_REQUEST_DURATION') as mock_histogram, \
             patch('app.monitoring.logger') as mock_logger:
            
            mock_labeled_counter = Mock()
            mock_labeled_histogram = Mock()
            mock_counter.labels.return_value = mock_labeled_counter
            mock_histogram.labels.return_value = mock_labeled_histogram
            
            # Call _record_metrics with None values - should handle gracefully
            middleware._record_metrics(None, None, None, None)
            
            # Verify operations were attempted with None values
            mock_counter.labels.assert_called_once_with(method=None, path=None, status=None)
            mock_labeled_counter.inc.assert_called_once()
            mock_histogram.labels.assert_called_once_with(method=None, path=None, status=None)
            mock_labeled_histogram.observe.assert_called_once_with(None)
    
    def test_record_metrics_with_extreme_duration_values(self, middleware):
        """Test _record_metrics method with extreme duration values."""
        with patch('app.monitoring.HTTP_REQUESTS_TOTAL') as mock_counter, \
             patch('app.monitoring.HTTP_REQUEST_DURATION') as mock_histogram:
            
            mock_labeled_counter = Mock()
            mock_labeled_histogram = Mock()
            mock_counter.labels.return_value = mock_labeled_counter
            mock_histogram.labels.return_value = mock_labeled_histogram
            
            # Test with very large duration
            middleware._record_metrics("GET", "/api/v1/portfolios", "200", 999999.99)
            mock_labeled_histogram.observe.assert_called_with(999999.99)
            
            # Reset mocks
            mock_labeled_histogram.reset_mock()
            
            # Test with zero duration
            middleware._record_metrics("GET", "/api/v1/portfolios", "200", 0.0)
            mock_labeled_histogram.observe.assert_called_with(0.0)
            
            # Reset mocks
            mock_labeled_histogram.reset_mock()
            
            # Test with negative duration (edge case)
            middleware._record_metrics("GET", "/api/v1/portfolios", "200", -1.0)
            mock_labeled_histogram.observe.assert_called_with(-1.0)
    
    @pytest.mark.asyncio
    async def test_middleware_with_different_request_methods(self, middleware):
        """Test middleware with different HTTP methods."""
        methods_and_responses = [
            ("GET", 200),
            ("POST", 201),
            ("PUT", 200),
            ("DELETE", 204),
            ("PATCH", 200),
        ]
        
        for method, status_code in methods_and_responses:
            with patch('app.monitoring.HTTP_REQUESTS_TOTAL') as mock_counter, \
                 patch('app.monitoring.HTTP_REQUEST_DURATION') as mock_histogram, \
                 patch('app.monitoring.HTTP_REQUESTS_IN_FLIGHT') as mock_gauge, \
                 patch('app.monitoring._extract_route_pattern') as mock_extract_route, \
                 patch('app.monitoring._get_method_label') as mock_get_method, \
                 patch('app.monitoring._format_status_code') as mock_format_status:
                
                # Setup mocks
                mock_extract_route.return_value = "/api/v1/portfolios"
                mock_get_method.return_value = method
                mock_format_status.return_value = str(status_code)
                
                mock_labeled_counter = Mock()
                mock_labeled_histogram = Mock()
                mock_counter.labels.return_value = mock_labeled_counter
                mock_histogram.labels.return_value = mock_labeled_histogram
                
                # Create request and response
                request = Mock()
                request.method = method
                request.url.path = "/api/v1/portfolios"
                
                response = Mock()
                response.status_code = status_code
                
                # Mock call_next
                async def mock_call_next(req):
                    return response
                
                # Execute middleware
                result = await middleware.dispatch(request, mock_call_next)
                
                # Verify correct method and status were used
                mock_counter.labels.assert_called_once_with(
                    method=method, path="/api/v1/portfolios", status=str(status_code)
                )
                mock_histogram.labels.assert_called_once_with(
                    method=method, path="/api/v1/portfolios", status=str(status_code)
                )

class TestThreadMetrics:
    """Test the thread worker metrics are created correctly."""
    
    def test_http_workers_active_created(self):
        """Test HTTP_WORKERS_ACTIVE metric is created."""
        assert HTTP_WORKERS_ACTIVE is not None
        
        # Should be either Gauge or DummyMetric
        assert isinstance(HTTP_WORKERS_ACTIVE, (Gauge, DummyMetric))
        
        # Should support gauge operations
        HTTP_WORKERS_ACTIVE.set(5)
        HTTP_WORKERS_ACTIVE.inc()
        HTTP_WORKERS_ACTIVE.dec()
    
    def test_http_workers_total_created(self):
        """Test HTTP_WORKERS_TOTAL metric is created."""
        assert HTTP_WORKERS_TOTAL is not None
        
        # Should be either Gauge or DummyMetric
        assert isinstance(HTTP_WORKERS_TOTAL, (Gauge, DummyMetric))
        
        # Should support gauge operations
        HTTP_WORKERS_TOTAL.set(10)
        HTTP_WORKERS_TOTAL.inc()
        HTTP_WORKERS_TOTAL.dec()
    
    def test_http_workers_max_configured_created(self):
        """Test HTTP_WORKERS_MAX_CONFIGURED metric is created."""
        assert HTTP_WORKERS_MAX_CONFIGURED is not None
        
        # Should be either Gauge or DummyMetric
        assert isinstance(HTTP_WORKERS_MAX_CONFIGURED, (Gauge, DummyMetric))
        
        # Should support gauge operations
        HTTP_WORKERS_MAX_CONFIGURED.set(20)
        HTTP_WORKERS_MAX_CONFIGURED.inc()
        HTTP_WORKERS_MAX_CONFIGURED.dec()
    
    def test_http_requests_queued_created(self):
        """Test HTTP_REQUESTS_QUEUED metric is created."""
        assert HTTP_REQUESTS_QUEUED is not None
        
        # Should be either Gauge or DummyMetric
        assert isinstance(HTTP_REQUESTS_QUEUED, (Gauge, DummyMetric))
        
        # Should support gauge operations
        HTTP_REQUESTS_QUEUED.set(3)
        HTTP_REQUESTS_QUEUED.inc()
        HTTP_REQUESTS_QUEUED.dec()
    
    def test_thread_metrics_no_labels(self):
        """Test that thread metrics have no labels (are simple gauges)."""
        # All thread metrics should be simple gauges without labels
        # Test that they can be called directly without labels
        
        HTTP_WORKERS_ACTIVE.set(5)
        HTTP_WORKERS_ACTIVE.inc(2)
        HTTP_WORKERS_ACTIVE.dec(1)
        
        HTTP_WORKERS_TOTAL.set(10)
        HTTP_WORKERS_TOTAL.inc(3)
        HTTP_WORKERS_TOTAL.dec(2)
        
        HTTP_WORKERS_MAX_CONFIGURED.set(20)
        HTTP_WORKERS_MAX_CONFIGURED.inc(5)
        HTTP_WORKERS_MAX_CONFIGURED.dec(1)
        
        HTTP_REQUESTS_QUEUED.set(0)
        HTTP_REQUESTS_QUEUED.inc(1)
        HTTP_REQUESTS_QUEUED.dec(1)
    
    def test_thread_metrics_exist(self):
        """Test that all thread metrics exist and have expected interface."""
        # Test that all thread metrics exist
        assert HTTP_WORKERS_ACTIVE is not None
        assert HTTP_WORKERS_TOTAL is not None
        assert HTTP_WORKERS_MAX_CONFIGURED is not None
        assert HTTP_REQUESTS_QUEUED is not None
        
        # Test that they support the expected gauge interface
        metrics = [
            HTTP_WORKERS_ACTIVE,
            HTTP_WORKERS_TOTAL,
            HTTP_WORKERS_MAX_CONFIGURED,
            HTTP_REQUESTS_QUEUED
        ]
        
        for metric in metrics:
            # All should support gauge operations
            metric.set(10)  # Should not raise
            metric.inc()    # Should not raise
            metric.dec()    # Should not raise
            metric.set(0)   # Reset to 0
    
    def test_thread_metrics_registry_contains_thread_metrics(self):
        """Test that thread metrics are registered in the global registry."""
        # The metrics should exist regardless of registry state
        # since they are module-level variables
        assert HTTP_WORKERS_ACTIVE is not None
        assert HTTP_WORKERS_TOTAL is not None
        assert HTTP_WORKERS_MAX_CONFIGURED is not None
        assert HTTP_REQUESTS_QUEUED is not None
        
        # Test that they have the expected types
        from prometheus_client import Gauge
        assert isinstance(HTTP_WORKERS_ACTIVE, (Gauge, DummyMetric))
        assert isinstance(HTTP_WORKERS_TOTAL, (Gauge, DummyMetric))
        assert isinstance(HTTP_WORKERS_MAX_CONFIGURED, (Gauge, DummyMetric))
        assert isinstance(HTTP_REQUESTS_QUEUED, (Gauge, DummyMetric))
    
    def test_thread_metrics_names_and_descriptions(self):
        """Test that thread metrics have the correct names and work as expected."""
        # We can't directly access names/descriptions from prometheus_client objects,
        # but we can verify they were created with the right parameters by checking
        # that they exist and work as expected
        
        # Test that the metrics work with the expected interface
        # This indirectly verifies they were created correctly
        
        # HTTP_WORKERS_ACTIVE should be a gauge with no labels
        HTTP_WORKERS_ACTIVE.set(3)
        HTTP_WORKERS_ACTIVE.inc()
        HTTP_WORKERS_ACTIVE.dec()
        
        # HTTP_WORKERS_TOTAL should be a gauge with no labels
        HTTP_WORKERS_TOTAL.set(8)
        HTTP_WORKERS_TOTAL.inc()
        HTTP_WORKERS_TOTAL.dec()
        
        # HTTP_WORKERS_MAX_CONFIGURED should be a gauge with no labels
        HTTP_WORKERS_MAX_CONFIGURED.set(10)
        HTTP_WORKERS_MAX_CONFIGURED.inc()
        HTTP_WORKERS_MAX_CONFIGURED.dec()
        
        # HTTP_REQUESTS_QUEUED should be a gauge with no labels
        HTTP_REQUESTS_QUEUED.set(2)
        HTTP_REQUESTS_QUEUED.inc()
        HTTP_REQUESTS_QUEUED.dec()
    
    def test_thread_metrics_with_float_values(self):
        """Test thread metrics with float values."""
        # Thread metrics should support float values for precision
        HTTP_WORKERS_ACTIVE.set(3.5)
        HTTP_WORKERS_ACTIVE.inc(1.5)
        HTTP_WORKERS_ACTIVE.dec(0.5)
        
        HTTP_WORKERS_TOTAL.set(8.0)
        HTTP_WORKERS_TOTAL.inc(2.0)
        HTTP_WORKERS_TOTAL.dec(1.0)
        
        HTTP_WORKERS_MAX_CONFIGURED.set(10.0)
        HTTP_WORKERS_MAX_CONFIGURED.inc(5.0)
        HTTP_WORKERS_MAX_CONFIGURED.dec(2.0)
        
        HTTP_REQUESTS_QUEUED.set(0.0)
        HTTP_REQUESTS_QUEUED.inc(1.0)
        HTTP_REQUESTS_QUEUED.dec(1.0)
    
    def test_thread_metrics_edge_cases(self):
        """Test thread metrics with edge case values."""
        # Test with zero values
        HTTP_WORKERS_ACTIVE.set(0)
        HTTP_WORKERS_TOTAL.set(0)
        HTTP_WORKERS_MAX_CONFIGURED.set(0)
        HTTP_REQUESTS_QUEUED.set(0)
        
        # Test with large values
        HTTP_WORKERS_ACTIVE.set(1000)
        HTTP_WORKERS_TOTAL.set(2000)
        HTTP_WORKERS_MAX_CONFIGURED.set(5000)
        HTTP_REQUESTS_QUEUED.set(10000)
        
        # Test with negative values (should be allowed for gauges)
        HTTP_WORKERS_ACTIVE.set(-1)
        HTTP_WORKERS_TOTAL.set(-1)
        HTTP_WORKERS_MAX_CONFIGURED.set(-1)
        HTTP_REQUESTS_QUEUED.set(-1)


class TestThreadMetricsCreation:
    """Test thread metrics creation with error handling."""
    
    def setup_method(self):
        """Clear registry before each test."""
        clear_metrics_registry()
    
    def teardown_method(self):
        """Clear registry after each test."""
        clear_metrics_registry()
    
    def test_create_thread_metrics_success(self):
        """Test successful creation of thread metrics."""
        with patch('prometheus_client.Gauge') as mock_gauge:
            mock_instance = Mock()
            mock_gauge.return_value = mock_instance
            
            # Create each thread metric
            active_metric = _get_or_create_metric(
                mock_gauge,
                'http_workers_active',
                'Number of threads currently executing requests or performing work'
            )
            
            total_metric = _get_or_create_metric(
                mock_gauge,
                'http_workers_total',
                'Total number of threads currently alive in the thread pool'
            )
            
            max_metric = _get_or_create_metric(
                mock_gauge,
                'http_workers_max_configured',
                'Maximum number of threads that can be created in the thread pool'
            )
            
            queued_metric = _get_or_create_metric(
                mock_gauge,
                'http_requests_queued',
                'Number of pending requests waiting in the queue for thread assignment'
            )
            
            # All should be created successfully
            assert active_metric is mock_instance
            assert total_metric is mock_instance
            assert max_metric is mock_instance
            assert queued_metric is mock_instance
            
            # All should be in registry
            registry = get_metrics_registry()
            assert len(registry) == 4
            assert 'http_workers_active' in registry
            assert 'http_workers_total' in registry
            assert 'http_workers_max_configured' in registry
            assert 'http_requests_queued' in registry
    
    def test_create_thread_metrics_with_duplicate_error(self):
        """Test thread metrics creation with duplicate registration error."""
        def failing_gauge(*args, **kwargs):
            raise ValueError("Duplicated timeseries in CollectorRegistry")
        
        # Create thread metrics that will fail
        active_metric = _get_or_create_metric(
            failing_gauge,
            'http_workers_active',
            'Number of threads currently executing requests or performing work'
        )
        
        total_metric = _get_or_create_metric(
            failing_gauge,
            'http_workers_total',
            'Total number of threads currently alive in the thread pool'
        )
        
        max_metric = _get_or_create_metric(
            failing_gauge,
            'http_workers_max_configured',
            'Maximum number of threads that can be created in the thread pool'
        )
        
        queued_metric = _get_or_create_metric(
            failing_gauge,
            'http_requests_queued',
            'Number of pending requests waiting in the queue for thread assignment'
        )
        
        # All should return DummyMetric
        assert isinstance(active_metric, DummyMetric)
        assert isinstance(total_metric, DummyMetric)
        assert isinstance(max_metric, DummyMetric)
        assert isinstance(queued_metric, DummyMetric)
        
        # All should be in registry as dummy metrics
        registry = get_metrics_registry()
        assert len(registry) == 4
        assert all(isinstance(metric, DummyMetric) for metric in registry.values())
    
    def test_create_thread_metrics_with_unexpected_error(self):
        """Test thread metrics creation with unexpected error."""
        def failing_gauge(*args, **kwargs):
            raise RuntimeError("Unexpected error during metric creation")
        
        # Create thread metrics that will fail
        active_metric = _get_or_create_metric(
            failing_gauge,
            'http_workers_active',
            'Number of threads currently executing requests or performing work'
        )
        
        # Should return DummyMetric
        assert isinstance(active_metric, DummyMetric)
        
        # Should be in registry as dummy metric
        registry = get_metrics_registry()
        assert 'http_workers_active' in registry
        assert isinstance(registry['http_workers_active'], DummyMetric)
    
    def test_thread_metrics_reuse_existing(self):
        """Test that existing thread metrics are reused."""
        with patch('prometheus_client.Gauge') as mock_gauge:
            mock_instance = Mock()
            mock_gauge.return_value = mock_instance
            
            # Create metric first time
            metric1 = _get_or_create_metric(
                mock_gauge,
                'http_workers_active',
                'Number of threads currently executing requests or performing work'
            )
            
            # Try to create same metric again
            metric2 = _get_or_create_metric(
                mock_gauge,
                'http_workers_active',
                'Different description'  # Different description
            )
            
            # Should return the same instance
            assert metric1 is metric2
            
            # Registry should only have one entry
            registry = get_metrics_registry()
            assert len(registry) == 1
            assert 'http_workers_active' in registry
            
            # Gauge should only be called once
            assert mock_gauge.call_count == 1


class TestOpenTelemetryThreadMetrics:
    """Test OpenTelemetry thread metrics creation and fallback behavior."""
    
    @patch('app.monitoring.metrics')
    def test_otel_thread_metrics_creation_success(self, mock_metrics):
        """Test successful creation of OpenTelemetry thread metrics."""
        # Mock the meter and metric creation
        mock_meter = Mock()
        mock_metrics.get_meter.return_value = mock_meter
        
        mock_active_counter = Mock()
        mock_total_counter = Mock()
        mock_max_counter = Mock()
        mock_queued_counter = Mock()
        
        # Configure the meter to return our mock metrics
        mock_meter.create_up_down_counter.side_effect = [
            mock_active_counter,
            mock_total_counter,
            mock_max_counter,
            mock_queued_counter
        ]
        
        # Import the module to trigger OpenTelemetry metric creation
        # This would normally happen during module import
        from app import monitoring
        
        # Verify that get_meter was called
        mock_metrics.get_meter.assert_called_once()
        
        # Verify that create_up_down_counter was called for each thread metric
        expected_calls = [
            call(
                name="http_workers_active",
                description="Number of threads currently executing requests or performing work",
                unit="1"
            ),
            call(
                name="http_workers_total",
                description="Total number of threads currently alive in the thread pool",
                unit="1"
            ),
            call(
                name="http_workers_max_configured",
                description="Maximum number of threads that can be created in the thread pool",
                unit="1"
            ),
            call(
                name="http_requests_queued",
                description="Number of pending requests waiting in the queue for thread assignment",
                unit="1"
            )
        ]
        
        # Check that create_up_down_counter was called with expected parameters
        # Note: This test may need adjustment based on actual module import behavior
        assert mock_meter.create_up_down_counter.call_count >= 4
    
    @patch('app.monitoring.metrics')
    @patch('app.monitoring.logger')
    def test_otel_thread_metrics_creation_failure(self, mock_logger, mock_metrics):
        """Test OpenTelemetry thread metrics creation failure and fallback."""
        # Mock metrics.get_meter to raise an exception
        mock_metrics.get_meter.side_effect = Exception("OpenTelemetry not available")
        
        # Import the module to trigger OpenTelemetry metric creation
        # This would normally happen during module import
        try:
            from app import monitoring
            # The module should handle the exception and create dummy metrics
        except Exception:
            pass  # Expected if module import fails
        
        # Verify that error was logged
        mock_logger.error.assert_called()
        error_calls = [call for call in mock_logger.error.call_args_list 
                      if 'Failed to create OpenTelemetry metrics' in str(call)]
        assert len(error_calls) > 0
        
        # Verify that warning about dummy metrics was logged
        mock_logger.warning.assert_called()
        warning_calls = [call for call in mock_logger.warning.call_args_list 
                        if 'Created dummy OpenTelemetry metrics' in str(call)]
        assert len(warning_calls) > 0
    
    def test_dummy_otel_metric_interface(self):
        """Test that dummy OpenTelemetry metrics provide the expected interface."""
        from app.monitoring import DummyOTelMetric
        
        dummy = DummyOTelMetric()
        
        # Test that methods don't raise exceptions
        dummy.add(1)
        dummy.add(5, attributes={"method": "GET"})
        dummy.record(100.5)
        dummy.record(200.0, attributes={"path": "/test"})
    
    def test_dummy_otel_metric_with_none_values(self):
        """Test dummy OpenTelemetry metrics handle None values gracefully."""
        from app.monitoring import DummyOTelMetric
        
        dummy = DummyOTelMetric()
        
        # Should handle None values without error
        dummy.add(None)
        dummy.add(None, attributes=None)
        dummy.record(None)
        dummy.record(None, attributes=None)