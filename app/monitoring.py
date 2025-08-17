"""
Enhanced HTTP Metrics Monitoring Module for GlobeCo Portfolio Service.

This module provides standardized HTTP metrics collection using both Prometheus client
(for /metrics endpoint) and OpenTelemetry (for collector export) with comprehensive 
error handling and duplicate registration prevention.
"""

import time
import threading
import asyncio
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, Optional, Callable, List

from fastapi import Request, Response
from prometheus_client import Counter, Gauge, Histogram
from starlette.middleware.base import BaseHTTPMiddleware
from app.logging_config import get_logger

# OpenTelemetry imports for collector integration
from opentelemetry import metrics
from opentelemetry.metrics import Counter as OTelCounter, Histogram as OTelHistogram, UpDownCounter as OTelGauge

logger = get_logger(__name__)

# Global metrics registry to prevent duplicate registration
_METRICS_REGISTRY: Dict[str, Any] = {}


class DummyMetric:
    """
    Dummy metric class for graceful fallback when registration fails.
    
    This class provides the same interface as Prometheus metrics but performs
    no actual operations, preventing service disruption when metric registration
    encounters errors.
    """
    
    def labels(self, **kwargs):
        """Return self to support method chaining."""
        return self
    
    def inc(self, amount: float = 1) -> None:
        """Dummy increment operation."""
        pass
    
    def observe(self, amount: float) -> None:
        """Dummy observe operation."""
        pass
    
    def set(self, value: float) -> None:
        """Dummy set operation."""
        pass
    
    def collect(self):
        """Return empty list for Prometheus collection."""
        return []


def _get_or_create_metric(
    metric_class, 
    name: str, 
    description: str, 
    labels: Optional[list] = None, 
    registry_key: Optional[str] = None, 
    **kwargs
) -> Any:
    """
    Get or create a metric, preventing duplicate registration.
    
    This function implements a global registry pattern to prevent duplicate
    metric registration errors that can occur during module reloads or
    circular imports.
    
    Args:
        metric_class: Prometheus metric class (Counter, Histogram, Gauge)
        name: Metric name
        description: Metric description
        labels: List of label names
        registry_key: Optional custom registry key (defaults to name)
        **kwargs: Additional arguments for metric creation
        
    Returns:
        Prometheus metric instance or DummyMetric on failure
    """
    if registry_key is None:
        registry_key = name

    # Check if metric already exists in our registry
    if registry_key in _METRICS_REGISTRY:
        logger.debug(
            "Reusing existing metric from registry",
            metric_name=name,
            registry_key=registry_key,
            metric_type=type(_METRICS_REGISTRY[registry_key]).__name__
        )
        return _METRICS_REGISTRY[registry_key]

    try:
        # Log metric creation attempt
        logger.debug(
            "Attempting to create new metric",
            metric_name=name,
            metric_class=metric_class.__name__ if hasattr(metric_class, '__name__') else str(metric_class),
            description=description,
            labels=labels,
            registry_key=registry_key,
            additional_kwargs=list(kwargs.keys()) if kwargs else []
        )
        
        # Create metric with or without labels
        if labels:
            metric = metric_class(name, description, labels, **kwargs)
        else:
            metric = metric_class(name, description, **kwargs)

        _METRICS_REGISTRY[registry_key] = metric
        logger.info(
            "Successfully created and registered metric",
            metric_name=name,
            metric_type=type(metric).__name__,
            registry_key=registry_key,
            has_labels=bool(labels),
            label_count=len(labels) if labels else 0,
            registry_size=len(_METRICS_REGISTRY)
        )
        return metric

    except ValueError as e:
        if "Duplicated timeseries" in str(e):
            logger.warning(
                "Metric already registered in Prometheus registry but not in our internal registry",
                metric_name=name,
                registry_key=registry_key,
                error=str(e),
                error_type=type(e).__name__,
                prometheus_registry_conflict=True
            )
            # Create dummy metric to prevent service disruption
            dummy = DummyMetric()
            _METRICS_REGISTRY[registry_key] = dummy
            logger.warning(
                "Created dummy metric to prevent service disruption",
                metric_name=name,
                registry_key=registry_key,
                fallback_type="DummyMetric",
                reason="prometheus_registry_conflict"
            )
            return dummy
        else:
            logger.error(
                "ValueError during metric creation - using dummy metric fallback",
                metric_name=name,
                registry_key=registry_key,
                error=str(e),
                error_type=type(e).__name__,
                metric_class=metric_class.__name__ if hasattr(metric_class, '__name__') else str(metric_class),
                exc_info=True
            )
            # Create dummy metric as fallback
            dummy = DummyMetric()
            _METRICS_REGISTRY[registry_key] = dummy
            logger.error(
                "Created dummy metric due to ValueError",
                metric_name=name,
                registry_key=registry_key,
                fallback_type="DummyMetric",
                reason="value_error"
            )
            return dummy
    except Exception as e:
        logger.error(
            "Unexpected error during metric creation - using dummy metric fallback",
            metric_name=name,
            registry_key=registry_key,
            error=str(e),
            error_type=type(e).__name__,
            metric_class=metric_class.__name__ if hasattr(metric_class, '__name__') else str(metric_class),
            exc_info=True
        )
        # Create dummy metric as fallback
        dummy = DummyMetric()
        _METRICS_REGISTRY[registry_key] = dummy
        logger.error(
            "Created dummy metric due to unexpected error",
            metric_name=name,
            registry_key=registry_key,
            fallback_type="DummyMetric",
            reason="unexpected_error"
        )
        return dummy


# Create the three standardized HTTP metrics (Prometheus - for /metrics endpoint)
HTTP_REQUESTS_TOTAL = _get_or_create_metric(
    Counter,
    'http_requests_total',
    'Total number of HTTP requests',
    ['method', 'path', 'status'],
)

HTTP_REQUEST_DURATION = _get_or_create_metric(
    Histogram,
    'http_request_duration',
    'HTTP request duration in milliseconds',
    ['method', 'path', 'status'],
    buckets=[5, 10, 25, 50, 100, 250, 500, 1000, 2500, 5000, 10000],
)

HTTP_REQUESTS_IN_FLIGHT = _get_or_create_metric(
    Gauge,
    'http_requests_in_flight',
    'Number of HTTP requests currently being processed'
)

# Create the four thread worker metrics (Prometheus - for /metrics endpoint)
HTTP_WORKERS_ACTIVE = _get_or_create_metric(
    Gauge,
    'http_workers_active',
    'Number of threads currently executing requests or performing work'
)

HTTP_WORKERS_TOTAL = _get_or_create_metric(
    Gauge,
    'http_workers_total',
    'Total number of threads currently alive in the thread pool'
)

HTTP_WORKERS_MAX_CONFIGURED = _get_or_create_metric(
    Gauge,
    'http_workers_max_configured',
    'Maximum number of threads that can be created in the thread pool'
)

HTTP_REQUESTS_QUEUED = _get_or_create_metric(
    Gauge,
    'http_requests_queued',
    'Number of pending requests waiting in the queue for thread assignment'
)

# Create OpenTelemetry metrics (for collector export)
# These will be sent to the OpenTelemetry Collector and then to Prometheus
try:
    meter = metrics.get_meter(__name__)
    
    # OpenTelemetry HTTP metrics
    otel_http_requests_total = meter.create_counter(
        name="http_requests_total",
        description="Total number of HTTP requests",
        unit="1"
    )
    
    otel_http_request_duration = meter.create_histogram(
        name="http_request_duration",
        description="HTTP request duration in milliseconds", 
        unit="ms"
    )
    
    otel_http_requests_in_flight = meter.create_up_down_counter(
        name="http_requests_in_flight",
        description="Number of HTTP requests currently being processed",
        unit="1"
    )
    
    # OpenTelemetry thread worker metrics
    otel_http_workers_active = meter.create_up_down_counter(
        name="http_workers_active",
        description="Number of threads currently executing requests or performing work",
        unit="1"
    )
    
    otel_http_workers_total = meter.create_up_down_counter(
        name="http_workers_total",
        description="Total number of threads currently alive in the thread pool",
        unit="1"
    )
    
    otel_http_workers_max_configured = meter.create_up_down_counter(
        name="http_workers_max_configured",
        description="Maximum number of threads that can be created in the thread pool",
        unit="1"
    )
    
    otel_http_requests_queued = meter.create_up_down_counter(
        name="http_requests_queued",
        description="Number of pending requests waiting in the queue for thread assignment",
        unit="1"
    )
    
    logger.info("Successfully created OpenTelemetry HTTP and thread metrics")
    
except Exception as e:
    logger.error(
        "Failed to create OpenTelemetry metrics",
        error=str(e),
        error_type=type(e).__name__,
        exc_info=True
    )
    # Create dummy metrics as fallback
    class DummyOTelMetric:
        def add(self, amount, attributes=None):
            pass
        def record(self, amount, attributes=None):
            pass
    
    otel_http_requests_total = DummyOTelMetric()
    otel_http_request_duration = DummyOTelMetric()
    otel_http_requests_in_flight = DummyOTelMetric()
    otel_http_workers_active = DummyOTelMetric()
    otel_http_workers_total = DummyOTelMetric()
    otel_http_workers_max_configured = DummyOTelMetric()
    otel_http_requests_queued = DummyOTelMetric()
    logger.warning("Created dummy OpenTelemetry metrics due to initialization failure")


# Thread Detection and Enumeration Functions

def _enumerate_active_threads() -> List[threading.Thread]:
    """
    Enumerate all active threads in the current process.
    
    Uses Python's threading.enumerate() to get a list of all currently
    active Thread objects in the current process.
    
    Returns:
        List of active Thread objects, empty list on error
    """
    try:
        threads = list(threading.enumerate())
        logger.debug(
            "Successfully enumerated active threads",
            thread_count=len(threads),
            current_thread=threading.current_thread().name
        )
        return threads
    except Exception as e:
        logger.error(
            "Failed to enumerate active threads",
            error=str(e),
            error_type=type(e).__name__,
            fallback_result="empty_list",
            exc_info=True
        )
        return []


