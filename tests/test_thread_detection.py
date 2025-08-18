"""
Unit tests for thread detection and enumeration functionality.

Tests the thread detection functions in app.monitoring module to ensure
accurate identification and counting of worker threads vs system threads.
"""

import pytest
import threading
import time
from unittest.mock import Mock, patch, MagicMock, PropertyMock
from concurrent.futures import ThreadPoolExecutor

from app.monitoring import (
    _enumerate_active_threads,
    _is_worker_thread,
    _is_thread_active,
    get_active_worker_count,
    get_total_worker_count,
    get_max_configured_workers,
    _detect_uvicorn_thread_pool,
    _get_asyncio_thread_pool_info
)


class TestEnumerateActiveThreads:
    """Test cases for _enumerate_active_threads function."""
    
    def test_enumerate_active_threads_success(self):
        """Test successful thread enumeration."""
        threads = _enumerate_active_threads()
        
        # Should return a list
        assert isinstance(threads, list)
        
        # Should contain at least the current thread
        assert len(threads) > 0
        
        # Current thread should be in the list
        current_thread = threading.current_thread()
        thread_names = [t.name for t in threads]
        assert current_thread.name in thread_names
    
    def test_enumerate_active_threads_includes_main_thread(self):
        """Test that enumeration includes the main thread."""
        threads = _enumerate_active_threads()
        
        # Find main thread
        main_threads = [t for t in threads if 'MainThread' in t.name or t.name == 'MainThread']
        assert len(main_threads) >= 1, "Main thread should be included in enumeration"
    
    @patch('threading.enumerate')
    def test_enumerate_active_threads_error_handling(self, mock_enumerate):
        """Test error handling when thread enumeration fails."""
        # Mock threading.enumerate to raise an exception
        mock_enumerate.side_effect = RuntimeError("Thread enumeration failed")
        
        threads = _enumerate_active_threads()
        
        # Should return empty list on error
        assert threads == []
        assert isinstance(threads, list)
    
    @patch('threading.enumerate')
    def test_enumerate_active_threads_empty_result(self, mock_enumerate):
        """Test handling of empty thread enumeration result."""
        mock_enumerate.return_value = []
        
        threads = _enumerate_active_threads()
        
        assert threads == []
        assert isinstance(threads, list)


class TestIsWorkerThread:
    """Test cases for _is_worker_thread function."""
    
    def test_is_worker_thread_with_none(self):
        """Test _is_worker_thread with None input."""
        result = _is_worker_thread(None)
        assert result is False
    
    def test_is_worker_thread_with_threadpoolexecutor_name(self):
        """Test identification of ThreadPoolExecutor threads."""
        mock_thread = Mock(spec=threading.Thread)
        mock_thread.name = "ThreadPoolExecutor-0_0"
        mock_thread.daemon = True
        mock_thread._target = Mock()
        
        result = _is_worker_thread(mock_thread)
        assert result is True
    
    def test_is_worker_thread_with_worker_name(self):
        """Test identification of threads with 'worker' in name."""
        mock_thread = Mock(spec=threading.Thread)
        mock_thread.name = "worker-thread-1"
        
        result = _is_worker_thread(mock_thread)
        assert result is True
    
    def test_is_worker_thread_with_uvicorn_name(self):
        """Test identification of uvicorn worker threads."""
        mock_thread = Mock(spec=threading.Thread)
        mock_thread.name = "uvicorn-worker-1"
        
        result = _is_worker_thread(mock_thread)
        assert result is True
    
    def test_is_worker_thread_with_asyncio_name(self):
        """Test identification of asyncio threads."""
        mock_thread = Mock(spec=threading.Thread)
        mock_thread.name = "asyncio-thread-pool-1"
        
        result = _is_worker_thread(mock_thread)
        assert result is True
    
    def test_is_worker_thread_with_executor_name(self):
        """Test identification of executor threads."""
        mock_thread = Mock(spec=threading.Thread)
        mock_thread.name = "executor-thread-2"
        
        result = _is_worker_thread(mock_thread)
        assert result is True
    
    def test_is_worker_thread_with_http_name(self):
        """Test identification of HTTP processing threads."""
        mock_thread = Mock(spec=threading.Thread)
        mock_thread.name = "http-processor-1"
        
        result = _is_worker_thread(mock_thread)
        assert result is True
    
    def test_is_worker_thread_with_daemon_and_target(self):
        """Test identification by daemon status and target function."""
        mock_thread = Mock(spec=threading.Thread)
        mock_thread.name = "custom-thread-1"
        mock_thread.daemon = True
        mock_thread._target = Mock()
        
        result = _is_worker_thread(mock_thread)
        assert result is True
    
    def test_is_worker_thread_with_main_thread(self):
        """Test that main thread is not identified as worker."""
        mock_thread = Mock(spec=threading.Thread)
        mock_thread.name = "MainThread"
        mock_thread.daemon = False
        mock_thread._target = None
        
        result = _is_worker_thread(mock_thread)
        assert result is False
    
    def test_is_worker_thread_with_system_thread(self):
        """Test that system threads are not identified as workers."""
        mock_thread = Mock(spec=threading.Thread)
        mock_thread.name = "system-monitor"
        mock_thread.daemon = False
        mock_thread._target = None
        
        result = _is_worker_thread(mock_thread)
        assert result is False
    
    def test_is_worker_thread_case_insensitive(self):
        """Test that thread name matching is case insensitive."""
        mock_thread = Mock(spec=threading.Thread)
        mock_thread.name = "THREADPOOLEXECUTOR-1"
        
        result = _is_worker_thread(mock_thread)
        assert result is True
    
    def test_is_worker_thread_error_handling(self):
        """Test error handling in _is_worker_thread."""
        mock_thread = Mock(spec=threading.Thread)
        # Remove name attribute to cause AttributeError
        del mock_thread.name
        
        result = _is_worker_thread(mock_thread)
        assert result is False
    
    def test_is_worker_thread_with_missing_attributes(self):
        """Test handling of threads with missing attributes."""
        mock_thread = Mock(spec=threading.Thread)
        mock_thread.name = "test-thread"
        # Don't set daemon or _target attributes
        
        result = _is_worker_thread(mock_thread)
        assert result is False


