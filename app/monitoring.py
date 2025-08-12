"""
Enhanced HTTP Metrics Monitoring Module for GlobeCo Portfolio Service.

This module provides standardized HTTP metrics collection using Prometheus client
with comprehensive error handling and duplicate registration prevention.
"""

import time
from typing import Any, Dict, Optional

from fastapi import Request
from prometheus_client import Counter, Gauge, Histogram
from app.logging_config import get_logger

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
        logger.debug(f"Reusing existing metric: {name}")
        return _METRICS_REGISTRY[registry_key]

    try:
        # Create metric with or without labels
        if labels:
            metric = metric_class(name, description, labels, **kwargs)
        else:
            metric = metric_class(name, description, **kwargs)

        _METRICS_REGISTRY[registry_key] = metric
        logger.info(f"Successfully created metric: {name}")
        return metric

    except ValueError as e:
        if "Duplicated timeseries" in str(e):
            logger.warning(
                "Metric already registered in Prometheus but not in our registry",
                metric_name=name,
                error=str(e),
                error_type=type(e).__name__
            )
            # Create dummy metric to prevent service disruption
            dummy = DummyMetric()
            _METRICS_REGISTRY[registry_key] = dummy
            logger.warning(f"Created dummy metric for {name} to prevent errors")
            return dummy
        else:
            logger.error(
                "Failed to create metric",
                metric_name=name,
                error=str(e),
                error_type=type(e).__name__,
                exc_info=True
            )
            # Create dummy metric as fallback
            dummy = DummyMetric()
            _METRICS_REGISTRY[registry_key] = dummy
            logger.error(f"Created dummy metric for {name} due to creation failure")
            return dummy
    except Exception as e:
        logger.error(
            "Unexpected error creating metric",
            metric_name=name,
            error=str(e),
            error_type=type(e).__name__,
            exc_info=True
        )
        # Create dummy metric as fallback
        dummy = DummyMetric()
        _METRICS_REGISTRY[registry_key] = dummy
        logger.error(f"Created dummy metric for {name} due to unexpected error")
        return dummy


# Create the three standardized HTTP metrics
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


# Initialize metrics on module import
logger.info("Enhanced HTTP metrics monitoring module initialized")
logger.info(f"Metrics registry contains {len(_METRICS_REGISTRY)} metrics")

# Log metric status for debugging
if logger.logger.isEnabledFor(10):  # DEBUG level
    for name, status in get_metric_status().items():
        logger.debug(f"Metric {name}: {status}")