def _is_worker_thread(thread: threading.Thread) -> bool:
    """
    Determine if a thread is a worker thread processing HTTP requests.
    
    Identifies threads based on naming patterns and characteristics that
    indicate they are part of the HTTP request processing thread pool.
    
    Args:
        thread: Thread object to examine
        
    Returns:
        True if thread appears to be an HTTP worker thread
    """
    try:
        if not thread or not hasattr(thread, 'name'):
            return False
            
        thread_name = thread.name.lower()
        
        # Check for common worker thread naming patterns
        worker_patterns = [
            'threadpoolexecutor',  # asyncio default thread pool
            'worker',              # generic worker threads
            'uvicorn',             # uvicorn worker threads
            'asyncio',             # asyncio thread pool threads
            'executor',            # general executor threads
            'http',                # HTTP processing threads
        ]
        
        # Check if thread name contains any worker patterns
        is_worker = any(pattern in thread_name for pattern in worker_patterns)
        
        # Additional checks for thread characteristics
        if not is_worker:
            # Check if thread is a daemon thread (often used for worker pools)
            # and has a target function (indicating it's doing work)
            if (hasattr(thread, 'daemon') and thread.daemon and 
                hasattr(thread, '_target') and thread._target is not None):
                is_worker = True
                logger.debug(
                    "Identified worker thread by daemon status and target",
                    thread_name=thread.name,
                    is_daemon=thread.daemon,
                    has_target=thread._target is not None
                )
        
        if is_worker:
            logger.debug(
                "Identified worker thread",
                thread_name=thread.name,
                thread_id=thread.ident,
                is_daemon=getattr(thread, 'daemon', None),
                is_alive=thread.is_alive()
            )
        
        return is_worker
        
    except Exception as e:
        logger.debug(
            "Error checking if thread is worker thread",
            thread_name=getattr(thread, 'name', 'unknown') if thread else 'none',
            error=str(e),
            error_type=type(e).__name__,
            fallback_result=False
        )
        return False


def _is_thread_active(thread: threading.Thread) -> bool:
    """
    Determine if a worker thread is actively processing work.
    
    Distinguishes between threads that are actively executing requests
    versus threads that are idle and waiting for work assignment.
    
    Args:
        thread: Thread object to examine
        
    Returns:
        True if thread appears to be actively processing work
    """
    try:
        if not thread or not thread.is_alive():
            return False
        
        # Check if thread has an active target function
        if hasattr(thread, '_target') and thread._target is not None:
            logger.debug(
                "Thread considered active due to target function",
                thread_name=thread.name,
                thread_id=thread.ident,
                target_function=getattr(thread._target, '__name__', 'unknown')
            )
            return True
        
        # For threads without direct target inspection, use heuristics
        # In a real implementation, this might involve checking thread state
        # or other indicators of activity. For now, we'll use conservative logic.
        
        # If it's a worker thread and alive, consider it potentially active
        # This is a conservative approach - in practice, you might want to
        # implement more sophisticated detection based on your specific
        # thread pool implementation
        
        return True  # Conservative: assume alive worker threads are active
        
    except Exception as e:
        logger.debug(
            "Error checking thread activity status",
            thread_name=getattr(thread, 'name', 'unknown') if thread else 'none',
            error=str(e),
            error_type=type(e).__name__,
            fallback_result=False
        )
        return False


def get_active_worker_count() -> int:
    """
    Count threads currently executing requests or performing work.
    
    Returns the number of threads with status "RUNNING" or "BUSY" that are
    actively processing HTTP requests or business logic.
    
    Returns:
        Number of active worker threads, 0 on error
    """
    try:
        threads = _enumerate_active_threads()
        if not threads:
            logger.debug("No threads found during enumeration")
            return 0
        
        active_count = 0
        worker_threads = []
        
        for thread in threads:
            try:
                if _is_worker_thread(thread):
                    worker_threads.append(thread)
                    if _is_thread_active(thread):
                        active_count += 1
            except Exception as e:
                logger.debug(
                    "Error processing individual thread for active count",
                    thread_name=getattr(thread, 'name', 'unknown'),
                    error=str(e),
                    error_type=type(e).__name__
                )
                continue
        
        logger.debug(
            "Counted active worker threads",
            total_threads=len(threads),
            worker_threads=len(worker_threads),
            active_workers=active_count,
            worker_thread_names=[getattr(t, 'name', 'unknown') for t in worker_threads[:5]]  # Log first 5 names
        )
        
        return active_count
        
    except Exception as e:
        logger.error(
            "Failed to count active worker threads",
            error=str(e),
            error_type=type(e).__name__,
            fallback_result=0,
            exc_info=True
        )
        return 0


def get_total_worker_count() -> int:
    """
    Count total number of threads currently alive in the thread pool.
    
    Returns all threads regardless of state (idle, busy, waiting, blocked).
    
    Returns:
        Total number of worker threads, 0 on error
    """
    try:
        threads = _enumerate_active_threads()
        if not threads:
            logger.debug("No threads found during enumeration")
            return 0
        
        worker_count = 0
        worker_threads = []
        
        for thread in threads:
            try:
                if _is_worker_thread(thread):
                    worker_count += 1
                    worker_threads.append(thread)
            except Exception as e:
                logger.debug(
                    "Error processing individual thread for total count",
                    thread_name=getattr(thread, 'name', 'unknown'),
                    error=str(e),
                    error_type=type(e).__name__
                )
                continue
        
        logger.debug(
            "Counted total worker threads",
            total_threads=len(threads),
            worker_threads=worker_count,
            worker_thread_names=[getattr(t, 'name', 'unknown') for t in worker_threads[:5]]  # Log first 5 names
        )
        
        return worker_count
        
    except Exception as e:
        logger.error(
            "Failed to count total worker threads",
            error=str(e),
            error_type=type(e).__name__,
            fallback_result=0,
            exc_info=True
        )
        return 0


def get_max_configured_workers() -> int:
    """
    Get the maximum number of threads configured for the thread pool.
    
    Detects the maximum thread pool size from various sources:
    1. Uvicorn thread pool configuration
    2. AsyncIO thread pool executor settings
    3. System defaults and fallbacks
    
    Returns:
        Maximum configured thread pool size, reasonable default on error
    """
    try:
        # Try to detect from Uvicorn thread pool first
        uvicorn_info = _detect_uvicorn_thread_pool()
        if uvicorn_info and uvicorn_info.get('max_workers'):
            max_workers = uvicorn_info['max_workers']
            logger.debug(
                "Detected max workers from Uvicorn thread pool",
                max_workers=max_workers,
                detection_method="uvicorn_thread_pool"
            )
            return max_workers
        
        # Try to detect from AsyncIO thread pool executor
        asyncio_info = _get_asyncio_thread_pool_info()
        if asyncio_info and asyncio_info.get('max_workers'):
            max_workers = asyncio_info['max_workers']
            logger.debug(
                "Detected max workers from AsyncIO thread pool",
                max_workers=max_workers,
                detection_method="asyncio_thread_pool"
            )
            return max_workers
        
        # Fallback to reasonable defaults based on system
        import os
        cpu_count = os.cpu_count() or 4
        
        # Use common thread pool sizing heuristics
        # For I/O bound work (like HTTP requests), typically use more threads than CPU cores
        default_max_workers = min(32, (cpu_count or 4) + 4)
        
        logger.info(
            "Using fallback thread pool size calculation",
            cpu_count=cpu_count,
            calculated_max_workers=default_max_workers,
            detection_method="system_fallback",
            heuristic="cpu_count_plus_4_capped_at_32"
        )
        
        return default_max_workers
        
    except Exception as e:
        logger.error(
            "Failed to detect maximum configured workers - using conservative fallback",
            error=str(e),
            error_type=type(e).__name__,
            fallback_result=8,
            exc_info=True
        )
        return 8  # Conservative fallback


def get_queued_requests_count() -> int:
    """
    Count pending requests waiting for thread assignment.
    
    Uses multiple detection approaches with fallback mechanisms:
    1. Uvicorn server queue inspection
    2. AsyncIO task queue analysis
    3. System-level connection queue detection
    4. Estimation from existing HTTP metrics correlation
    
    Returns:
        Number of requests waiting in queue, 0 on error or when no queue detected
    """
    try:
        # Try multiple approaches in order of reliability
        detection_approaches = [
            _detect_uvicorn_queue,
            _detect_asyncio_queue,
            _detect_system_level_queue,
            _estimate_queue_from_metrics
        ]
        
        for approach in detection_approaches:
            try:
                result = approach()
                if result is not None and result >= 0:
                    try:
                        logger.debug(
                            "Successfully detected queue depth",
                            approach=approach.__name__,
                            queue_depth=result
                        )
                    except Exception:
                        # Ignore logger errors
                        pass
                    return result
            except Exception as e:
                try:
                    logger.debug(
                        "Queue detection approach failed",
                        approach=approach.__name__,
                        error=str(e),
                        error_type=type(e).__name__
                    )
                except Exception:
                    # Ignore logger errors
                    pass
                continue
        
        # All approaches failed, return safe fallback
        try:
            logger.debug(
                "All queue detection approaches failed, returning fallback",
                fallback_result=0
            )
        except Exception:
            # Ignore logger errors
            pass
        return 0
        
    except Exception as e:
        try:
            logger.error(
                "Failed to detect queued requests count",
                error=str(e),
                error_type=type(e).__name__,
                fallback_result=0,
                exc_info=True
            )
        except Exception:
            # Ignore logger errors
            pass
        return 0


