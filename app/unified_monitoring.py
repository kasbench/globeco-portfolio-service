"""
Unified OpenTelemetry-only monitoring system for Portfolio Service.

This module provides a complete OpenTelemetry monitoring solution that replaces
all Prometheus metrics with OTLP export to localhost:4317. It includes:
- Unified tracer and meter setup
- OTLP exporter configuration
- Resource attributes for Kubernetes environments
- Environment-based configuration
"""

import logging
import os
from typing import Optional, Dict, Any
from dataclasses import dataclass

from opentelemetry import trace, metrics
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter as OTLPSpanExporterGRPC
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter as OTLPMetricExporterGRPC
import grpc
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.instrumentation.logging import LoggingInstrumentor

from app.environment_config import get_config_manager, MonitoringConfig
from app.configurable_sampler import ConfigurableSampler, create_environment_sampler
from app.async_metrics_collector import AsyncMetricsCollector, create_async_metrics_collector, CircuitBreakerConfig, RetryConfig


@dataclass
class OTLPConfig:
    """Configuration for OTLP exporters."""
    endpoint: str = "http://localhost:4317"
    insecure: bool = True
    timeout: int = 30  # seconds
    compression: Optional[Any] = None  # gRPC compression constant
    headers: Optional[Dict[str, str]] = None


