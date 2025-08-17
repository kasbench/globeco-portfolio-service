"""
Unit tests for request queue depth detection functionality.

Tests the queue detection functions in app.monitoring module including
fallback mechanisms and error handling.
"""

import pytest
import threading
import asyncio
from unittest.mock import Mock, patch, MagicMock, mock_open
from concurrent.futures import ThreadPoolExecutor

import app.monitoring
from app.monitoring import (
    get_queued_requests_count,
    _detect_request_queue_depth,
    _detect_uvicorn_queue,
    _detect_asyncio_queue,
    _detect_system_level_queue,
    _estimate_queue_from_metrics,
    HTTP_REQUESTS_IN_FLIGHT,
    get_active_worker_count,
    get_total_worker_count
)


class TestQueueDetection:
    """Test suite for queue detection functionality."""
    
    def test_get_queued_requests_count_success(self):
        """Test successful queue detection using first available method."""
        with patch.object(app.monitoring, '_detect_uvicorn_queue', return_value=5), \
             patch.object(app.monitoring, '_detect_asyncio_queue', return_value=None), \
             patch.object(app.monitoring, '_detect_system_level_queue', return_value=None), \
             patch.object(app.monitoring, '_estimate_queue_from_metrics', return_value=None):
            result = get_queued_requests_count()
            assert result == 5
    
    def test_get_queued_requests_count_fallback_chain(self):
        """Test fallback chain when first methods fail."""
        with patch.object(app.monitoring, '_detect_uvicorn_queue', return_value=None), \
             patch.object(app.monitoring, '_detect_asyncio_queue', return_value=None), \
             patch.object(app.monitoring, '_detect_system_level_queue', return_value=None), \
             patch.object(app.monitoring, '_estimate_queue_from_metrics', return_value=3):
            result = get_queued_requests_count()
            assert result == 3
    
    def test_get_queued_requests_count_all_methods_fail(self):
        """Test fallback to 0 when all detection methods fail."""
        with patch.object(app.monitoring, '_detect_uvicorn_queue', return_value=None), \
             patch.object(app.monitoring, '_detect_asyncio_queue', return_value=None), \
             patch.object(app.monitoring, '_detect_system_level_queue', return_value=None), \
             patch.object(app.monitoring, '_estimate_queue_from_metrics', return_value=None):
            result = get_queued_requests_count()
            assert result == 0
    
    def test_get_queued_requests_count_exception_handling(self):
        """Test graceful handling of exceptions in queue detection."""
        with patch.object(app.monitoring, '_detect_uvicorn_queue', side_effect=Exception("Test error")), \
             patch.object(app.monitoring, '_detect_asyncio_queue', return_value=2), \
             patch.object(app.monitoring, '_detect_system_level_queue', return_value=None), \
             patch.object(app.monitoring, '_estimate_queue_from_metrics', return_value=None):
            result = get_queued_requests_count()
            assert result == 2
    
    def test_get_queued_requests_count_negative_values_ignored(self):
        """Test that negative queue values are ignored."""
        with patch.object(app.monitoring, '_detect_uvicorn_queue', return_value=-1), \
             patch.object(app.monitoring, '_detect_asyncio_queue', return_value=4), \
             patch.object(app.monitoring, '_detect_system_level_queue', return_value=None), \
             patch.object(app.monitoring, '_estimate_queue_from_metrics', return_value=None):
            result = get_queued_requests_count()
            assert result == 4
    
    def test_detect_request_queue_depth_delegates_correctly(self):
        """Test that _detect_request_queue_depth delegates to get_queued_requests_count."""
        with patch.object(app.monitoring, 'get_queued_requests_count', return_value=7) as mock_get:
            result = _detect_request_queue_depth()
            assert result == 7
            mock_get.assert_called_once()


