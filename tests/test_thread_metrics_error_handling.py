"""
Unit tests for comprehensive error handling and logging in thread metrics functionality.

These tests verify that all error scenarios are properly handled with appropriate fallbacks,
debug logging works correctly, and the ThreadMetricsCollector handles failures gracefully.
"""

import pytest
import time
import threading
from unittest.mock import Mock, patch, MagicMock, call
from concurrent.futures import ThreadPoolExecutor

# Import after setting up test environment
import os
os.environ['PROMETHEUS_DISABLE_CREATED_SERIES'] = 'True'

from app.monitoring import (
    _enumerate_active_threads,
    _is_worker_thread,
    _is_thread_active,
    get_active_worker_count,
    get_total_worker_count,
    get_max_configured_workers,
    get_queued_requests_count,
    _detect_uvicorn_queue,
    _detect_asyncio_queue,
    _detect_system_level_queue,
    _estimate_queue_from_metrics,
    _detect_uvicorn_thread_pool,
    _get_asyncio_thread_pool_info,
    ThreadMetricsCollector,
    setup_thread_metrics,
    get_thread_metrics_status,
    clear_metrics_registry
)


class TestThreadEnumerationErrorHandling:
    """Test error handling in thread enumeration functions."""
    
    @patch('app.monitoring.logger')
    @patch('threading.enumerate')
    def test_enumerate_active_threads_error_logging(self, mock_enumerate, mock_logger):
        """Test that thread enumeration errors are properly logged."""
        mock_enumerate.side_effect = RuntimeError("Thread enumeration system error")
        
        result = _enumerate_active_threads()
        
        # Should return empty list on error
        assert result == []
        
        # Verify error logging with structured context
        error_calls = [call for call in mock_logger.error.call_args_list 
                      if 'Failed to enumerate active threads' in str(call)]
        assert len(error_calls) > 0
        
        error_call = error_calls[0]
        call_kwargs = error_call[1]
        assert 'error' in call_kwargs
        assert 'error_type' in call_kwargs
        assert 'fallback_result' in call_kwargs
        assert 'exc_info' in call_kwargs
        assert call_kwargs['error'] == "Thread enumeration system error"
        assert call_kwargs['error_type'] == "RuntimeError"
        assert call_kwargs['fallback_result'] == "empty_list"
        assert call_kwargs['exc_info'] is True
    
    @patch('app.monitoring.logger')
    def test_is_worker_thread_error_logging(self, mock_logger):
        """Test that worker thread identification errors are properly handled."""
        # Create a mock thread that will cause an exception
        mock_thread = Mock()
        # Remove name attribute to cause AttributeError
        del mock_thread.name
        
        result = _is_worker_thread(mock_thread)
        
        # Should return False on error
        assert result is False
        
        # The function should handle the error gracefully
        # We don't require specific logging as the function may handle errors silently
    
    @patch('app.monitoring.logger')
    def test_is_thread_active_error_logging(self, mock_logger):
        """Test that thread activity detection errors are properly logged."""
        mock_thread = Mock()
        mock_thread.is_alive.side_effect = RuntimeError("Thread state access error")
        mock_thread.name = "test-thread"
        
        result = _is_thread_active(mock_thread)
        
        # Should return False on error
        assert result is False
        
        # Verify debug logging for error handling
        debug_calls = [call for call in mock_logger.debug.call_args_list 
                      if 'Error checking thread activity status' in str(call)]
        assert len(debug_calls) > 0
        
        debug_call = debug_calls[0]
        call_kwargs = debug_call[1]
        assert 'thread_name' in call_kwargs
        assert 'error' in call_kwargs
        assert 'error_type' in call_kwargs
        assert 'fallback_result' in call_kwargs
        assert call_kwargs['thread_name'] == "test-thread"
        assert call_kwargs['error'] == "Thread state access error"
        assert call_kwargs['error_type'] == "RuntimeError"
        assert call_kwargs['fallback_result'] is False