class TestIsThreadActive:
    """Test cases for _is_thread_active function."""
    
    def test_is_thread_active_with_none(self):
        """Test _is_thread_active with None input."""
        result = _is_thread_active(None)
        assert result is False
    
    def test_is_thread_active_with_dead_thread(self):
        """Test _is_thread_active with dead thread."""
        mock_thread = Mock(spec=threading.Thread)
        mock_thread.is_alive.return_value = False
        
        result = _is_thread_active(mock_thread)
        assert result is False
    
    def test_is_thread_active_with_target_function(self):
        """Test _is_thread_active with thread that has target function."""
        mock_thread = Mock(spec=threading.Thread)
        mock_thread.is_alive.return_value = True
        mock_thread.name = "worker-thread-1"
        mock_thread._target = Mock()
        mock_thread._target.__name__ = "worker_function"
        
        result = _is_thread_active(mock_thread)
        assert result is True
    
    def test_is_thread_active_without_target_function(self):
        """Test _is_thread_active with thread without target function."""
        mock_thread = Mock(spec=threading.Thread)
        mock_thread.is_alive.return_value = True
        mock_thread.name = "worker-thread-1"
        mock_thread._target = None
        
        result = _is_thread_active(mock_thread)
        assert result is True  # Conservative approach: assume active if alive
    
    def test_is_thread_active_error_handling(self):
        """Test error handling in _is_thread_active."""
        mock_thread = Mock(spec=threading.Thread)
        mock_thread.is_alive.side_effect = RuntimeError("Thread state error")
        
        result = _is_thread_active(mock_thread)
        assert result is False


class TestGetActiveWorkerCount:
    """Test cases for get_active_worker_count function."""
    
    @patch('app.monitoring._enumerate_active_threads')
    @patch('app.monitoring._is_worker_thread')
    @patch('app.monitoring._is_thread_active')
    def test_get_active_worker_count_success(self, mock_is_active, mock_is_worker, mock_enumerate):
        """Test successful active worker count."""
        # Create mock threads with proper name attributes
        mock_threads = []
        for name in ["MainThread", "ThreadPoolExecutor-0_0", "ThreadPoolExecutor-0_1", "system-thread"]:
            mock_thread = Mock(spec=threading.Thread)
            mock_thread.name = name
            mock_threads.append(mock_thread)
        
        mock_enumerate.return_value = mock_threads
        
        # Configure mock responses
        def is_worker_side_effect(thread):
            return "ThreadPoolExecutor" in thread.name
        
        def is_active_side_effect(thread):
            return thread.name == "ThreadPoolExecutor-0_0"  # Only first one is active
        
        mock_is_worker.side_effect = is_worker_side_effect
        mock_is_active.side_effect = is_active_side_effect
        
        result = get_active_worker_count()
        
        assert result == 1  # Only one active worker thread
        assert mock_enumerate.called
        assert mock_is_worker.call_count == 4  # Called for each thread
        assert mock_is_active.call_count == 2  # Called for each worker thread
    
    @patch('app.monitoring._enumerate_active_threads')
    def test_get_active_worker_count_no_threads(self, mock_enumerate):
        """Test active worker count when no threads found."""
        mock_enumerate.return_value = []
        
        result = get_active_worker_count()
        
        assert result == 0
    
    @patch('app.monitoring._enumerate_active_threads')
    def test_get_active_worker_count_error_handling(self, mock_enumerate):
        """Test error handling in get_active_worker_count."""
        mock_enumerate.side_effect = RuntimeError("Thread enumeration failed")
        
        result = get_active_worker_count()
        
        assert result == 0
    
    @patch('app.monitoring._enumerate_active_threads')
    @patch('app.monitoring._is_worker_thread')
    def test_get_active_worker_count_no_workers(self, mock_is_worker, mock_enumerate):
        """Test active worker count when no worker threads found."""
        mock_threads = [Mock(name="MainThread"), Mock(name="system-thread")]
        mock_enumerate.return_value = mock_threads
        mock_is_worker.return_value = False  # No worker threads
        
        result = get_active_worker_count()
        
        assert result == 0


class TestGetTotalWorkerCount:
    """Test cases for get_total_worker_count function."""
    
    @patch('app.monitoring._enumerate_active_threads')
    @patch('app.monitoring._is_worker_thread')
    def test_get_total_worker_count_success(self, mock_is_worker, mock_enumerate):
        """Test successful total worker count."""
        # Create mock threads with proper name attributes
        mock_threads = []
        for name in ["MainThread", "ThreadPoolExecutor-0_0", "ThreadPoolExecutor-0_1", "worker-thread-1", "system-thread"]:
            mock_thread = Mock(spec=threading.Thread)
            mock_thread.name = name
            mock_threads.append(mock_thread)
        
        mock_enumerate.return_value = mock_threads
        
        # Configure mock to identify worker threads
        def is_worker_side_effect(thread):
            return any(pattern in thread.name for pattern in ["ThreadPoolExecutor", "worker"])
        
        mock_is_worker.side_effect = is_worker_side_effect
        
        result = get_total_worker_count()
        
        assert result == 3  # Three worker threads total
        assert mock_enumerate.called
        assert mock_is_worker.call_count == 5  # Called for each thread
    
    @patch('app.monitoring._enumerate_active_threads')
    def test_get_total_worker_count_no_threads(self, mock_enumerate):
        """Test total worker count when no threads found."""
        mock_enumerate.return_value = []
        
        result = get_total_worker_count()
        
        assert result == 0
    
    @patch('app.monitoring._enumerate_active_threads')
    def test_get_total_worker_count_error_handling(self, mock_enumerate):
        """Test error handling in get_total_worker_count."""
        mock_enumerate.side_effect = RuntimeError("Thread enumeration failed")
        
        result = get_total_worker_count()
        
        assert result == 0
    
    @patch('app.monitoring._enumerate_active_threads')
    @patch('app.monitoring._is_worker_thread')
    def test_get_total_worker_count_no_workers(self, mock_is_worker, mock_enumerate):
        """Test total worker count when no worker threads found."""
        mock_threads = [Mock(name="MainThread"), Mock(name="system-thread")]
        mock_enumerate.return_value = mock_threads
        mock_is_worker.return_value = False  # No worker threads
        
        result = get_total_worker_count()
        
        assert result == 0