class TestUvicornQueueDetection:
    """Test suite for Uvicorn queue detection."""
    
    def test_detect_uvicorn_queue_no_servers(self):
        """Test behavior when no Uvicorn servers are found."""
        with patch('gc.get_objects', return_value=[]):
            result = _detect_uvicorn_queue()
            assert result is None
    
    def test_detect_uvicorn_queue_with_qsize_attribute(self):
        """Test detection when server has queue with qsize() method."""
        # Create mock server with queue
        mock_queue = Mock()
        mock_queue.qsize.return_value = 3
        
        mock_server = Mock()
        mock_server.__class__.__name__ = 'Server'
        mock_server.__class__.__module__ = 'uvicorn.server'
        mock_server.request_queue = mock_queue
        
        with patch('gc.get_objects', return_value=[mock_server]):
            result = _detect_uvicorn_queue()
            assert result == 3
    
    def test_detect_uvicorn_queue_with_len_attribute(self):
        """Test detection when server has queue with __len__ method."""
        # Create mock server with queue
        mock_queue = [1, 2, 3, 4]  # List with 4 items
        
        mock_server = Mock()
        mock_server.__class__.__name__ = 'Server'
        mock_server.__class__.__module__ = 'uvicorn.server'
        # Remove the default mock attributes that might interfere
        del mock_server.request_queue
        del mock_server.connection_queue
        del mock_server.backlog
        del mock_server._request_queue
        del mock_server._pending_requests
        mock_server.pending_requests = mock_queue
        
        with patch('gc.get_objects', return_value=[mock_server]):
            result = _detect_uvicorn_queue()
            assert result == 4
    
    def test_detect_uvicorn_queue_socket_inspection(self):
        """Test socket backlog inspection when queue attributes not found."""
        # Create mock server with socket
        mock_socket = Mock()
        mock_socket.getsockopt.return_value = 2
        
        mock_server_obj = Mock()
        mock_server_obj.sockets = [mock_socket]
        
        mock_server = Mock()
        mock_server.__class__.__name__ = 'Server'
        mock_server.__class__.__module__ = 'uvicorn.server'
        # Remove the default mock attributes that might interfere
        del mock_server.request_queue
        del mock_server.pending_requests
        del mock_server.connection_queue
        del mock_server.backlog
        del mock_server._request_queue
        del mock_server._pending_requests
        mock_server.server = mock_server_obj
        
        with patch('gc.get_objects', return_value=[mock_server]):
            result = _detect_uvicorn_queue()
            assert result == 2
    
    def test_detect_uvicorn_queue_exception_handling(self):
        """Test graceful handling of exceptions during Uvicorn queue detection."""
        with patch('gc.get_objects', side_effect=Exception("GC error")):
            result = _detect_uvicorn_queue()
            assert result is None
    
    def test_detect_uvicorn_queue_non_uvicorn_server_ignored(self):
        """Test that non-Uvicorn servers are ignored."""
        mock_server = Mock()
        mock_server.__class__.__name__ = 'Server'
        mock_server.__class__.__module__ = 'other.server'  # Not uvicorn
        
        with patch('gc.get_objects', return_value=[mock_server]):
            result = _detect_uvicorn_queue()
            assert result is None