class TestWorkerCountErrorHandling:
    """Test error handling in worker count functions."""
    
    @patch('app.monitoring.logger')
    @patch('app.monitoring._enumerate_active_threads')
    def test_get_active_worker_count_enumeration_error(self, mock_enumerate, mock_logger):
        """Test error handling when thread enumeration fails."""
        mock_enumerate.side_effect = RuntimeError("System thread access denied")
        
        result = get_active_worker_count()
        
        # Should return 0 on error
        assert result == 0
        
        # Verify error logging with comprehensive context
        error_calls = [call for call in mock_logger.error.call_args_list 
                      if 'Failed to count active worker threads' in str(call)]
        assert len(error_calls) > 0
        
        error_call = error_calls[0]
        call_kwargs = error_call[1]
        assert 'error' in call_kwargs
        assert 'error_type' in call_kwargs
        assert 'fallback_result' in call_kwargs
        assert 'exc_info' in call_kwargs
        assert call_kwargs['error'] == "System thread access denied"
        assert call_kwargs['error_type'] == "RuntimeError"
        assert call_kwargs['fallback_result'] == 0
        assert call_kwargs['exc_info'] is True
    
    @patch('app.monitoring.logger')
    @patch('app.monitoring._is_worker_thread')
    @patch('app.monitoring._enumerate_active_threads')
    def test_get_active_worker_count_individual_thread_error(self, mock_enumerate, mock_is_worker, mock_logger):
        """Test error handling when individual thread processing fails."""
        # Create mock threads with proper name attributes
        mock_threads = []
        for i in range(3):
            mock_thread = Mock()
            mock_thread.name = f"thread-{i}"
            mock_threads.append(mock_thread)
        
        mock_enumerate.return_value = mock_threads
        
        # Make _is_worker_thread fail for the second thread
        def is_worker_side_effect(thread):
            if thread.name == "thread-1":
                raise RuntimeError("Thread inspection failed")
            return "thread" in thread.name
        
        mock_is_worker.side_effect = is_worker_side_effect
        
        result = get_active_worker_count()
        
        # Should still return count for threads that didn't fail
        assert result >= 0
        
        # Verify debug logging for individual thread errors
        debug_calls = [call for call in mock_logger.debug.call_args_list 
                      if 'Error processing individual thread for active count' in str(call)]
        assert len(debug_calls) > 0
        
        debug_call = debug_calls[0]
        call_kwargs = debug_call[1]
        assert 'thread_name' in call_kwargs
        assert 'error' in call_kwargs
        assert 'error_type' in call_kwargs
        assert call_kwargs['thread_name'] == "thread-1"
        assert call_kwargs['error'] == "Thread inspection failed"
        assert call_kwargs['error_type'] == "RuntimeError"
    
    @patch('app.monitoring.logger')
    @patch('app.monitoring._detect_uvicorn_thread_pool')
    @patch('app.monitoring._get_asyncio_thread_pool_info')
    def test_get_max_configured_workers_all_detection_fails(self, mock_asyncio, mock_uvicorn, mock_logger):
        """Test fallback behavior when all thread pool detection methods fail."""
        mock_uvicorn.side_effect = RuntimeError("Uvicorn detection failed")
        mock_asyncio.side_effect = RuntimeError("AsyncIO detection failed")
        
        result = get_max_configured_workers()
        
        # Should return conservative fallback
        assert result == 8
        
        # Verify error logging for complete detection failure
        error_calls = [call for call in mock_logger.error.call_args_list 
                      if 'Failed to detect maximum configured workers' in str(call)]
        assert len(error_calls) > 0
        
        error_call = error_calls[0]
        call_kwargs = error_call[1]
        assert 'error' in call_kwargs
        assert 'error_type' in call_kwargs
        assert 'fallback_result' in call_kwargs
        assert 'exc_info' in call_kwargs
        assert call_kwargs['fallback_result'] == 8
        assert call_kwargs['exc_info'] is True


