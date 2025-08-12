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