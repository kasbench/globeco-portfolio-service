"""
Unit tests for ThreadMetricsCollector class.

Tests the collector behavior, throttling logic, and integration with
both Prometheus and OpenTelemetry metrics systems.
"""

import pytest
import time
from unittest.mock import Mock, patch, MagicMock
from app.monitoring import (
    ThreadMetricsCollector,
    setup_thread_metrics,
    get_thread_metrics_collector,
    is_thread_metrics_enabled,
    _thread_metrics_collector
)


class TestThreadMetricsCollector:
    """Test cases for ThreadMetricsCollector class."""
    
    def setup_method(self):
        """Setup for each test method."""
        # Reset global collector state
        import app.monitoring
        app.monitoring._thread_metrics_collector = None
    
    def test_collector_initialization(self):
        """Test ThreadMetricsCollector initialization."""
        collector = ThreadMetricsCollector(update_interval=2.0)
        
        assert collector.update_interval == 2.0
        assert collector.last_update == 0.0
        assert collector._otel_values == {
            'workers_active': 0,
            'workers_total': 0,
            'workers_max_configured': 0,
            'requests_queued': 0
        }
    
    def test_collector_default_initialization(self):
        """Test ThreadMetricsCollector with default parameters."""
        collector = ThreadMetricsCollector()
        
        assert collector.update_interval == 1.0
        assert collector.last_update == 0.0
        assert len(collector._otel_values) == 4
    
    def test_update_interval_getter_setter(self):
        """Test update interval getter and setter methods."""
        collector = ThreadMetricsCollector(update_interval=1.0)
        
        # Test getter
        assert collector.get_update_interval() == 1.0
        
        # Test setter
        collector.set_update_interval(2.5)
        assert collector.get_update_interval() == 2.5
        assert collector.update_interval == 2.5
    
    def test_update_interval_validation(self):
        """Test update interval validation."""
        collector = ThreadMetricsCollector()
        
        # Test invalid intervals
        with pytest.raises(ValueError, match="Update interval must be positive"):
            collector.set_update_interval(0)
        
        with pytest.raises(ValueError, match="Update interval must be positive"):
            collector.set_update_interval(-1.0)
    
    def test_last_update_time_getter(self):
        """Test last update time getter."""
        collector = ThreadMetricsCollector()
        
        # Initially should be 0.0
        assert collector.get_last_update_time() == 0.0
        
        # After setting, should return the set value
        collector.last_update = 123.456
        assert collector.get_last_update_time() == 123.456
    
    def test_current_otel_values_getter(self):
        """Test current OpenTelemetry values getter."""
        collector = ThreadMetricsCollector()
        
        # Test initial values
        values = collector.get_current_otel_values()
        expected = {
            'workers_active': 0,
            'workers_total': 0,
            'workers_max_configured': 0,
            'requests_queued': 0
        }
        assert values == expected
        
        # Test that it returns a copy (not the original dict)
        values['workers_active'] = 999
        assert collector._otel_values['workers_active'] == 0
    
    @patch('app.monitoring.time.time')
    def test_collect_throttling(self, mock_time):
        """Test that collect() properly throttles updates."""
        collector = ThreadMetricsCollector(update_interval=2.0)
        
        # First call should proceed
        mock_time.return_value = 100.0
        with patch.object(collector, '_update_worker_metrics') as mock_worker, \
             patch.object(collector, '_update_queue_metrics') as mock_queue:
            
            collector.collect()
            
            mock_worker.assert_called_once()
            mock_queue.assert_called_once()
            assert collector.last_update == 100.0
        
        # Second call within throttle interval should be skipped
        mock_time.return_value = 101.0  # Only 1 second later, but interval is 2.0
        with patch.object(collector, '_update_worker_metrics') as mock_worker, \
             patch.object(collector, '_update_queue_metrics') as mock_queue:
            
            collector.collect()
            
            mock_worker.assert_not_called()
            mock_queue.assert_not_called()
            assert collector.last_update == 100.0  # Should not update
        
        # Third call after throttle interval should proceed
        mock_time.return_value = 102.5  # 2.5 seconds later, exceeds 2.0 interval
        with patch.object(collector, '_update_worker_metrics') as mock_worker, \
             patch.object(collector, '_update_queue_metrics') as mock_queue:
            
            collector.collect()
            
            mock_worker.assert_called_once()
            mock_queue.assert_called_once()
            assert collector.last_update == 102.5
    
    @patch('app.monitoring.time.time')
    def test_collect_error_handling(self, mock_time):
        """Test that collect() handles errors gracefully."""
        collector = ThreadMetricsCollector()
        mock_time.return_value = 100.0
        
        # Test error in _update_worker_metrics
        with patch.object(collector, '_update_worker_metrics', side_effect=Exception("Worker error")), \
             patch.object(collector, '_update_queue_metrics') as mock_queue:
            
            # Should not raise exception
            collector.collect()
            
            # Queue metrics should still be called despite worker error
            mock_queue.assert_called_once()
    
    @patch('app.monitoring.get_active_worker_count')
    @patch('app.monitoring.get_total_worker_count')
    @patch('app.monitoring.get_max_configured_workers')
    @patch('app.monitoring.HTTP_WORKERS_ACTIVE')
    @patch('app.monitoring.HTTP_WORKERS_TOTAL')
    @patch('app.monitoring.HTTP_WORKERS_MAX_CONFIGURED')
    @patch('app.monitoring.otel_http_workers_active')
    @patch('app.monitoring.otel_http_workers_total')
    @patch('app.monitoring.otel_http_workers_max_configured')
    def test_update_worker_metrics_success(
        self, mock_otel_max, mock_otel_total, mock_otel_active,
        mock_prom_max, mock_prom_total, mock_prom_active,
        mock_get_max, mock_get_total, mock_get_active
    ):
        """Test successful worker metrics update."""
        collector = ThreadMetricsCollector()
        
        # Setup mock return values
        mock_get_active.return_value = 3
        mock_get_total.return_value = 8
        mock_get_max.return_value = 10
        
        # Call the method
        collector._update_worker_metrics()
        
        # Verify Prometheus metrics were updated
        mock_prom_active.set.assert_called_once_with(3)
        mock_prom_total.set.assert_called_once_with(8)
        mock_prom_max.set.assert_called_once_with(10)
        
        # Verify OpenTelemetry metrics were updated with deltas
        mock_otel_active.add.assert_called_once_with(3)  # 3 - 0 = 3
        mock_otel_total.add.assert_called_once_with(8)   # 8 - 0 = 8
        mock_otel_max.add.assert_called_once_with(10)    # 10 - 0 = 10
        
        # Verify internal state was updated
        assert collector._otel_values['workers_active'] == 3
        assert collector._otel_values['workers_total'] == 8
        assert collector._otel_values['workers_max_configured'] == 10
    
    @patch('app.monitoring.get_active_worker_count')
    @patch('app.monitoring.get_total_worker_count')
    @patch('app.monitoring.get_max_configured_workers')
    @patch('app.monitoring.otel_http_workers_active')
    @patch('app.monitoring.otel_http_workers_total')
    @patch('app.monitoring.otel_http_workers_max_configured')
    def test_update_worker_metrics_delta_calculation(
        self, mock_otel_max, mock_otel_total, mock_otel_active,
        mock_get_max, mock_get_total, mock_get_active
    ):
        """Test delta calculation for OpenTelemetry metrics."""
        collector = ThreadMetricsCollector()
        
        # Set initial values
        collector._otel_values = {
            'workers_active': 2,
            'workers_total': 5,
            'workers_max_configured': 10,
            'requests_queued': 0
        }
        
        # Setup new values
        mock_get_active.return_value = 4  # Delta: +2
        mock_get_total.return_value = 7   # Delta: +2
        mock_get_max.return_value = 10    # Delta: 0 (no change)
        
        # Call the method
        collector._update_worker_metrics()
        
        # Verify OpenTelemetry deltas
        mock_otel_active.add.assert_called_once_with(2)  # 4 - 2 = 2
        mock_otel_total.add.assert_called_once_with(2)   # 7 - 5 = 2
        mock_otel_max.add.assert_not_called()            # 10 - 10 = 0, no call
        
        # Verify internal state was updated
        assert collector._otel_values['workers_active'] == 4
        assert collector._otel_values['workers_total'] == 7
        assert collector._otel_values['workers_max_configured'] == 10
    
    @patch('app.monitoring.get_active_worker_count', side_effect=Exception("Count error"))
    def test_update_worker_metrics_error_handling(self, mock_get_active):
        """Test error handling in worker metrics update."""
        collector = ThreadMetricsCollector()
        
        # Should not raise exception
        collector._update_worker_metrics()
        
        # Internal state should remain unchanged
        assert collector._otel_values['workers_active'] == 0
    
    @patch('app.monitoring.get_queued_requests_count')
    @patch('app.monitoring.HTTP_REQUESTS_QUEUED')
    @patch('app.monitoring.otel_http_requests_queued')
    def test_update_queue_metrics_success(
        self, mock_otel_queued, mock_prom_queued, mock_get_queued
    ):
        """Test successful queue metrics update."""
        collector = ThreadMetricsCollector()
        
        # Setup mock return value
        mock_get_queued.return_value = 5
        
        # Call the method
        collector._update_queue_metrics()
        
        # Verify Prometheus metric was updated
        mock_prom_queued.set.assert_called_once_with(5)
        
        # Verify OpenTelemetry metric was updated with delta
        mock_otel_queued.add.assert_called_once_with(5)  # 5 - 0 = 5
        
        # Verify internal state was updated
        assert collector._otel_values['requests_queued'] == 5
    
    @patch('app.monitoring.get_queued_requests_count')
    @patch('app.monitoring.otel_http_requests_queued')
    def test_update_queue_metrics_no_delta(self, mock_otel_queued, mock_get_queued):
        """Test queue metrics update when there's no change."""
        collector = ThreadMetricsCollector()
        collector._otel_values['requests_queued'] = 3
        
        # Setup same value (no change)
        mock_get_queued.return_value = 3
        
        # Call the method
        collector._update_queue_metrics()
        
        # Verify OpenTelemetry metric was not called (no delta)
        mock_otel_queued.add.assert_not_called()
        
        # Verify internal state remains the same
        assert collector._otel_values['requests_queued'] == 3
    
    @patch('app.monitoring.time.time')
    def test_force_update(self, mock_time):
        """Test force_update bypasses throttling."""
        collector = ThreadMetricsCollector(update_interval=10.0)
        mock_time.return_value = 100.0
        
        # Set last_update to recent time (should normally throttle)
        collector.last_update = 99.0
        
        with patch.object(collector, '_update_worker_metrics') as mock_worker, \
             patch.object(collector, '_update_queue_metrics') as mock_queue:
            
            collector.force_update()
            
            # Should call update methods despite recent last_update
            mock_worker.assert_called_once()
            mock_queue.assert_called_once()
            assert collector.last_update == 100.0
    
    @patch('app.monitoring.time.time')
    def test_force_update_error_recovery(self, mock_time):
        """Test force_update updates timestamp even with errors."""
        collector = ThreadMetricsCollector()
        mock_time.return_value = 100.0
        
        # Set initial last_update
        collector.last_update = 50.0
        
        with patch.object(collector, '_update_worker_metrics', side_effect=Exception("Force error")):
            collector.force_update()
            
            # Should update timestamp even with errors (new behavior)
            assert collector.last_update == 100.0