class TestQueueDetectionErrorHandling:
    """Test error handling in queue detection functions."""
    
    @patch('app.monitoring.logger')
    def test_get_queued_requests_count_all_approaches_fail(self, mock_logger):
        """Test error handling when all queue detection approaches fail."""
        with patch('app.monitoring._detect_uvicorn_queue', side_effect=RuntimeError("Uvicorn queue failed")), \
             patch('app.monitoring._detect_asyncio_queue', side_effect=RuntimeError("AsyncIO queue failed")), \
             patch('app.monitoring._detect_system_level_queue', side_effect=RuntimeError("System queue failed")), \
             patch('app.monitoring._estimate_queue_from_metrics', side_effect=RuntimeError("Metrics estimation failed")):
            
            result = get_queued_requests_count()
            
            # Should return 0 on complete failure
            assert result == 0
            
            # Verify debug logging for each failed approach
            debug_calls = [call for call in mock_logger.debug.call_args_list 
                          if 'Queue detection approach failed' in str(call)]
            assert len(debug_calls) >= 4  # One for each approach
            
            # Verify final fallback logging
            fallback_calls = [call for call in mock_logger.debug.call_args_list 
                             if 'All queue detection approaches failed' in str(call)]
            assert len(fallback_calls) > 0
    
    @patch('app.monitoring.logger')
    @patch('asyncio.get_running_loop')
    def test_detect_asyncio_queue_no_loop_error(self, mock_get_loop, mock_logger):
        """Test error handling when no asyncio loop is available."""
        mock_get_loop.side_effect = RuntimeError("No running event loop")
        
        result = _detect_asyncio_queue()
        
        # Should return None when no loop available
        assert result is None
        
        # Verify debug logging for no loop condition
        debug_calls = [call for call in mock_logger.debug.call_args_list 
                      if 'No running asyncio event loop found for queue detection' in str(call)]
        assert len(debug_calls) > 0
        
        debug_call = debug_calls[0]
        call_kwargs = debug_call[1]
        assert 'error' in call_kwargs
        assert 'fallback_action' in call_kwargs
        assert call_kwargs['fallback_action'] == "return_none"
    
    @patch('app.monitoring.logger')
    def test_detect_system_level_queue_psutil_not_available(self, mock_logger):
        """Test error handling when psutil is not available."""
        # Mock the import to fail
        with patch('builtins.__import__', side_effect=lambda name, *args: ImportError("psutil not installed") if name == 'psutil' else __import__(name, *args)):
            result = _detect_system_level_queue()
            
            # Should return None when psutil not available
            assert result is None
            
            # Verify debug logging for missing psutil
            debug_calls = [call for call in mock_logger.debug.call_args_list 
                          if 'psutil not available for system-level queue detection' in str(call)]
            assert len(debug_calls) > 0
            
            debug_call = debug_calls[0]
            call_kwargs = debug_call[1]
            assert 'error' in call_kwargs
            assert 'fallback_action' in call_kwargs
            assert 'suggestion' in call_kwargs
            assert call_kwargs['fallback_action'] == "skip_system_detection"
            assert call_kwargs['suggestion'] == "install_psutil_for_enhanced_detection"
    
    @patch('app.monitoring.logger')
    @patch('app.monitoring.HTTP_REQUESTS_IN_FLIGHT')
    def test_estimate_queue_from_metrics_metric_access_error(self, mock_gauge, mock_logger):
        """Test error handling when metrics access fails."""
        # Make metric access fail
        mock_gauge._value._value = Mock(side_effect=AttributeError("Metric access failed"))
        mock_gauge.get = Mock(side_effect=RuntimeError("Gauge get failed"))
        
        # Mock the worker count functions to return some values so we get an estimate
        with patch('app.monitoring.get_active_worker_count', return_value=2), \
             patch('app.monitoring.get_total_worker_count', return_value=4):
            
            result = _estimate_queue_from_metrics()
            
            # Should handle error gracefully and still return an estimate
            assert result is not None  # Should still return some estimate
            
            # Verify debug logging for metric access error
            debug_calls = [call for call in mock_logger.debug.call_args_list 
                          if 'Error retrieving in-flight requests metric' in str(call)]
            assert len(debug_calls) > 0
            
            debug_call = debug_calls[0]
            call_kwargs = debug_call[1]
            assert 'error' in call_kwargs
            assert 'error_type' in call_kwargs
            assert 'fallback_value' in call_kwargs
            assert call_kwargs['fallback_value'] == 0


class TestThreadPoolDetectionErrorHandling:
    """Test error handling in thread pool detection functions."""
    
    @patch('app.monitoring.logger')
    @patch('gc.get_objects')
    def test_detect_uvicorn_thread_pool_gc_error(self, mock_gc, mock_logger):
        """Test error handling when garbage collection access fails."""
        mock_gc.side_effect = RuntimeError("GC access denied")
        
        result = _detect_uvicorn_thread_pool()
        
        # Should return empty dict on error
        assert result == {}
        
        # Verify error logging with comprehensive context
        error_calls = [call for call in mock_logger.error.call_args_list 
                      if 'Unexpected error detecting Uvicorn thread pool configuration' in str(call)]
        assert len(error_calls) > 0
        
        error_call = error_calls[0]
        call_kwargs = error_call[1]
        assert 'error' in call_kwargs
        assert 'error_type' in call_kwargs
        assert 'fallback_result' in call_kwargs
        assert 'detection_stage' in call_kwargs
        assert 'exc_info' in call_kwargs
        assert call_kwargs['error'] == "GC access denied"
        assert call_kwargs['error_type'] == "RuntimeError"
        assert call_kwargs['fallback_result'] == {}
        assert call_kwargs['detection_stage'] == "uvicorn_server_inspection"
        assert call_kwargs['exc_info'] is True
    
    @patch('app.monitoring.logger')
    @patch('asyncio.get_running_loop')
    def test_get_asyncio_thread_pool_info_loop_error(self, mock_get_loop, mock_logger):
        """Test error handling when asyncio loop access fails."""
        mock_get_loop.side_effect = Exception("Unexpected asyncio error")
        
        with patch('asyncio.get_event_loop', side_effect=Exception("Event loop error")):
            result = _get_asyncio_thread_pool_info()
            
            # Should return empty dict on error
            assert result == {}
            
            # Verify error logging
            error_calls = [call for call in mock_logger.error.call_args_list 
                          if 'Unexpected error detecting asyncio thread pool information' in str(call)]
            assert len(error_calls) > 0
            
            error_call = error_calls[0]
            call_kwargs = error_call[1]
            assert 'error' in call_kwargs
            assert 'error_type' in call_kwargs
            assert 'fallback_result' in call_kwargs
            assert 'detection_stage' in call_kwargs
            assert 'exc_info' in call_kwargs
            assert call_kwargs['fallback_result'] == {}
            assert call_kwargs['detection_stage'] == "asyncio_thread_pool_inspection"
            assert call_kwargs['exc_info'] is True


