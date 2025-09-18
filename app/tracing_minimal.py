"""
Minimal tracing module that bypasses OpenTelemetry for performance.
"""

from typing import Any, Callable, TypeVar, Awaitable
from functools import wraps

F = TypeVar('F', bound=Callable[..., Awaitable[Any]])

def trace_database_operation(operation_name: str, collection_name: str = "portfolio"):
    """
    Minimal decorator that bypasses tracing for performance.
    """
    def decorator(func: F) -> F:
        # Just return the original function without tracing
        return func
    return decorator

async def trace_database_call(operation_name: str, collection_name: str, operation_func: Callable, **extra_attributes):
    """
    Minimal database call wrapper that bypasses tracing for performance.
    """
    # Just execute the operation without tracing
    return await operation_func()