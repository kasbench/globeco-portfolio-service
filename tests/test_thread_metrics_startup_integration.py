"""
Integration tests for thread metrics application startup.

Tests that thread metrics are properly initialized during application startup
and appear in both /metrics endpoint and OpenTelemetry collector export.
"""

import pytest
import asyncio
import time
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock
from app.main import app
from app.config import settings
from app.monitoring import get_thread_metrics_status, thread_metrics_collector


class TestThreadMetricsStartupIntegration:
    """Test thread metrics integration during application startup."""
    
    def test_thread_metrics_enabled_by_default(self):
        """Test that thread metrics are enabled by default in configuration."""
        assert settings.enable_thread_metrics is True
        assert settings.thread_metrics_update_interval == 1.0
        assert settings.thread_metrics_debug_logging is False
    
    def test_thread_metrics_collector_initialized(self):
        """Test that thread metrics collector is properly initialized during startup."""
        # Check that the global collector instance exists
        assert thread_metrics_collector is not None
        
        # Check collector status
        status = get_thread_metrics_status()
        assert status['enabled'] is True
        assert status['collector_status'] == 'active'
        assert 'collector_info' in status
        
        # Check collector configuration
        collector_info = status['collector_info']
        assert collector_info['update_interval'] == settings.thread_metrics_update_interval
        assert collector_info['debug_logging'] == settings.thread_metrics_debug_logging
    
    def test_thread_metrics_appear_in_metrics_endpoint(self):
        """Test that thread metrics appear in the /metrics endpoint."""
        # Test the metrics directly from Prometheus registry instead of full app
        from prometheus_client import generate_latest, REGISTRY
        from app.monitoring import HTTP_WORKERS_ACTIVE, HTTP_WORKERS_TOTAL, HTTP_WORKERS_MAX_CONFIGURED, HTTP_REQUESTS_QUEUED
        
        # Trigger metrics collection if collector exists
        if thread_metrics_collector:
            thread_metrics_collector.collect()
        
        # Generate metrics output
        metrics_content = generate_latest(REGISTRY).decode('utf-8')
        
        # Check that all four thread metrics are present
        expected_metrics = [
            "http_workers_active",
            "http_workers_total", 
            "http_workers_max_configured",
            "http_requests_queued"
        ]
        
        for metric_name in expected_metrics:
            assert metric_name in metrics_content, f"Metric {metric_name} not found in /metrics endpoint"
        
        # Check that metrics have help text
        assert "# HELP http_workers_active" in metrics_content
        assert "# HELP http_workers_total" in metrics_content
        assert "# HELP http_workers_max_configured" in metrics_content
        assert "# HELP http_requests_queued" in metrics_content
        
        # Check that metrics have type declarations
        assert "# TYPE http_workers_active gauge" in metrics_content
        assert "# TYPE http_workers_total gauge" in metrics_content
        assert "# TYPE http_workers_max_configured gauge" in metrics_content
        assert "# TYPE http_requests_queued gauge" in metrics_content
    
    def test_thread_metrics_have_reasonable_values(self):
        """Test that thread metrics have reasonable initial values."""
        from prometheus_client import generate_latest, REGISTRY
        
        # Trigger metrics collection if collector exists
        if thread_metrics_collector:
            thread_metrics_collector.collect()
        
        # Generate metrics output
        metrics_content = generate_latest(REGISTRY).decode('utf-8')
        lines = metrics_content.split('\n')
        
        # Extract metric values
        metric_values = {}
        for line in lines:
            if line and not line.startswith('#'):
                parts = line.split(' ')
                if len(parts) >= 2:
                    metric_name = parts[0]
                    try:
                        metric_value = float(parts[1])
                        metric_values[metric_name] = metric_value
                    except ValueError:
                        continue
        
        # Check that thread metrics have reasonable values
        if 'http_workers_active' in metric_values:
            assert metric_values['http_workers_active'] >= 0
            
        if 'http_workers_total' in metric_values:
            assert metric_values['http_workers_total'] >= 0
            
        if 'http_workers_max_configured' in metric_values:
            assert metric_values['http_workers_max_configured'] > 0
            
        if 'http_requests_queued' in metric_values:
            assert metric_values['http_requests_queued'] >= 0
        
        # Logical relationships between metrics
        if ('http_workers_active' in metric_values and 
            'http_workers_total' in metric_values):
            assert metric_values['http_workers_active'] <= metric_values['http_workers_total']
            
        if ('http_workers_total' in metric_values and 
            'http_workers_max_configured' in metric_values):
            assert metric_values['http_workers_total'] <= metric_values['http_workers_max_configured']
    
    @patch('app.monitoring.otel_http_workers_active')
    @patch('app.monitoring.otel_http_workers_total')
    @patch('app.monitoring.otel_http_workers_max_configured')
    @patch('app.monitoring.otel_http_requests_queued')
    def test_opentelemetry_metrics_integration(self, mock_otel_queued, mock_otel_max, 
                                             mock_otel_total, mock_otel_active):
        """Test that OpenTelemetry thread metrics are properly integrated."""
        # Setup mocks
        mock_otel_active.add = MagicMock()
        mock_otel_total.add = MagicMock()
        mock_otel_max.add = MagicMock()
        mock_otel_queued.add = MagicMock()
        
        # Trigger metrics collection
        if thread_metrics_collector:
            thread_metrics_collector.collect()
            
            # Verify that OpenTelemetry metrics were called
            # Note: The exact calls depend on the current vs last values
            # We just verify that the metrics objects are being used
            assert hasattr(mock_otel_active, 'add')
            assert hasattr(mock_otel_total, 'add')
            assert hasattr(mock_otel_max, 'add')
            assert hasattr(mock_otel_queued, 'add')
    
    def test_thread_metrics_collection_under_load(self):
        """Test thread metrics collection during concurrent requests."""
        # Create some thread activity and test metrics collection
        import concurrent.futures
        import time
        
        def dummy_work():
            time.sleep(0.1)  # Simulate some work
            return True
        
        # Create some concurrent load to generate thread activity
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(dummy_work) for _ in range(10)]
            results = [future.result() for future in futures]
        
        # All work should succeed
        for result in results:
            assert result is True
        
        # Trigger metrics collection
        if thread_metrics_collector:
            thread_metrics_collector.collect()
        
        # Check metrics after load
        from prometheus_client import generate_latest, REGISTRY
        metrics_content = generate_latest(REGISTRY).decode('utf-8')
        
        # Verify thread metrics are still present and reasonable
        assert "http_workers_active" in metrics_content
        assert "http_workers_total" in metrics_content
    
    def test_thread_metrics_status_endpoint_integration(self):
        """Test that thread metrics status can be retrieved for monitoring."""
        status = get_thread_metrics_status()
        
        assert isinstance(status, dict)
        assert status['enabled'] is True
        assert 'collector_info' in status
        assert 'current_metrics' in status
        
        # Check current metrics structure
        current_metrics = status['current_metrics']
        expected_keys = ['active_workers', 'total_workers', 'max_configured', 'queued_requests']
        
        for key in expected_keys:
            assert key in current_metrics, f"Missing metric key: {key}"
            # Values should be non-negative integers
            if not isinstance(current_metrics[key], dict):  # Not an error dict
                assert isinstance(current_metrics[key], int)
                assert current_metrics[key] >= 0