class UnifiedMonitoring:
    """
    Unified OpenTelemetry monitoring system that completely replaces Prometheus.
    
    This class provides:
    - OpenTelemetry tracer and meter setup
    - OTLP export to localhost:4317 (hostport routing)
    - Resource attributes for Kubernetes environments
    - Environment-based configuration
    - No Prometheus dependencies or endpoints
    """
    
    def __init__(self, config: Optional[MonitoringConfig] = None):
        """
        Initialize unified OpenTelemetry monitoring.
        
        Args:
            config: Monitoring configuration (uses environment config if None)
        """
        self._logger = logging.getLogger(__name__)
        self._config = config or get_config_manager().get_monitoring_config()
        self._resource: Optional[Resource] = None
        self._tracer_provider: Optional[TracerProvider] = None
        self._meter_provider: Optional[MeterProvider] = None
        self._tracer = None
        self._meter = None
        self._sampler: Optional[ConfigurableSampler] = None
        self._async_collector: Optional[AsyncMetricsCollector] = None
        self._initialized = False
        
        # OTLP configuration
        self._otlp_config = self._create_otlp_config()
        
        self._logger.info(
            f"UnifiedMonitoring initialized: monitoring_mode={self._config.mode.value}, "
            f"tracing_enabled={self._config.enable_tracing}, metrics_enabled={self._config.enable_metrics}, "
            f"otlp_endpoint={self._otlp_config.endpoint}, sample_rate={self._config.sample_rate}"
        )
    
    def _create_otlp_config(self) -> OTLPConfig:
        """
        Create OTLP configuration from environment and monitoring config.
        
        Returns:
            OTLPConfig with endpoint and settings
        """
        # Use localhost:4317 for hostport routing to node-local collector
        endpoint = self._config.otlp_endpoint
        
        # Override with environment variable if set
        env_endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
        if env_endpoint:
            endpoint = env_endpoint
            self._logger.info(f"Using OTLP endpoint from environment: {endpoint}")
        
        # Ensure gRPC endpoint format for localhost:4317
        if endpoint == "http://localhost:4317" or endpoint == "localhost:4317":
            endpoint = "http://localhost:4317"
        
        return OTLPConfig(
            endpoint=endpoint,
            insecure=True,  # Use insecure for localhost
            timeout=30,
            compression=grpc.Compression.Gzip  # Use gRPC compression constant
        )
    
    def _create_resource(self) -> Resource:
        """
        Create OpenTelemetry resource with proper attributes.
        
        Returns:
            Resource with service and Kubernetes attributes
        """
        attributes = {
            "service.name": "globeco-portfolio-service",
            "service.version": "2.0.0",
            "service.namespace": "globeco",
            "deployment.environment": get_config_manager().current_environment,
        }
        
        # Add Kubernetes attributes if available
        k8s_attributes = {
            "k8s.pod.name": os.getenv("MY_POD_NAME", os.getenv("HOSTNAME", "unknown")),
            "k8s.pod.ip": os.getenv("MY_POD_IP", "unknown"),
            "k8s.namespace.name": os.getenv("MY_NAMESPACE", "globeco"),
            "k8s.deployment.name": "globeco-portfolio-service",
            "k8s.node.name": os.getenv("MY_NODE_NAME", "unknown"),
            "k8s.cluster.name": os.getenv("CLUSTER_NAME", "unknown"),
        }
        
        # Only add K8s attributes if we're actually in Kubernetes
        if any(value != "unknown" for value in k8s_attributes.values()):
            attributes.update(k8s_attributes)
            self._logger.debug("Added Kubernetes resource attributes", **k8s_attributes)
        
        resource = Resource.create(attributes)
        
        self._logger.info(
            f"OpenTelemetry resource created: service_name={attributes['service.name']}, "
            f"service_version={attributes['service.version']}, environment={attributes['deployment.environment']}, "
            f"kubernetes_detected={any(value != 'unknown' for value in k8s_attributes.values())}"
        )
        
        return resource
    
    def _setup_tracer(self) -> None:
        """Setup OpenTelemetry tracer with OTLP export and configurable sampling."""
        if not self._config.enable_tracing:
            self._logger.info("Tracing disabled by configuration")
            return
        
        try:
            # Create configurable sampler for environment-based sampling
            self._sampler = create_environment_sampler(
                environment=get_config_manager().current_environment,
                sample_rate=self._config.sample_rate
            )
            
            # Create tracer provider with resource and sampler
            self._tracer_provider = TracerProvider(
                resource=self._resource,
                sampler=self._sampler
            )
            
            # Create OTLP span exporter
            span_exporter = OTLPSpanExporterGRPC(
                endpoint=self._otlp_config.endpoint,
                insecure=self._otlp_config.insecure,
                timeout=self._otlp_config.timeout,
                compression=self._otlp_config.compression,
                headers=self._otlp_config.headers
            )
            
            # Add batch span processor
            span_processor = BatchSpanProcessor(
                span_exporter,
                max_queue_size=2048,
                max_export_batch_size=512,
                export_timeout_millis=30000,
                schedule_delay_millis=5000
            )
            
            self._tracer_provider.add_span_processor(span_processor)
            
            # Set global tracer provider
            trace.set_tracer_provider(self._tracer_provider)
            
            # Get tracer instance
            self._tracer = trace.get_tracer("globeco.portfolio.service")
            
            self._logger.info(
                f"OpenTelemetry tracer configured successfully: endpoint={self._otlp_config.endpoint}, "
                f"compression={self._otlp_config.compression}, max_queue_size=2048, max_export_batch_size=512, "
                f"sampler={self._sampler.get_description()}, sample_rate={self._sampler.sample_rate}, "
                f"sampling_strategy={self._sampler.strategy.value}"
            )
            
        except Exception as e:
            self._logger.error(
                f"Failed to setup OpenTelemetry tracer: error={str(e)}, error_type={type(e).__name__}, "
                f"endpoint={self._otlp_config.endpoint}",
                exc_info=True
            )
            raise
    
    def _setup_meter(self) -> None:
        """Setup OpenTelemetry meter with async OTLP export and circuit breaker."""
        if not self._config.enable_metrics:
            self._logger.info("Metrics disabled by configuration")
            return
        
        try:
            # Create async metrics collector with circuit breaker
            circuit_breaker_config = CircuitBreakerConfig(
                failure_threshold=5,
                recovery_timeout=60,
                success_threshold=3,
                timeout=30
            )
            
            retry_config = RetryConfig(
                max_retries=3,
                initial_delay=1.0,
                max_delay=60.0,
                backoff_multiplier=2.0,
                jitter=True
            )
            
            self._async_collector = create_async_metrics_collector(
                otlp_endpoint=self._otlp_config.endpoint,
                circuit_breaker_config=circuit_breaker_config,
                retry_config=retry_config,
                buffer_size=1000,
                buffer_timeout=300
            )
            
            # Create OTLP metric exporter for direct use (fallback)
            metric_exporter = OTLPMetricExporterGRPC(
                endpoint=self._otlp_config.endpoint,
                insecure=self._otlp_config.insecure,
                timeout=self._otlp_config.timeout,
                compression=self._otlp_config.compression,
                headers=self._otlp_config.headers
            )
            
            # Create periodic exporting metric reader
            metric_reader = PeriodicExportingMetricReader(
                exporter=metric_exporter,
                export_interval_millis=self._config.export_interval * 1000,  # Convert to milliseconds
                export_timeout_millis=30000  # 30 seconds timeout
            )
            
            # Create meter provider with resource and reader
            self._meter_provider = MeterProvider(
                resource=self._resource,
                metric_readers=[metric_reader]
            )
            
            # Set global meter provider
            metrics.set_meter_provider(self._meter_provider)
            
            # Get meter instance
            self._meter = metrics.get_meter("globeco.portfolio.service")
            
            self._logger.info(
                f"OpenTelemetry meter configured successfully: endpoint={self._otlp_config.endpoint}, "
                f"export_interval_seconds={self._config.export_interval}, compression={self._otlp_config.compression}, "
                f"async_collector_enabled=True, circuit_breaker_enabled=True"
            )
            
        except Exception as e:
            self._logger.error(
                f"Failed to setup OpenTelemetry meter: error={str(e)}, error_type={type(e).__name__}, "
                f"endpoint={self._otlp_config.endpoint}",
                exc_info=True
            )
            raise
    
    def initialize(self) -> bool:
        """
        Initialize the unified monitoring system.
        
        Returns:
            True if initialization successful, False otherwise
        """
        if self._initialized:
            self._logger.warning("UnifiedMonitoring already initialized")
            return True
        
        try:
            # Create resource
            self._resource = self._create_resource()
            
            # Setup tracer if enabled
            if self._config.enable_tracing:
                self._setup_tracer()
            
            # Setup meter if enabled
            if self._config.enable_metrics:
                self._setup_meter()
                
                # Start async metrics collector
                if self._async_collector:
                    import asyncio
                    try:
                        loop = asyncio.get_event_loop()
                        loop.create_task(self._async_collector.start())
                        self._logger.info("Async metrics collector started")
                    except RuntimeError:
                        # No event loop running, will start later
                        self._logger.info("Async metrics collector will start when event loop is available")
            
            # Instrument libraries
            self._instrument_libraries()
            
            self._initialized = True
            
            self._logger.info(
                f"UnifiedMonitoring initialization completed successfully: tracing_enabled={self._config.enable_tracing}, "
                f"metrics_enabled={self._config.enable_metrics}, otlp_endpoint={self._otlp_config.endpoint}, "
                f"environment={get_config_manager().current_environment}"
            )
            
            return True
            
        except Exception as e:
            self._logger.error(
                f"UnifiedMonitoring initialization failed: error={str(e)}, error_type={type(e).__name__}",
                exc_info=True
            )
            return False
    
    def _instrument_libraries(self) -> None:
        """Instrument common libraries with OpenTelemetry."""
        try:
            # Instrument HTTPX for outbound HTTP calls
            HTTPXClientInstrumentor().instrument()
            
            # Instrument logging
            LoggingInstrumentor().instrument(set_logging_format=True)
            
            self._logger.debug("Library instrumentation completed")
            
        except Exception as e:
            self._logger.warning(
                "Library instrumentation failed",
                error=str(e),
                error_type=type(e).__name__
            )
    
    def instrument_fastapi(self, app) -> None:
        """
        Instrument FastAPI application.
        
        Args:
            app: FastAPI application instance
        """
        if not self._config.enable_tracing:
            self._logger.info("FastAPI instrumentation skipped (tracing disabled)")
            return
        
        try:
            FastAPIInstrumentor().instrument_app(app)
            self._logger.info("FastAPI instrumentation completed")
        except Exception as e:
            self._logger.error(
                f"FastAPI instrumentation failed: error={str(e)}, error_type={type(e).__name__}",
                exc_info=True
            )
    
    async def start_async_components(self) -> None:
        """Start async components like metrics collector."""
        if not self._initialized:
            raise RuntimeError("UnifiedMonitoring not initialized")
        
        if self._async_collector:
            try:
                await self._async_collector.start()
                self._logger.info("Async metrics collector started successfully")
            except Exception as e:
                self._logger.error(
                    f"Failed to start async metrics collector: error={str(e)}, error_type={type(e).__name__}",
                    exc_info=True
                )
    
    async def stop_async_components(self) -> None:
        """Stop async components like metrics collector."""
        if self._async_collector:
            try:
                await self._async_collector.stop()
                self._logger.info("Async metrics collector stopped successfully")
            except Exception as e:
                self._logger.error(
                    f"Failed to stop async metrics collector: error={str(e)}, error_type={type(e).__name__}",
                    exc_info=True
                )
    
    @property
    def tracer(self):
        """Get OpenTelemetry tracer instance."""
        if not self._initialized:
            raise RuntimeError("UnifiedMonitoring not initialized")
        return self._tracer
    
    @property
    def meter(self):
        """Get OpenTelemetry meter instance."""
        if not self._initialized:
            raise RuntimeError("UnifiedMonitoring not initialized")
        return self._meter
    
    @property
    def is_tracing_enabled(self) -> bool:
        """Check if tracing is enabled."""
        return self._config.enable_tracing
    
    @property
    def is_metrics_enabled(self) -> bool:
        """Check if metrics are enabled."""
        return self._config.enable_metrics
    
    @property
    def sampler(self) -> Optional[ConfigurableSampler]:
        """Get the configurable sampler instance."""
        return self._sampler
    
    @property
    def async_collector(self) -> Optional[AsyncMetricsCollector]:
        """Get the async metrics collector instance."""
        return self._async_collector
    
    def get_monitoring_status(self) -> Dict[str, Any]:
        """
        Get current monitoring status and configuration.
        
        Returns:
            Dictionary with monitoring status information
        """
        return {
            "initialized": self._initialized,
            "tracing": {
                "enabled": self._config.enable_tracing,
                "provider_set": self._tracer_provider is not None,
                "tracer_available": self._tracer is not None,
                "sampler_configured": self._sampler is not None,
                "sampling_stats": self._sampler.get_sampling_stats() if self._sampler else None,
            },
            "metrics": {
                "enabled": self._config.enable_metrics,
                "provider_set": self._meter_provider is not None,
                "meter_available": self._meter is not None,
                "async_collector_configured": self._async_collector is not None,
                "async_collector_stats": self._async_collector.get_stats() if self._async_collector else None,
            },
            "otlp": {
                "endpoint": self._otlp_config.endpoint,
                "insecure": self._otlp_config.insecure,
                "compression": self._otlp_config.compression,
            },
            "config": {
                "mode": self._config.mode.value,
                "sample_rate": self._config.sample_rate,
                "export_interval": self._config.export_interval,
                "environment": get_config_manager().current_environment,
            }
        }
    
    def shutdown(self) -> None:
        """Shutdown monitoring system and flush pending data."""
        if not self._initialized:
            return
        
        try:
            # Shutdown async metrics collector
            if self._async_collector:
                import asyncio
                try:
                    loop = asyncio.get_event_loop()
                    loop.create_task(self._async_collector.stop())
                    self._logger.debug("Async metrics collector shutdown initiated")
                except RuntimeError:
                    self._logger.warning("No event loop available for async collector shutdown")
            
            # Shutdown tracer provider
            if self._tracer_provider:
                self._tracer_provider.shutdown()
                self._logger.debug("Tracer provider shutdown completed")
            
            # Shutdown meter provider
            if self._meter_provider:
                self._meter_provider.shutdown()
                self._logger.debug("Meter provider shutdown completed")
            
            self._initialized = False
            
            self._logger.info("UnifiedMonitoring shutdown completed")
            
        except Exception as e:
            self._logger.error(
                f"Error during UnifiedMonitoring shutdown: error={str(e)}, error_type={type(e).__name__}",
                exc_info=True
            )