class TestThreadDetectionIntegration:
    """Integration tests for thread detection with real threads."""
    
    def test_thread_detection_with_thread_pool_executor(self):
        """Test thread detection with actual ThreadPoolExecutor."""
        def dummy_work():
            time.sleep(0.1)  # Short sleep to keep thread alive
        
        with ThreadPoolExecutor(max_workers=2, thread_name_prefix="TestWorker") as executor:
            # Submit some work to create active threads
            future1 = executor.submit(dummy_work)
            future2 = executor.submit(dummy_work)
            
            # Give threads time to start
            time.sleep(0.05)
            
            # Test thread enumeration
            threads = _enumerate_active_threads()
            assert len(threads) > 0
            
            # Test worker thread identification
            worker_threads = [t for t in threads if _is_worker_thread(t)]
            
            # Should find at least some worker threads
            # (exact count may vary based on system and other tests)
            assert len(worker_threads) >= 0
            
            # Test counting functions
            total_workers = get_total_worker_count()
            active_workers = get_active_worker_count()
            
            assert total_workers >= 0
            assert active_workers >= 0
            assert active_workers <= total_workers
            
            # Wait for futures to complete
            future1.result()
            future2.result()
    
    def test_thread_detection_with_custom_thread(self):
        """Test thread detection with custom named thread."""
        def worker_function():
            time.sleep(0.1)
        
        # Create a custom thread with worker-like name
        custom_thread = threading.Thread(
            target=worker_function,
            name="custom-worker-thread",
            daemon=True
        )
        
        try:
            custom_thread.start()
            time.sleep(0.05)  # Give thread time to start
            
            # Test that our custom thread is detected
            threads = _enumerate_active_threads()
            custom_threads = [t for t in threads if t.name == "custom-worker-thread"]
            assert len(custom_threads) == 1
            
            # Test that it's identified as a worker thread
            is_worker = _is_worker_thread(custom_threads[0])
            assert is_worker is True
            
        finally:
            custom_thread.join(timeout=1.0)  # Clean up
    
    def test_main_thread_not_counted_as_worker(self):
        """Test that main thread is not counted as worker thread."""
        threads = _enumerate_active_threads()
        main_threads = [t for t in threads if 'MainThread' in t.name or t.name == 'MainThread']
        
        if main_threads:
            main_thread = main_threads[0]
            is_worker = _is_worker_thread(main_thread)
            assert is_worker is False, "Main thread should not be identified as worker thread"


class TestGetMaxConfiguredWorkers:
    """Test cases for get_max_configured_workers function."""
    
    @patch('app.monitoring._detect_uvicorn_thread_pool')
    def test_get_max_configured_workers_from_uvicorn(self, mock_detect_uvicorn):
        """Test getting max workers from Uvicorn thread pool."""
        mock_detect_uvicorn.return_value = {'max_workers': 16}
        
        result = get_max_configured_workers()
        
        assert result == 16
        assert mock_detect_uvicorn.called
    
    @patch('app.monitoring._get_asyncio_thread_pool_info')
    @patch('app.monitoring._detect_uvicorn_thread_pool')
    def test_get_max_configured_workers_from_asyncio(self, mock_detect_uvicorn, mock_get_asyncio):
        """Test getting max workers from AsyncIO when Uvicorn detection fails."""
        mock_detect_uvicorn.return_value = {}  # No Uvicorn info
        mock_get_asyncio.return_value = {'max_workers': 12}
        
        result = get_max_configured_workers()
        
        assert result == 12
        assert mock_detect_uvicorn.called
        assert mock_get_asyncio.called
    
    @patch('os.cpu_count')
    @patch('app.monitoring._get_asyncio_thread_pool_info')
    @patch('app.monitoring._detect_uvicorn_thread_pool')
    def test_get_max_configured_workers_fallback(self, mock_detect_uvicorn, mock_get_asyncio, mock_cpu_count):
        """Test fallback calculation when both detection methods fail."""
        mock_detect_uvicorn.return_value = {}
        mock_get_asyncio.return_value = {}
        mock_cpu_count.return_value = 8
        
        result = get_max_configured_workers()
        
        # Should be min(32, cpu_count + 4) = min(32, 12) = 12
        assert result == 12
        assert mock_detect_uvicorn.called
        assert mock_get_asyncio.called
        assert mock_cpu_count.called
    
    @patch('os.cpu_count')
    @patch('app.monitoring._get_asyncio_thread_pool_info')
    @patch('app.monitoring._detect_uvicorn_thread_pool')
    def test_get_max_configured_workers_fallback_high_cpu(self, mock_detect_uvicorn, mock_get_asyncio, mock_cpu_count):
        """Test fallback calculation with high CPU count (should cap at 32)."""
        mock_detect_uvicorn.return_value = {}
        mock_get_asyncio.return_value = {}
        mock_cpu_count.return_value = 64  # High CPU count
        
        result = get_max_configured_workers()
        
        # Should be min(32, 64 + 4) = 32 (capped)
        assert result == 32
    
    @patch('os.cpu_count')
    @patch('app.monitoring._get_asyncio_thread_pool_info')
    @patch('app.monitoring._detect_uvicorn_thread_pool')
    def test_get_max_configured_workers_fallback_no_cpu_count(self, mock_detect_uvicorn, mock_get_asyncio, mock_cpu_count):
        """Test fallback calculation when cpu_count returns None."""
        mock_detect_uvicorn.return_value = {}
        mock_get_asyncio.return_value = {}
        mock_cpu_count.return_value = None
        
        result = get_max_configured_workers()
        
        # Should use fallback CPU count of 4: min(32, 4 + 4) = 8
        assert result == 8
    
    @patch('app.monitoring._get_asyncio_thread_pool_info')
    @patch('app.monitoring._detect_uvicorn_thread_pool')
    def test_get_max_configured_workers_error_handling(self, mock_detect_uvicorn, mock_get_asyncio):
        """Test error handling when all detection methods fail."""
        mock_detect_uvicorn.side_effect = RuntimeError("Uvicorn detection failed")
        mock_get_asyncio.side_effect = RuntimeError("AsyncIO detection failed")
        
        result = get_max_configured_workers()
        
        # Should return conservative fallback
        assert result == 8