def _detect_request_queue_depth() -> int:
    """
    Detect the number of requests waiting for thread assignment.
    
    This is the main queue detection function that coordinates multiple
    detection approaches and implements fallback mechanisms.
    
    Returns:
        Number of pending requests or 0 if detection fails
    """
    return get_queued_requests_count()


def _detect_uvicorn_queue() -> Optional[int]:
    """
    Detect request queue depth by inspecting Uvicorn server queue.
    
    Attempts to inspect the Uvicorn server's internal request queue
    to determine how many requests are waiting for thread assignment.
    
    Returns:
        Number of queued requests or None if detection fails
    """
    try:
        import sys
        import gc
        
        # Look for Uvicorn server instances in the garbage collector
        uvicorn_servers = []
        
        for obj in gc.get_objects():
            # Look for Uvicorn server objects
            if hasattr(obj, '__class__') and obj.__class__.__name__ == 'Server':
                module_name = getattr(obj.__class__, '__module__', '')
                if 'uvicorn' in module_name.lower():
                    uvicorn_servers.append(obj)
        
        if not uvicorn_servers:
            logger.debug("No Uvicorn server instances found for queue inspection")
            return None
        
        # Examine the first Uvicorn server instance
        server = uvicorn_servers[0]
        
        # Look for various queue-related attributes that might exist
        queue_attributes = [
            'request_queue',
            'pending_requests',
            'connection_queue',
            'backlog',
            '_request_queue',
            '_pending_requests'
        ]
        
        for attr_name in queue_attributes:
            if hasattr(server, attr_name):
                queue_obj = getattr(server, attr_name, None)
                if queue_obj:
                    # Try to get queue size
                    if hasattr(queue_obj, 'qsize') and callable(queue_obj.qsize):
                        try:
                            queue_depth = queue_obj.qsize()
                            logger.debug(
                                "Found Uvicorn queue via qsize()",
                                attribute=attr_name,
                                queue_depth=queue_depth
                            )
                            return queue_depth
                        except Exception as e:
                            logger.debug(
                                "Error calling qsize() on queue object",
                                attribute=attr_name,
                                error=str(e)
                            )
                            continue
                    elif hasattr(queue_obj, '__len__'):
                        try:
                            queue_depth = len(queue_obj)
                            logger.debug(
                                "Found Uvicorn queue via len()",
                                attribute=attr_name,
                                queue_depth=queue_depth
                            )
                            return queue_depth
                        except Exception as e:
                            logger.debug(
                                "Error calling len() on queue object",
                                attribute=attr_name,
                                error=str(e)
                            )
                            continue
        
        # Try to inspect server's socket backlog if available
        if hasattr(server, 'server') and server.server:
            server_obj = server.server
            if hasattr(server_obj, 'sockets'):
                # This is a more advanced approach that might work with some configurations
                for socket_obj in server_obj.sockets:
                    if hasattr(socket_obj, 'getsockopt'):
                        try:
                            import socket as socket_module
                            # Try to get socket queue length (this is system-dependent)
                            backlog = socket_obj.getsockopt(socket_module.SOL_SOCKET, socket_module.SO_ACCEPTCONN)
                            if backlog > 0:
                                logger.debug(
                                    "Detected socket backlog",
                                    backlog=backlog
                                )
                                return backlog
                        except Exception as e:
                            logger.debug(
                                "Error getting socket backlog",
                                error=str(e)
                            )
                            continue
        
        logger.debug("Could not find Uvicorn queue information")
        return None
        
    except Exception as e:
        logger.debug(
            "Error detecting Uvicorn queue depth",
            error=str(e),
            error_type=type(e).__name__
        )
        return None


def _detect_asyncio_queue() -> Optional[int]:
    """
    Detect request queue depth by analyzing AsyncIO task queue.
    
    Inspects the current asyncio event loop to find pending tasks
    that might represent queued HTTP requests.
    
    Returns:
        Number of queued requests or None if detection fails
    """
    try:
        import asyncio
        
        # Try to get the current event loop
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            # No running loop
            logger.debug("No running asyncio event loop found")
            return None
        
        queue_depth = 0
        found_queue_info = False
        
        # Count pending tasks that might be HTTP requests
        if hasattr(loop, '_scheduled'):
            try:
                scheduled_tasks = len(loop._scheduled)
                logger.debug(
                    "Found scheduled asyncio tasks",
                    scheduled_count=scheduled_tasks
                )
                queue_depth += scheduled_tasks
                found_queue_info = True
            except Exception as e:
                logger.debug(
                    "Error accessing scheduled tasks",
                    error=str(e)
                )
        
        # Check for ready tasks (don't add to queue depth as they're being processed)
        if hasattr(loop, '_ready'):
            try:
                ready_tasks = len(loop._ready)
                logger.debug(
                    "Found ready asyncio tasks",
                    ready_count=ready_tasks
                )
                # Don't add ready tasks to queue depth as they're being processed
            except Exception as e:
                logger.debug(
                    "Error accessing ready tasks",
                    error=str(e)
                )
        
        # Look for thread pool executor queue
        if hasattr(loop, '_default_executor'):
            executor = loop._default_executor
            if executor and hasattr(executor, '_work_queue'):
                work_queue = executor._work_queue
                if hasattr(work_queue, 'qsize') and callable(work_queue.qsize):
                    try:
                        executor_queue_size = work_queue.qsize()
                        logger.debug(
                            "Found thread pool executor queue",
                            executor_queue_size=executor_queue_size
                        )
                        queue_depth += executor_queue_size
                        found_queue_info = True
                    except Exception as e:
                        logger.debug(
                            "Error getting executor queue size",
                            error=str(e)
                        )
        
        # Only return a value if we found some meaningful queue information
        if found_queue_info and queue_depth >= 0:
            logger.debug(
                "Detected AsyncIO queue depth",
                total_queue_depth=queue_depth
            )
            return queue_depth
        
        return None
        
    except Exception as e:
        logger.debug(
            "Error detecting AsyncIO queue depth",
            error=str(e),
            error_type=type(e).__name__
        )
        return None


def _detect_system_level_queue() -> Optional[int]:
    """
    Detect request queue depth using system-level connection queue detection.
    
    Uses system-level tools to inspect network connection queues and
    socket backlogs that might indicate pending HTTP requests.
    
    Returns:
        Number of queued requests or None if detection fails
    """
    try:
        import socket
        import os
        
        # This is a more advanced approach that tries to inspect system-level queues
        # In practice, this is quite difficult to implement reliably across different
        # operating systems and configurations
        
        # Try to get information about listening sockets
        # This is a simplified approach - in a real implementation you might
        # use more sophisticated system inspection tools
        
        # For now, we'll implement a basic approach that looks for signs of
        # connection backlog, but this is inherently limited
        
        # Check if we can get process information
        pid = os.getpid()
        
        # Try to read network statistics (Linux-specific)
        try:
            if os.path.exists('/proc/net/tcp'):
                with open('/proc/net/tcp', 'r') as f:
                    lines = f.readlines()
                    # This would require parsing the TCP connection table
                    # to find listening sockets and their queue depths
                    # For now, we'll just log that we attempted this approach
                    logger.debug(
                        "Attempted system-level TCP queue inspection",
                        tcp_lines=len(lines),
                        approach="proc_net_tcp"
                    )
        except Exception:
            pass
        
        # This approach is quite complex and system-dependent
        # For the initial implementation, we'll return None to indicate
        # that this method is not yet fully implemented
        logger.debug("System-level queue detection not fully implemented")
        return None
        
    except Exception as e:
        logger.debug(
            "Error in system-level queue detection",
            error=str(e),
            error_type=type(e).__name__
        )
        return None


def _estimate_queue_from_metrics() -> Optional[int]:
    """
    Estimate queue depth from existing HTTP metrics correlation.
    
    Uses the relationship between requests in flight, active worker threads,
    and recent request rate to estimate how many requests might be queued.
    
    Returns:
        Estimated number of queued requests or None if estimation fails
    """
    try:
        # Get current metrics values - if these fail, we can't estimate
        active_workers = get_active_worker_count()
        total_workers = get_total_worker_count()
        
        # Try to get current requests in flight
        requests_in_flight = 0
        try:
            # Access the Prometheus gauge value
            if hasattr(HTTP_REQUESTS_IN_FLIGHT, '_value'):
                requests_in_flight = HTTP_REQUESTS_IN_FLIGHT._value._value
            elif hasattr(HTTP_REQUESTS_IN_FLIGHT, 'get'):
                requests_in_flight = HTTP_REQUESTS_IN_FLIGHT.get()
        except Exception as e:
            try:
                logger.debug(
                    "Could not get requests in flight metric",
                    error=str(e)
                )
            except Exception:
                # Ignore logger errors
                pass
            # Keep requests_in_flight as 0 when gauge access fails
            # This is not a fatal error - we can still estimate with worker counts
        
        # Basic estimation logic:
        # If we have more requests in flight than active workers,
        # the difference might represent queued requests
        estimated_queue = max(0, requests_in_flight - active_workers)
        
        # Apply some heuristics to make the estimate more reasonable
        if estimated_queue > 0:
            # Cap the estimate at a reasonable maximum based on total workers
            max_reasonable_queue = total_workers * 2  # Allow up to 2x worker count in queue
            estimated_queue = min(estimated_queue, max_reasonable_queue)
            
            try:
                logger.debug(
                    "Estimated queue depth from metrics correlation",
                    requests_in_flight=requests_in_flight,
                    active_workers=active_workers,
                    total_workers=total_workers,
                    estimated_queue=estimated_queue,
                    estimation_method="requests_minus_workers"
                )
            except Exception:
                # Ignore logger errors
                pass
            
            return estimated_queue
        
        # If no queue estimated, try alternative approach
        # Look for signs of thread saturation
        if active_workers >= total_workers and requests_in_flight > active_workers:
            # All workers are busy and we have more requests than workers
            # This suggests some queuing might be happening
            saturation_queue = min(requests_in_flight - active_workers, total_workers)
            
            try:
                logger.debug(
                    "Estimated queue from thread saturation",
                    active_workers=active_workers,
                    total_workers=total_workers,
                    requests_in_flight=requests_in_flight,
                    saturation_queue=saturation_queue,
                    estimation_method="saturation_based"
                )
            except Exception:
                # Ignore logger errors
                pass
            
            return saturation_queue
        
        # No queue detected through metrics correlation
        try:
            logger.debug(
                "No queue estimated from metrics correlation",
                requests_in_flight=requests_in_flight,
                active_workers=active_workers,
                total_workers=total_workers
            )
        except Exception:
            # Ignore logger errors
            pass
        return 0
        
    except Exception as e:
        try:
            logger.debug(
                "Error estimating queue from metrics correlation",
                error=str(e),
                error_type=type(e).__name__
            )
        except Exception:
            # Ignore logger errors
            pass
        # Return None when there are fundamental errors (like worker count failures)
        # This indicates complete failure of this estimation method
        return None


