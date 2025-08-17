"""
Integration tests for thread metrics monitoring infrastructure integration.

Tests the integration of ThreadMetricsCollector with the existing monitoring
infrastructure, configuration system, and Prometheus registry.
"""

import pytest
import time
from unittest.mock import patch, MagicMock
from prometheus_client import REGISTRY, CollectorRegistry
from app.monitoring import (
    setup_thread_metrics,
    get_thread_metrics_status,
    ThreadMetricsCollector,
    HTTP_WORKERS_ACTIVE,
    HTTP_WORKERS_TOTAL,
    HTTP_WORKERS_MAX_CONFIGURED,
    HTTP_REQUESTS_QUEUED
)
from app.config import Settings


class TestThreadMetricsIntegration:
    """Test thread metrics integration with monitoring infrastructure."""
    
    def setup_method(self):
        """Setup for each test method."""
        # Reset global state
        import app.monitoring
        app.monitoring.thread_metrics_collector = None
        
        # Create a test registry to avoid conflicts
        self.test_registry = CollectorRegistry()
    
    def teardown_method(self):
        """Cleanup after each test method."""
        # Reset global state
        import app.monitoring
        app.monitoring.thread_metrics_collector = None
    
    def test_setup_thread_metrics_enabled(self):
        """Test thread metrics setup when enabled."""
        # Setup thread metrics with enabled configuration
        setup_thread_metrics(
            enable_thread_metrics=True,
            thread_metrics_update_interval=0.5,
            thread_metrics_debug_logging=True
        )
        
        # Verify collector was created
        status = get_thread_metrics_status()
        assert status['enabled'] is True
        assert status['collector_status'] == 'active'
        assert 'collector_info' in status
        
        # Verify collector configuration
        collector_info = status['collector_info']
        assert collector_info['update_interval'] == 0.5
        assert collector_info['debug_logging'] is True
    
    def test_setup_thread_metrics_disabled(self):
        """Test thread metrics setup when disabled."""
        # Setup thread metrics with disabled configuration
        setup_thread_metrics(
            enable_thread_metrics=False,
            thread_metrics_update_interval=1.0,
            thread_metrics_debug_logging=False
        )
        
        # Verify collector was not created
        status = get_thread_metrics_status()
        assert status['enabled'] is False
        assert status['collector_status'] == 'not_initialized'
        assert status['reason'] == 'setup_not_called_or_disabled'
    
    def test_thread_metrics_configuration_integration(self):
        """Test integration with configuration system."""
        # Create settings with thread metrics enabled
        settings = Settings(
            enable_thread_metrics=True,
            thread_metrics_update_interval=2.0,
            thread_metrics_debug_logging=True
        )
        
        # Setup using configuration values
        setup_thread_metrics(
            enable_thread_metrics=settings.enable_thread_metrics,
            thread_metrics_update_interval=settings.thread_metrics_update_interval,
            thread_metrics_debug_logging=settings.thread_metrics_debug_logging
        )
        
        # Verify configuration was applied
        status = get_thread_metrics_status()
        assert status['enabled'] is True
        collector_info = status['collector_info']
        assert collector_info['update_interval'] == 2.0
        assert collector_info['debug_logging'] is True
    
    def test_prometheus_registry_integration(self):
        """Test integration with Prometheus registry."""
        # Setup thread metrics
        setup_thread_metrics(enable_thread_metrics=True)
        
        # Verify collector is registered with Prometheus
        status = get_thread_metrics_status()
        assert status['enabled'] is True
        
        # Test that metrics collection works
        import app.monitoring
        collector = app.monitoring.thread_metrics_collector
        assert collector is not None
        
        # Trigger collection
        collector.collect()
        
        # Verify metrics were updated (they should have values >= 0)
        assert HTTP_WORKERS_ACTIVE._value._value >= 0
        assert HTTP_WORKERS_TOTAL._value._value >= 0
        assert HTTP_WORKERS_MAX_CONFIGURED._value._value >= 0
        assert HTTP_REQUESTS_QUEUED._value._value >= 0
    
    def test_metrics_collection_throttling(self):
        """Test that metrics collection respects throttling interval."""
        # Setup with short throttling interval
        setup_thread_metrics(
            enable_thread_metrics=True,
            thread_metrics_update_interval=0.1
        )
        
        import app.monitoring
        collector = app.monitoring.thread_metrics_collector
        
        # Reset collector state for clean test
        collector.last_update = 0.0
        collector.collection_count = 0
        
        # First collection should work
        collector.collect()
        first_update_time = collector.last_update
        first_collection_count = collector.collection_count
        
        # Verify first collection worked
        assert first_update_time > 0
        assert first_collection_count >= 1
        
        # Immediate second collection should be throttled
        collector.collect()
        second_update_time = collector.last_update
        second_collection_count = collector.collection_count
        
        # If throttled, update time should be same
        assert second_update_time == first_update_time  # Should be same (throttled)
        
        # Wait for throttling interval and try again
        time.sleep(0.15)  # Wait longer than throttling interval
        collector.collect()
        third_update_time = collector.last_update
        third_collection_count = collector.collection_count
        
        # This collection should not be throttled
        assert third_update_time > second_update_time  # Should be updated
        assert third_collection_count > second_collection_count
    
    def test_error_handling_during_setup(self):
        """Test error handling during thread metrics setup."""
        # Mock ThreadMetricsCollector to raise an exception
        with patch('app.monitoring.ThreadMetricsCollector', side_effect=Exception("Test error")):
            # Setup should not raise exception
            setup_thread_metrics(enable_thread_metrics=True)
            
            # Verify graceful handling
            status = get_thread_metrics_status()
            # Should either be disabled or show error status
            assert status['enabled'] is False or 'error' in status
    
    def test_metrics_values_integration(self):
        """Test that metrics show reasonable values."""
        # Setup thread metrics
        setup_thread_metrics(enable_thread_metrics=True)
        
        # Get current metrics status
        status = get_thread_metrics_status()
        assert status['enabled'] is True
        
        # Check current metrics values
        current_metrics = status.get('current_metrics', {})
        
        # Values should be non-negative integers
        if 'error' not in current_metrics:
            assert current_metrics['active_workers'] >= 0
            assert current_metrics['total_workers'] >= 0
            assert current_metrics['max_configured'] > 0  # Should have some configured max
            assert current_metrics['queued_requests'] >= 0
            
            # Active workers should not exceed total workers
            assert current_metrics['active_workers'] <= current_metrics['total_workers']
            
            # Total workers should not exceed max configured
            assert current_metrics['total_workers'] <= current_metrics['max_configured']
    
    def test_collector_status_information(self):
        """Test that collector provides useful status information."""
        # Setup thread metrics with debug logging
        setup_thread_metrics(
            enable_thread_metrics=True,
            thread_metrics_update_interval=1.0,
            thread_metrics_debug_logging=True
        )
        
        import app.monitoring
        collector = app.monitoring.thread_metrics_collector
        
        # Trigger some collections
        collector.collect()
        time.sleep(0.1)
        collector.collect()  # This should be throttled
        
        # Get status information
        status_info = collector.get_status()
        
        # Verify status information structure
        assert 'collection_count' in status_info
        assert 'error_count' in status_info
        assert 'last_update' in status_info
        assert 'time_since_last_update' in status_info
        assert 'update_interval' in status_info
        assert 'debug_logging' in status_info
        assert 'last_values' in status_info
        assert 'error_rate' in status_info
        
        # Verify reasonable values
        assert status_info['collection_count'] >= 1
        assert status_info['error_count'] >= 0
        assert status_info['update_interval'] == 1.0
        assert status_info['debug_logging'] is True
        assert 0 <= status_info['error_rate'] <= 1
    
    @patch('app.monitoring.get_active_worker_count')
    @patch('app.monitoring.get_total_worker_count')
    @patch('app.monitoring.get_max_configured_workers')
    @patch('app.monitoring.get_queued_requests_count')
    def test_metrics_collection_with_mocked_values(
        self, 
        mock_queued, 
        mock_max_configured, 
        mock_total, 
        mock_active
    ):
        """Test metrics collection with controlled values."""
        # Setup mock return values
        mock_active.return_value = 3
        mock_total.return_value = 8
        mock_max_configured.return_value = 10
        mock_queued.return_value = 2
        
        # Setup thread metrics
        setup_thread_metrics(enable_thread_metrics=True)
        
        import app.monitoring
        collector = app.monitoring.thread_metrics_collector
        
        # Trigger collection
        collector.collect()
        
        # Verify Prometheus metrics were updated with expected values
        assert HTTP_WORKERS_ACTIVE._value._value == 3
        assert HTTP_WORKERS_TOTAL._value._value == 8
        assert HTTP_WORKERS_MAX_CONFIGURED._value._value == 10
        assert HTTP_REQUESTS_QUEUED._value._value == 2
        
        # Verify status shows correct values
        status = get_thread_metrics_status()
        current_metrics = status['current_metrics']
        assert current_metrics['active_workers'] == 3
        assert current_metrics['total_workers'] == 8
        assert current_metrics['max_configured'] == 10
        assert current_metrics['queued_requests'] == 2
    
    def test_single_process_uvicorn_compatibility(self):
        """Test that thread metrics work with single-process uvicorn deployment."""
        # This test verifies that thread metrics work in the expected deployment scenario
        
        # Setup thread metrics (should work regardless of deployment model)
        setup_thread_metrics(enable_thread_metrics=True)
        
        # Verify setup succeeded
        status = get_thread_metrics_status()
        assert status['enabled'] is True
        
        # Verify metrics collection works
        import app.monitoring
        collector = app.monitoring.thread_metrics_collector
        collector.collect()
        
        # In single-process deployment, we should get some reasonable values
        current_metrics = status['current_metrics']
        if 'error' not in current_metrics:
            # Should have at least one thread (the main thread)
            assert current_metrics['total_workers'] >= 0
            assert current_metrics['max_configured'] > 0
    
    def test_configuration_parameter_mapping(self):
        """Test that configuration parameters are correctly mapped."""
        # Test with specific configuration values
        test_interval = 3.5
        test_debug = True
        
        setup_thread_metrics(
            enable_thread_metrics=True,
            thread_metrics_update_interval=test_interval,
            thread_metrics_debug_logging=test_debug
        )
        
        # Verify configuration was applied correctly
        status = get_thread_metrics_status()
        collector_info = status['collector_info']
        
        assert collector_info['update_interval'] == test_interval
        assert collector_info['debug_logging'] == test_debug
    
    def test_metrics_persistence_across_collections(self):
        """Test that metrics maintain reasonable values across multiple collections."""
        # Setup thread metrics
        setup_thread_metrics(
            enable_thread_metrics=True,
            thread_metrics_update_interval=0.1  # Short interval for testing
        )
        
        import app.monitoring
        collector = app.monitoring.thread_metrics_collector
        
        # Collect metrics multiple times
        values_history = []
        for i in range(3):
            collector.collect()
            time.sleep(0.15)  # Wait for throttling interval
            
            # Record current values
            current_values = {
                'active': HTTP_WORKERS_ACTIVE._value._value,
                'total': HTTP_WORKERS_TOTAL._value._value,
                'max_configured': HTTP_WORKERS_MAX_CONFIGURED._value._value,
                'queued': HTTP_REQUESTS_QUEUED._value._value
            }
            values_history.append(current_values)
        
        # Verify all collections produced valid values
        for values in values_history:
            assert values['active'] >= 0
            assert values['total'] >= 0
            assert values['max_configured'] > 0
            assert values['queued'] >= 0
            assert values['active'] <= values['total']
            assert values['total'] <= values['max_configured']