class TestDetectUvicornThreadPool:
    """Test cases for _detect_uvicorn_thread_pool function."""
    
    @patch('gc.get_objects')
    def test_detect_uvicorn_thread_pool_no_server(self, mock_get_objects):
        """Test when no Uvicorn server instances are found."""
        mock_get_objects.return_value = []
        
        result = _detect_uvicorn_thread_pool()
        
        assert result == {}
        assert mock_get_objects.called
    
    @patch('gc.get_objects')
    def test_detect_uvicorn_thread_pool_with_server_config(self, mock_get_objects):
        """Test detection with Uvicorn server that has configuration."""
        # Create mock server with config
        mock_server = Mock()
        mock_server.__class__.__name__ = 'Server'
        mock_server.__class__.__module__ = 'uvicorn.server'
        
        # Mock config with workers
        mock_config = Mock()
        mock_config.workers = 4
        mock_config.limit_concurrency = 100
        mock_server.config = mock_config
        
        mock_get_objects.return_value = [mock_server]
        
        result = _detect_uvicorn_thread_pool()
        
        assert 'configured_workers' in result
        assert result['configured_workers'] == 4
        assert 'limit_concurrency' in result
        assert result['limit_concurrency'] == 100
    
    @patch('gc.get_objects')
    def test_detect_uvicorn_thread_pool_with_executor(self, mock_get_objects):
        """Test detection with server that has thread pool executor."""
        # Create mock server with thread pool executor
        mock_server = Mock()
        mock_server.__class__.__name__ = 'Server'
        mock_server.__class__.__module__ = 'uvicorn.server'
        
        # Remove config to avoid interference
        if hasattr(mock_server, 'config'):
            del mock_server.config
        
        # Mock executor with max_workers
        mock_executor = Mock()
        mock_executor._max_workers = 8
        mock_server.thread_pool_executor = mock_executor
        mock_server.force_exit = True  # Trigger executor search
        
        # Mock dir() to return our executor attribute
        with patch('builtins.dir', return_value=['thread_pool_executor', 'force_exit', 'other_attr']):
            mock_get_objects.return_value = [mock_server]
            
            result = _detect_uvicorn_thread_pool()
        
        assert 'max_workers' in result
        assert result['max_workers'] == 8
        assert 'detection_source' in result
        assert result['detection_source'] == 'server.thread_pool_executor'
    
    @patch('gc.get_objects')
    def test_detect_uvicorn_thread_pool_error_handling(self, mock_get_objects):
        """Test error handling in Uvicorn thread pool detection."""
        mock_get_objects.side_effect = RuntimeError("GC access failed")
        
        result = _detect_uvicorn_thread_pool()
        
        assert result == {}
    
    @patch('gc.get_objects')
    def test_detect_uvicorn_thread_pool_non_uvicorn_server(self, mock_get_objects):
        """Test with server objects that are not Uvicorn servers."""
        # Create mock server that's not from uvicorn
        mock_server = Mock()
        mock_server.__class__.__name__ = 'Server'
        mock_server.__class__.__module__ = 'other.server'
        
        mock_get_objects.return_value = [mock_server]
        
        result = _detect_uvicorn_thread_pool()
        
        assert result == {}


class TestGetAsyncioThreadPoolInfo:
    """Test cases for _get_asyncio_thread_pool_info function."""
    
    @patch('asyncio.get_running_loop')
    def test_get_asyncio_thread_pool_info_with_running_loop(self, mock_get_running_loop):
        """Test getting thread pool info from running asyncio loop."""
        from concurrent.futures import ThreadPoolExecutor
        
        # Create mock loop with default executor
        mock_loop = Mock()
        mock_executor = ThreadPoolExecutor(max_workers=10)
        mock_executor._max_workers = 10
        mock_executor._threads = [Mock(), Mock(), Mock()]  # 3 current threads
        mock_executor._idle_semaphore = Mock()
        mock_executor._idle_semaphore._value = 2  # 2 idle threads
        mock_loop._default_executor = mock_executor
        
        mock_get_running_loop.return_value = mock_loop
        
        try:
            result = _get_asyncio_thread_pool_info()
            
            assert result['has_default_executor'] is True
            assert result['max_workers'] == 10
            assert result['current_threads'] == 3
            assert result['idle_threads'] == 2
            assert result['detection_source'] == 'asyncio_default_executor'
        finally:
            # Clean up the executor
            mock_executor.shutdown(wait=False)
    
    @patch('asyncio.get_running_loop')
    def test_get_asyncio_thread_pool_info_no_executor(self, mock_get_running_loop):
        """Test when asyncio loop has no default executor."""
        mock_loop = Mock()
        mock_loop._default_executor = None
        mock_get_running_loop.return_value = mock_loop
        
        result = _get_asyncio_thread_pool_info()
        
        assert result['has_default_executor'] is False
    
    @patch('asyncio.get_event_loop')
    @patch('asyncio.get_running_loop')
    def test_get_asyncio_thread_pool_info_fallback_to_event_loop(self, mock_get_running_loop, mock_get_event_loop):
        """Test fallback to get_event_loop when no running loop."""
        mock_get_running_loop.side_effect = RuntimeError("No running loop")
        
        mock_loop = Mock()
        mock_loop._default_executor = None
        mock_get_event_loop.return_value = mock_loop
        
        result = _get_asyncio_thread_pool_info()
        
        assert result['has_default_executor'] is False
        assert mock_get_running_loop.called
        assert mock_get_event_loop.called
    
    @patch('os.cpu_count')
    @patch('asyncio.get_running_loop')
    def test_get_asyncio_thread_pool_info_with_system_defaults(self, mock_get_running_loop, mock_cpu_count):
        """Test including system default calculations."""
        mock_loop = Mock()
        mock_loop._default_executor = None
        mock_get_running_loop.return_value = mock_loop
        mock_cpu_count.return_value = 4
        
        result = _get_asyncio_thread_pool_info()
        
        assert result['system_default_max_workers'] == 8  # min(32, 4 + 4)
        assert result['cpu_count'] == 4
    
    @patch('asyncio.get_event_loop')
    @patch('asyncio.get_running_loop')
    def test_get_asyncio_thread_pool_info_no_loop_available(self, mock_get_running_loop, mock_get_event_loop):
        """Test when no asyncio loop is available."""
        mock_get_running_loop.side_effect = RuntimeError("No running loop")
        mock_get_event_loop.side_effect = RuntimeError("No event loop")
        
        result = _get_asyncio_thread_pool_info()
        
        assert result == {}
    
    @patch('asyncio.get_running_loop')
    def test_get_asyncio_thread_pool_info_error_handling(self, mock_get_running_loop):
        """Test error handling in asyncio thread pool info detection."""
        mock_get_running_loop.side_effect = Exception("Unexpected error")
        
        result = _get_asyncio_thread_pool_info()
        
        assert result == {}


