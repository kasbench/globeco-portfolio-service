"""
Async metrics collector with circuit breaker for OpenTelemetry OTLP export.

This module provides:
- Background metrics processing to avoid blocking request threads
- Circuit breaker pattern for OTLP export failures
- Retry logic with exponential backoff
- Graceful degradation when collector is unavailable
"""

import asyncio
import logging
import time
from asyncio import Queue, Task
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Dict, Any, List, Callable
from concurrent.futures import ThreadPoolExecutor
import threading

from opentelemetry.sdk.metrics.export import MetricExporter, MetricExportResult
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter as OTLPMetricExporterGRPC
from opentelemetry.sdk.metrics._internal.export import MetricsData
import grpc

from app.environment_config import get_config_manager


class CircuitState(str, Enum):
    """Circuit breaker states."""
    CLOSED = "closed"      # Normal operation
    OPEN = "open"          # Failing, rejecting requests
    HALF_OPEN = "half_open"  # Testing if service recovered


@dataclass
class CircuitBreakerConfig:
    """Configuration for circuit breaker."""
    failure_threshold: int = 5  # Number of failures before opening
    recovery_timeout: int = 60  # Seconds to wait before trying again
    success_threshold: int = 3  # Successful calls needed to close circuit
    timeout: int = 30  # Request timeout in seconds


@dataclass
class RetryConfig:
    """Configuration for retry logic."""
    max_retries: int = 3
    initial_delay: float = 1.0  # Initial delay in seconds
    max_delay: float = 60.0     # Maximum delay in seconds
    backoff_multiplier: float = 2.0  # Exponential backoff multiplier
    jitter: bool = True  # Add random jitter to delays


@dataclass
class MetricsBuffer:
    """Buffer for metrics data with metadata."""
    metrics_data: MetricsData
    timestamp: float = field(default_factory=time.time)
    retry_count: int = 0
    
    @property
    def age_seconds(self) -> float:
        """Get age of buffered metrics in seconds."""
        return time.time() - self.timestamp


class CircuitBreaker:
    """
    Circuit breaker implementation for OTLP metric export.
    
    Provides protection against cascading failures when the OTLP collector
    is unavailable or experiencing issues.
    """
    
    def __init__(self, config: CircuitBreakerConfig):
        """
        Initialize circuit breaker.
        
        Args:
            config: Circuit breaker configuration
        """
        self._config = config
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._last_failure_time = 0.0
        self._lock = threading.Lock()
        self._logger = logging.getLogger(__name__)
        
        self._logger.info(
            f"CircuitBreaker initialized: failure_threshold={config.failure_threshold}, "
            f"recovery_timeout={config.recovery_timeout}, success_threshold={config.success_threshold}, "
            f"timeout={config.timeout}"
        )
    
    def can_execute(self) -> bool:
        """
        Check if operation can be executed.
        
        Returns:
            True if operation should proceed, False if circuit is open
        """
        with self._lock:
            if self._state == CircuitState.CLOSED:
                return True
            elif self._state == CircuitState.OPEN:
                # Check if recovery timeout has passed
                if time.time() - self._last_failure_time >= self._config.recovery_timeout:
                    self._state = CircuitState.HALF_OPEN
                    self._success_count = 0
                    self._logger.info("Circuit breaker transitioning to HALF_OPEN")
                    return True
                return False
            elif self._state == CircuitState.HALF_OPEN:
                return True
            
            return False
    
    def record_success(self) -> None:
        """Record successful operation."""
        with self._lock:
            self._failure_count = 0
            
            if self._state == CircuitState.HALF_OPEN:
                self._success_count += 1
                if self._success_count >= self._config.success_threshold:
                    self._state = CircuitState.CLOSED
                    self._logger.info("Circuit breaker closed after successful recovery")
            
            if self._state == CircuitState.CLOSED:
                self._logger.debug("Circuit breaker: operation succeeded")
    
    def record_failure(self) -> None:
        """Record failed operation."""
        with self._lock:
            self._failure_count += 1
            self._last_failure_time = time.time()
            
            if self._state == CircuitState.HALF_OPEN:
                self._state = CircuitState.OPEN
                self._logger.warning("Circuit breaker opened during recovery attempt")
            elif (self._state == CircuitState.CLOSED and 
                  self._failure_count >= self._config.failure_threshold):
                self._state = CircuitState.OPEN
                self._logger.warning(
                    f"Circuit breaker opened due to failure threshold: "
                    f"failure_count={self._failure_count}, threshold={self._config.failure_threshold}"
                )
    
    @property
    def state(self) -> CircuitState:
        """Get current circuit state."""
        return self._state
    
    @property
    def failure_count(self) -> int:
        """Get current failure count."""
        return self._failure_count
    
    def get_stats(self) -> Dict[str, Any]:
        """
        Get circuit breaker statistics.
        
        Returns:
            Dictionary with circuit breaker stats
        """
        with self._lock:
            return {
                "state": self._state.value,
                "failure_count": self._failure_count,
                "success_count": self._success_count,
                "last_failure_time": self._last_failure_time,
                "time_since_last_failure": time.time() - self._last_failure_time if self._last_failure_time > 0 else 0,
                "config": {
                    "failure_threshold": self._config.failure_threshold,
                    "recovery_timeout": self._config.recovery_timeout,
                    "success_threshold": self._config.success_threshold,
                    "timeout": self._config.timeout,
                }
            }