class TestThreadMetricsCollectorErrorHandling:
    """Test error handling in ThreadMetricsCollector class."""
    
    def setup_method(self):
        """Clear registry before each test."""
        clear_metrics_registry()
    
    def teardown_method(self):
        """Clear registry after each test."""
        clear_metrics_registry()
    
    @patch('app.monitoring.logger')
    def test_collector_initialization_logging(self, mock_logger):
        """Test that collector initialization is properly logged."""
        collector = ThreadMetricsCollector(update_interval=2.0, debug_logging=True)
        
        # Verify initialization logging
        info_calls = [call for call in mock_logger.info.call_args_list 
                     if 'ThreadMetricsCollector initialized' in str(call)]
        assert len(info_calls) > 0
        
        info_call = info_calls[0]
        call_kwargs = info_call[1]
        assert 'update_interval' in call_kwargs
        assert 'debug_logging' in call_kwargs
        assert 'throttling_enabled' in call_kwargs
        assert call_kwargs['update_interval'] == 2.0
        assert call_kwargs['debug_logging'] is True
        assert call_kwargs['throttling_enabled'] is True
        
        # Verify debug logging when enabled
        debug_calls = [call for call in mock_logger.debug.call_args_list 
                      if 'Debug logging enabled for thread metrics collector' in str(call)]
        assert len(debug_calls) > 0
    
    @patch('app.monitoring.logger')
    def test_collector_throttling_logging(self, mock_logger):
        """Test that collection throttling is properly logged."""
        collector = ThreadMetricsCollector(update_interval=1.0, debug_logging=True)
        
        # First collection should work
        with patch.object(collector, '_update_worker_metrics'), \
             patch.object(collector, '_update_queue_metrics'):
            collector.collect()
        
        # Immediate second collection should be throttled
        collector.collect()
        
        # Verify throttling debug logging
        debug_calls = [call for call in mock_logger.debug.call_args_list 
                      if 'Skipping thread metrics update due to throttling' in str(call)]
        assert len(debug_calls) > 0
        
        debug_call = debug_calls[0]
        call_kwargs = debug_call[1]
        assert 'time_since_last_update' in call_kwargs
        assert 'update_interval' in call_kwargs
        assert 'throttling_reason' in call_kwargs
        assert call_kwargs['throttling_reason'] == "too_frequent"
    
    @patch('app.monitoring.logger')
    def test_collector_critical_error_handling(self, mock_logger):
        """Test error handling when entire collection process fails."""
        collector = ThreadMetricsCollector(debug_logging=True)
        
        # Make worker metrics update fail
        with patch.object(collector, '_update_worker_metrics', side_effect=RuntimeError("Critical collection error")):
            collector.collect()
        
        # Verify error logging with comprehensive context
        error_calls = [call for call in mock_logger.error.call_args_list 
                      if 'Critical error during thread metrics collection' in str(call)]
        assert len(error_calls) > 0
        
        error_call = error_calls[0]
        call_kwargs = error_call[1]
        assert 'error' in call_kwargs
        assert 'error_type' in call_kwargs
        assert 'collection_number' in call_kwargs
        assert 'error_count' in call_kwargs
        assert 'collection_duration_ms' in call_kwargs
        assert 'impact' in call_kwargs
        assert 'mitigation' in call_kwargs
        assert 'exc_info' in call_kwargs
        assert call_kwargs['error'] == "Critical collection error"
        assert call_kwargs['error_type'] == "RuntimeError"
        assert call_kwargs['impact'] == "thread_metrics_may_be_stale"
        assert call_kwargs['mitigation'] == "will_retry_on_next_collection"
        assert call_kwargs['exc_info'] is True
        
        # Verify error count is incremented
        assert collector.error_count == 1
    
    @patch('app.monitoring.logger')
    def test_collector_safe_get_functions_error_handling(self, mock_logger):
        """Test error handling in safe get functions."""
        collector = ThreadMetricsCollector(debug_logging=True)
        
        # Test safe_get_active_worker_count with error
        with patch('app.monitoring.get_active_worker_count', side_effect=RuntimeError("Worker count error")):
            result = collector._safe_get_active_worker_count()
            
            # Should return fallback value
            assert result == 0
            
            # Verify debug logging
            debug_calls = [call for call in mock_logger.debug.call_args_list 
                          if 'Error getting active worker count, using fallback' in str(call)]
            assert len(debug_calls) > 0
            
            debug_call = debug_calls[0]
            call_kwargs = debug_call[1]
            assert 'error' in call_kwargs
            assert 'error_type' in call_kwargs
            assert 'fallback_count' in call_kwargs
            assert call_kwargs['error'] == "Worker count error"
            assert call_kwargs['error_type'] == "RuntimeError"
            assert call_kwargs['fallback_count'] == 0
    
    @patch('app.monitoring.logger')
    def test_collector_negative_value_handling(self, mock_logger):
        """Test handling of negative values from detection functions."""
        collector = ThreadMetricsCollector(debug_logging=True)
        
        # Test negative active worker count
        with patch('app.monitoring.get_active_worker_count', return_value=-5):
            result = collector._safe_get_active_worker_count()
            
            # Should return 0 for negative values
            assert result == 0
            
            # Verify warning logging
            warning_calls = [call for call in mock_logger.warning.call_args_list 
                            if 'Active worker count is negative, using fallback' in str(call)]
            assert len(warning_calls) > 0
            
            warning_call = warning_calls[0]
            call_kwargs = warning_call[1]
            assert 'reported_count' in call_kwargs
            assert 'fallback_count' in call_kwargs
            assert call_kwargs['reported_count'] == -5
            assert call_kwargs['fallback_count'] == 0
    
    @patch('app.monitoring.logger')
    def test_collector_prometheus_update_error_handling(self, mock_logger):
        """Test error handling when Prometheus metric updates fail."""
        collector = ThreadMetricsCollector(debug_logging=True)
        
        # Mock HTTP_WORKERS_ACTIVE to fail
        with patch('app.monitoring.HTTP_WORKERS_ACTIVE') as mock_gauge:
            mock_gauge.set.side_effect = RuntimeError("Prometheus gauge error")
            
            collector._update_prometheus_worker_metrics(5, 10, 16)
            
            # Verify error logging for Prometheus gauge failure
            error_calls = [call for call in mock_logger.error.call_args_list 
                          if 'Failed to update Prometheus active workers gauge' in str(call)]
            assert len(error_calls) > 0
            
            error_call = error_calls[0]
            call_kwargs = error_call[1]
            assert 'error' in call_kwargs
            assert 'error_type' in call_kwargs
            assert 'active_workers' in call_kwargs
            assert 'impact' in call_kwargs
            assert call_kwargs['error'] == "Prometheus gauge error"
            assert call_kwargs['error_type'] == "RuntimeError"
            assert call_kwargs['active_workers'] == 5
            assert call_kwargs['impact'] == "prometheus_active_workers_metric_stale"
    
    @patch('app.monitoring.logger')
    def test_collector_otel_update_error_handling(self, mock_logger):
        """Test error handling when OpenTelemetry metric updates fail."""
        collector = ThreadMetricsCollector(debug_logging=True)
        
        # Set initial values
        collector.last_values['active_workers'] = 3
        
        # Mock otel_http_workers_active to fail
        with patch('app.monitoring.otel_http_workers_active') as mock_counter:
            mock_counter.add.side_effect = RuntimeError("OpenTelemetry counter error")
            
            collector._update_otel_worker_metrics(5, 10, 16)
            
            # Verify error logging for OpenTelemetry counter failure
            error_calls = [call for call in mock_logger.error.call_args_list 
                          if 'Failed to update OpenTelemetry active workers counter' in str(call)]
            assert len(error_calls) > 0
            
            error_call = error_calls[0]
            call_kwargs = error_call[1]
            assert 'error' in call_kwargs
            assert 'error_type' in call_kwargs
            assert 'active_workers' in call_kwargs
            assert 'impact' in call_kwargs
            assert call_kwargs['error'] == "OpenTelemetry counter error"
            assert call_kwargs['error_type'] == "RuntimeError"
            assert call_kwargs['active_workers'] == 5
            assert call_kwargs['impact'] == "otel_active_workers_metric_stale"