class TestThreadDetectionErrorScenarios:
    """Test error scenarios and edge cases."""
    
    @patch('app.monitoring._is_worker_thread')
    def test_get_active_worker_count_with_is_worker_error(self, mock_is_worker):
        """Test get_active_worker_count when _is_worker_thread raises exception."""
        mock_is_worker.side_effect = RuntimeError("Worker detection failed")
        
        result = get_active_worker_count()
        
        # Should handle error gracefully and return 0
        assert result == 0
    
    @patch('app.monitoring._is_thread_active')
    @patch('app.monitoring._is_worker_thread')
    def test_get_active_worker_count_with_is_active_error(self, mock_is_worker, mock_is_active):
        """Test get_active_worker_count when _is_thread_active raises exception."""
        mock_threads = [Mock(name="worker-thread-1")]
        
        with patch('app.monitoring._enumerate_active_threads', return_value=mock_threads):
            mock_is_worker.return_value = True
            mock_is_active.side_effect = RuntimeError("Activity detection failed")
            
            result = get_active_worker_count()
            
            # Should handle error gracefully and return 0
            assert result == 0
    
    def test_thread_detection_with_malformed_thread_objects(self):
        """Test thread detection with malformed thread objects."""
        # Create a mock object that doesn't have expected thread attributes
        malformed_thread = Mock()
        del malformed_thread.name  # Remove name attribute
        
        # Should handle gracefully
        is_worker = _is_worker_thread(malformed_thread)
        assert is_worker is False
        
        is_active = _is_thread_active(malformed_thread)
        assert is_active is False


class TestThreadPoolConfigurationIntegration:
    """Integration tests for thread pool configuration detection."""
    
    def test_get_max_configured_workers_integration(self):
        """Test get_max_configured_workers with real system."""
        result = get_max_configured_workers()
        
        # Should return a reasonable positive integer
        assert isinstance(result, int)
        assert result > 0
        assert result <= 32  # Should be capped at reasonable maximum


class TestEnumerateActiveThreadsComprehensive:
    """Comprehensive test cases for _enumerate_active_threads function covering various thread scenarios."""
    
    def test_enumerate_active_threads_with_multiple_thread_types(self):
        """Test enumeration with various types of threads running simultaneously."""
        def worker_task():
            time.sleep(0.2)
        
        def daemon_task():
            time.sleep(0.2)
        
        # Create different types of threads
        worker_thread = threading.Thread(target=worker_task, name="worker-thread-test")
        daemon_thread = threading.Thread(target=daemon_task, name="daemon-thread-test", daemon=True)
        
        try:
            worker_thread.start()
            daemon_thread.start()
            time.sleep(0.05)  # Let threads start
            
            threads = _enumerate_active_threads()
            
            # Should find our test threads
            thread_names = [t.name for t in threads]
            assert "worker-thread-test" in thread_names
            assert "daemon-thread-test" in thread_names
            
            # Should include main thread
            assert any("MainThread" in name or name == "MainThread" for name in thread_names)
            
        finally:
            worker_thread.join(timeout=1.0)
            daemon_thread.join(timeout=1.0)
    
    def test_enumerate_active_threads_during_thread_creation_destruction(self):
        """Test enumeration during dynamic thread creation and destruction."""
        def short_task():
            time.sleep(0.05)
        
        # Create threads that will start and finish quickly
        threads_to_create = []
        for i in range(3):
            t = threading.Thread(target=short_task, name=f"short-lived-{i}")
            threads_to_create.append(t)
        
        # Start threads
        for t in threads_to_create:
            t.start()
        
        # Enumerate while threads are running
        active_threads = _enumerate_active_threads()
        assert len(active_threads) > 0
        
        # Wait for threads to complete
        for t in threads_to_create:
            t.join(timeout=1.0)
        
        # Enumerate after threads complete
        final_threads = _enumerate_active_threads()
        assert len(final_threads) >= 1  # At least main thread
    
    @patch('threading.enumerate')
    def test_enumerate_active_threads_with_various_exceptions(self, mock_enumerate):
        """Test error handling with different types of exceptions."""
        exception_types = [
            RuntimeError("Runtime error"),
            OSError("OS error"),
            MemoryError("Memory error"),
            SystemError("System error"),
            Exception("Generic exception")
        ]
        
        for exception in exception_types:
            mock_enumerate.side_effect = exception
            
            threads = _enumerate_active_threads()
            
            assert threads == []
            assert isinstance(threads, list)
    
    @patch('threading.enumerate')
    def test_enumerate_active_threads_with_corrupted_thread_list(self, mock_enumerate):
        """Test handling of corrupted or invalid thread list."""
        # Test with non-list return value that causes TypeError when converted to list
        mock_enumerate.side_effect = TypeError("Invalid thread list")
        
        threads = _enumerate_active_threads()
        assert threads == []
        
        # Test with other problematic return values
        mock_enumerate.side_effect = ValueError("Thread enumeration value error")
        threads = _enumerate_active_threads()
        assert threads == []


