"""
Circuit breaker pattern implementation for external dependencies.

This module provides a general-purpose circuit breaker that can be used to protect
against cascading failures when external services are unavailable or experiencing issues.
It includes:
- Configurable failure thresholds and recovery timeouts
- Circuit states (CLOSED, OPEN, HALF_OPEN) with proper transitions
- Metrics and monitoring for circuit breaker operations
- Thread-safe implementation for concurrent usage
"""

import logging
import time
import threading
from dataclasses import dataclass
from enum import Enum
from typing import Optional, Dict, Any, Callable, TypeVar, Generic, Union
from contextlib import contextmanager
import asyncio
from functools import wraps

T = TypeVar('T')


class CircuitState(str, Enum):
    """Circuit breaker states."""
    CLOSED = "closed"      # Normal operation, requests allowed
    OPEN = "open"          # Failing, rejecting requests immediately
    HALF_OPEN = "half_open"  # Testing if service recovered, limited requests allowed


@dataclass
class CircuitBreakerConfig:
    """Configuration for circuit breaker."""
    failure_threshold: int = 5  # Number of failures before opening circuit
    recovery_timeout: int = 60  # Seconds to wait before trying again
    success_threshold: int = 3  # Successful calls needed to close circuit from half-open
    timeout: int = 30  # Request timeout in seconds
    name: str = "default"  # Name for logging and metrics


class CircuitBreakerError(Exception):
    """Exception raised when circuit breaker is open."""
    
    def __init__(self, circuit_name: str, state: CircuitState):
        self.circuit_name = circuit_name
        self.state = state
        super().__init__(f"Circuit breaker '{circuit_name}' is {state.value}")