def _detect_uvicorn_thread_pool() -> Dict[str, Any]:
    """
    Detect Uvicorn's thread pool configuration and current state.
    
    Attempts to inspect the running Uvicorn server instance to determine
    thread pool configuration. This works with single-process uvicorn deployment.
    
    Returns:
        Dictionary with thread pool information or empty dict on failure
    """
    try:
        import sys
        import gc
        
        # Look for Uvicorn server instances in the garbage collector
        # This is a heuristic approach since Uvicorn doesn't expose thread pool info directly
        uvicorn_servers = []
        
        for obj in gc.get_objects():
            # Look for Uvicorn server objects
            if hasattr(obj, '__class__') and obj.__class__.__name__ == 'Server':
                module_name = getattr(obj.__class__, '__module__', '')
                if 'uvicorn' in module_name.lower():
                    uvicorn_servers.append(obj)
        
        if not uvicorn_servers:
            logger.debug("No Uvicorn server instances found in garbage collector")
            return {}
        
        # Examine the first Uvicorn server instance
        server = uvicorn_servers[0]
        thread_pool_info = {}
        
        # Try to get configuration from the server
        if hasattr(server, 'config'):
            config = server.config
            
            # Check for worker-related configuration
            if hasattr(config, 'workers') and config.workers:
                thread_pool_info['configured_workers'] = config.workers
            
            # Check for other thread-related settings
            if hasattr(config, 'limit_concurrency') and config.limit_concurrency:
                thread_pool_info['limit_concurrency'] = config.limit_concurrency
        
        # Try to inspect the server's thread pool executor if available
        if hasattr(server, 'force_exit'):
            # Look for thread pool in server attributes
            for attr_name in dir(server):
                attr_value = getattr(server, attr_name, None)
                if attr_value and hasattr(attr_value, '_max_workers'):
                    thread_pool_info['max_workers'] = attr_value._max_workers
                    thread_pool_info['detection_source'] = f'server.{attr_name}'
                    break
        
        if thread_pool_info:
            logger.debug(
                "Successfully detected Uvicorn thread pool configuration",
                thread_pool_info=thread_pool_info,
                server_count=len(uvicorn_servers)
            )
        else:
            logger.debug(
                "Found Uvicorn server but could not extract thread pool configuration",
                server_count=len(uvicorn_servers)
            )
        
        return thread_pool_info
        
    except Exception as e:
        logger.debug(
            "Error detecting Uvicorn thread pool configuration",
            error=str(e),
            error_type=type(e).__name__,
            fallback_result="empty_dict"
        )
        return {}


def _get_asyncio_thread_pool_info() -> Dict[str, Any]:
    """
    Get information about asyncio's default thread pool executor.
    
    FastAPI/Uvicorn uses asyncio's thread pool for blocking operations.
    This function inspects the current event loop's thread pool executor.
    
    Returns:
        Dictionary with thread pool executor information or empty dict on failure
    """
    try:
        import asyncio
        import concurrent.futures
        
        thread_pool_info = {}
        
        # Try to get the current event loop
        try:
            loop = asyncio.get_running_loop()
            logger.debug("Found running asyncio event loop")
        except RuntimeError:
            # No running loop, try to get the event loop policy's loop
            try:
                loop = asyncio.get_event_loop()
                logger.debug("Got asyncio event loop from policy")
            except Exception:
                logger.debug("No asyncio event loop available")
                return {}
        
        # Get the default thread pool executor
        if hasattr(loop, '_default_executor'):
            executor = loop._default_executor
            if executor:
                thread_pool_info['has_default_executor'] = True
                thread_pool_info['executor_type'] = type(executor).__name__
                
                # Check if it's a ThreadPoolExecutor
                if isinstance(executor, concurrent.futures.ThreadPoolExecutor):
                    if hasattr(executor, '_max_workers'):
                        thread_pool_info['max_workers'] = executor._max_workers
                        thread_pool_info['detection_source'] = 'asyncio_default_executor'
                    
                    if hasattr(executor, '_threads'):
                        thread_pool_info['current_threads'] = len(executor._threads)
                    
                    if hasattr(executor, '_idle_semaphore'):
                        # Try to get information about idle threads
                        try:
                            idle_count = executor._idle_semaphore._value
                            thread_pool_info['idle_threads'] = idle_count
                        except Exception:
                            pass
            else:
                thread_pool_info['has_default_executor'] = False
        
        # Also check the default thread pool executor class settings
        try:
            # Get the default max_workers calculation from ThreadPoolExecutor
            import os
            cpu_count = os.cpu_count()
            if cpu_count:
                # ThreadPoolExecutor default is min(32, (os.cpu_count() or 1) + 4)
                default_max_workers = min(32, cpu_count + 4)
                thread_pool_info['system_default_max_workers'] = default_max_workers
                thread_pool_info['cpu_count'] = cpu_count
        except Exception:
            pass
        
        if thread_pool_info:
            logger.debug(
                "Successfully gathered asyncio thread pool information",
                thread_pool_info=thread_pool_info
            )
        else:
            logger.debug("No asyncio thread pool information available")
        
        return thread_pool_info
        
    except Exception as e:
        logger.debug(
            "Error getting asyncio thread pool information",
            error=str(e),
            error_type=type(e).__name__,
            fallback_result="empty_dict"
        )
        return {}


def get_metrics_registry() -> Dict[str, Any]:
    """
    Get the current metrics registry for testing and debugging.
    
    Returns:
        Dictionary containing all registered metrics
    """
    return _METRICS_REGISTRY.copy()


def clear_metrics_registry() -> None:
    """
    Clear the metrics registry for testing purposes.
    
    Warning: This should only be used in tests to reset state.
    """
    global _METRICS_REGISTRY
    _METRICS_REGISTRY.clear()
    logger.debug("Metrics registry cleared")


def is_dummy_metric(metric: Any) -> bool:
    """
    Check if a metric is a dummy metric.
    
    Args:
        metric: Metric instance to check
        
    Returns:
        True if metric is a DummyMetric instance
    """
    return isinstance(metric, DummyMetric)


def get_metric_status() -> Dict[str, Dict[str, Any]]:
    """
    Get status information about all registered metrics.
    
    Returns:
        Dictionary with metric names and their status information
    """
    status = {}
    for name, metric in _METRICS_REGISTRY.items():
        status[name] = {
            'type': type(metric).__name__,
            'is_dummy': is_dummy_metric(metric),
            'class_module': type(metric).__module__
        }
    return status


# Global thread metrics collector instance
_thread_metrics_collector: Optional['ThreadMetricsCollector'] = None


def setup_thread_metrics(
    enable_thread_metrics: bool = True,
    update_interval: float = 1.0,
    debug_logging: bool = False
) -> Optional['ThreadMetricsCollector']:
    """
    Setup thread metrics collection.
    
    Integrates with existing monitoring infrastructure and creates a
    ThreadMetricsCollector that updates metrics when Prometheus scrapes.
    
    Args:
        enable_thread_metrics: Whether to enable thread metrics collection
        update_interval: Update interval in seconds for throttling
        debug_logging: Enable debug logging for thread metrics
        
    Returns:
        ThreadMetricsCollector instance if enabled, None if disabled
    """
    global _thread_metrics_collector
    
    if not enable_thread_metrics:
        logger.info(
            "Thread metrics collection disabled via configuration",
            enable_thread_metrics=False,
            reason="configuration_setting"
        )
        # Reset global collector when disabled
        _thread_metrics_collector = None
        return None
    
    try:
        # Create the thread metrics collector
        _thread_metrics_collector = ThreadMetricsCollector(update_interval=update_interval)
        
        # Register collector with Prometheus registry to trigger updates on scrape
        from prometheus_client import REGISTRY
        
        # Check if collector is already registered to avoid duplicate registration
        try:
            REGISTRY.register(_thread_metrics_collector)
            logger.info(
                "Thread metrics collector registered with Prometheus registry",
                update_interval=update_interval,
                debug_logging=debug_logging,
                registration_successful=True
            )
        except ValueError as e:
            if "Duplicated timeseries" in str(e) or "already registered" in str(e).lower():
                logger.warning(
                    "Thread metrics collector already registered - continuing with existing registration",
                    error=str(e),
                    registration_status="already_registered"
                )
            else:
                raise
        
        # Log successful setup
        logger.info(
            "Thread metrics collection enabled successfully",
            collector_type="ThreadMetricsCollector",
            update_interval=update_interval,
            debug_logging=debug_logging,
            metrics_collected=[
                "http_workers_active",
                "http_workers_total", 
                "http_workers_max_configured",
                "http_requests_queued"
            ],
            prometheus_integration=True,
            opentelemetry_integration=True
        )
        
        return _thread_metrics_collector
        
    except Exception as e:
        logger.error(
            "Failed to setup thread metrics collection",
            error=str(e),
            error_type=type(e).__name__,
            enable_thread_metrics=enable_thread_metrics,
            update_interval=update_interval,
            debug_logging=debug_logging,
            fallback_action="thread_metrics_disabled",
            exc_info=True
        )
        _thread_metrics_collector = None
        return None