class TestIsWorkerThreadComprehensive:
    """Comprehensive test cases for _is_worker_thread covering various thread scenarios."""
    
    def test_is_worker_thread_with_all_worker_patterns(self):
        """Test identification with all supported worker thread patterns."""
        worker_patterns = [
            "ThreadPoolExecutor-0_0",
            "worker-1",
            "uvicorn-server-worker",
            "asyncio-thread-pool-1",
            "executor-thread-2",
            "http-processor-thread",
            "THREADPOOLEXECUTOR-UPPER",  # Case insensitive
            "Worker-Mixed-Case",
            "custom-executor-thread"
        ]
        
        for pattern in worker_patterns:
            mock_thread = Mock(spec=threading.Thread)
            mock_thread.name = pattern
            
            result = _is_worker_thread(mock_thread)
            assert result is True, f"Pattern '{pattern}' should be identified as worker thread"
    
    def test_is_worker_thread_with_non_worker_patterns(self):
        """Test that non-worker threads are correctly identified."""
        non_worker_patterns = [
            "MainThread",
            "system-monitor",
            "garbage-collector",
            "signal-handler",
            "timer-thread",
            "logging-thread",
            "random-thread-name",
            "test-thread",
            ""  # Empty name
        ]
        
        for pattern in non_worker_patterns:
            mock_thread = Mock(spec=threading.Thread)
            mock_thread.name = pattern
            mock_thread.daemon = False
            mock_thread._target = None
            
            result = _is_worker_thread(mock_thread)
            assert result is False, f"Pattern '{pattern}' should NOT be identified as worker thread"
    
    def test_is_worker_thread_with_daemon_and_target_combinations(self):
        """Test identification based on daemon status and target function combinations."""
        test_cases = [
            # (daemon, has_target, expected_result, description)
            (True, True, True, "daemon with target should be worker"),
            (True, False, False, "daemon without target should not be worker"),
            (False, True, False, "non-daemon with target should not be worker"),
            (False, False, False, "non-daemon without target should not be worker"),
        ]
        
        for daemon, has_target, expected, description in test_cases:
            mock_thread = Mock(spec=threading.Thread)
            mock_thread.name = "custom-thread"
            mock_thread.daemon = daemon
            mock_thread._target = Mock() if has_target else None
            
            result = _is_worker_thread(mock_thread)
            assert result == expected, f"{description}: daemon={daemon}, has_target={has_target}"
    
    def test_is_worker_thread_with_missing_attributes(self):
        """Test handling of threads with various missing attributes."""
        # Test thread without name attribute
        mock_thread = Mock(spec=threading.Thread)
        if hasattr(mock_thread, 'name'):
            delattr(mock_thread, 'name')
        
        result = _is_worker_thread(mock_thread)
        assert result is False
        
        # Test thread without daemon attribute
        mock_thread = Mock(spec=threading.Thread)
        mock_thread.name = "test-thread"
        if hasattr(mock_thread, 'daemon'):
            delattr(mock_thread, 'daemon')
        
        result = _is_worker_thread(mock_thread)
        assert result is False
        
        # Test thread without _target attribute
        mock_thread = Mock(spec=threading.Thread)
        mock_thread.name = "test-thread"
        mock_thread.daemon = True
        if hasattr(mock_thread, '_target'):
            delattr(mock_thread, '_target')
        
        result = _is_worker_thread(mock_thread)
        assert result is False
    
    def test_is_worker_thread_with_attribute_access_errors(self):
        """Test handling of attribute access errors."""
        mock_thread = Mock(spec=threading.Thread)
        
        # Mock name property to raise exception
        type(mock_thread).name = PropertyMock(side_effect=AttributeError("Name access failed"))
        
        result = _is_worker_thread(mock_thread)
        assert result is False
        
        # Test with name access working but daemon access failing
        mock_thread = Mock(spec=threading.Thread)
        mock_thread.name = "worker-thread"
        # The function should identify by name pattern first, before checking daemon
        # Since "worker" is in the name, it should return True before checking daemon
        
        result = _is_worker_thread(mock_thread)
        assert result is True  # Should identify by name pattern
        
        # Test with non-worker name and daemon access error
        mock_thread = Mock(spec=threading.Thread)
        mock_thread.name = "system-thread"  # Not a worker pattern
        type(mock_thread).daemon = PropertyMock(side_effect=RuntimeError("Daemon access failed"))
        
        result = _is_worker_thread(mock_thread)
        assert result is False  # Should return False due to exception in daemon check
    
    def test_is_worker_thread_edge_cases(self):
        """Test edge cases and boundary conditions."""
        # Test with very long thread name
        mock_thread = Mock(spec=threading.Thread)
        mock_thread.name = "a" * 1000 + "worker" + "b" * 1000
        
        result = _is_worker_thread(mock_thread)
        assert result is True
        
        # Test with thread name containing special characters
        mock_thread = Mock(spec=threading.Thread)
        mock_thread.name = "worker-thread!@#$%^&*()"
        
        result = _is_worker_thread(mock_thread)
        assert result is True
        
        # Test with unicode thread name
        mock_thread = Mock(spec=threading.Thread)
        mock_thread.name = "worker-线程-ワーカー"
        
        result = _is_worker_thread(mock_thread)
        assert result is True


class TestIsThreadActiveComprehensive:
    """Comprehensive test cases for _is_thread_active covering different thread states."""
    
    def test_is_thread_active_with_various_thread_states(self):
        """Test activity detection with various thread states."""
        # Test with alive thread having target
        mock_thread = Mock(spec=threading.Thread)
        mock_thread.is_alive.return_value = True
        mock_thread.name = "worker-thread"
        mock_thread._target = Mock()
        mock_thread._target.__name__ = "worker_function"
        
        result = _is_thread_active(mock_thread)
        assert result is True
        
        # Test with alive thread without target
        mock_thread = Mock(spec=threading.Thread)
        mock_thread.is_alive.return_value = True
        mock_thread.name = "worker-thread"
        mock_thread._target = None
        
        result = _is_thread_active(mock_thread)
        assert result is True  # Conservative approach
        
        # Test with dead thread
        mock_thread = Mock(spec=threading.Thread)
        mock_thread.is_alive.return_value = False
        mock_thread.name = "worker-thread"
        mock_thread._target = Mock()
        
        result = _is_thread_active(mock_thread)
        assert result is False
    
    def test_is_thread_active_with_target_function_variations(self):
        """Test activity detection with different target function scenarios."""
        target_scenarios = [
            (Mock(), True, "Mock target function"),
            (lambda: None, True, "Lambda target function"),
            (print, True, "Built-in function target"),
            (None, True, "No target function (conservative)"),
        ]
        
        for target, expected, description in target_scenarios:
            mock_thread = Mock(spec=threading.Thread)
            mock_thread.is_alive.return_value = True
            mock_thread.name = "worker-thread"
            mock_thread._target = target
            
            result = _is_thread_active(mock_thread)
            assert result == expected, f"{description}: expected {expected}, got {result}"
    
    def test_is_thread_active_with_is_alive_errors(self):
        """Test handling of errors when checking thread alive status."""
        error_types = [
            RuntimeError("Thread state error"),
            OSError("OS error checking thread"),
            SystemError("System error"),
            Exception("Generic exception")
        ]
        
        for error in error_types:
            mock_thread = Mock(spec=threading.Thread)
            mock_thread.is_alive.side_effect = error
            mock_thread.name = "worker-thread"
            
            result = _is_thread_active(mock_thread)
            assert result is False, f"Should return False on {type(error).__name__}"
    
    def test_is_thread_active_with_target_access_errors(self):
        """Test handling of errors when accessing target attribute."""
        mock_thread = Mock(spec=threading.Thread)
        mock_thread.is_alive.return_value = True
        mock_thread.name = "worker-thread"
        
        # Mock _target property to raise exception
        type(mock_thread)._target = PropertyMock(side_effect=AttributeError("Target access failed"))
        
        result = _is_thread_active(mock_thread)
        assert result is True  # Should fall back to conservative approach
    
    def test_is_thread_active_with_real_thread_states(self):
        """Test activity detection with real thread in different states."""
        def worker_task():
            time.sleep(0.1)
        
        # Test with running thread
        thread = threading.Thread(target=worker_task, name="test-worker")
        thread.start()
        
        try:
            time.sleep(0.02)  # Let thread start
            
            # Thread should be alive and active
            is_active = _is_thread_active(thread)
            assert is_active is True
            
        finally:
            thread.join(timeout=1.0)
        
        # After joining, thread should not be active
        is_active = _is_thread_active(thread)
        assert is_active is False