class CircuitBreaker(Generic[T]):
    """
    Circuit breaker implementation for protecting against external service failures.
    
    The circuit breaker monitors the success/failure rate of operations and can be in
    one of three states:
    - CLOSED: Normal operation, all requests are allowed
    - OPEN: Service is failing, all requests are rejected immediately
    - HALF_OPEN: Testing recovery, limited requests are allowed
    
    This implementation is thread-safe and can be used in both sync and async contexts.
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
        self._last_success_time = 0.0
        self._lock = threading.RLock()  # Use RLock for nested locking
        self._logger = logging.getLogger(f"{__name__}.{config.name}")
        
        # Statistics
        self._stats = {
            "total_requests": 0,
            "successful_requests": 0,
            "failed_requests": 0,
            "rejected_requests": 0,
            "state_transitions": {
                "closed_to_open": 0,
                "open_to_half_open": 0,
                "half_open_to_closed": 0,
                "half_open_to_open": 0,
            }
        }
        
        self._logger.info(
            f"CircuitBreaker '{config.name}' initialized: failure_threshold={config.failure_threshold}, "
            f"recovery_timeout={config.recovery_timeout}, success_threshold={config.success_threshold}, "
            f"timeout={config.timeout}"
        )
    
    def can_execute(self) -> bool:
        """
        Check if operation can be executed based on circuit state.
        
        Returns:
            True if operation should proceed, False if circuit is open
        """
        with self._lock:
            current_time = time.time()
            
            if self._state == CircuitState.CLOSED:
                return True
            elif self._state == CircuitState.OPEN:
                # Check if recovery timeout has passed
                if current_time - self._last_failure_time >= self._config.recovery_timeout:
                    self._transition_to_half_open()
                    return True
                return False
            elif self._state == CircuitState.HALF_OPEN:
                return True
            
            return False
    
    def record_success(self) -> None:
        """Record successful operation and update circuit state."""
        with self._lock:
            current_time = time.time()
            self._last_success_time = current_time
            self._failure_count = 0
            self._stats["successful_requests"] += 1
            
            if self._state == CircuitState.HALF_OPEN:
                self._success_count += 1
                if self._success_count >= self._config.success_threshold:
                    self._transition_to_closed()
            
            self._logger.debug(
                f"Circuit breaker '{self._config.name}': operation succeeded, "
                f"state={self._state.value}, success_count={self._success_count}"
            )
    
    def record_failure(self, error: Optional[Exception] = None) -> None:
        """
        Record failed operation and update circuit state.
        
        Args:
            error: Optional exception that caused the failure
        """
        with self._lock:
            current_time = time.time()
            self._last_failure_time = current_time
            self._failure_count += 1
            self._success_count = 0  # Reset success count on any failure
            self._stats["failed_requests"] += 1
            
            error_info = f", error={str(error)}" if error else ""
            
            if self._state == CircuitState.HALF_OPEN:
                self._transition_to_open()
                self._logger.warning(
                    f"Circuit breaker '{self._config.name}': failure during recovery, "
                    f"transitioning to OPEN{error_info}"
                )
            elif (self._state == CircuitState.CLOSED and 
                  self._failure_count >= self._config.failure_threshold):
                self._transition_to_open()
                self._logger.warning(
                    f"Circuit breaker '{self._config.name}': failure threshold reached, "
                    f"transitioning to OPEN, failure_count={self._failure_count}, "
                    f"threshold={self._config.failure_threshold}{error_info}"
                )
            else:
                self._logger.debug(
                    f"Circuit breaker '{self._config.name}': operation failed, "
                    f"state={self._state.value}, failure_count={self._failure_count}{error_info}"
                )
    
    def _transition_to_open(self) -> None:
        """Transition circuit to OPEN state."""
        if self._state != CircuitState.OPEN:
            old_state = self._state
            self._state = CircuitState.OPEN
            self._stats["state_transitions"][f"{old_state.value}_to_open"] += 1
            self._logger.warning(
                f"Circuit breaker '{self._config.name}' transitioned: {old_state.value} -> OPEN"
            )
    
    def _transition_to_half_open(self) -> None:
        """Transition circuit to HALF_OPEN state."""
        if self._state != CircuitState.HALF_OPEN:
            old_state = self._state
            self._state = CircuitState.HALF_OPEN
            self._success_count = 0
            self._stats["state_transitions"][f"{old_state.value}_to_half_open"] += 1
            self._logger.info(
                f"Circuit breaker '{self._config.name}' transitioned: {old_state.value} -> HALF_OPEN"
            )
    
    def _transition_to_closed(self) -> None:
        """Transition circuit to CLOSED state."""
        if self._state != CircuitState.CLOSED:
            old_state = self._state
            self._state = CircuitState.CLOSED
            self._failure_count = 0
            self._success_count = 0
            self._stats["state_transitions"][f"{old_state.value}_to_closed"] += 1
            self._logger.info(
                f"Circuit breaker '{self._config.name}' transitioned: {old_state.value} -> CLOSED"
            )
    
    @contextmanager
    def protect(self):
        """
        Context manager for protecting operations with circuit breaker.
        
        Usage:
            with circuit_breaker.protect():
                result = external_service_call()
        
        Raises:
            CircuitBreakerError: If circuit is open
        """
        with self._lock:
            self._stats["total_requests"] += 1
        
        if not self.can_execute():
            with self._lock:
                self._stats["rejected_requests"] += 1
            raise CircuitBreakerError(self._config.name, self._state)
        
        try:
            yield
            self.record_success()
        except Exception as e:
            self.record_failure(e)
            raise
    
    def call(self, func: Callable[..., T], *args, **kwargs) -> T:
        """
        Execute function with circuit breaker protection.
        
        Args:
            func: Function to execute
            *args: Positional arguments for function
            **kwargs: Keyword arguments for function
            
        Returns:
            Function result
            
        Raises:
            CircuitBreakerError: If circuit is open
        """
        with self.protect():
            return func(*args, **kwargs)
    
    async def call_async(self, func: Callable[..., T], *args, **kwargs) -> T:
        """
        Execute async function with circuit breaker protection.
        
        Args:
            func: Async function to execute
            *args: Positional arguments for function
            **kwargs: Keyword arguments for function
            
        Returns:
            Function result
            
        Raises:
            CircuitBreakerError: If circuit is open
        """
        with self._lock:
            self._stats["total_requests"] += 1
        
        if not self.can_execute():
            with self._lock:
                self._stats["rejected_requests"] += 1
            raise CircuitBreakerError(self._config.name, self._state)
        
        try:
            if asyncio.iscoroutinefunction(func):
                result = await func(*args, **kwargs)
            else:
                result = func(*args, **kwargs)
            self.record_success()
            return result
        except Exception as e:
            self.record_failure(e)
            raise
    
    @property
    def state(self) -> CircuitState:
        """Get current circuit state."""
        return self._state
    
    @property
    def name(self) -> str:
        """Get circuit breaker name."""
        return self._config.name
    
    @property
    def failure_count(self) -> int:
        """Get current failure count."""
        return self._failure_count
    
    @property
    def success_count(self) -> int:
        """Get current success count (for half-open state)."""
        return self._success_count
    
    def is_closed(self) -> bool:
        """Check if circuit is closed (normal operation)."""
        return self._state == CircuitState.CLOSED
    
    def is_open(self) -> bool:
        """Check if circuit is open (rejecting requests)."""
        return self._state == CircuitState.OPEN
    
    def is_half_open(self) -> bool:
        """Check if circuit is half-open (testing recovery)."""
        return self._state == CircuitState.HALF_OPEN
    
    def reset(self) -> None:
        """Reset circuit breaker to closed state."""
        with self._lock:
            old_state = self._state
            self._state = CircuitState.CLOSED
            self._failure_count = 0
            self._success_count = 0
            self._last_failure_time = 0.0
            self._last_success_time = time.time()
            
            self._logger.info(
                f"Circuit breaker '{self._config.name}' manually reset: {old_state.value} -> CLOSED"
            )
    
    def force_open(self) -> None:
        """Force circuit breaker to open state."""
        with self._lock:
            old_state = self._state
            self._state = CircuitState.OPEN
            self._last_failure_time = time.time()
            
            self._logger.warning(
                f"Circuit breaker '{self._config.name}' manually opened: {old_state.value} -> OPEN"
            )
    
    def get_stats(self) -> Dict[str, Any]:
        """
        Get circuit breaker statistics and status.
        
        Returns:
            Dictionary with circuit breaker statistics
        """
        with self._lock:
            current_time = time.time()
            
            return {
                "name": self._config.name,
                "state": self._state.value,
                "failure_count": self._failure_count,
                "success_count": self._success_count,
                "last_failure_time": self._last_failure_time,
                "last_success_time": self._last_success_time,
                "time_since_last_failure": (
                    current_time - self._last_failure_time 
                    if self._last_failure_time > 0 else 0
                ),
                "time_since_last_success": (
                    current_time - self._last_success_time 
                    if self._last_success_time > 0 else 0
                ),
                "config": {
                    "failure_threshold": self._config.failure_threshold,
                    "recovery_timeout": self._config.recovery_timeout,
                    "success_threshold": self._config.success_threshold,
                    "timeout": self._config.timeout,
                },
                "statistics": self._stats.copy(),
                "health": {
                    "is_healthy": self._state == CircuitState.CLOSED,
                    "can_execute": self.can_execute(),
                    "failure_rate": (
                        self._stats["failed_requests"] / max(1, self._stats["total_requests"])
                        if self._stats["total_requests"] > 0 else 0.0
                    ),
                    "success_rate": (
                        self._stats["successful_requests"] / max(1, self._stats["total_requests"])
                        if self._stats["total_requests"] > 0 else 0.0
                    ),
                }
            }


def circuit_breaker(config: CircuitBreakerConfig):
    """
    Decorator for protecting functions with circuit breaker.
    
    Args:
        config: Circuit breaker configuration
        
    Usage:
        @circuit_breaker(CircuitBreakerConfig(name="external_api"))
        def call_external_api():
            return requests.get("https://api.example.com")
    """
    breaker = CircuitBreaker(config)
    
    def decorator(func):
        if asyncio.iscoroutinefunction(func):
            @wraps(func)
            async def async_wrapper(*args, **kwargs):
                return await breaker.call_async(func, *args, **kwargs)
            return async_wrapper
        else:
            @wraps(func)
            def sync_wrapper(*args, **kwargs):
                return breaker.call(func, *args, **kwargs)
            return sync_wrapper
    
    return decorator


class CircuitBreakerRegistry:
    """
    Registry for managing multiple circuit breakers.
    
    This class provides centralized management of circuit breakers,
    allowing for easy monitoring and configuration of multiple circuits.
    """
    
    def __init__(self):
        """Initialize circuit breaker registry."""
        self._breakers: Dict[str, CircuitBreaker] = {}
        self._lock = threading.Lock()
        self._logger = logging.getLogger(__name__)
    
    def register(self, name: str, config: CircuitBreakerConfig) -> CircuitBreaker:
        """
        Register a new circuit breaker.
        
        Args:
            name: Unique name for the circuit breaker
            config: Circuit breaker configuration
            
        Returns:
            CircuitBreaker instance
            
        Raises:
            ValueError: If circuit breaker with same name already exists
        """
        with self._lock:
            if name in self._breakers:
                raise ValueError(f"Circuit breaker '{name}' already registered")
            
            # Update config name to match registry name
            config.name = name
            breaker = CircuitBreaker(config)
            self._breakers[name] = breaker
            
            self._logger.info(f"Circuit breaker '{name}' registered")
            return breaker
    
    def get(self, name: str) -> Optional[CircuitBreaker]:
        """
        Get circuit breaker by name.
        
        Args:
            name: Circuit breaker name
            
        Returns:
            CircuitBreaker instance or None if not found
        """
        with self._lock:
            return self._breakers.get(name)
    
    def get_or_create(self, name: str, config: CircuitBreakerConfig) -> CircuitBreaker:
        """
        Get existing circuit breaker or create new one.
        
        Args:
            name: Circuit breaker name
            config: Circuit breaker configuration (used only if creating new)
            
        Returns:
            CircuitBreaker instance
        """
        with self._lock:
            if name in self._breakers:
                return self._breakers[name]
            
            config.name = name
            breaker = CircuitBreaker(config)
            self._breakers[name] = breaker
            
            self._logger.info(f"Circuit breaker '{name}' created")
            return breaker
    
    def remove(self, name: str) -> bool:
        """
        Remove circuit breaker from registry.
        
        Args:
            name: Circuit breaker name
            
        Returns:
            True if removed, False if not found
        """
        with self._lock:
            if name in self._breakers:
                del self._breakers[name]
                self._logger.info(f"Circuit breaker '{name}' removed")
                return True
            return False
    
    def list_breakers(self) -> Dict[str, CircuitBreaker]:
        """
        Get all registered circuit breakers.
        
        Returns:
            Dictionary of circuit breaker name to instance
        """
        with self._lock:
            return self._breakers.copy()
    
    def get_all_stats(self) -> Dict[str, Dict[str, Any]]:
        """
        Get statistics for all circuit breakers.
        
        Returns:
            Dictionary of circuit breaker name to statistics
        """
        with self._lock:
            return {name: breaker.get_stats() for name, breaker in self._breakers.items()}
    
    def reset_all(self) -> None:
        """Reset all circuit breakers to closed state."""
        with self._lock:
            for breaker in self._breakers.values():
                breaker.reset()
            self._logger.info("All circuit breakers reset")
    
    def get_health_summary(self) -> Dict[str, Any]:
        """
        Get health summary for all circuit breakers.
        
        Returns:
            Dictionary with overall health information
        """
        with self._lock:
            total_breakers = len(self._breakers)
            healthy_breakers = sum(1 for b in self._breakers.values() if b.is_closed())
            open_breakers = sum(1 for b in self._breakers.values() if b.is_open())
            half_open_breakers = sum(1 for b in self._breakers.values() if b.is_half_open())
            
            return {
                "total_breakers": total_breakers,
                "healthy_breakers": healthy_breakers,
                "open_breakers": open_breakers,
                "half_open_breakers": half_open_breakers,
                "overall_health": healthy_breakers / max(1, total_breakers),
                "breaker_states": {
                    name: breaker.state.value 
                    for name, breaker in self._breakers.items()
                }
            }


# Global circuit breaker registry
_registry = CircuitBreakerRegistry()


def get_circuit_breaker_registry() -> CircuitBreakerRegistry:
    """Get global circuit breaker registry."""
    return _registry


def get_circuit_breaker(name: str, config: Optional[CircuitBreakerConfig] = None) -> CircuitBreaker:
    """
    Get or create circuit breaker from global registry.
    
    Args:
        name: Circuit breaker name
        config: Configuration (required if creating new circuit breaker)
        
    Returns:
        CircuitBreaker instance
        
    Raises:
        ValueError: If circuit breaker doesn't exist and no config provided
    """
    breaker = _registry.get(name)
    if breaker is None:
        if config is None:
            raise ValueError(f"Circuit breaker '{name}' not found and no config provided")
        breaker = _registry.register(name, config)
    
    return breaker