class TestAsyncIOQueueDetection:
    """Test suite for AsyncIO queue detection."""
    
    def test_detect_asyncio_queue_no_running_loop(self):
        """Test behavior when no asyncio loop is running."""
        with patch('asyncio.get_running_loop', side_effect=RuntimeError("No loop")):
            result = _detect_asyncio_queue()
            assert result is None
    
    def test_detect_asyncio_queue_with_scheduled_tasks(self):
        """Test detection of scheduled asyncio tasks."""
        mock_loop = Mock()
        mock_loop._scheduled = [1, 2, 3]  # 3 scheduled tasks
        mock_loop._ready = []
        # Remove default executor to avoid interference
        del mock_loop._default_executor
        
        with patch('asyncio.get_running_loop', return_value=mock_loop):
            result = _detect_asyncio_queue()
            assert result == 3
    
    def test_detect_asyncio_queue_with_executor_queue(self):
        """Test detection of thread pool executor queue."""
        mock_work_queue = Mock()
        mock_work_queue.qsize.return_value = 5
        
        mock_executor = Mock()
        mock_executor._work_queue = mock_work_queue
        
        mock_loop = Mock()
        mock_loop._scheduled = []
        mock_loop._ready = []
        mock_loop._default_executor = mock_executor
        
        with patch('asyncio.get_running_loop', return_value=mock_loop):
            result = _detect_asyncio_queue()
            assert result == 5
    
    def test_detect_asyncio_queue_combined_sources(self):
        """Test detection combining multiple queue sources."""
        mock_work_queue = Mock()
        mock_work_queue.qsize.return_value = 2
        
        mock_executor = Mock()
        mock_executor._work_queue = mock_work_queue
        
        mock_loop = Mock()
        mock_loop._scheduled = [1, 2, 3]  # 3 scheduled tasks
        mock_loop._ready = [1]  # 1 ready task (not counted in queue)
        mock_loop._default_executor = mock_executor
        
        with patch('asyncio.get_running_loop', return_value=mock_loop):
            result = _detect_asyncio_queue()
            assert result == 5  # 3 scheduled + 2 executor queue
    
    def test_detect_asyncio_queue_no_queue_found(self):
        """Test behavior when no queue information is found."""
        mock_loop = Mock()
        # No _scheduled, _ready, or _default_executor attributes
        del mock_loop._scheduled
        del mock_loop._ready
        del mock_loop._default_executor
        
        with patch('asyncio.get_running_loop', return_value=mock_loop):
            result = _detect_asyncio_queue()
            assert result is None
    
    def test_detect_asyncio_queue_exception_handling(self):
        """Test graceful handling of exceptions during AsyncIO queue detection."""
        with patch('asyncio.get_running_loop', side_effect=Exception("Loop error")):
            result = _detect_asyncio_queue()
            assert result is None


class TestSystemLevelQueueDetection:
    """Test suite for system-level queue detection."""
    
    def test_detect_system_level_queue_not_implemented(self):
        """Test that system-level detection returns None (not fully implemented)."""
        result = _detect_system_level_queue()
        assert result is None
    
    def test_detect_system_level_queue_exception_handling(self):
        """Test graceful handling of exceptions in system-level detection."""
        with patch('os.getpid', side_effect=Exception("System error")):
            result = _detect_system_level_queue()
            assert result is None
    
    def test_detect_system_level_queue_proc_net_tcp_access(self):
        """Test attempt to access /proc/net/tcp on Linux systems."""
        mock_file_content = "sl  local_address rem_address   st tx_queue rx_queue\n"
        
        with patch('os.path.exists', return_value=True), \
             patch('builtins.open', mock_open(read_data=mock_file_content)):
            result = _detect_system_level_queue()
            # Should still return None as parsing is not implemented
            assert result is None