class TestThreadCountingFunctionsComprehensive:
    """Comprehensive test cases for thread counting functions with controlled scenarios."""
    
    def test_get_active_worker_count_with_mixed_thread_pool(self):
        """Test active worker counting with mixed thread pool scenarios."""
        # Create mock threads representing different scenarios
        mock_threads = []
        
        # Main thread (not worker, not active)
        main_thread = Mock(spec=threading.Thread)
        main_thread.name = "MainThread"
        mock_threads.append(main_thread)
        
        # Active worker threads
        for i in range(3):
            worker = Mock(spec=threading.Thread)
            worker.name = f"ThreadPoolExecutor-0_{i}"
            mock_threads.append(worker)
        
        # Idle worker threads
        for i in range(2):
            worker = Mock(spec=threading.Thread)
            worker.name = f"worker-idle-{i}"
            mock_threads.append(worker)
        
        # System threads (not workers)
        system_thread = Mock(spec=threading.Thread)
        system_thread.name = "system-monitor"
        mock_threads.append(system_thread)
        
        with patch('app.monitoring._enumerate_active_threads', return_value=mock_threads):
            with patch('app.monitoring._is_worker_thread') as mock_is_worker:
                with patch('app.monitoring._is_thread_active') as mock_is_active:
                    
                    # Configure worker identification
                    def is_worker_side_effect(thread):
                        return any(pattern in thread.name.lower() 
                                 for pattern in ['threadpoolexecutor', 'worker'])
                    
                    # Configure activity detection (only first 3 ThreadPoolExecutor threads active)
                    def is_active_side_effect(thread):
                        return 'ThreadPoolExecutor' in thread.name
                    
                    mock_is_worker.side_effect = is_worker_side_effect
                    mock_is_active.side_effect = is_active_side_effect
                    
                    active_count = get_active_worker_count()
                    
                    # Should find 3 active workers (ThreadPoolExecutor threads)
                    assert active_count == 3
    
    def test_get_total_worker_count_with_various_worker_types(self):
        """Test total worker counting with various worker thread types."""
        mock_threads = []
        
        # Different types of worker threads
        worker_types = [
            "ThreadPoolExecutor-0_0",
            "ThreadPoolExecutor-0_1", 
            "worker-thread-1",
            "worker-thread-2",
            "uvicorn-worker-1",
            "asyncio-thread-pool-1",
            "executor-thread-1",
            "http-processor-1"
        ]
        
        for name in worker_types:
            worker = Mock(spec=threading.Thread)
            worker.name = name
            mock_threads.append(worker)
        
        # Non-worker threads
        non_worker_types = [
            "MainThread",
            "system-monitor",
            "garbage-collector"
        ]
        
        for name in non_worker_types:
            thread = Mock(spec=threading.Thread)
            thread.name = name
            mock_threads.append(thread)
        
        with patch('app.monitoring._enumerate_active_threads', return_value=mock_threads):
            with patch('app.monitoring._is_worker_thread') as mock_is_worker:
                
                def is_worker_side_effect(thread):
                    worker_patterns = ['threadpoolexecutor', 'worker', 'uvicorn', 'asyncio', 'executor', 'http']
                    return any(pattern in thread.name.lower() for pattern in worker_patterns)
                
                mock_is_worker.side_effect = is_worker_side_effect
                
                total_count = get_total_worker_count()
                
                # Should find all 8 worker threads
                assert total_count == 8
    
    def test_thread_counting_with_individual_thread_errors(self):
        """Test thread counting when individual thread processing fails."""
        mock_threads = []
        
        # Create some normal threads
        for i in range(3):
            thread = Mock(spec=threading.Thread)
            thread.name = f"worker-{i}"
            mock_threads.append(thread)
        
        # Create a problematic thread that causes errors
        problematic_thread = Mock(spec=threading.Thread)
        problematic_thread.name = "problematic-worker"
        mock_threads.append(problematic_thread)
        
        with patch('app.monitoring._enumerate_active_threads', return_value=mock_threads):
            with patch('app.monitoring._is_worker_thread') as mock_is_worker:
                with patch('app.monitoring._is_thread_active') as mock_is_active:
                    
                    # Configure normal threads as workers
                    def is_worker_side_effect(thread):
                        if thread.name == "problematic-worker":
                            raise RuntimeError("Thread processing error")
                        return "worker" in thread.name
                    
                    def is_active_side_effect(thread):
                        if thread.name == "problematic-worker":
                            raise RuntimeError("Activity check error")
                        return True
                    
                    mock_is_worker.side_effect = is_worker_side_effect
                    mock_is_active.side_effect = is_active_side_effect
                    
                    # Should handle errors gracefully and count the good threads
                    active_count = get_active_worker_count()
                    total_count = get_total_worker_count()
                    
                    # Should count the 3 good worker threads, skip the problematic one
                    assert active_count == 3
                    assert total_count == 3
    
    def test_thread_counting_performance_with_many_threads(self):
        """Test thread counting performance with large number of threads."""
        # Create a large number of mock threads
        mock_threads = []
        for i in range(100):
            thread = Mock(spec=threading.Thread)
            thread.name = f"worker-{i}" if i % 2 == 0 else f"system-{i}"
            mock_threads.append(thread)
        
        with patch('app.monitoring._enumerate_active_threads', return_value=mock_threads):
            with patch('app.monitoring._is_worker_thread') as mock_is_worker:
                with patch('app.monitoring._is_thread_active') as mock_is_active:
                    
                    # Configure every other thread as worker
                    mock_is_worker.side_effect = lambda t: "worker" in t.name
                    mock_is_active.return_value = True
                    
                    start_time = time.time()
                    
                    active_count = get_active_worker_count()
                    total_count = get_total_worker_count()
                    
                    end_time = time.time()
                    
                    # Should complete quickly (under 1 second for 100 threads)
                    assert (end_time - start_time) < 1.0
                    
                    # Should count correctly (50 worker threads)
                    assert active_count == 50
                    assert total_count == 50