class TestThreadMetricsSetup:
    """Test cases for thread metrics setup functions."""
    
    def setup_method(self):
        """Setup for each test method."""
        # Reset global collector state
        import app.monitoring
        app.monitoring._thread_metrics_collector = None
    
    def test_setup_thread_metrics_enabled(self):
        """Test setup_thread_metrics when enabled."""
        with patch('prometheus_client.REGISTRY') as mock_registry:
            collector = setup_thread_metrics(
                enable_thread_metrics=True,
                update_interval=2.0,
                debug_logging=True
            )
            
            assert collector is not None
            assert isinstance(collector, ThreadMetricsCollector)
            assert collector.get_update_interval() == 2.0
            
            # Verify registration with Prometheus
            mock_registry.register.assert_called_once_with(collector)
    
    def test_setup_thread_metrics_disabled(self):
        """Test setup_thread_metrics when disabled."""
        collector = setup_thread_metrics(enable_thread_metrics=False)
        
        assert collector is None
        assert get_thread_metrics_collector() is None
        assert not is_thread_metrics_enabled()
    
    def test_setup_thread_metrics_duplicate_registration(self):
        """Test handling of duplicate registration."""
        with patch('prometheus_client.REGISTRY') as mock_registry:
            # Simulate duplicate registration error
            mock_registry.register.side_effect = ValueError("Duplicated timeseries")
            
            collector = setup_thread_metrics(enable_thread_metrics=True)
            
            # Should still return collector despite registration error
            assert collector is not None
            assert isinstance(collector, ThreadMetricsCollector)
    
    def test_setup_thread_metrics_error_handling(self):
        """Test error handling in setup_thread_metrics."""
        with patch('app.monitoring.ThreadMetricsCollector', side_effect=Exception("Setup error")):
            collector = setup_thread_metrics(enable_thread_metrics=True)
            
            assert collector is None
            assert get_thread_metrics_collector() is None
            assert not is_thread_metrics_enabled()
    
    def test_get_thread_metrics_collector(self):
        """Test get_thread_metrics_collector function."""
        # Initially should be None
        assert get_thread_metrics_collector() is None
        
        # After setup should return collector
        with patch('prometheus_client.REGISTRY'):
            collector = setup_thread_metrics(enable_thread_metrics=True)
            assert get_thread_metrics_collector() is collector
    
    def test_is_thread_metrics_enabled(self):
        """Test is_thread_metrics_enabled function."""
        # Initially should be False
        assert not is_thread_metrics_enabled()
        
        # After setup should be True
        with patch('prometheus_client.REGISTRY'):
            setup_thread_metrics(enable_thread_metrics=True)
            assert is_thread_metrics_enabled()
        
        # After disabling should be False
        setup_thread_metrics(enable_thread_metrics=False)
        assert not is_thread_metrics_enabled()