class AsyncMetricsCollector:
    """
    Async metrics collector with circuit breaker and retry logic.
    
    This collector provides:
    - Background processing of metrics to avoid blocking request threads
    - Circuit breaker protection against OTLP collector failures
    - Exponential backoff retry logic
    - Metrics buffering during outages
    - Graceful degradation and recovery
    """
    
    def __init__(
        self,
        otlp_exporter: MetricExporter,
        circuit_breaker_config: Optional[CircuitBreakerConfig] = None,
        retry_config: Optional[RetryConfig] = None,
        buffer_size: int = 1000,
        buffer_timeout: int = 300  # 5 minutes
    ):
        """
        Initialize async metrics collector.
        
        Args:
            otlp_exporter: OTLP metric exporter
            circuit_breaker_config: Circuit breaker configuration
            retry_config: Retry configuration
            buffer_size: Maximum number of metrics to buffer
            buffer_timeout: Maximum age of buffered metrics in seconds
        """
        self._logger = logging.getLogger(__name__)
        self._otlp_exporter = otlp_exporter
        
        # Configuration
        self._circuit_breaker_config = circuit_breaker_config or CircuitBreakerConfig()
        self._retry_config = retry_config or RetryConfig()
        self._buffer_size = buffer_size
        self._buffer_timeout = buffer_timeout
        
        # Circuit breaker
        self._circuit_breaker = CircuitBreaker(self._circuit_breaker_config)
        
        # Async components
        self._metrics_queue: Optional[Queue] = None
        self._buffer: List[MetricsBuffer] = []
        self._buffer_lock = asyncio.Lock()
        self._processing_task: Optional[Task] = None
        self._cleanup_task: Optional[Task] = None
        self._shutdown_event = asyncio.Event()
        
        # Statistics
        self._stats = {
            "metrics_processed": 0,
            "metrics_failed": 0,
            "metrics_buffered": 0,
            "metrics_dropped": 0,
            "circuit_breaker_opens": 0,
            "retry_attempts": 0,
        }
        self._stats_lock = threading.Lock()
        
        self._logger.info(
            f"AsyncMetricsCollector initialized: buffer_size={buffer_size}, "
            f"buffer_timeout={buffer_timeout}, circuit_breaker_config={self._circuit_breaker_config.__dict__}, "
            f"retry_config={self._retry_config.__dict__}"
        )
    
    async def start(self) -> None:
        """Start the async metrics collector."""
        if self._processing_task is not None:
            self._logger.warning("AsyncMetricsCollector already started")
            return
        
        # Create queue and tasks
        self._metrics_queue = Queue(maxsize=self._buffer_size)
        self._processing_task = asyncio.create_task(self._process_metrics())
        self._cleanup_task = asyncio.create_task(self._cleanup_buffer())
        
        self._logger.info("AsyncMetricsCollector started")
    
    async def stop(self) -> None:
        """Stop the async metrics collector and flush remaining metrics."""
        if self._processing_task is None:
            return
        
        # Signal shutdown
        self._shutdown_event.set()
        
        # Cancel tasks
        if self._processing_task:
            self._processing_task.cancel()
            try:
                await self._processing_task
            except asyncio.CancelledError:
                pass
        
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
        
        # Flush remaining metrics
        await self._flush_buffer()
        
        self._processing_task = None
        self._cleanup_task = None
        self._metrics_queue = None
        
        self._logger.info("AsyncMetricsCollector stopped")
    
    async def export_metrics(self, metrics_data: MetricsData) -> bool:
        """
        Export metrics asynchronously.
        
        Args:
            metrics_data: Metrics data to export
            
        Returns:
            True if queued successfully, False if queue is full
        """
        if self._metrics_queue is None:
            self._logger.error("AsyncMetricsCollector not started")
            return False
        
        try:
            # Try to put metrics in queue (non-blocking)
            self._metrics_queue.put_nowait(metrics_data)
            return True
        except asyncio.QueueFull:
            # Queue is full, increment dropped counter
            with self._stats_lock:
                self._stats["metrics_dropped"] += 1
            
            self._logger.warning(
                f"Metrics queue full, dropping metrics: "
                f"queue_size={self._metrics_queue.qsize()}, max_size={self._buffer_size}"
            )
            return False
    
    async def _process_metrics(self) -> None:
        """Background task to process metrics from queue."""
        self._logger.info("Metrics processing task started")
        
        while not self._shutdown_event.is_set():
            try:
                # Get metrics from queue with timeout
                try:
                    metrics_data = await asyncio.wait_for(
                        self._metrics_queue.get(),
                        timeout=1.0
                    )
                except asyncio.TimeoutError:
                    continue
                
                # Process the metrics
                await self._export_with_circuit_breaker(metrics_data)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                self._logger.error(
                    f"Error in metrics processing task: error={str(e)}, error_type={type(e).__name__}",
                    exc_info=True
                )
                await asyncio.sleep(1.0)  # Brief pause on error
        
        self._logger.info("Metrics processing task stopped")
    
    async def _export_with_circuit_breaker(self, metrics_data: MetricsData) -> None:
        """
        Export metrics with circuit breaker protection.
        
        Args:
            metrics_data: Metrics data to export
        """
        # Check circuit breaker
        if not self._circuit_breaker.can_execute():
            # Circuit is open, buffer the metrics
            await self._buffer_metrics(metrics_data)
            return
        
        # Attempt export with retry
        success = await self._export_with_retry(metrics_data)
        
        if success:
            self._circuit_breaker.record_success()
            with self._stats_lock:
                self._stats["metrics_processed"] += 1
        else:
            self._circuit_breaker.record_failure()
            with self._stats_lock:
                self._stats["metrics_failed"] += 1
            
            # Buffer failed metrics for retry
            await self._buffer_metrics(metrics_data)
    
    async def _export_with_retry(self, metrics_data: MetricsData) -> bool:
        """
        Export metrics with exponential backoff retry.
        
        Args:
            metrics_data: Metrics data to export
            
        Returns:
            True if export succeeded, False otherwise
        """
        delay = self._retry_config.initial_delay
        
        for attempt in range(self._retry_config.max_retries + 1):
            try:
                # Run export in thread pool to avoid blocking
                loop = asyncio.get_event_loop()
                with ThreadPoolExecutor(max_workers=1) as executor:
                    future = loop.run_in_executor(
                        executor,
                        self._otlp_exporter.export,
                        metrics_data
                    )
                    
                    # Wait for export with timeout
                    result = await asyncio.wait_for(
                        future,
                        timeout=self._circuit_breaker_config.timeout
                    )
                
                # Check export result
                if result == MetricExportResult.SUCCESS:
                    if attempt > 0:
                        self._logger.info(
                            f"Metrics export succeeded after retry: attempt={attempt}, total_attempts={attempt + 1}"
                        )
                    return True
                else:
                    self._logger.warning(
                        f"Metrics export failed: result={result}, attempt={attempt + 1}, "
                        f"max_attempts={self._retry_config.max_retries + 1}"
                    )
                
            except asyncio.TimeoutError:
                self._logger.warning(
                    f"Metrics export timeout: attempt={attempt + 1}, timeout={self._circuit_breaker_config.timeout}"
                )
            except Exception as e:
                self._logger.warning(
                    f"Metrics export error: error={str(e)}, error_type={type(e).__name__}, attempt={attempt + 1}"
                )
            
            # Don't retry on last attempt
            if attempt < self._retry_config.max_retries:
                with self._stats_lock:
                    self._stats["retry_attempts"] += 1
                
                # Add jitter if enabled
                actual_delay = delay
                if self._retry_config.jitter:
                    import random
                    actual_delay *= (0.5 + random.random() * 0.5)
                
                await asyncio.sleep(actual_delay)
                delay = min(delay * self._retry_config.backoff_multiplier, self._retry_config.max_delay)
        
        return False
    
    async def _buffer_metrics(self, metrics_data: MetricsData) -> None:
        """
        Buffer metrics for later retry.
        
        Args:
            metrics_data: Metrics data to buffer
        """
        async with self._buffer_lock:
            # Remove old metrics if buffer is full
            if len(self._buffer) >= self._buffer_size:
                removed = self._buffer.pop(0)
                with self._stats_lock:
                    self._stats["metrics_dropped"] += 1
                
                self._logger.warning(
                    f"Buffer full, dropping old metrics: buffer_size={len(self._buffer)}, "
                    f"dropped_age_seconds={removed.age_seconds}"
                )
            
            # Add new metrics to buffer
            self._buffer.append(MetricsBuffer(metrics_data))
            with self._stats_lock:
                self._stats["metrics_buffered"] += 1
            
            self._logger.debug(
                f"Metrics buffered: buffer_size={len(self._buffer)}, max_buffer_size={self._buffer_size}"
            )
    
    async def _cleanup_buffer(self) -> None:
        """Background task to clean up old buffered metrics and retry exports."""
        self._logger.info("Buffer cleanup task started")
        
        while not self._shutdown_event.is_set():
            try:
                await asyncio.sleep(30.0)  # Check every 30 seconds
                await self._process_buffer()
            except asyncio.CancelledError:
                break
            except Exception as e:
                self._logger.error(
                    f"Error in buffer cleanup task: error={str(e)}, error_type={type(e).__name__}",
                    exc_info=True
                )
        
        self._logger.info("Buffer cleanup task stopped")
    
    async def _process_buffer(self) -> None:
        """Process buffered metrics and remove expired ones."""
        async with self._buffer_lock:
            if not self._buffer:
                return
            
            current_time = time.time()
            processed_count = 0
            expired_count = 0
            
            # Process buffer in reverse order (oldest first)
            i = 0
            while i < len(self._buffer):
                buffer_item = self._buffer[i]
                
                # Remove expired metrics
                if buffer_item.age_seconds > self._buffer_timeout:
                    self._buffer.pop(i)
                    expired_count += 1
                    with self._stats_lock:
                        self._stats["metrics_dropped"] += 1
                    continue
                
                # Try to export if circuit breaker allows
                if self._circuit_breaker.can_execute():
                    success = await self._export_with_retry(buffer_item.metrics_data)
                    if success:
                        self._buffer.pop(i)
                        processed_count += 1
                        self._circuit_breaker.record_success()
                        with self._stats_lock:
                            self._stats["metrics_processed"] += 1
                        continue
                    else:
                        self._circuit_breaker.record_failure()
                        buffer_item.retry_count += 1
                
                i += 1
            
            if processed_count > 0 or expired_count > 0:
                self._logger.info(
                    f"Buffer processing completed: processed={processed_count}, expired={expired_count}, "
                    f"remaining={len(self._buffer)}, circuit_state={self._circuit_breaker.state.value}"
                )
    
    async def _flush_buffer(self) -> None:
        """Flush all buffered metrics on shutdown."""
        async with self._buffer_lock:
            if not self._buffer:
                return
            
            self._logger.info(f"Flushing {len(self._buffer)} buffered metrics")
            
            for buffer_item in self._buffer:
                try:
                    # Force export without circuit breaker on shutdown
                    await self._export_with_retry(buffer_item.metrics_data)
                except Exception as e:
                    self._logger.warning(
                        f"Failed to flush buffered metrics: error={str(e)}, age_seconds={buffer_item.age_seconds}"
                    )
            
            self._buffer.clear()
    
    def get_stats(self) -> Dict[str, Any]:
        """
        Get collector statistics.
        
        Returns:
            Dictionary with collector statistics
        """
        with self._stats_lock:
            stats = self._stats.copy()
        
        stats.update({
            "buffer_size": len(self._buffer),
            "max_buffer_size": self._buffer_size,
            "queue_size": self._metrics_queue.qsize() if self._metrics_queue else 0,
            "circuit_breaker": self._circuit_breaker.get_stats(),
            "is_running": self._processing_task is not None and not self._processing_task.done(),
        })
        
        return stats


def create_async_metrics_collector(
    otlp_endpoint: str = "http://localhost:4317",
    **kwargs
) -> AsyncMetricsCollector:
    """
    Create async metrics collector with default OTLP exporter.
    
    Args:
        otlp_endpoint: OTLP endpoint URL
        **kwargs: Additional arguments for AsyncMetricsCollector
        
    Returns:
        Configured AsyncMetricsCollector
    """
    # Create OTLP exporter
    otlp_exporter = OTLPMetricExporterGRPC(
        endpoint=otlp_endpoint,
        insecure=True,
        compression=grpc.Compression.Gzip
    )
    
    return AsyncMetricsCollector(otlp_exporter, **kwargs)