def get_thread_metrics_collector() -> Optional['ThreadMetricsCollector']:
    """
    Get the current thread metrics collector instance.
    
    Returns:
        ThreadMetricsCollector instance if setup, None if not enabled
    """
    return _thread_metrics_collector


def is_thread_metrics_enabled() -> bool:
    """
    Check if thread metrics collection is currently enabled.
    
    Returns:
        True if thread metrics collector is active
    """
    return _thread_metrics_collector is not None


def _extract_route_pattern(request: Request) -> str:
    """
    Extract route pattern from request URL to prevent high cardinality metrics.
    
    Converts URLs with parameters to route patterns specific to the GlobeCo Portfolio Service.
    For example: /api/v1/portfolio/507f1f77bcf86cd799439011 -> /api/v1/portfolio/{portfolioId}
    
    Args:
        request: FastAPI Request object
        
    Returns:
        Route pattern string with parameterized IDs
    """
    try:
        path = request.url.path.rstrip('/')
        
        if not path:
            return "/"
        
        # Portfolio service specific route patterns
        if path.startswith("/api/v1/portfolio"):
            return _extract_portfolio_v1_route_pattern(path)
        elif path.startswith("/api/v2/portfolios"):
            return _extract_portfolio_v2_route_pattern(path)
        elif path == "/health":
            return "/health"
        elif path == "/metrics":
            return "/metrics"
        elif path == "/":
            return "/"
        
        # Fallback for unmatched routes
        return _sanitize_unmatched_route(path)
        
    except Exception as e:
        # Safely get path for logging without causing another exception
        try:
            path_for_logging = getattr(request.url, 'path', 'unknown')
            url_for_logging = str(request.url) if hasattr(request, 'url') else 'unknown'
        except Exception:
            path_for_logging = 'unknown'
            url_for_logging = 'unknown'
            
        logger.error(
            "Critical error in route pattern extraction - using fallback pattern",
            error=str(e),
            error_type=type(e).__name__,
            path=path_for_logging,
            url=url_for_logging,
            fallback_pattern="/unknown",
            impact="metrics_cardinality_protection",
            exc_info=True
        )
        return "/unknown"


def _extract_portfolio_v1_route_pattern(path: str) -> str:
    """
    Extract route pattern for v1 API portfolio endpoints.
    
    Handles:
    - /api/v1/portfolios (collection operations)
    - /api/v1/portfolio/{portfolioId} (individual portfolio operations)
    
    Args:
        path: URL path string
        
    Returns:
        Parameterized route pattern
    """
    parts = path.split("/")
    
    if len(parts) == 4:  # /api/v1/portfolios
        return "/api/v1/portfolios"
    elif len(parts) == 5:  # /api/v1/portfolio/{portfolioId}
        return "/api/v1/portfolio/{portfolioId}"
    
    # Fallback for unexpected v1 patterns
    return "/api/v1/portfolio/unknown"


def _extract_portfolio_v2_route_pattern(path: str) -> str:
    """
    Extract route pattern for v2 API portfolio endpoints.
    
    Handles:
    - /api/v2/portfolios (search with query parameters)
    
    Args:
        path: URL path string
        
    Returns:
        Parameterized route pattern
    """
    parts = path.split("/")
    
    if len(parts) == 4:  # /api/v2/portfolios
        return "/api/v2/portfolios"
    
    # Fallback for unexpected v2 patterns
    return "/api/v2/portfolios/unknown"


def _sanitize_unmatched_route(path: str) -> str:
    """
    Sanitize unmatched routes to prevent high cardinality metrics.
    
    This method handles routes that don't match the known portfolio service patterns
    by parameterizing ID-like path segments to prevent metric explosion.
    
    The function detects and parameterizes various ID formats:
    - MongoDB ObjectIds (24-char hex) -> {id}
    - UUIDs (with/without hyphens) -> {id}
    - Numeric IDs -> {id}
    - Long alphanumeric identifiers -> {id}
    
    Args:
        path: URL path string
        
    Returns:
        Sanitized route pattern with IDs parameterized
    """
    try:
        parts = path.split("/")
        sanitized_parts = []
        
        for part in parts:
            if not part:
                # Keep empty parts (for leading/trailing slashes)
                sanitized_parts.append(part)
                continue
            
            # Check if part looks like an ID that should be parameterized
            if _looks_like_id(part):
                sanitized_parts.append("{id}")
                logger.debug(
                    "Parameterized ID in unmatched route",
                    original_part=part,
                    path=path
                )
            else:
                # Keep the original part but limit length to prevent abuse
                sanitized_part = part[:50] if len(part) > 50 else part
                sanitized_parts.append(sanitized_part)
                
                # Log if we truncated a long part
                if len(part) > 50:
                    logger.debug(
                        "Truncated long path segment in unmatched route",
                        original_length=len(part),
                        truncated_part=sanitized_part,
                        path=path
                    )
        
        result = "/".join(sanitized_parts)
        
        # Ensure we don't create overly long patterns
        if len(result) > 200:
            logger.warning(
                "Route pattern exceeds maximum length after sanitization - using fallback",
                original_path=path,
                sanitized_pattern=result[:50] + "..." if len(result) > 50 else result,
                sanitized_length=len(result),
                max_allowed_length=200,
                fallback_pattern="/unknown",
                reason="length_protection"
            )
            return "/unknown"
        
        # Log the sanitization result for debugging
        if result != path:
            logger.debug(
                "Successfully sanitized unmatched route pattern",
                original_path=path,
                sanitized_pattern=result,
                path_segments_count=len(parts),
                parameterized_segments=sum(1 for part in sanitized_parts if part == "{id}"),
                truncated_segments=sum(1 for i, part in enumerate(parts) if part and len(part) > 50 and sanitized_parts[i] != "{id}")
            )
        
        return result
        
    except Exception as e:
        logger.error(
            "Critical error during route sanitization - using fallback pattern",
            error=str(e),
            error_type=type(e).__name__,
            path=path,
            fallback_pattern="/unknown",
            impact="metrics_cardinality_protection",
            exc_info=True
        )
        return "/unknown"


def _looks_like_id(part: str) -> bool:
    """
    Check if a path part looks like an ID that should be parameterized.
    
    Detects various ID formats commonly used in APIs:
    - MongoDB ObjectId (24-character hexadecimal)
    - UUID (with or without hyphens)
    - Numeric IDs
    - Long alphanumeric identifiers
    
    Args:
        part: Path segment to check
        
    Returns:
        True if the part looks like an ID that should be parameterized
    """
    try:
        # Early return for empty or None
        if not part:
            return False
        
        # MongoDB ObjectId (exactly 24 character hex)
        if _is_mongodb_objectid(part):
            return True
        
        # UUID format (with hyphens: exactly 8-4-4-4-12 format)
        if _is_uuid_with_hyphens(part):
            return True
        
        # UUID format (without hyphens: exactly 32 character hex)
        if _is_uuid_without_hyphens(part):
            return True
        
        # Numeric ID (pure digits)
        if _is_numeric_id(part):
            return True
        
        # Long alphanumeric ID that looks like an identifier
        if _is_alphanumeric_id(part):
            return True
        
        return False
        
    except Exception:
        # If any error occurs during ID detection, err on the side of caution
        return False


def _is_mongodb_objectid(part: str) -> bool:
    """
    Check if a path part is a MongoDB ObjectId.
    
    MongoDB ObjectIds are exactly 24 characters long and contain only hexadecimal characters.
    
    Args:
        part: Path segment to check
        
    Returns:
        True if the part looks like a MongoDB ObjectId
    """
    if len(part) != 24:
        return False
    
    return all(c in '0123456789abcdefABCDEF' for c in part)


def _is_uuid_with_hyphens(part: str) -> bool:
    """
    Check if a path part is a UUID with hyphens.
    
    Standard UUID format: 8-4-4-4-12 hexadecimal characters separated by hyphens.
    Example: 550e8400-e29b-41d4-a716-446655440000
    
    Args:
        part: Path segment to check
        
    Returns:
        True if the part looks like a UUID with hyphens
    """
    if len(part) != 36 or part.count('-') != 4:
        return False
    
    uuid_parts = part.split('-')
    if (len(uuid_parts) != 5 or 
        len(uuid_parts[0]) != 8 or len(uuid_parts[1]) != 4 or 
        len(uuid_parts[2]) != 4 or len(uuid_parts[3]) != 4 or 
        len(uuid_parts[4]) != 12):
        return False
    
    # Check if all parts are hexadecimal
    try:
        for uuid_part in uuid_parts:
            int(uuid_part, 16)
        return True
    except ValueError:
        return False


def _is_uuid_without_hyphens(part: str) -> bool:
    """
    Check if a path part is a UUID without hyphens.
    
    UUID without hyphens: exactly 32 hexadecimal characters.
    Example: 550e8400e29b41d4a716446655440000
    
    Args:
        part: Path segment to check
        
    Returns:
        True if the part looks like a UUID without hyphens
    """
    if len(part) != 32:
        return False
    
    return all(c in '0123456789abcdefABCDEF' for c in part)


def _is_numeric_id(part: str) -> bool:
    """
    Check if a path part is a numeric ID.
    
    Numeric IDs are strings containing only digits.
    Examples: "123", "456789", "1"
    
    Args:
        part: Path segment to check
        
    Returns:
        True if the part looks like a numeric ID
    """
    return part.isdigit() and len(part) >= 1


