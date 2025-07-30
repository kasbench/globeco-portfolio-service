from opentelemetry import trace
from functools import wraps
from typing import Any, Callable, TypeVar, Awaitable
import asyncio

# Get tracer for database operations
tracer = trace.get_tracer(__name__)

F = TypeVar('F', bound=Callable[..., Awaitable[Any]])

def trace_database_operation(operation_name: str, collection_name: str = "portfolio"):
    """
    Decorator to trace database operations with OpenTelemetry spans
    
    Args:
        operation_name: Name of the database operation (e.g., "find_all", "find_by_id", "insert", "update", "delete")
        collection_name: Name of the MongoDB collection being accessed
    """
    def decorator(func: F) -> F:
        @wraps(func)
        async def wrapper(*args, **kwargs):
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
    Context manager function to trace database operations
    
    Args:
        operation_name: Name of the database operation
        collection_name: Name of the MongoDB collection
        operation_func: The async function to execute
        extra_attributes: Additional attributes to add to the span
    """
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