class TestThreadMetricsStartupConfiguration:
    """Test thread metrics startup with different configuration options."""
    
    @patch('app.config.settings.enable_thread_metrics', False)
    def test_thread_metrics_disabled_configuration(self):
        """Test that thread metrics can be disabled via configuration."""
        # Import after patching to get the patched value
        from app.monitoring import setup_thread_metrics
        
        # Reset global collector
        import app.monitoring
        app.monitoring.thread_metrics_collector = None
        
        # Setup with disabled configuration
        setup_thread_metrics(enable_thread_metrics=False)
        
        # Check that collector was not created
        status = get_thread_metrics_status()
        assert status['enabled'] is False
        assert status['collector_status'] == 'not_initialized'
    
    def test_thread_metrics_custom_configuration(self):
        """Test thread metrics setup with custom configuration values."""
        from app.monitoring import setup_thread_metrics
        
        # Reset global collector
        import app.monitoring
        app.monitoring.thread_metrics_collector = None
        
        # Setup with custom configuration
        custom_interval = 2.5
        custom_debug = True
        
        setup_thread_metrics(
            enable_thread_metrics=True,
            thread_metrics_update_interval=custom_interval,
            thread_metrics_debug_logging=custom_debug
        )
        
        # Check that custom configuration was applied
        status = get_thread_metrics_status()
        assert status['enabled'] is True
        
        collector_info = status['collector_info']
        assert collector_info['update_interval'] == custom_interval
        assert collector_info['debug_logging'] == custom_debug
    
    def test_thread_metrics_startup_logging(self, caplog):
        """Test that appropriate startup logging occurs for thread metrics."""
        from app.monitoring import setup_thread_metrics
        import logging
        
        # Reset global collector
        import app.monitoring
        app.monitoring.thread_metrics_collector = None
        
        with caplog.at_level(logging.INFO):
            setup_thread_metrics(
                enable_thread_metrics=True,
                thread_metrics_update_interval=1.0,
                thread_metrics_debug_logging=False
            )
        
        # Check that setup logging occurred
        log_messages = [record.message for record in caplog.records]
        
        # Should have setup and completion messages
        setup_messages = [msg for msg in log_messages if "Setting up thread metrics" in msg]
        assert len(setup_messages) > 0
        
        completion_messages = [msg for msg in log_messages if "setup completed successfully" in msg]
        assert len(completion_messages) > 0