class TestThreadMetricsIntegration:
    """Integration tests for thread metrics collector."""
    
    def setup_method(self):
        """Setup for each test method."""
        # Reset global collector state
        import app.monitoring
        app.monitoring._thread_metrics_collector = None
    
    @patch('app.monitoring.get_active_worker_count')
    @patch('app.monitoring.get_total_worker_count')
    @patch('app.monitoring.get_max_configured_workers')
    @patch('app.monitoring.get_queued_requests_count')
    def test_full_collection_cycle(
        self, mock_get_queued, mock_get_max, mock_get_total, mock_get_active
    ):
        """Test a full collection cycle with real metric values."""
        # Setup mock values
        mock_get_active.return_value = 2
        mock_get_total.return_value = 4
        mock_get_max.return_value = 8
        mock_get_queued.return_value = 1
        
        with patch('prometheus_client.REGISTRY'):
            collector = setup_thread_metrics(enable_thread_metrics=True)
            
            # Force an update to test the full cycle
            collector.force_update()
            
            # Verify internal state was updated correctly
            otel_values = collector.get_current_otel_values()
            assert otel_values['workers_active'] == 2
            assert otel_values['workers_total'] == 4
            assert otel_values['workers_max_configured'] == 8
            assert otel_values['requests_queued'] == 1
    
    def test_collector_with_configuration(self):
        """Test collector setup with various configurations."""
        test_configs = [
            {'update_interval': 0.5, 'debug_logging': True},
            {'update_interval': 5.0, 'debug_logging': False},
            {'update_interval': 1.0, 'debug_logging': True},
        ]
        
        for config in test_configs:
            # Reset state
            import app.monitoring
            app.monitoring._thread_metrics_collector = None
            
            with patch('prometheus_client.REGISTRY'):
                collector = setup_thread_metrics(
                    enable_thread_metrics=True,
                    **config
                )
                
                assert collector is not None
                assert collector.get_update_interval() == config['update_interval']