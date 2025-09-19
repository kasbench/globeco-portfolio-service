"""
Monitoring health checks and graceful degradation system.

This module provides:
- Health checks for OTLP collector connectivity
- Graceful degradation when monitoring services are unavailable
- Local metrics buffering during outages
- Recovery logic and monitoring service restoration
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Dict, Any, List, Callable
import threading
from concurrent.futures import ThreadPoolExecutor
import json

import httpx
from opentelemetry.sdk.metrics._internal.export import MetricsData
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter as OTLPMetricExporterGRPC
from opentelemetry.sdk.metrics.export import MetricExportResult
import grpc

from app.circuit_breaker import CircuitBreaker, CircuitBreakerConfig, CircuitBreakerError
from app.environment_config import get_config_manager


class MonitoringHealthStatus(str, Enum):
    """Health status for monitoring services."""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


@dataclass
class HealthCheckConfig:
    """Configuration for health checks."""
    check_interval: int = 30  # seconds
    timeout: int = 10  # seconds
    max_failures: int = 3
    recovery_threshold: int = 2  # successful checks needed for recovery


@dataclass
class BufferedMetric:
    """Buffered metric data with metadata."""
    data: MetricsData
    timestamp: float = field(default_factory=time.time)
    retry_count: int = 0
    
    @property
    def age_seconds(self) -> float:
        """Get age of buffered metric in seconds."""
        return time.time() - self.timestamp


class MonitoringHealthChecker:
    """
    Health checker for monitoring services with graceful degradation.
    
    This class monitors the health of OTLP collectors and other monitoring
    services, providing graceful degradation when services are unavailable.
    """
    
    def __init__(
        self,
        otlp_endpoint: str = "http://localhost:4317",
        health_config: Optional[HealthCheckConfig] = None
    ):
        """
        Initialize monitoring health checker.
        
        Args:
            otlp_endpoint: OTLP collector endpoint
            health_config: Health check configuration
        """
        self._logger = logging.getLogger(__name__)
        self._otlp_endpoint = otlp_endpoint
        self._health_config = health_config or HealthCheckConfig()
        
        # Health status
        self._status = MonitoringHealthStatus.UNKNOWN
        self._last_check_time = 0.0
        self._consecutive_failures = 0
        self._consecutive_successes = 0
        self._status_lock = threading.Lock()
        
        # Health check task
        self._health_check_task: Optional[asyncio.Task] = None
        self._shutdown_event = asyncio.Event()
        
        # Circuit breaker for OTLP export
        circuit_config = CircuitBreakerConfig(
            name="otlp_export",
            failure_threshold=self._health_config.max_failures,
            recovery_timeout=60,
            success_threshold=self._health_config.recovery_threshold,
            timeout=self._health_config.timeout
        )
        self._circuit_breaker = CircuitBreaker(circuit_config)
        
        # Metrics buffering
        self._buffer: List[BufferedMetric] = []
        self._buffer_lock = asyncio.Lock()
        self._max_buffer_size = 1000
        self._buffer_timeout = 300  # 5 minutes
        
        # Statistics
        self._stats = {
            "health_checks_performed": 0,
            "health_checks_successful": 0,
            "health_checks_failed": 0,
            "metrics_buffered": 0,
            "metrics_dropped": 0,
            "recovery_attempts": 0,
            "successful_recoveries": 0,
        }
        self._stats_lock = threading.Lock()
        
        # Status change callbacks
        self._status_callbacks: List[Callable[[MonitoringHealthStatus, MonitoringHealthStatus], None]] = []
        
        self._logger.info(
            f"MonitoringHealthChecker initialized: otlp_endpoint={otlp_endpoint}, "
            f"check_interval={self._health_config.check_interval}, "
            f"timeout={self._health_config.timeout}, max_failures={self._health_config.max_failures}"
        )
    
    async def start(self) -> None:
        """Start health checking."""
        if self._health_check_task is not None:
            self._logger.warning("MonitoringHealthChecker already started")
            return
        
        self._shutdown_event.clear()
        self._health_check_task = asyncio.create_task(self._health_check_loop())
        
        # Perform initial health check
        await self._perform_health_check()
        
        self._logger.info("MonitoringHealthChecker started")
    
    async def stop(self) -> None:
        """Stop health checking and flush buffered metrics."""
        if self._health_check_task is None:
            return
        
        # Signal shutdown
        self._shutdown_event.set()
        
        # Cancel health check task
        self._health_check_task.cancel()
        try:
            await self._health_check_task
        except asyncio.CancelledError:
            pass
        
        # Attempt to flush buffered metrics
        await self._flush_buffer()
        
        self._health_check_task = None
        
        self._logger.info("MonitoringHealthChecker stopped")
    
    async def _health_check_loop(self) -> None:
        """Background health check loop."""
        self._logger.info("Health check loop started")
        
        while not self._shutdown_event.is_set():
            try:
                await self._perform_health_check()
                await asyncio.sleep(self._health_config.check_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                self._logger.error(
                    f"Error in health check loop: error={str(e)}, error_type={type(e).__name__}",
                    exc_info=True
                )
                await asyncio.sleep(5.0)  # Brief pause on error
        
        self._logger.info("Health check loop stopped")
    
    async def _perform_health_check(self) -> None:
        """Perform health check on OTLP collector."""
        with self._stats_lock:
            self._stats["health_checks_performed"] += 1
        
        try:
            # Check OTLP collector health
            is_healthy = await self._check_otlp_health()
            
            with self._status_lock:
                self._last_check_time = time.time()
                
                if is_healthy:
                    self._consecutive_failures = 0
                    self._consecutive_successes += 1
                    
                    # Update status based on consecutive successes
                    old_status = self._status
                    if self._status == MonitoringHealthStatus.UNHEALTHY:
                        if self._consecutive_successes >= self._health_config.recovery_threshold:
                            self._status = MonitoringHealthStatus.HEALTHY
                            with self._stats_lock:
                                self._stats["successful_recoveries"] += 1
                    elif self._status in [MonitoringHealthStatus.UNKNOWN, MonitoringHealthStatus.DEGRADED]:
                        self._status = MonitoringHealthStatus.HEALTHY
                    
                    if old_status != self._status:
                        self._notify_status_change(old_status, self._status)
                    
                    with self._stats_lock:
                        self._stats["health_checks_successful"] += 1
                    
                    # Record success in circuit breaker
                    self._circuit_breaker.record_success()
                    
                    # Try to flush buffered metrics on recovery
                    if old_status != MonitoringHealthStatus.HEALTHY:
                        asyncio.create_task(self._attempt_buffer_flush())
                
                else:
                    self._consecutive_successes = 0
                    self._consecutive_failures += 1
                    
                    # Update status based on consecutive failures
                    old_status = self._status
                    if self._consecutive_failures >= self._health_config.max_failures:
                        self._status = MonitoringHealthStatus.UNHEALTHY
                    elif self._consecutive_failures > 1:
                        self._status = MonitoringHealthStatus.DEGRADED
                    
                    if old_status != self._status:
                        self._notify_status_change(old_status, self._status)
                    
                    with self._stats_lock:
                        self._stats["health_checks_failed"] += 1
                    
                    # Record failure in circuit breaker
                    self._circuit_breaker.record_failure()
        
        except Exception as e:
            self._logger.error(
                f"Health check failed with exception: error={str(e)}, error_type={type(e).__name__}",
                exc_info=True
            )
            
            with self._status_lock:
                self._consecutive_failures += 1
                old_status = self._status
                self._status = MonitoringHealthStatus.UNHEALTHY
                
                if old_status != self._status:
                    self._notify_status_change(old_status, self._status)
            
            with self._stats_lock:
                self._stats["health_checks_failed"] += 1
            
            self._circuit_breaker.record_failure(e)
    
    async def _check_otlp_health(self) -> bool:
        """
        Check OTLP collector health.
        
        Returns:
            True if healthy, False otherwise
        """
        try:
            # For gRPC OTLP endpoint, we'll try a simple connection test
            # by creating a temporary exporter and testing connectivity
            
            # Parse endpoint to get host and port
            endpoint = self._otlp_endpoint.replace("http://", "").replace("https://", "")
            if ":" in endpoint:
                host, port = endpoint.split(":", 1)
                port = int(port)
            else:
                host = endpoint
                port = 4317  # Default OTLP gRPC port
            
            # Test gRPC connection
            async with asyncio.timeout(self._health_config.timeout):
                # Create a simple gRPC channel and test connectivity
                channel = grpc.aio.insecure_channel(f"{host}:{port}")
                try:
                    # Try to get channel state
                    await channel.channel_ready()
                    return True
                finally:
                    await channel.close()
        
        except Exception as e:
            self._logger.debug(
                f"OTLP health check failed: endpoint={self._otlp_endpoint}, "
                f"error={str(e)}, error_type={type(e).__name__}"
            )
            return False
    
    def _notify_status_change(
        self, 
        old_status: MonitoringHealthStatus, 
        new_status: MonitoringHealthStatus
    ) -> None:
        """
        Notify callbacks of status change.
        
        Args:
            old_status: Previous status
            new_status: New status
        """
        self._logger.info(
            f"Monitoring health status changed: {old_status.value} -> {new_status.value}"
        )
        
        for callback in self._status_callbacks:
            try:
                callback(old_status, new_status)
            except Exception as e:
                self._logger.error(
                    f"Status change callback failed: callback={callback.__name__}, "
                    f"error={str(e)}, error_type={type(e).__name__}",
                    exc_info=True
                )
    
    def register_status_callback(
        self, 
        callback: Callable[[MonitoringHealthStatus, MonitoringHealthStatus], None]
    ) -> None:
        """
        Register callback for status changes.
        
        Args:
            callback: Function to call on status change (old_status, new_status)
        """
        self._status_callbacks.append(callback)
        self._logger.debug(f"Status change callback registered: {callback.__name__}")
    
    async def export_metrics_with_fallback(self, metrics_data: MetricsData) -> bool:
        """
        Export metrics with fallback to buffering.
        
        Args:
            metrics_data: Metrics data to export
            
        Returns:
            True if exported successfully, False if buffered
        """
        # Check circuit breaker
        if not self._circuit_breaker.can_execute():
            await self._buffer_metrics(metrics_data)
            return False
        
        try:
            # Attempt direct export
            with self._circuit_breaker.protect():
                exporter = OTLPMetricExporterGRPC(
                    endpoint=self._otlp_endpoint,
                    insecure=True,
                    timeout=self._health_config.timeout,
                    compression=grpc.Compression.Gzip
                )
                
                # Export in thread pool to avoid blocking
                loop = asyncio.get_event_loop()
                with ThreadPoolExecutor(max_workers=1) as executor:
                    future = loop.run_in_executor(executor, exporter.export, metrics_data)
                    result = await asyncio.wait_for(future, timeout=self._health_config.timeout)
                
                if result == MetricExportResult.SUCCESS:
                    return True
                else:
                    raise Exception(f"Export failed with result: {result}")
        
        except (CircuitBreakerError, Exception) as e:
            self._logger.debug(
                f"Metrics export failed, buffering: error={str(e)}, error_type={type(e).__name__}"
            )
            await self._buffer_metrics(metrics_data)
            return False
    
    async def _buffer_metrics(self, metrics_data: MetricsData) -> None:
        """
        Buffer metrics for later retry.
        
        Args:
            metrics_data: Metrics data to buffer
        """
        async with self._buffer_lock:
            # Remove old metrics if buffer is full
            if len(self._buffer) >= self._max_buffer_size:
                removed = self._buffer.pop(0)
                with self._stats_lock:
                    self._stats["metrics_dropped"] += 1
                
                self._logger.warning(
                    f"Metrics buffer full, dropping old metrics: buffer_size={len(self._buffer)}, "
                    f"dropped_age_seconds={removed.age_seconds}"
                )
            
            # Add new metrics to buffer
            self._buffer.append(BufferedMetric(metrics_data))
            with self._stats_lock:
                self._stats["metrics_buffered"] += 1
            
            self._logger.debug(
                f"Metrics buffered: buffer_size={len(self._buffer)}, max_size={self._max_buffer_size}"
            )
    
    async def _attempt_buffer_flush(self) -> None:
        """Attempt to flush buffered metrics."""
        if not self._buffer:
            return
        
        with self._stats_lock:
            self._stats["recovery_attempts"] += 1
        
        self._logger.info(f"Attempting to flush {len(self._buffer)} buffered metrics")
        
        async with self._buffer_lock:
            flushed_count = 0
            failed_count = 0
            
            # Process buffer in batches
            i = 0
            while i < len(self._buffer) and self._circuit_breaker.can_execute():
                buffered_metric = self._buffer[i]
                
                # Skip expired metrics
                if buffered_metric.age_seconds > self._buffer_timeout:
                    self._buffer.pop(i)
                    with self._stats_lock:
                        self._stats["metrics_dropped"] += 1
                    continue
                
                try:
                    # Attempt export
                    exporter = OTLPMetricExporterGRPC(
                        endpoint=self._otlp_endpoint,
                        insecure=True,
                        timeout=self._health_config.timeout,
                        compression=grpc.Compression.Gzip
                    )
                    
                    loop = asyncio.get_event_loop()
                    with ThreadPoolExecutor(max_workers=1) as executor:
                        future = loop.run_in_executor(executor, exporter.export, buffered_metric.data)
                        result = await asyncio.wait_for(future, timeout=self._health_config.timeout)
                    
                    if result == MetricExportResult.SUCCESS:
                        self._buffer.pop(i)
                        flushed_count += 1
                        self._circuit_breaker.record_success()
                        continue
                    else:
                        raise Exception(f"Export failed with result: {result}")
                
                except Exception as e:
                    self._logger.debug(
                        f"Buffer flush failed for metric: error={str(e)}, age_seconds={buffered_metric.age_seconds}"
                    )
                    buffered_metric.retry_count += 1
                    failed_count += 1
                    self._circuit_breaker.record_failure(e)
                    
                    # Remove metrics that have been retried too many times
                    if buffered_metric.retry_count >= 3:
                        self._buffer.pop(i)
                        with self._stats_lock:
                            self._stats["metrics_dropped"] += 1
                        continue
                
                i += 1
            
            self._logger.info(
                f"Buffer flush completed: flushed={flushed_count}, failed={failed_count}, "
                f"remaining={len(self._buffer)}"
            )
    
    async def _flush_buffer(self) -> None:
        """Flush all buffered metrics on shutdown."""
        if not self._buffer:
            return
        
        self._logger.info(f"Flushing {len(self._buffer)} buffered metrics on shutdown")
        
        async with self._buffer_lock:
            for buffered_metric in self._buffer:
                try:
                    # Force export without circuit breaker on shutdown
                    exporter = OTLPMetricExporterGRPC(
                        endpoint=self._otlp_endpoint,
                        insecure=True,
                        timeout=self._health_config.timeout,
                        compression=grpc.Compression.Gzip
                    )
                    
                    loop = asyncio.get_event_loop()
                    with ThreadPoolExecutor(max_workers=1) as executor:
                        future = loop.run_in_executor(executor, exporter.export, buffered_metric.data)
                        await asyncio.wait_for(future, timeout=self._health_config.timeout)
                
                except Exception as e:
                    self._logger.warning(
                        f"Failed to flush buffered metric on shutdown: "
                        f"error={str(e)}, age_seconds={buffered_metric.age_seconds}"
                    )
            
            self._buffer.clear()
    
    @property
    def status(self) -> MonitoringHealthStatus:
        """Get current health status."""
        return self._status
    
    @property
    def is_healthy(self) -> bool:
        """Check if monitoring is healthy."""
        return self._status == MonitoringHealthStatus.HEALTHY
    
    @property
    def can_export(self) -> bool:
        """Check if metrics can be exported directly."""
        return self._circuit_breaker.can_execute() and self._status != MonitoringHealthStatus.UNHEALTHY
    
    def get_health_info(self) -> Dict[str, Any]:
        """
        Get detailed health information.
        
        Returns:
            Dictionary with health information
        """
        with self._status_lock:
            return {
                "status": self._status.value,
                "is_healthy": self.is_healthy,
                "can_export": self.can_export,
                "last_check_time": self._last_check_time,
                "time_since_last_check": time.time() - self._last_check_time if self._last_check_time > 0 else 0,
                "consecutive_failures": self._consecutive_failures,
                "consecutive_successes": self._consecutive_successes,
                "circuit_breaker": self._circuit_breaker.get_stats(),
                "buffer": {
                    "size": len(self._buffer),
                    "max_size": self._max_buffer_size,
                    "oldest_age_seconds": (
                        min(m.age_seconds for m in self._buffer) if self._buffer else 0
                    ),
                },
                "config": {
                    "otlp_endpoint": self._otlp_endpoint,
                    "check_interval": self._health_config.check_interval,
                    "timeout": self._health_config.timeout,
                    "max_failures": self._health_config.max_failures,
                    "recovery_threshold": self._health_config.recovery_threshold,
                },
                "statistics": self._stats.copy(),
            }


class GracefulMonitoringManager:
    """
    Manager for graceful degradation of monitoring services.
    
    This class coordinates health checking, circuit breaking, and fallback
    behavior for all monitoring components.
    """
    
    def __init__(self):
        """Initialize graceful monitoring manager."""
        self._logger = logging.getLogger(__name__)
        self._config = get_config_manager().get_monitoring_config()
        
        # Health checker
        self._health_checker = MonitoringHealthChecker(
            otlp_endpoint=self._config.otlp_endpoint,
            health_config=HealthCheckConfig(
                check_interval=30,
                timeout=10,
                max_failures=3,
                recovery_threshold=2
            )
        )
        
        # Register for status changes
        self._health_checker.register_status_callback(self._on_status_change)
        
        # Fallback behavior flags
        self._fallback_mode = False
        self._fallback_lock = threading.Lock()
        
        self._logger.info("GracefulMonitoringManager initialized")
    
    async def start(self) -> None:
        """Start graceful monitoring."""
        await self._health_checker.start()
        self._logger.info("GracefulMonitoringManager started")
    
    async def stop(self) -> None:
        """Stop graceful monitoring."""
        await self._health_checker.stop()
        self._logger.info("GracefulMonitoringManager stopped")
    
    def _on_status_change(
        self, 
        old_status: MonitoringHealthStatus, 
        new_status: MonitoringHealthStatus
    ) -> None:
        """
        Handle monitoring status changes.
        
        Args:
            old_status: Previous status
            new_status: New status
        """
        with self._fallback_lock:
            old_fallback = self._fallback_mode
            self._fallback_mode = new_status != MonitoringHealthStatus.HEALTHY
            
            if old_fallback != self._fallback_mode:
                if self._fallback_mode:
                    self._logger.warning(
                        f"Entering fallback mode due to monitoring degradation: "
                        f"status={new_status.value}"
                    )
                else:
                    self._logger.info(
                        f"Exiting fallback mode, monitoring recovered: "
                        f"status={new_status.value}"
                    )
    
    async def export_metrics(self, metrics_data: MetricsData) -> bool:
        """
        Export metrics with graceful degradation.
        
        Args:
            metrics_data: Metrics data to export
            
        Returns:
            True if exported successfully, False if degraded
        """
        return await self._health_checker.export_metrics_with_fallback(metrics_data)
    
    @property
    def is_healthy(self) -> bool:
        """Check if monitoring is healthy."""
        return self._health_checker.is_healthy
    
    @property
    def is_fallback_mode(self) -> bool:
        """Check if in fallback mode."""
        with self._fallback_lock:
            return self._fallback_mode
    
    def get_status(self) -> Dict[str, Any]:
        """
        Get monitoring status.
        
        Returns:
            Dictionary with status information
        """
        return {
            "health_checker": self._health_checker.get_health_info(),
            "fallback_mode": self.is_fallback_mode,
            "config": {
                "otlp_endpoint": self._config.otlp_endpoint,
                "metrics_enabled": self._config.enable_metrics,
                "tracing_enabled": self._config.enable_tracing,
            }
        }


# Global graceful monitoring manager
_monitoring_manager: Optional[GracefulMonitoringManager] = None


def get_monitoring_manager() -> GracefulMonitoringManager:
    """
    Get global monitoring manager.
    
    Returns:
        GracefulMonitoringManager instance
    """
    global _monitoring_manager
    if _monitoring_manager is None:
        _monitoring_manager = GracefulMonitoringManager()
    return _monitoring_manager


async def initialize_monitoring_manager() -> GracefulMonitoringManager:
    """
    Initialize and start global monitoring manager.
    
    Returns:
        GracefulMonitoringManager instance
    """
    manager = get_monitoring_manager()
    await manager.start()
    return manager