class TestMetricsBasedQueueEstimation:
    """Test suite for metrics-based queue estimation."""
    
    def test_estimate_queue_from_metrics_basic_estimation(self):
        """Test basic queue estimation from requests vs workers."""
        with patch.object(app.monitoring, 'get_active_worker_count', return_value=3), \
             patch.object(app.monitoring, 'get_total_worker_count', return_value=5):
            
            # Mock HTTP_REQUESTS_IN_FLIGHT to return 7
            mock_gauge = Mock()
            mock_gauge._value._value = 7
            
            with patch.object(app.monitoring, 'HTTP_REQUESTS_IN_FLIGHT', mock_gauge):
                result = _estimate_queue_from_metrics()
                assert result == 4  # 7 requests - 3 active workers = 4 queued
    
    def test_estimate_queue_from_metrics_no_queue_detected(self):
        """Test when no queue is estimated from metrics."""
        with patch.object(app.monitoring, 'get_active_worker_count', return_value=5), \
             patch.object(app.monitoring, 'get_total_worker_count', return_value=8):
            
            # Mock HTTP_REQUESTS_IN_FLIGHT to return 3 (less than active workers)
            mock_gauge = Mock()
            mock_gauge._value._value = 3
            
            with patch.object(app.monitoring, 'HTTP_REQUESTS_IN_FLIGHT', mock_gauge):
                result = _estimate_queue_from_metrics()
                assert result == 0  # No queue estimated
    
    def test_estimate_queue_from_metrics_saturation_based(self):
        """Test saturation-based queue estimation."""
        with patch.object(app.monitoring, 'get_active_worker_count', return_value=5), \
             patch.object(app.monitoring, 'get_total_worker_count', return_value=5):  # All workers active
            
            # Mock HTTP_REQUESTS_IN_FLIGHT to return 8 (more than workers)
            mock_gauge = Mock()
            mock_gauge._value._value = 8
            
            with patch.object(app.monitoring, 'HTTP_REQUESTS_IN_FLIGHT', mock_gauge):
                result = _estimate_queue_from_metrics()
                assert result == 3  # 8 requests - 5 active workers = 3 queued
    
    def test_estimate_queue_from_metrics_capped_at_reasonable_maximum(self):
        """Test that queue estimation is capped at reasonable maximum."""
        with patch.object(app.monitoring, 'get_active_worker_count', return_value=2), \
             patch.object(app.monitoring, 'get_total_worker_count', return_value=4):
            
            # Mock HTTP_REQUESTS_IN_FLIGHT to return very high value
            mock_gauge = Mock()
            mock_gauge._value._value = 100
            
            with patch.object(app.monitoring, 'HTTP_REQUESTS_IN_FLIGHT', mock_gauge):
                result = _estimate_queue_from_metrics()
                # Should be capped at 2 * total_workers = 8
                assert result == 8
    
    def test_estimate_queue_from_metrics_gauge_access_error(self):
        """Test handling of errors when accessing gauge values."""
        with patch.object(app.monitoring, 'get_active_worker_count', return_value=3), \
             patch.object(app.monitoring, 'get_total_worker_count', return_value=5):
            
            # Create a mock gauge that raises exception when _value._value is accessed
            class MockGauge:
                @property
                def _value(self):
                    class MockValue:
                        @property
                        def _value(self):
                            raise Exception("Gauge error")
                    return MockValue()
                
                def get(self):
                    raise Exception("Gauge error")
            
            mock_gauge = MockGauge()
            
            with patch.object(app.monitoring, 'HTTP_REQUESTS_IN_FLIGHT', mock_gauge):
                result = _estimate_queue_from_metrics()
                # Should handle error gracefully and return 0
                assert result == 0
    
    def test_estimate_queue_from_metrics_exception_handling(self):
        """Test graceful handling of exceptions during metrics estimation."""
        with patch.object(app.monitoring, 'get_active_worker_count', side_effect=Exception("Worker count error")):
            result = _estimate_queue_from_metrics()
            assert result is None





class TestQueueDetectionIntegration:
    """Integration tests for queue detection functionality."""
    
    def test_queue_detection_with_real_asyncio_loop(self):
        """Test queue detection with a real asyncio event loop."""
        async def test_with_loop():
            # This test runs with a real asyncio loop
            result = _detect_asyncio_queue()
            # Should return None or a valid number, not raise an exception
            assert result is None or isinstance(result, int)
        
        # Run the test with asyncio
        asyncio.run(test_with_loop())
    
    def test_queue_detection_error_resilience(self):
        """Test that queue detection is resilient to various error conditions."""
        # Test with all detection methods raising different types of exceptions
        with patch.object(app.monitoring, '_detect_uvicorn_queue', side_effect=ValueError("Value error")), \
             patch.object(app.monitoring, '_detect_asyncio_queue', side_effect=RuntimeError("Runtime error")), \
             patch.object(app.monitoring, '_detect_system_level_queue', side_effect=OSError("OS error")), \
             patch.object(app.monitoring, '_estimate_queue_from_metrics', side_effect=AttributeError("Attribute error")):
            
            result = get_queued_requests_count()
            assert result == 0  # Should fallback gracefully
    
    def test_queue_detection_performance(self):
        """Test that queue detection completes quickly."""
        import time
        
        start_time = time.time()
        result = get_queued_requests_count()
        end_time = time.time()
        
        # Queue detection should complete in reasonable time (< 100ms)
        assert end_time - start_time < 0.1
        assert isinstance(result, int)
        assert result >= 0


if __name__ == '__main__':
    pytest.main([__file__])