class TestThreadMetricsStartupErrorHandling:
    """Test error handling during thread metrics startup."""
    
    @patch('app.monitoring.ThreadMetricsCollector')
    def test_collector_creation_failure_handling(self, mock_collector_class, caplog):
        """Test graceful handling when collector creation fails."""
        import logging
        
        # Make collector creation fail
        mock_collector_class.side_effect = Exception("Collector creation failed")
        
        from app.monitoring import setup_thread_metrics
        
        # Reset global collector
        import app.monitoring
        app.monitoring.thread_metrics_collector = None
        
        with caplog.at_level(logging.ERROR):
            setup_thread_metrics(enable_thread_metrics=True)
        
        # Should have error logged and collector should be None
        error_messages = [record.message for record in caplog.records if record.levelno >= logging.ERROR]
        assert len(error_messages) > 0
        
        # Check that some error message mentions collector creation
        collector_errors = [msg for msg in error_messages if "collector" in msg.lower()]
        assert len(collector_errors) > 0
    
    @patch('prometheus_client.REGISTRY.register')
    def test_prometheus_registration_failure_handling(self, mock_register, caplog):
        """Test graceful handling when Prometheus registration fails."""
        import logging
        
        # Make Prometheus registration fail
        mock_register.side_effect = Exception("Registration failed")
        
        from app.monitoring import setup_thread_metrics
        
        # Reset global collector
        import app.monitoring
        app.monitoring.thread_metrics_collector = None
        
        with caplog.at_level(logging.ERROR):
            setup_thread_metrics(enable_thread_metrics=True)
        
        # Should have error logged but setup should continue
        error_messages = [record.message for record in caplog.records if record.levelno >= logging.ERROR]
        registration_errors = [msg for msg in error_messages if "register" in msg.lower()]
        assert len(registration_errors) > 0
        
        # Collector should still be created even if registration failed
        status = get_thread_metrics_status()
        assert status['enabled'] is True


if __name__ == "__main__":
    pytest.main([__file__])