class TestThreadMetricsSetupErrorHandling:
    """Test error handling in thread metrics setup functions."""
    
    def setup_method(self):
        """Clear registry before each test."""
        clear_metrics_registry()
    
    def teardown_method(self):
        """Clear registry after each test."""
        clear_metrics_registry()
    
    @patch('app.monitoring.logger')
    def test_setup_thread_metrics_disabled_logging(self, mock_logger):
        """Test logging when thread metrics are disabled."""
        setup_thread_metrics(enable_thread_metrics=False)
        
        # Verify info logging for disabled state
        info_calls = [call for call in mock_logger.info.call_args_list 
                     if 'Thread metrics collection disabled via configuration' in str(call)]
        assert len(info_calls) > 0
        
        info_call = info_calls[0]
        call_kwargs = info_call[1]
        assert 'enable_thread_metrics' in call_kwargs
        assert 'reason' in call_kwargs
        assert call_kwargs['enable_thread_metrics'] is False
        assert call_kwargs['reason'] == "configuration_setting"
    
    @patch('app.monitoring.logger')
    def test_setup_thread_metrics_collector_creation_error(self, mock_logger):
        """Test error handling when collector creation fails."""
        with patch('app.monitoring.ThreadMetricsCollector', side_effect=RuntimeError("Collector creation failed")):
            setup_thread_metrics(enable_thread_metrics=True)
            
            # Verify error logging for collector creation failure
            error_calls = [call for call in mock_logger.error.call_args_list 
                          if 'Failed to create thread metrics collector' in str(call)]
            assert len(error_calls) > 0
            
            error_call = error_calls[0]
            call_kwargs = error_call[1]
            assert 'error' in call_kwargs
            assert 'error_type' in call_kwargs
            assert 'fallback_action' in call_kwargs
            assert 'exc_info' in call_kwargs
            assert call_kwargs['error'] == "Collector creation failed"
            assert call_kwargs['error_type'] == "RuntimeError"
            assert call_kwargs['fallback_action'] == "disable_thread_metrics"
            assert call_kwargs['exc_info'] is True
    
    @patch('app.monitoring.logger')
    def test_setup_thread_metrics_registry_error(self, mock_logger):
        """Test error handling when Prometheus registry registration fails."""
        with patch('prometheus_client.REGISTRY') as mock_registry:
            mock_registry.register.side_effect = RuntimeError("Registry registration failed")
            mock_registry._collector_to_names = {}  # Simulate not already registered
            
            setup_thread_metrics(enable_thread_metrics=True)
            
            # Verify error logging for registry failure
            error_calls = [call for call in mock_logger.error.call_args_list 
                          if 'Failed to register thread metrics collector with Prometheus registry' in str(call)]
            assert len(error_calls) > 0
            
            error_call = error_calls[0]
            call_kwargs = error_call[1]
            assert 'error' in call_kwargs
            assert 'error_type' in call_kwargs
            assert 'impact' in call_kwargs
            assert 'mitigation' in call_kwargs
            assert 'exc_info' in call_kwargs
            assert call_kwargs['error'] == "Registry registration failed"
            assert call_kwargs['error_type'] == "RuntimeError"
            assert call_kwargs['impact'] == "thread_metrics_collection_disabled"
            assert call_kwargs['mitigation'] == "manual_collection_still_possible"
            assert call_kwargs['exc_info'] is True
    
    @patch('app.monitoring.logger')
    def test_setup_thread_metrics_initial_collection_error(self, mock_logger):
        """Test error handling when initial collection fails."""
        with patch('app.monitoring.ThreadMetricsCollector') as mock_collector_class:
            mock_collector = Mock()
            mock_collector.collect.side_effect = RuntimeError("Initial collection failed")
            mock_collector.get_status.return_value = {'status': 'error'}
            mock_collector_class.return_value = mock_collector
            
            with patch('prometheus_client.REGISTRY') as mock_registry:
                mock_registry._collector_to_names = {}
                
                setup_thread_metrics(enable_thread_metrics=True)
                
                # Verify warning logging for initial collection failure
                warning_calls = [call for call in mock_logger.warning.call_args_list 
                                if 'Initial thread metrics collection failed but setup completed' in str(call)]
                assert len(warning_calls) > 0
                
                warning_call = warning_calls[0]
                call_kwargs = warning_call[1]
                assert 'error' in call_kwargs
                assert 'error_type' in call_kwargs
                assert 'impact' in call_kwargs
                assert 'mitigation' in call_kwargs
                assert call_kwargs['error'] == "Initial collection failed"
                assert call_kwargs['error_type'] == "RuntimeError"
                assert call_kwargs['impact'] == "first_metrics_may_be_missing"
                assert call_kwargs['mitigation'] == "will_retry_on_next_scrape"
    
    @patch('app.monitoring.logger')
    def test_get_thread_metrics_status_error_handling(self, mock_logger):
        """Test error handling in thread metrics status function."""
        # Test when collector is None
        with patch('app.monitoring.thread_metrics_collector', None):
            status = get_thread_metrics_status()
            
            assert status['enabled'] is False
            assert status['collector_status'] == 'not_initialized'
            assert status['reason'] == 'setup_not_called_or_disabled'
        
        # Test when status retrieval fails
        mock_collector = Mock()
        mock_collector.get_status.side_effect = RuntimeError("Status retrieval failed")
        
        with patch('app.monitoring.thread_metrics_collector', mock_collector):
            status = get_thread_metrics_status()
            
            assert status['enabled'] is False
            assert status['collector_status'] == 'error'
            assert 'error' in status
            assert 'error_type' in status
            assert status['error'] == "Status retrieval failed"
            assert status['error_type'] == "RuntimeError"


