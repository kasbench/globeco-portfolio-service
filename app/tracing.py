from opentelemetry import trace
from functools import wraps
from typing import Any, Callable, TypeVar, Awaitable
import asyncio
import os

# Get tracer for database operations
tracer = trace.get_tracer(__name__)

F = TypeVar('F', bound=Callable[..., Awaitable[Any]])

# Environment-based database tracing configuration
def _is_database_tracing_enabled() -> bool:
    """
    Check if database tracing is enabled based on environment configuration.
    
    Returns:
        True if database tracing should be enabled, False for fast-path execution
    """
    # Check environment variable first (for runtime override)
    env_value = os.getenv("ENABLE_DATABASE_TRACING")
    if env_value is not None:
        return env_value.lower() in ("true", "1", "yes", "on")
    
    # Check environment profile - production defaults to False for performance
    try:
        from app.environment_config import get_config_manager
        config_manager = get_config_manager()
        return config_manager.current_profile.monitoring.enable_database_tracing
    except Exception:
        # Fallback: disable tracing in production, enable in development
        environment = os.getenv("PORTFOLIO_SERVICE_ENV", "development").lower()
        return environment != "production"

def trace_database_operation(operation_name: str, collection_name: str = "portfolio"):
    """
    Decorator to trace database operations with OpenTelemetry spans.
    
    Implements conditional tracing based on environment configuration for optimal performance.
    
    Args:
        operation_name: Name of the database operation (e.g., "find_all", "find_by_id", "insert", "update", "delete")
        collection_name: Name of the MongoDB collection being accessed
    """
    def decorator(func: F) -> F:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Fast-path execution when tracing is disabled
            if not _is_database_tracing_enabled():
                return await func(*args, **kwargs)
            
            # Full tracing path when enabled
            with tracer.start_as_current_span(
                f"db.{collection_name}.{operation_name}",
                attributes={
                    "db.system": "mongodb",
                    "db.name": "portfolio_db",
                    "db.collection.name": collection_name,
                    "db.operation": operation_name,
                }
            ) as span:
                try:
                    result = await func(*args, **kwargs)
                    span.set_status(trace.Status(trace.StatusCode.OK))
                    return result
                except Exception as e:
                    span.set_status(trace.Status(trace.StatusCode.ERROR, str(e)))
                    span.record_exception(e)
                    raise
        return wrapper
    return decorator

async def trace_database_call(operation_name: str, collection_name: str, operation_func: Callable, **extra_attributes):
    """
    Context manager function to trace database operations with conditional tracing.
    
    Implements fast-path execution when tracing is disabled for optimal performance.
    
    Args:
        operation_name: Name of the database operation
        collection_name: Name of the MongoDB collection
        operation_func: The async function to execute
        extra_attributes: Additional attributes to add to the span
    """
    # Fast-path execution when tracing is disabled
    if not _is_database_tracing_enabled():
        return await operation_func()
    
    # Full tracing path when enabled
    attributes = {
        "db.system": "mongodb",
        "db.name": "portfolio_db", 
        "db.collection.name": collection_name,
        "db.operation": operation_name,
        **extra_attributes
    }
    
    with tracer.start_as_current_span(
        f"db.{collection_name}.{operation_name}",
        attributes=attributes
    ) as span:
        try:
            result = await operation_func()
            span.set_status(trace.Status(trace.StatusCode.OK))
            
            # Add result-specific attributes
            if hasattr(result, '__len__') and operation_name in ["find_all", "find_with_pagination"]:
                span.set_attribute("db.result.count", len(result))
            elif result is not None and operation_name == "count":
                span.set_attribute("db.result.count", result)
                
            return result
        except Exception as e:
            span.set_status(trace.Status(trace.StatusCode.ERROR, str(e)))
            span.record_exception(e)
            raise