# Global unified monitoring instance
_unified_monitoring: Optional[UnifiedMonitoring] = None


def get_unified_monitoring() -> UnifiedMonitoring:
    """
    Get global unified monitoring instance.
    
    Returns:
        UnifiedMonitoring instance
        
    Raises:
        RuntimeError: If monitoring not initialized
    """
    global _unified_monitoring
    if _unified_monitoring is None:
        raise RuntimeError("UnifiedMonitoring not initialized. Call initialize_unified_monitoring() first.")
    return _unified_monitoring


def initialize_unified_monitoring(config: Optional[MonitoringConfig] = None) -> UnifiedMonitoring:
    """
    Initialize global unified monitoring instance.
    
    Args:
        config: Optional monitoring configuration
        
    Returns:
        UnifiedMonitoring instance
    """
    global _unified_monitoring
    _unified_monitoring = UnifiedMonitoring(config)
    
    # Initialize the monitoring system
    success = _unified_monitoring.initialize()
    if not success:
        raise RuntimeError("Failed to initialize UnifiedMonitoring")
    
    return _unified_monitoring


def is_monitoring_initialized() -> bool:
    """Check if unified monitoring is initialized."""
    global _unified_monitoring
    return _unified_monitoring is not None and _unified_monitoring._initialized


# Convenience functions for common operations
def get_tracer():
    """Get OpenTelemetry tracer instance."""
    return get_unified_monitoring().tracer


def get_meter():
    """Get OpenTelemetry meter instance."""
    return get_unified_monitoring().meter


def is_tracing_enabled() -> bool:
    """Check if tracing is enabled."""
    try:
        return get_unified_monitoring().is_tracing_enabled
    except RuntimeError:
        return False


def is_metrics_enabled() -> bool:
    """Check if metrics are enabled."""
    try:
        return get_unified_monitoring().is_metrics_enabled
    except RuntimeError:
        return False