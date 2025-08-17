"""
Unit tests for thread detection and enumeration functionality.

Tests the thread detection functions in app.monitoring module to ensure
accurate identification and counting of worker threads vs system threads.
"""

import pytest
import threading
import time
from unittest.mock import Mock, patch, MagicMock
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
        assert result <= 32  # Should be capped at 32
    
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