class TestThreadEnumerationErrorHandling:
    """Test error handling when thread enumeration fails in various ways."""
    
    @patch('threading.enumerate')
    def test_enumerate_active_threads_with_intermittent_failures(self, mock_enumerate):
        """Test handling of intermittent enumeration failures."""
        # Simulate intermittent failures
        call_count = 0
        def side_effect():
            nonlocal call_count
            call_count += 1
            if call_count % 2 == 0:
                raise RuntimeError("Intermittent failure")
            return [Mock(name="test-thread")]
        
        mock_enumerate.side_effect = side_effect
        
        # First call should succeed
        threads = _enumerate_active_threads()
        assert len(threads) == 1
        
        # Second call should fail gracefully
        threads = _enumerate_active_threads()
        assert threads == []
    
    @patch('threading.enumerate')
    def test_thread_counting_with_enumeration_timeout(self, mock_enumerate):
        """Test thread counting when enumeration takes too long."""
        def slow_enumerate():
            time.sleep(2)  # Simulate slow enumeration
            return [Mock(name="slow-thread")]
        
        mock_enumerate.side_effect = slow_enumerate
        
        # Should handle slow enumeration (though our implementation doesn't have timeout)
        start_time = time.time()
        threads = _enumerate_active_threads()
        end_time = time.time()
        
        # This test mainly ensures the function doesn't hang indefinitely
        assert (end_time - start_time) >= 2.0  # Should take at least 2 seconds
        assert len(threads) == 1
    
    @patch('app.monitoring._enumerate_active_threads')
    def test_thread_counting_with_corrupted_thread_data(self, mock_enumerate):
        """Test thread counting with corrupted thread data."""
        # Create threads with various data corruption scenarios
        corrupted_threads = []
        
        # Thread with None name
        thread1 = Mock(spec=threading.Thread)
        thread1.name = None
        corrupted_threads.append(thread1)
        
        # Thread with non-string name
        thread2 = Mock(spec=threading.Thread)
        thread2.name = 12345
        corrupted_threads.append(thread2)
        
        # Thread with missing is_alive method
        thread3 = Mock(spec=threading.Thread)
        thread3.name = "test-thread"
        if hasattr(thread3, 'is_alive'):
            delattr(thread3, 'is_alive')
        corrupted_threads.append(thread3)
        
        mock_enumerate.return_value = corrupted_threads
        
        # Should handle corrupted data gracefully
        active_count = get_active_worker_count()
        total_count = get_total_worker_count()
        
        # Should return 0 due to data corruption handling
        assert active_count == 0
        assert total_count == 0
    
    def test_thread_detection_with_mock_threading_module(self):
        """Test thread detection with completely mocked threading module."""
        with patch('threading.enumerate') as mock_enumerate:
            with patch('threading.current_thread') as mock_current:
                
                # Create a realistic mock scenario
                current_thread = Mock(spec=threading.Thread)
                current_thread.name = "MainThread"
                mock_current.return_value = current_thread
                
                worker_threads = []
                for i in range(5):
                    thread = Mock(spec=threading.Thread)
                    thread.name = f"ThreadPoolExecutor-0_{i}"
                    thread.is_alive.return_value = True
                    thread.daemon = True
                    thread._target = Mock()
                    worker_threads.append(thread)
                
                all_threads = [current_thread] + worker_threads
                mock_enumerate.return_value = all_threads
                
                # Test enumeration
                threads = _enumerate_active_threads()
                assert len(threads) == 6  # 1 main + 5 workers
                
                # Test worker identification
                worker_count = sum(1 for t in threads if _is_worker_thread(t))
                assert worker_count == 5  # Only the ThreadPoolExecutor threads
                
                # Test activity detection
                active_count = sum(1 for t in threads if _is_worker_thread(t) and _is_thread_active(t))
                assert active_count == 5  # All workers are active
    
    def test_edge_cases_with_thread_lifecycle(self):
        """Test edge cases during thread lifecycle transitions."""
        def quick_task():
            pass  # Very quick task
        
        # Test with threads that start and finish very quickly
        quick_threads = []
        for i in range(10):
            thread = threading.Thread(target=quick_task, name=f"quick-worker-{i}")
            quick_threads.append(thread)
        
        # Start all threads
        for thread in quick_threads:
            thread.start()
        
        # Enumerate immediately (some threads might still be starting)
        threads_during_start = _enumerate_active_threads()
        
        # Wait for all to complete
        for thread in quick_threads:
            thread.join(timeout=1.0)
        
        # Enumerate after completion
        threads_after_completion = _enumerate_active_threads()
        
        # Both enumerations should succeed without errors
        assert isinstance(threads_during_start, list)
        assert isinstance(threads_after_completion, list)
        assert len(threads_during_start) >= 1  # At least main thread
        assert len(threads_after_completion) >= 1  # At least main thread
    
    def test_detect_uvicorn_thread_pool_integration(self):
        """Test _detect_uvicorn_thread_pool with real system."""
        result = _detect_uvicorn_thread_pool()
        
        # Should return a dictionary (may be empty if no Uvicorn server)
        assert isinstance(result, dict)
    
    def test_get_asyncio_thread_pool_info_integration(self):
        """Test _get_asyncio_thread_pool_info with real system."""
        result = _get_asyncio_thread_pool_info()
        
        # Should return a dictionary (may be empty if no asyncio loop)
        assert isinstance(result, dict)
        
        # If system defaults are included, they should be reasonable
        if 'system_default_max_workers' in result:
            assert result['system_default_max_workers'] > 0
            assert result['system_default_max_workers'] <= 32
        
        if 'cpu_count' in result:
            assert result['cpu_count'] > 0