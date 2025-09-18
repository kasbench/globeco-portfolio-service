"""
Configurable trace sampling for OpenTelemetry.

This module provides environment-based trace sampling with:
- Production sampling (1-10% of requests)
- Development sampling (100% of requests)
- Staging sampling (configurable, typically 50%)
- Validation and defaults for sampling configuration
"""

import logging
from typing import Optional, Sequence, Dict, Any
from enum import Enum

from opentelemetry.sdk.trace.sampling import (
    Sampler,
    SamplingResult,
    Decision,
    TraceIdRatioBased,
    ALWAYS_ON,
    ALWAYS_OFF,
    ParentBased,
)
from opentelemetry.trace import Link, SpanKind
from opentelemetry.util.types import Attributes

from app.environment_config import get_config_manager, MonitoringMode


class SamplingStrategy(str, Enum):
    """Sampling strategies for different environments."""
    ALWAYS_ON = "always_on"      # 100% sampling (development)
    ALWAYS_OFF = "always_off"    # 0% sampling (disabled)
    RATIO_BASED = "ratio_based"  # Configurable ratio sampling
    PARENT_BASED = "parent_based"  # Follow parent span decisions


class ConfigurableSampler(Sampler):
    """
    Environment-based configurable sampler for OpenTelemetry traces.
    
    This sampler adapts sampling behavior based on the deployment environment:
    - Development: 100% sampling for full observability
    - Staging: 50% sampling for balanced observability and performance
    - Production: 1-10% sampling for minimal performance impact
    
    The sampler validates configuration and provides safe defaults.
    """
    
    def __init__(
        self,
        sample_rate: Optional[float] = None,
        strategy: Optional[SamplingStrategy] = None,
        environment: Optional[str] = None
    ):
        """
        Initialize configurable sampler.
        
        Args:
            sample_rate: Override sample rate (0.0-1.0)
            strategy: Override sampling strategy
            environment: Override environment detection
        """
        self._logger = logging.getLogger(__name__)
        
        # Get configuration
        config_manager = get_config_manager()
        if environment:
            config_manager.reload_profile(environment)
        
        self._environment = config_manager.current_environment
        self._monitoring_config = config_manager.get_monitoring_config()
        
        # Determine sampling configuration
        self._sample_rate = self._determine_sample_rate(sample_rate)
        self._strategy = self._determine_strategy(strategy)
        
        # Create underlying sampler
        self._underlying_sampler = self._create_underlying_sampler()
        
        # Validation
        self._validate_configuration()
        
        self._logger.info(
            f"ConfigurableSampler initialized: environment={self._environment}, "
            f"sample_rate={self._sample_rate}, strategy={self._strategy.value}, "
            f"monitoring_mode={self._monitoring_config.mode.value}, "
            f"underlying_sampler={type(self._underlying_sampler).__name__}"
        )
    
    def _determine_sample_rate(self, override_rate: Optional[float]) -> float:
        """
        Determine sample rate based on environment and overrides.
        
        Args:
            override_rate: Optional override sample rate
            
        Returns:
            Validated sample rate between 0.0 and 1.0
        """
        if override_rate is not None:
            if not 0.0 <= override_rate <= 1.0:
                raise ValueError(f"Sample rate must be between 0.0 and 1.0, got {override_rate}")
            return override_rate
        
        # Use configuration sample rate
        config_rate = self._monitoring_config.sample_rate
        
        # Environment-specific defaults if config rate is not set properly
        if config_rate is None or not 0.0 <= config_rate <= 1.0:
            if self._environment == "development":
                config_rate = 1.0  # 100% sampling in development
            elif self._environment == "staging":
                config_rate = 0.5  # 50% sampling in staging
            elif self._environment == "production":
                config_rate = 0.1  # 10% sampling in production
            else:
                config_rate = 0.1  # Conservative default
            
            self._logger.warning(
                f"Invalid sample rate in configuration, using environment default: "
                f"config_sample_rate={self._monitoring_config.sample_rate}, environment={self._environment}, "
                f"default_rate={config_rate}"
            )
        
        return config_rate
    
    def _determine_strategy(self, override_strategy: Optional[SamplingStrategy]) -> SamplingStrategy:
        """
        Determine sampling strategy based on environment and configuration.
        
        Args:
            override_strategy: Optional override strategy
            
        Returns:
            Sampling strategy
        """
        if override_strategy is not None:
            return override_strategy
        
        # Determine strategy based on environment and configuration
        if not self._monitoring_config.enable_tracing:
            return SamplingStrategy.ALWAYS_OFF
        
        if self._environment == "development":
            return SamplingStrategy.ALWAYS_ON
        elif self._sample_rate == 0.0:
            return SamplingStrategy.ALWAYS_OFF
        elif self._sample_rate == 1.0:
            return SamplingStrategy.ALWAYS_ON
        else:
            return SamplingStrategy.PARENT_BASED
    
    def _create_underlying_sampler(self) -> Sampler:
        """
        Create the underlying OpenTelemetry sampler based on strategy.
        
        Returns:
            Configured OpenTelemetry sampler
        """
        if self._strategy == SamplingStrategy.ALWAYS_ON:
            return ALWAYS_ON
        elif self._strategy == SamplingStrategy.ALWAYS_OFF:
            return ALWAYS_OFF
        elif self._strategy == SamplingStrategy.RATIO_BASED:
            return TraceIdRatioBased(self._sample_rate)
        elif self._strategy == SamplingStrategy.PARENT_BASED:
            # Use parent-based sampling with ratio-based root sampler
            root_sampler = TraceIdRatioBased(self._sample_rate)
            return ParentBased(root=root_sampler)
        else:
            raise ValueError(f"Unknown sampling strategy: {self._strategy}")
    
    def _validate_configuration(self) -> None:
        """
        Validate sampling configuration.
        
        Raises:
            ValueError: If configuration is invalid
        """
        errors = []
        
        # Validate sample rate
        if not 0.0 <= self._sample_rate <= 1.0:
            errors.append(f"Sample rate must be between 0.0 and 1.0, got {self._sample_rate}")
        
        # Validate strategy consistency
        if self._strategy == SamplingStrategy.ALWAYS_ON and self._sample_rate != 1.0:
            errors.append(f"ALWAYS_ON strategy requires sample_rate=1.0, got {self._sample_rate}")
        
        if self._strategy == SamplingStrategy.ALWAYS_OFF and self._sample_rate != 0.0:
            errors.append(f"ALWAYS_OFF strategy requires sample_rate=0.0, got {self._sample_rate}")
        
        # Validate environment-specific constraints
        if self._environment == "production" and self._sample_rate > 0.1:
            self._logger.warning(
                f"High sample rate in production environment may impact performance: "
                f"environment={self._environment}, sample_rate={self._sample_rate}, recommended_max=0.1"
            )
        
        if errors:
            raise ValueError(f"Sampling configuration validation failed: {'; '.join(errors)}")
    
    def should_sample(
        self,
        parent_context: Optional[Any],
        trace_id: int,
        name: str,
        kind: SpanKind = SpanKind.INTERNAL,
        attributes: Attributes = None,
        links: Sequence[Link] = None,
        trace_state: Optional[Any] = None,
    ) -> SamplingResult:
        """
        Determine if a span should be sampled.
        
        Args:
            parent_context: Parent span context
            trace_id: Trace ID
            name: Span name
            kind: Span kind
            attributes: Span attributes
            links: Span links
            trace_state: Trace state
            
        Returns:
            SamplingResult with decision and attributes
        """
        try:
            # Delegate to underlying sampler
            result = self._underlying_sampler.should_sample(
                parent_context=parent_context,
                trace_id=trace_id,
                name=name,
                kind=kind,
                attributes=attributes,
                links=links,
                trace_state=trace_state,
            )
            
            # Add sampling metadata to attributes
            if result.attributes is None:
                result_attributes = {}
            else:
                result_attributes = dict(result.attributes)
            
            result_attributes.update({
                "sampling.strategy": self._strategy.value,
                "sampling.rate": self._sample_rate,
                "sampling.environment": self._environment,
            })
            
            # Create new result with updated attributes
            return SamplingResult(
                decision=result.decision,
                attributes=result_attributes,
                trace_state=result.trace_state,
            )
            
        except Exception as e:
            self._logger.error(
                f"Error in sampling decision: error={str(e)}, error_type={type(e).__name__}, "
                f"trace_id={trace_id}, span_name={name}",
                exc_info=True
            )
            # Fallback to not sampling on error
            return SamplingResult(
                decision=Decision.NOT_RECORD,
                attributes={"sampling.error": str(e)},
            )
    
    def get_description(self) -> str:
        """
        Get human-readable description of the sampler.
        
        Returns:
            Sampler description
        """
        return (
            f"ConfigurableSampler("
            f"environment={self._environment}, "
            f"strategy={self._strategy.value}, "
            f"rate={self._sample_rate})"
        )
    
    @property
    def sample_rate(self) -> float:
        """Get current sample rate."""
        return self._sample_rate
    
    @property
    def strategy(self) -> SamplingStrategy:
        """Get current sampling strategy."""
        return self._strategy
    
    @property
    def environment(self) -> str:
        """Get current environment."""
        return self._environment
    
    def get_sampling_stats(self) -> Dict[str, Any]:
        """
        Get sampling configuration statistics.
        
        Returns:
            Dictionary with sampling statistics
        """
        return {
            "environment": self._environment,
            "strategy": self._strategy.value,
            "sample_rate": self._sample_rate,
            "tracing_enabled": self._monitoring_config.enable_tracing,
            "monitoring_mode": self._monitoring_config.mode.value,
            "underlying_sampler": type(self._underlying_sampler).__name__,
            "expected_sampling_percentage": self._sample_rate * 100,
        }
    
    def update_sample_rate(self, new_rate: float) -> None:
        """
        Update sample rate at runtime.
        
        Args:
            new_rate: New sample rate (0.0-1.0)
            
        Raises:
            ValueError: If new rate is invalid
        """
        if not 0.0 <= new_rate <= 1.0:
            raise ValueError(f"Sample rate must be between 0.0 and 1.0, got {new_rate}")
        
        old_rate = self._sample_rate
        self._sample_rate = new_rate
        
        # Update strategy if needed
        if new_rate == 0.0:
            self._strategy = SamplingStrategy.ALWAYS_OFF
        elif new_rate == 1.0:
            self._strategy = SamplingStrategy.ALWAYS_ON
        else:
            self._strategy = SamplingStrategy.PARENT_BASED
        
        # Recreate underlying sampler
        self._underlying_sampler = self._create_underlying_sampler()
        
        self._logger.info(
            f"Sample rate updated: old_rate={old_rate}, new_rate={new_rate}, "
            f"new_strategy={self._strategy.value}, environment={self._environment}"
        )