def _is_alphanumeric_id(part: str) -> bool:
    """
    Check if a path part is a long alphanumeric identifier.
    
    Alphanumeric IDs are longer identifiers that contain both letters and numbers,
    but are not in the specific formats of ObjectId or UUID.
    
    Criteria:
    - Longer than 8 characters
    - Contains only alphanumeric characters, hyphens, and underscores
    - Must contain at least one digit (number)
    - Not in the 20-40 character range (to avoid confusion with malformed ObjectIds/UUIDs)
    
    Examples: "user-abc123def", "session_token_xyz789"
    
    Args:
        part: Path segment to check
        
    Returns:
        True if the part looks like an alphanumeric ID
    """
    if len(part) <= 8:
        return False
    
    # Must be alphanumeric with allowed separators
    if not part.replace('-', '').replace('_', '').isalnum():
        return False
    
    # Must contain at least one digit (not just letters and separators)
    if not any(c.isdigit() for c in part):
        return False
    
    # Exclude strings that might be malformed hex IDs (close to ObjectId/UUID length)
    if 20 <= len(part) <= 40:
        return False
    
    return True


def _get_method_label(method: str) -> str:
    """
    Format HTTP method as uppercase string for consistent labeling.
    
    Converts HTTP method names to uppercase and validates against known methods.
    Falls back to safe defaults for invalid or unknown methods.
    
    Args:
        method: HTTP method string (e.g., 'get', 'POST', 'Put')
        
    Returns:
        Uppercase HTTP method string or 'UNKNOWN' for invalid methods
    """
    try:
        # Handle None or non-string input
        if not isinstance(method, str):
            logger.warning(
                "Invalid method type for label formatting",
                method=method,
                method_type=type(method).__name__
            )
            return "UNKNOWN"
        
        # Strip whitespace and convert to uppercase
        method_upper = method.strip().upper()
        
        # Handle empty string after stripping
        if not method_upper:
            logger.warning("Empty method string after stripping whitespace")
            return "UNKNOWN"
        
        # Define valid HTTP methods according to RFC 7231 and common extensions
        valid_methods = {
            "GET", "POST", "PUT", "DELETE", "PATCH",
            "HEAD", "OPTIONS", "TRACE", "CONNECT"
        }
        
        # Log warning for unknown methods but still return them
        # This allows for custom methods while maintaining visibility
        if method_upper not in valid_methods:
            logger.debug(
                "Non-standard HTTP method encountered - allowing but logging for visibility",
                method=method,
                method_upper=method_upper,
                valid_methods=list(valid_methods),
                action="allow_with_logging"
            )
        
        return method_upper
        
    except Exception as e:
        logger.error(
            "Critical error formatting HTTP method label - using fallback",
            error=str(e),
            error_type=type(e).__name__,
            method=method,
            method_type=type(method).__name__ if method is not None else "NoneType",
            fallback_value="UNKNOWN",
            exc_info=True
        )
        return "UNKNOWN"


def _format_status_code(status_code: int) -> str:
    """
    Format HTTP status code as string for consistent labeling.
    
    Converts numeric HTTP status codes to strings and validates they are
    within the valid HTTP status code range (100-599).
    
    Args:
        status_code: HTTP status code integer (e.g., 200, 404, 500)
        
    Returns:
        Status code as string or 'unknown' for invalid codes
    """
    try:
        # Handle None or non-integer input
        if not isinstance(status_code, int):
            logger.warning(
                "Invalid status code type for label formatting",
                status_code=status_code,
                status_code_type=type(status_code).__name__
            )
            return "unknown"
        
        # Validate status code is within valid HTTP range
        # HTTP status codes are defined as 100-599 in RFC 7231
        if status_code < 100 or status_code > 599:
            logger.warning(
                "HTTP status code outside valid range - using fallback",
                status_code=status_code,
                valid_range="100-599",
                fallback_value="unknown",
                rfc_reference="RFC 7231"
            )
            return "unknown"
        
        # Convert to string for consistent labeling
        status_str = str(status_code)
        logger.debug(
            "Successfully formatted status code label",
            status_code=status_code,
            formatted_label=status_str
        )
        return status_str
        
    except Exception as e:
        logger.error(
            "Critical error formatting HTTP status code label - using fallback",
            error=str(e),
            error_type=type(e).__name__,
            status_code=status_code,
            status_code_type=type(status_code).__name__ if status_code is not None else "NoneType",
            fallback_value="unknown",
            exc_info=True
        )
        return "unknown"


class ThreadMetricsCollector:
    """
    Collector that updates thread metrics on demand with throttling.
    
    This collector integrates with Prometheus collection mechanism to update
    thread metrics whenever the /metrics endpoint is scraped. It includes
    update throttling to prevent excessive collection and handles both
    Prometheus and OpenTelemetry metrics.
    """
    
    def __init__(self, update_interval: float = 1.0):
        """
        Initialize the thread metrics collector.
        
        Args:
            update_interval: Minimum interval between updates in seconds (default: 1.0)
        """
        self.update_interval = update_interval
        self.last_update = 0.0
        
        # Track OpenTelemetry metric values for delta updates
        self._otel_values = {
            'workers_active': 0,
            'workers_total': 0,
            'workers_max_configured': 0,
            'requests_queued': 0
        }
        
        logger.info(
            "ThreadMetricsCollector initialized",
            update_interval=self.update_interval,
            throttling_enabled=True,
            metrics_tracked=list(self._otel_values.keys())
        )
    
    def collect(self):
        """
        Collect and update all thread metrics.
        
        Called by Prometheus client during metrics export. Implements
        throttling to prevent excessive updates and handles both
        Prometheus and OpenTelemetry metrics.
        """
        current_time = time.time()
        
        # Check if we should skip update due to throttling
        if current_time - self.last_update < self.update_interval:
            logger.debug(
                "Skipping thread metrics update due to throttling",
                time_since_last_update=current_time - self.last_update,
                update_interval=self.update_interval,
                throttling_active=True
            )
            return
        
        logger.debug(
            "Starting thread metrics collection",
            time_since_last_update=current_time - self.last_update,
            throttling_bypassed=True
        )
        
        # Update worker thread metrics (with individual error handling)
        try:
            self._update_worker_metrics()
        except Exception as e:
            logger.error(
                "Failed to update worker metrics during collection",
                error=str(e),
                error_type=type(e).__name__,
                impact="worker_metrics_may_be_stale",
                exc_info=True
            )
        
        # Update request queue metrics (with individual error handling)
        try:
            self._update_queue_metrics()
        except Exception as e:
            logger.error(
                "Failed to update queue metrics during collection",
                error=str(e),
                error_type=type(e).__name__,
                impact="queue_metrics_may_be_stale",
                exc_info=True
            )
        
        # Update last update timestamp
        self.last_update = current_time
        
        logger.debug(
            "Thread metrics collection completed",
            collection_time=time.time() - current_time,
            next_update_allowed_at=self.last_update + self.update_interval
        )
    
    def _update_worker_metrics(self):
        """
        Update worker thread count metrics for both Prometheus and OpenTelemetry.
        
        Collects current worker thread counts and updates both metric systems
        with proper error handling and delta calculations for OpenTelemetry.
        """
        try:
            # Get current worker thread counts
            active_count = get_active_worker_count()
            total_count = get_total_worker_count()
            max_configured = get_max_configured_workers()
            
            logger.debug(
                "Collected worker thread counts",
                active_workers=active_count,
                total_workers=total_count,
                max_configured_workers=max_configured
            )
            
            # Update Prometheus metrics (for /metrics endpoint)
            try:
                HTTP_WORKERS_ACTIVE.set(active_count)
                HTTP_WORKERS_TOTAL.set(total_count)
                HTTP_WORKERS_MAX_CONFIGURED.set(max_configured)
                
                logger.debug(
                    "Updated Prometheus worker metrics",
                    active_workers=active_count,
                    total_workers=total_count,
                    max_configured_workers=max_configured
                )
                
            except Exception as e:
                logger.error(
                    "Failed to update Prometheus worker metrics",
                    error=str(e),
                    error_type=type(e).__name__,
                    active_count=active_count,
                    total_count=total_count,
                    max_configured=max_configured,
                    exc_info=True
                )
            
            # Update OpenTelemetry metrics (for collector export)
            try:
                # Calculate deltas for UpDownCounter metrics
                active_delta = active_count - self._otel_values['workers_active']
                total_delta = total_count - self._otel_values['workers_total']
                max_configured_delta = max_configured - self._otel_values['workers_max_configured']
                
                # Update OpenTelemetry metrics with deltas
                if active_delta != 0:
                    otel_http_workers_active.add(active_delta)
                    self._otel_values['workers_active'] = active_count
                
                if total_delta != 0:
                    otel_http_workers_total.add(total_delta)
                    self._otel_values['workers_total'] = total_count
                
                if max_configured_delta != 0:
                    otel_http_workers_max_configured.add(max_configured_delta)
                    self._otel_values['workers_max_configured'] = max_configured
                
                logger.debug(
                    "Updated OpenTelemetry worker metrics",
                    active_delta=active_delta,
                    total_delta=total_delta,
                    max_configured_delta=max_configured_delta,
                    new_otel_values={
                        'active': self._otel_values['workers_active'],
                        'total': self._otel_values['workers_total'],
                        'max_configured': self._otel_values['workers_max_configured']
                    }
                )
                
            except Exception as e:
                logger.error(
                    "Failed to update OpenTelemetry worker metrics",
                    error=str(e),
                    error_type=type(e).__name__,
                    active_count=active_count,
                    total_count=total_count,
                    max_configured=max_configured,
                    current_otel_values=self._otel_values.copy(),
                    exc_info=True
                )
                
        except Exception as e:
            logger.error(
                "Failed to collect worker thread counts",
                error=str(e),
                error_type=type(e).__name__,
                impact="worker_metrics_not_updated",
                exc_info=True
            )
    
    def _update_queue_metrics(self):
        """
        Update request queue depth metrics for both Prometheus and OpenTelemetry.
        
        Collects current request queue depth and updates both metric systems
        with proper error handling and delta calculations for OpenTelemetry.
        """
        try:
            # Get current queue depth
            queued_count = get_queued_requests_count()
            
            logger.debug(
                "Collected request queue depth",
                queued_requests=queued_count
            )
            
            # Update Prometheus metrics (for /metrics endpoint)
            try:
                HTTP_REQUESTS_QUEUED.set(queued_count)
                
                logger.debug(
                    "Updated Prometheus queue metrics",
                    queued_requests=queued_count
                )
                
            except Exception as e:
                logger.error(
                    "Failed to update Prometheus queue metrics",
                    error=str(e),
                    error_type=type(e).__name__,
                    queued_count=queued_count,
                    exc_info=True
                )
            
            # Update OpenTelemetry metrics (for collector export)
            try:
                # Calculate delta for UpDownCounter metric
                queued_delta = queued_count - self._otel_values['requests_queued']
                
                # Update OpenTelemetry metric with delta
                if queued_delta != 0:
                    otel_http_requests_queued.add(queued_delta)
                    self._otel_values['requests_queued'] = queued_count
                
                logger.debug(
                    "Updated OpenTelemetry queue metrics",
                    queued_delta=queued_delta,
                    new_otel_value=self._otel_values['requests_queued']
                )
                
            except Exception as e:
                logger.error(
                    "Failed to update OpenTelemetry queue metrics",
                    error=str(e),
                    error_type=type(e).__name__,
                    queued_count=queued_count,
                    current_otel_value=self._otel_values['requests_queued'],
                    exc_info=True
                )
                
        except Exception as e:
            logger.error(
                "Failed to collect request queue depth",
                error=str(e),
                error_type=type(e).__name__,
                impact="queue_metrics_not_updated",
                exc_info=True
            )
    
    def get_last_update_time(self) -> float:
        """
        Get the timestamp of the last metrics update.
        
        Returns:
            Timestamp of last update (0.0 if never updated)
        """
        return self.last_update
    
    def get_update_interval(self) -> float:
        """
        Get the configured update interval.
        
        Returns:
            Update interval in seconds
        """
        return self.update_interval
    
    def set_update_interval(self, interval: float):
        """
        Set a new update interval.
        
        Args:
            interval: New update interval in seconds
        """
        if interval <= 0:
            raise ValueError("Update interval must be positive")
        
        old_interval = self.update_interval
        self.update_interval = interval
        
        logger.info(
            "Thread metrics collector update interval changed",
            old_interval=old_interval,
            new_interval=self.update_interval
        )
    
    def force_update(self):
        """
        Force an immediate metrics update, bypassing throttling.
        
        This method should be used sparingly and primarily for testing
        or when immediate metrics updates are required.
        """
        logger.info(
            "Forcing immediate thread metrics update",
            bypassing_throttling=True,
            time_since_last_update=time.time() - self.last_update
        )
        
        # Temporarily reset last_update to force collection
        original_last_update = self.last_update
        self.last_update = 0.0
        
        # Call collect which will update the timestamp
        self.collect()
    
    def get_current_otel_values(self) -> Dict[str, int]:
        """
        Get the current OpenTelemetry metric values being tracked.
        
        Returns:
            Dictionary of current OpenTelemetry metric values
        """
        return self._otel_values.copy()