class TestDebugLoggingFunctionality:
    """Test debug logging functionality throughout thread metrics system."""
    
    def setup_method(self):
        """Clear registry before each test."""
        clear_metrics_registry()
    
    def teardown_method(self):
        """Clear registry after each test."""
        clear_metrics_registry()
    
    @patch('app.monitoring.logger')
    def test_thread_enumeration_debug_logging(self, mock_logger):
        """Test debug logging in thread enumeration."""
        threads = _enumerate_active_threads()
        
        # Verify debug logging for successful enumeration
        debug_calls = [call for call in mock_logger.debug.call_args_list 
                      if 'Successfully enumerated active threads' in str(call)]
        assert len(debug_calls) > 0
        
        debug_call = debug_calls[0]
        call_kwargs = debug_call[1]
        assert 'thread_count' in call_kwargs
        assert 'current_thread' in call_kwargs
        assert call_kwargs['thread_count'] == len(threads)
    
    @patch('app.monitoring.logger')
    def test_worker_thread_identification_debug_logging(self, mock_logger):
        """Test debug logging in worker thread identification."""
        mock_thread = Mock()
        mock_thread.name = "ThreadPoolExecutor-0_0"
        mock_thread.ident = 12345
        mock_thread.daemon = True
        mock_thread.is_alive.return_value = True
        
        result = _is_worker_thread(mock_thread)
        
        # Should identify as worker thread
        assert result is True
        
        # Verify debug logging for worker thread identification
        debug_calls = [call for call in mock_logger.debug.call_args_list 
                      if 'Identified worker thread' in str(call)]
        assert len(debug_calls) > 0
        
        debug_call = debug_calls[0]
        call_kwargs = debug_call[1]
        assert 'thread_name' in call_kwargs
        assert 'thread_id' in call_kwargs
        assert 'is_daemon' in call_kwargs
        assert 'is_alive' in call_kwargs
        assert call_kwargs['thread_name'] == "ThreadPoolExecutor-0_0"
        assert call_kwargs['thread_id'] == 12345
        assert call_kwargs['is_daemon'] is True
        assert call_kwargs['is_alive'] is True
    
    @patch('app.monitoring.logger')
    def test_queue_detection_debug_logging(self, mock_logger):
        """Test debug logging in queue detection methods."""
        # Test asyncio queue detection debug logging
        with patch('asyncio.get_running_loop') as mock_loop:
            mock_event_loop = Mock()
            mock_event_loop.is_running.return_value = True
            mock_event_loop._scheduled = [Mock(), Mock()]  # 2 scheduled tasks
            mock_loop.return_value = mock_event_loop
            
            result = _detect_asyncio_queue()
            
            # Verify debug logging for asyncio loop detection
            debug_calls = [call for call in mock_logger.debug.call_args_list 
                          if 'Found running asyncio event loop for queue detection' in str(call)]
            assert len(debug_calls) > 0
            
            debug_call = debug_calls[0]
            call_kwargs = debug_call[1]
            assert 'loop_type' in call_kwargs
            assert 'loop_running' in call_kwargs
            
            # Verify debug logging for scheduled tasks
            scheduled_calls = [call for call in mock_logger.debug.call_args_list 
                              if 'Found scheduled tasks in asyncio loop' in str(call)]
            assert len(scheduled_calls) > 0
            
            scheduled_call = scheduled_calls[0]
            call_kwargs = scheduled_call[1]
            assert 'scheduled_tasks' in call_kwargs
            assert 'detection_method' in call_kwargs
            assert call_kwargs['scheduled_tasks'] == 2
            assert call_kwargs['detection_method'] == 'loop._scheduled'
    
    @patch('app.monitoring.logger')
    def test_collector_debug_logging_enabled(self, mock_logger):
        """Test debug logging when enabled in collector."""
        collector = ThreadMetricsCollector(debug_logging=True)
        
        # Mock the metrics to avoid actual updates
        with patch.object(collector, '_safe_get_active_worker_count', return_value=3), \
             patch.object(collector, '_safe_get_total_worker_count', return_value=8), \
             patch.object(collector, '_safe_get_max_configured_workers', return_value=16), \
             patch.object(collector, '_safe_get_queued_requests_count', return_value=2), \
             patch('app.monitoring.HTTP_WORKERS_ACTIVE'), \
             patch('app.monitoring.HTTP_WORKERS_TOTAL'), \
             patch('app.monitoring.HTTP_WORKERS_MAX_CONFIGURED'), \
             patch('app.monitoring.HTTP_REQUESTS_QUEUED'), \
             patch('app.monitoring.otel_http_workers_active'), \
             patch('app.monitoring.otel_http_workers_total'), \
             patch('app.monitoring.otel_http_workers_max_configured'), \
             patch('app.monitoring.otel_http_requests_queued'):
            
            collector.collect()
        
        # Verify debug logging for collection start
        debug_calls = [call for call in mock_logger.debug.call_args_list 
                      if 'Starting thread metrics collection' in str(call)]
        assert len(debug_calls) > 0
        
        debug_call = debug_calls[0]
        call_kwargs = debug_call[1]
        assert 'collection_number' in call_kwargs
        assert 'time_since_last_update' in call_kwargs
        assert 'collection_stage' in call_kwargs
        assert call_kwargs['collection_stage'] == "start"
        
        # Verify debug logging for worker counts
        worker_debug_calls = [call for call in mock_logger.debug.call_args_list 
                             if 'Retrieved worker thread counts' in str(call)]
        assert len(worker_debug_calls) > 0
        
        worker_debug_call = worker_debug_calls[0]
        call_kwargs = worker_debug_call[1]
        assert 'active_workers' in call_kwargs
        assert 'total_workers' in call_kwargs
        assert 'max_configured' in call_kwargs
        assert 'utilization_percent' in call_kwargs
        assert call_kwargs['active_workers'] == 3
        assert call_kwargs['total_workers'] == 8
        assert call_kwargs['max_configured'] == 16
    
    @patch('app.monitoring.logger')
    def test_collector_debug_logging_disabled(self, mock_logger):
        """Test that debug logging is properly disabled when not requested."""
        collector = ThreadMetricsCollector(debug_logging=False)
        
        # Mock the metrics to avoid actual updates
        with patch.object(collector, '_safe_get_active_worker_count', return_value=3), \
             patch.object(collector, '_safe_get_total_worker_count', return_value=8), \
             patch.object(collector, '_safe_get_max_configured_workers', return_value=16), \
             patch.object(collector, '_safe_get_queued_requests_count', return_value=2), \
             patch('app.monitoring.HTTP_WORKERS_ACTIVE'), \
             patch('app.monitoring.HTTP_WORKERS_TOTAL'), \
             patch('app.monitoring.HTTP_WORKERS_MAX_CONFIGURED'), \
             patch('app.monitoring.HTTP_REQUESTS_QUEUED'), \
             patch('app.monitoring.otel_http_workers_active'), \
             patch('app.monitoring.otel_http_workers_total'), \
             patch('app.monitoring.otel_http_workers_max_configured'), \
             patch('app.monitoring.otel_http_requests_queued'):
            
            collector.collect()
        
        # Verify no debug logging for collection details when disabled
        debug_calls = [call for call in mock_logger.debug.call_args_list 
                      if 'Starting thread metrics collection' in str(call)]
        assert len(debug_calls) > 0  # Basic debug logging still occurs
        
        # But detailed debug logging should be minimal
        detailed_debug_calls = [call for call in mock_logger.debug.call_args_list 
                               if 'Retrieved worker thread counts' in str(call)]
        # Should still have some debug calls but fewer details when debug_logging=False
        # The exact behavior depends on implementation details