def create_environment_sampler(
    environment: Optional[str] = None,
    sample_rate: Optional[float] = None
) -> ConfigurableSampler:
    """
    Create a sampler configured for the specified environment.
    
    Args:
        environment: Target environment (development, staging, production)
        sample_rate: Override sample rate
        
    Returns:
        Configured ConfigurableSampler
    """
    return ConfigurableSampler(
        sample_rate=sample_rate,
        environment=environment
    )


def get_recommended_sample_rate(environment: str) -> float:
    """
    Get recommended sample rate for an environment.
    
    Args:
        environment: Environment name
        
    Returns:
        Recommended sample rate
    """
    recommendations = {
        "development": 1.0,   # 100% for full observability
        "staging": 0.5,       # 50% for balanced observability
        "production": 0.1,    # 10% for minimal performance impact
    }
    
    return recommendations.get(environment.lower(), 0.1)


def validate_sample_rate(sample_rate: float, environment: str) -> bool:
    """
    Validate if a sample rate is appropriate for an environment.
    
    Args:
        sample_rate: Sample rate to validate
        environment: Target environment
        
    Returns:
        True if sample rate is appropriate
    """
    if not 0.0 <= sample_rate <= 1.0:
        return False
    
    # Environment-specific validation
    if environment == "production" and sample_rate > 0.1:
        return False  # Too high for production
    
    if environment == "development" and sample_rate < 0.5:
        return False  # Too low for development debugging
    
    return True


# Default samplers for each environment
def get_development_sampler() -> ConfigurableSampler:
    """Get sampler optimized for development environment."""
    return ConfigurableSampler(
        sample_rate=1.0,
        strategy=SamplingStrategy.ALWAYS_ON,
        environment="development"
    )


def get_staging_sampler() -> ConfigurableSampler:
    """Get sampler optimized for staging environment."""
    return ConfigurableSampler(
        sample_rate=0.5,
        strategy=SamplingStrategy.PARENT_BASED,
        environment="staging"
    )


def get_production_sampler() -> ConfigurableSampler:
    """Get sampler optimized for production environment."""
    return ConfigurableSampler(
        sample_rate=0.1,
        strategy=SamplingStrategy.PARENT_BASED,
        environment="production"
    )