class EnhancedHTTPMetricsMiddleware(BaseHTTPMiddleware):
    """
    Enhanced middleware to collect standardized HTTP request metrics.

    This middleware implements the standardized HTTP metrics with proper timing,
    in-flight tracking, and comprehensive error handling using Prometheus.
    
    Collects three core metrics:
    - http_requests_total: Counter of total HTTP requests
    - http_request_duration: Histogram of request durations in milliseconds
    - http_requests_in_flight: Gauge of currently processing requests
    """

    def __init__(self, app, debug_logging: bool = False):
        """
        Initialize the middleware.
        
        Args:
            app: ASGI application
            debug_logging: Enable debug logging for metrics collection
        """
        super().__init__(app)
        self.debug_logging = debug_logging
        
        # Log middleware initialization with comprehensive details
        logger.info(
            "EnhancedHTTPMetricsMiddleware initialized successfully",
            debug_logging_enabled=self.debug_logging,
            middleware_version="enhanced",
            metrics_collected=["http_requests_total", "http_request_duration", "http_requests_in_flight"],
            timing_precision="milliseconds",
            error_handling="comprehensive"
        )
        
        if self.debug_logging:
            logger.debug(
                "Debug logging enabled for HTTP metrics middleware - verbose metrics information will be logged",
                log_level="debug",
                performance_impact="minimal",
                recommended_for="development_and_troubleshooting"
            )
            
        # Validate that metrics are available
        try:
            # Test that metrics are accessible
            if is_dummy_metric(HTTP_REQUESTS_TOTAL):
                logger.warning(
                    "HTTP requests total counter is using dummy metric - metrics may not be recorded",
                    metric_name="http_requests_total",
                    metric_type="DummyMetric",
                    impact="counter_metrics_disabled"
                )
            
            if is_dummy_metric(HTTP_REQUEST_DURATION):
                logger.warning(
                    "HTTP request duration histogram is using dummy metric - duration metrics may not be recorded",
                    metric_name="http_request_duration",
                    metric_type="DummyMetric",
                    impact="duration_metrics_disabled"
                )
                
            if is_dummy_metric(HTTP_REQUESTS_IN_FLIGHT):
                logger.warning(
                    "HTTP requests in-flight gauge is using dummy metric - in-flight metrics may not be recorded",
                    metric_name="http_requests_in_flight",
                    metric_type="DummyMetric",
                    impact="in_flight_metrics_disabled"
                )
                
        except Exception as e:
            logger.error(
                "Error validating metrics during middleware initialization",
                error=str(e),
                error_type=type(e).__name__,
                impact="metrics_validation_failed",
                exc_info=True
            )

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """
        Process request and collect all three standardized HTTP metrics.

        Uses high-precision timing with time.perf_counter() for millisecond accuracy.
        Implements comprehensive error handling to ensure metrics are recorded
        even when request processing fails.

        Args:
            request: The incoming HTTP request
            call_next: The next middleware/endpoint to call

        Returns:
            Response with metrics recorded for the request
        """
        # Start high-precision timing using perf_counter for millisecond precision
        start_time = time.perf_counter()
        
        # Extract basic request information for logging
        request_method = getattr(request, 'method', 'UNKNOWN')
        request_path = 'unknown'
        request_url = 'unknown'
        
        try:
            if hasattr(request, 'url'):
                request_path = getattr(request.url, 'path', 'unknown')
                request_url = str(request.url)
        except Exception as e:
            logger.debug(
                "Could not extract request URL information for logging",
                error=str(e),
                fallback_path=request_path,
                fallback_url=request_url
            )

        if self.debug_logging:
            logger.debug(
                "Starting HTTP request processing with metrics collection",
                method=request_method,
                path=request_path,
                url=request_url,
                start_time=start_time,
                timing_precision="perf_counter_milliseconds"
            )

        # Increment in-flight requests gauge with error protection
        in_flight_incremented = False
        otel_in_flight_incremented = False
        
        # Increment Prometheus in-flight gauge
        try:
            HTTP_REQUESTS_IN_FLIGHT.inc()
            in_flight_incremented = True
            if self.debug_logging:
                logger.debug(
                    "Successfully incremented Prometheus in-flight requests gauge",
                    method=request_method,
                    path=request_path,
                    gauge_operation="increment"
                )
        except Exception as e:
            logger.error(
                "Failed to increment Prometheus in-flight requests gauge - continuing request processing",
                error=str(e),
                error_type=type(e).__name__,
                method=request_method,
                path=request_path,
                gauge_operation="increment",
                impact="in_flight_prometheus_metrics_disabled",
                exc_info=True,
            )
        
        # Increment OpenTelemetry in-flight gauge
        try:
            otel_http_requests_in_flight.add(1)
            otel_in_flight_incremented = True
            if self.debug_logging:
                logger.debug(
                    "Successfully incremented OpenTelemetry in-flight requests gauge",
                    method=request_method,
                    path=request_path,
                    gauge_operation="increment"
                )
        except Exception as e:
            logger.error(
                "Failed to increment OpenTelemetry in-flight requests gauge - continuing request processing",
                error=str(e),
                error_type=type(e).__name__,
                method=request_method,
                path=request_path,
                gauge_operation="increment",
                impact="in_flight_otel_metrics_disabled",
                exc_info=True,
            )

        try:
            # Process the request through the application
            response = await call_next(request)

            # Calculate duration in milliseconds with high precision
            duration_ms = (time.perf_counter() - start_time) * 1000

            # Extract labels for metrics
            method = _get_method_label(request.method)
            path = _extract_route_pattern(request)
            status = _format_status_code(response.status_code)

            # Record all three metrics with comprehensive error handling
            try:
                self._record_metrics(method, path, status, duration_ms)
            except Exception as metrics_error:
                logger.error(
                    "Failed to record metrics for successful request - continuing request processing",
                    error=str(metrics_error),
                    error_type=type(metrics_error).__name__,
                    method=method,
                    path=path,
                    status=status,
                    duration_ms=round(duration_ms, 2),
                    impact="metrics_recording_failed_but_request_succeeded",
                    exc_info=True
                )

            # Log slow requests (> 1000ms) for performance monitoring
            if duration_ms > 1000:
                logger.warning(
                    "Slow request detected - performance monitoring alert",
                    method=method,
                    path=path,
                    duration_ms=round(duration_ms, 2),
                    status=status,
                    request_url=str(request.url) if hasattr(request, 'url') else 'unknown',
                    slow_request_threshold_ms=1000,
                    performance_impact="high"
                )
                
                # Additional debug info for slow requests if debug logging is enabled
                if self.debug_logging:
                    logger.debug(
                        "Slow request debug information",
                        method=method,
                        path=path,
                        duration_ms=round(duration_ms, 2),
                        status=status,
                        request_headers=dict(request.headers) if hasattr(request, 'headers') else {},
                        client_host=getattr(request.client, 'host', 'unknown') if hasattr(request, 'client') else 'unknown',
                        query_params=str(request.url.query) if hasattr(request, 'url') and hasattr(request.url, 'query') else 'none'
                    )

            return response

        except Exception as e:
            # Calculate duration even for exceptions to maintain accurate metrics
            duration_ms = (time.perf_counter() - start_time) * 1000

            # Extract labels for error metrics with comprehensive error handling
            method = "UNKNOWN"
            path = "/unknown"
            
            try:
                method = _get_method_label(request.method)
            except Exception as method_error:
                logger.debug(
                    "Could not extract method for error metrics",
                    error=str(method_error),
                    fallback_method=method
                )
                
            try:
                path = _extract_route_pattern(request)
            except Exception as path_error:
                logger.debug(
                    "Could not extract path pattern for error metrics",
                    error=str(path_error),
                    fallback_path=path
                )
            
            status = "500"  # All exceptions result in 500 status for metrics

            # Record metrics even when exceptions occur
            try:
                self._record_metrics(method, path, status, duration_ms)
                if self.debug_logging:
                    logger.debug(
                        "Successfully recorded metrics for failed request",
                        method=method,
                        path=path,
                        status=status,
                        duration_ms=round(duration_ms, 2)
                    )
            except Exception as metrics_error:
                logger.error(
                    "Failed to record metrics for failed request - double error condition",
                    original_error=str(e),
                    metrics_error=str(metrics_error),
                    method=method,
                    path=path,
                    status=status,
                    duration_ms=round(duration_ms, 2),
                    impact="metrics_recording_failed"
                )

            logger.error(
                "Request processing failed - attempted metrics collection for error case",
                error=str(e),
                error_type=type(e).__name__,
                method=method,
                path=path,
                status=status,
                duration_ms=round(duration_ms, 2),
                request_url=request_url,
                error_handling="metrics_recorded_for_500_status",
                exc_info=True,
            )

            # Re-raise the exception to maintain normal error handling
            raise
        finally:
            # Always decrement in-flight requests gauge
            # Only decrement if we successfully incremented to avoid negative values
            if in_flight_incremented:
                try:
                    HTTP_REQUESTS_IN_FLIGHT.dec()
                    if self.debug_logging:
                        logger.debug(
                            "Successfully decremented Prometheus in-flight requests gauge",
                            method=request_method,
                            path=request_path,
                            gauge_operation="decrement"
                        )
                except Exception as e:
                    logger.error(
                        "Critical error decrementing Prometheus in-flight requests gauge - gauge may be inaccurate",
                        error=str(e),
                        error_type=type(e).__name__,
                        method=request_method,
                        path=request_path,
                        gauge_operation="decrement",
                        impact="prometheus_gauge_accuracy_compromised",
                        mitigation="gauge_will_self_correct_over_time",
                        exc_info=True,
                    )
            else:
                if self.debug_logging:
                    logger.debug(
                        "Skipping Prometheus in-flight gauge decrement - was not incremented",
                        method=request_method,
                        path=request_path,
                        reason="increment_failed_or_skipped"
                    )
            
            # Decrement OpenTelemetry in-flight gauge
            if otel_in_flight_incremented:
                try:
                    otel_http_requests_in_flight.add(-1)
                    if self.debug_logging:
                        logger.debug(
                            "Successfully decremented OpenTelemetry in-flight requests gauge",
                            method=request_method,
                            path=request_path,
                            gauge_operation="decrement"
                        )
                except Exception as e:
                    logger.error(
                        "Critical error decrementing OpenTelemetry in-flight requests gauge - gauge may be inaccurate",
                        error=str(e),
                        error_type=type(e).__name__,
                        method=request_method,
                        path=request_path,
                        gauge_operation="decrement",
                        impact="otel_gauge_accuracy_compromised",
                        mitigation="gauge_will_self_correct_over_time",
                        exc_info=True,
                    )
            else:
                if self.debug_logging:
                    logger.debug(
                        "Skipping OpenTelemetry in-flight gauge decrement - was not incremented",
                        method=request_method,
                        path=request_path,
                        reason="increment_failed_or_skipped"
                    )

    def _record_metrics(
        self, method: str, path: str, status: str, duration_ms: float
    ) -> None:
        """
        Record all three HTTP metrics with comprehensive error handling.
        
        Records metrics to both:
        - Prometheus (exposed via /metrics endpoint)
        - OpenTelemetry (sent to collector and then to Prometheus)

        Args:
            method: HTTP method (uppercase)
            path: Route pattern with parameterized IDs
            status: HTTP status code as string
            duration_ms: Request duration in milliseconds
        """
        # Debug logging for metric values during development
        if self.debug_logging:
            logger.debug(
                "Recording HTTP metrics to both Prometheus and OpenTelemetry",
                method=method,
                path=path,
                status=status,
                duration_ms=duration_ms,
            )

        # Prepare attributes for OpenTelemetry metrics
        otel_attributes = {
            "method": method,
            "path": path,
            "status": status
        }

        # Record Prometheus counter metrics with error handling
        try:
            HTTP_REQUESTS_TOTAL.labels(method=method, path=path, status=status).inc()
            if self.debug_logging:
                logger.debug(
                    "Successfully recorded Prometheus HTTP requests total counter",
                    method=method,
                    path=path,
                    status=status,
                )
        except Exception as e:
            logger.error(
                "Failed to record Prometheus HTTP requests total counter",
                error=str(e),
                error_type=type(e).__name__,
                method=method,
                path=path,
                status=status,
                exc_info=True,
            )

        # Record Prometheus histogram metrics with error handling
        try:
            HTTP_REQUEST_DURATION.labels(method=method, path=path, status=status).observe(duration_ms)
            if self.debug_logging:
                logger.debug(
                    "Successfully recorded Prometheus HTTP request duration histogram",
                    method=method,
                    path=path,
                    status=status,
                    duration_ms=duration_ms,
                )
        except Exception as e:
            logger.error(
                "Failed to record Prometheus HTTP request duration histogram",
                error=str(e),
                error_type=type(e).__name__,
                method=method,
                path=path,
                status=status,
                duration_ms=duration_ms,
                exc_info=True,
            )

        # Record OpenTelemetry counter metrics with error handling
        try:
            otel_http_requests_total.add(1, attributes=otel_attributes)
            if self.debug_logging:
                logger.debug(
                    "Successfully recorded OpenTelemetry HTTP requests total counter",
                    method=method,
                    path=path,
                    status=status,
                )
        except Exception as e:
            logger.error(
                "Failed to record OpenTelemetry HTTP requests total counter",
                error=str(e),
                error_type=type(e).__name__,
                method=method,
                path=path,
                status=status,
                exc_info=True,
            )

        # Record OpenTelemetry histogram metrics with error handling
        try:
            otel_http_request_duration.record(duration_ms, attributes=otel_attributes)
            if self.debug_logging:
                logger.debug(
                    "Successfully recorded OpenTelemetry HTTP request duration histogram",
                    method=method,
                    path=path,
                    status=status,
                    duration_ms=duration_ms,
                )
        except Exception as e:
            logger.error(
                "Failed to record OpenTelemetry HTTP request duration histogram",
                error=str(e),
                error_type=type(e).__name__,
                method=method,
                path=path,
                status=status,
                duration_ms=duration_ms,
                exc_info=True,
            )

        # Record OpenTelemetry counter metrics with error handling
        try:
            otel_http_requests_total.add(1, attributes=otel_attributes)
            if self.debug_logging:
                logger.debug(
                    "Successfully recorded OpenTelemetry HTTP requests total counter",
                    method=method,
                    path=path,
                    status=status,
                )
        except Exception as e:
            logger.error(
                "Failed to record OpenTelemetry HTTP requests total counter",
                error=str(e),
                error_type=type(e).__name__,
                method=method,
                path=path,
                status=status,
                exc_info=True,
            )

        # Record Prometheus histogram metrics with error handling
        try:
            HTTP_REQUEST_DURATION.labels(
                method=method, path=path, status=status
            ).observe(duration_ms)
            if self.debug_logging:
                logger.debug(
                    "Successfully recorded Prometheus HTTP request duration histogram",
                    method=method,
                    path=path,
                    status=status,
                    duration_ms=duration_ms,
                )
        except Exception as e:
            logger.error(
                "Failed to record Prometheus HTTP request duration histogram",
                error=str(e),
                error_type=type(e).__name__,
                method=method,
                path=path,
                status=status,
                duration_ms=duration_ms,
                exc_info=True,
            )

        # Record OpenTelemetry histogram metrics with error handling
        try:
            otel_http_request_duration.record(duration_ms, attributes=otel_attributes)
            if self.debug_logging:
                logger.debug(
                    "Successfully recorded OpenTelemetry HTTP request duration histogram",
                    method=method,
                    path=path,
                    status=status,
                    duration_ms=duration_ms,
                )
        except Exception as e:
            logger.error(
                "Failed to record OpenTelemetry HTTP request duration histogram",
                error=str(e),
                error_type=type(e).__name__,
                method=method,
                path=path,
                status=status,
                duration_ms=duration_ms,
                exc_info=True,
            )


# Initialize metrics on module import
logger.info("Enhanced HTTP metrics monitoring module initialized")
logger.info(f"Metrics registry contains {len(_METRICS_REGISTRY)} metrics")

# Log metric status for debugging
if logger.logger.isEnabledFor(10):  # DEBUG level
    for name, status in get_metric_status().items():
        logger.debug(f"Metric {name}: {status}")