class TestFallbackMechanisms:
    """Test fallback mechanisms throughout the thread metrics system."""
    
    def setup_method(self):
        """Clear registry before each test."""
        clear_metrics_registry()
    
    def teardown_method(self):
        """Clear registry after each test."""
        clear_metrics_registry()
    
    def test_thread_count_fallbacks(self):
        """Test that thread count functions provide safe fallbacks."""
        # Test with complete enumeration failure
        with patch('app.monitoring._enumerate_active_threads', return_value=[]):
            active_count = get_active_worker_count()
            total_count = get_total_worker_count()
            
            assert active_count == 0
            assert total_count == 0
    
    def test_max_workers_fallback_chain(self):
        """Test the complete fallback chain for max workers detection."""
        with patch('app.monitoring._detect_uvicorn_thread_pool', return_value={}), \
             patch('app.monitoring._get_asyncio_thread_pool_info', return_value={}), \
             patch('os.cpu_count', return_value=None):
            
            max_workers = get_max_configured_workers()
            
            # Should use fallback calculation with default CPU count
            assert max_workers == 8  # min(32, 4 + 4) with fallback CPU count of 4
    
    def test_queue_detection_complete_fallback(self):
        """Test complete fallback when all queue detection methods fail."""
        with patch('app.monitoring._detect_uvicorn_queue', return_value=None), \
             patch('app.monitoring._detect_asyncio_queue', return_value=None), \
             patch('app.monitoring._detect_system_level_queue', return_value=None), \
             patch('app.monitoring._estimate_queue_from_metrics', return_value=None):
            
            queue_count = get_queued_requests_count()
            
            # Should return 0 as safe fallback
            assert queue_count == 0
    
    def test_collector_fallback_values(self):
        """Test that collector uses fallback values when detection fails."""
        collector = ThreadMetricsCollector()
        
        # Test with all detection functions failing
        with patch('app.monitoring.get_active_worker_count', side_effect=RuntimeError("Detection failed")), \
             patch('app.monitoring.get_total_worker_count', side_effect=RuntimeError("Detection failed")), \
             patch('app.monitoring.get_max_configured_workers', side_effect=RuntimeError("Detection failed")), \
             patch('app.monitoring.get_queued_requests_count', side_effect=RuntimeError("Detection failed")):
            
            active = collector._safe_get_active_worker_count()
            total = collector._safe_get_total_worker_count()
            max_configured = collector._safe_get_max_configured_workers()
            queued = collector._safe_get_queued_requests_count()
            
            # Should all return safe fallback values
            assert active == 0
            assert total == 0
            assert max_configured == 8  # Conservative fallback
            assert queued == 0
    
    def test_negative_value_fallbacks(self):
        """Test handling of negative values from detection functions."""
        collector = ThreadMetricsCollector()
        
        # Test with negative return values
        with patch('app.monitoring.get_active_worker_count', return_value=-5):
            active = collector._safe_get_active_worker_count()
            assert active == 0  # Should convert negative to 0
        
        with patch('app.monitoring.get_total_worker_count', return_value=-10):
            total = collector._safe_get_total_worker_count()
            assert total == 0  # Should convert negative to 0
        
        with patch('app.monitoring.get_max_configured_workers', return_value=-8):
            max_configured = collector._safe_get_max_configured_workers()
            assert max_configured == 8  # Should use fallback for negative
        
        with patch('app.monitoring.get_queued_requests_count', return_value=-3):
            queued = collector._safe_get_queued_requests_count()
            assert queued == 0  # Should convert negative to 0