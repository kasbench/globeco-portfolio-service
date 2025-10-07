"""
Python runtime metrics for OpenTelemetry.

This module provides Python runtime metrics equivalent to what Prometheus
python_client provided automatically, including:
- Python version info
- Process metrics (CPU, memory, file descriptors)
- Garbage collection metrics
- Thread metrics
"""

import gc
import os
import platform
import psutil
import sys
import threading
import time
from typing import Dict, Any, Optional

from opentelemetry import metrics
from opentelemetry.metrics import Meter


class PythonRuntimeMetrics:
    """
    Collects Python runtime metrics using OpenTelemetry.
    
    Provides metrics equivalent to Prometheus python_client:
    - python_info: Python version information
    - process_*: Process CPU, memory, file descriptors
    - python_gc_*: Garbage collection statistics
    - python_threads_*: Thread information
    """
    
    def __init__(self, meter: Optional[Meter] = None):
        """
        Initialize Python runtime metrics collector.
        
        Args:
            meter: OpenTelemetry meter instance (uses global if None)
        """
        self._meter = meter or metrics.get_meter("python.runtime")
        self._process = psutil.Process()
        self._start_time = time.time()
        
        # Create metrics instruments
        self._create_metrics()
        
        # Record static info metrics
        self._record_python_info()
    
    def _create_metrics(self) -> None:
        """Create OpenTelemetry metric instruments."""
        # Python info (static)
        self._python_info = self._meter.create_counter(
            name="python_info",
            description="Python platform information",
            unit="1"
        )
        
        # Process metrics
        self._process_cpu_seconds = self._meter.create_counter(
            name="process_cpu_seconds_total",
            description="Total user and system CPU time spent in seconds",
            unit="s"
        )
        
        self._process_memory_bytes = self._meter.create_up_down_counter(
            name="process_resident_memory_bytes",
            description="Resident memory size in bytes",
            unit="By"
        )
        
        self._process_virtual_memory_bytes = self._meter.create_up_down_counter(
            name="process_virtual_memory_bytes",
            description="Virtual memory size in bytes",
            unit="By"
        )
        
        self._process_open_fds = self._meter.create_up_down_counter(
            name="process_open_fds",
            description="Number of open file descriptors",
            unit="1"
        )
        
        self._process_max_fds = self._meter.create_up_down_counter(
            name="process_max_fds",
            description="Maximum number of open file descriptors",
            unit="1"
        )
        
        self._process_start_time_seconds = self._meter.create_counter(
            name="process_start_time_seconds",
            description="Start time of the process since unix epoch in seconds",
            unit="s"
        )
        
        # Garbage collection metrics
        self._python_gc_objects_collected = self._meter.create_counter(
            name="python_gc_objects_collected_total",
            description="Objects collected during gc",
            unit="1"
        )
        
        self._python_gc_objects_uncollectable = self._meter.create_counter(
            name="python_gc_objects_uncollectable_total",
            description="Uncollectable objects found during GC",
            unit="1"
        )
        
        self._python_gc_collections = self._meter.create_counter(
            name="python_gc_collections_total",
            description="Number of times this generation was collected",
            unit="1"
        )
        
        # Thread metrics
        self._python_threads = self._meter.create_up_down_counter(
            name="python_threads",
            description="Number of threads",
            unit="1"
        )
    
    def _record_python_info(self) -> None:
        """Record static Python platform information."""
        python_version = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
        
        self._python_info.add(1, attributes={
            "version": python_version,
            "implementation": platform.python_implementation(),
            "major": str(sys.version_info.major),
            "minor": str(sys.version_info.minor),
            "patchlevel": str(sys.version_info.micro)
        })
        
        # Record process start time (static)
        self._process_start_time_seconds.add(self._start_time)
    
    def collect_metrics(self) -> None:
        """Collect and record current runtime metrics."""
        try:
            self._collect_process_metrics()
            self._collect_gc_metrics()
            self._collect_thread_metrics()
        except Exception as e:
            # Don't let metrics collection crash the application
            import logging
            logger = logging.getLogger(__name__)
            logger.warning(f"Failed to collect Python runtime metrics: {e}")
    
    def _collect_process_metrics(self) -> None:
        """Collect process-level metrics."""
        # CPU times
        cpu_times = self._process.cpu_times()
        self._process_cpu_seconds.add(cpu_times.user, attributes={"type": "user"})
        self._process_cpu_seconds.add(cpu_times.system, attributes={"type": "system"})
        
        # Memory usage
        memory_info = self._process.memory_info()
        self._process_memory_bytes.add(memory_info.rss)
        self._process_virtual_memory_bytes.add(memory_info.vms)
        
        # File descriptors (Unix-like systems only)
        try:
            if hasattr(self._process, "num_fds"):
                self._process_open_fds.add(self._process.num_fds())
            
            # Get max file descriptors from system limits
            import resource
            max_fds = resource.getrlimit(resource.RLIMIT_NOFILE)[1]
            if max_fds != resource.RLIM_INFINITY:
                self._process_max_fds.add(max_fds)
        except (AttributeError, OSError):
            # Not available on all platforms
            pass
    
    def _collect_gc_metrics(self) -> None:
        """Collect garbage collection metrics."""
        # Get GC stats for each generation
        gc_stats = gc.get_stats()
        
        for generation, stats in enumerate(gc_stats):
            gen_attrs = {"generation": str(generation)}
            
            self._python_gc_collections.add(
                stats.get("collections", 0), 
                attributes=gen_attrs
            )
            
            self._python_gc_objects_collected.add(
                stats.get("collected", 0), 
                attributes=gen_attrs
            )
            
            self._python_gc_objects_uncollectable.add(
                stats.get("uncollectable", 0), 
                attributes=gen_attrs
            )
    
    def _collect_thread_metrics(self) -> None:
        """Collect thread metrics."""
        thread_count = threading.active_count()
        self._python_threads.add(thread_count)


# Global runtime metrics collector
_runtime_metrics: Optional[PythonRuntimeMetrics] = None


def initialize_python_runtime_metrics(meter: Optional[Meter] = None) -> PythonRuntimeMetrics:
    """
    Initialize global Python runtime metrics collector.
    
    Args:
        meter: OpenTelemetry meter instance
        
    Returns:
        PythonRuntimeMetrics instance
    """
    global _runtime_metrics
    _runtime_metrics = PythonRuntimeMetrics(meter)
    return _runtime_metrics


def get_python_runtime_metrics() -> Optional[PythonRuntimeMetrics]:
    """Get the global Python runtime metrics collector."""
    return _runtime_metrics


def collect_runtime_metrics() -> None:
    """Collect runtime metrics if initialized."""
    if _runtime_metrics:
        _runtime_metrics.collect_metrics()


def is_runtime_metrics_initialized() -> bool:
    """Check if runtime metrics are initialized."""
    return _runtime_metrics is not None