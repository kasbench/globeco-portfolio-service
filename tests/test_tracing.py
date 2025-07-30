import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from app.tracing import trace_database_call


@pytest.fixture
def mock_tracer():
    """Mock the tracer to capture span creation"""
    with patch('app.tracing.tracer') as mock_tracer:
        mock_span = MagicMock()
        mock_tracer.start_as_current_span.return_value.__enter__.return_value = mock_span
        mock_tracer.start_as_current_span.return_value.__exit__.return_value = None
        yield mock_tracer, mock_span


@pytest.mark.asyncio
async def test_trace_database_call_success(mock_tracer):
    """Test that database calls are properly traced on success"""
    mock_tracer_obj, mock_span = mock_tracer
    
    # Mock database operation
    mock_result = ["portfolio1", "portfolio2"]
    mock_operation = AsyncMock(return_value=mock_result)
    
    # Execute traced database call
    result = await trace_database_call(
        "find_all",
        "portfolio", 
        mock_operation,
        **{"db.query.limit": 10}
    )
    
    # Verify result
    assert result == mock_result
    mock_operation.assert_called_once()
    
    # Verify span was created with correct name and attributes
    mock_tracer_obj.start_as_current_span.assert_called_once_with(
        "db.portfolio.find_all",
        attributes={
            "db.system": "mongodb",
            "db.name": "portfolio_db",
            "db.collection.name": "portfolio",
            "db.operation": "find_all",
            "db.query.limit": 10
        }
    )
    
    # Verify span status was set to OK
    mock_span.set_status.assert_called_once()
    status_call = mock_span.set_status.call_args[0][0]
    from opentelemetry import trace
    assert status_call.status_code == trace.StatusCode.OK
    mock_span.set_attribute.assert_called_once_with("db.result.count", 2)


@pytest.mark.asyncio
async def test_trace_database_call_error(mock_tracer):
    """Test that database call errors are properly traced"""
    mock_tracer_obj, mock_span = mock_tracer
    
    # Mock database operation that raises an exception
    test_error = Exception("Database connection failed")
    mock_operation = AsyncMock(side_effect=test_error)
    
    # Execute traced database call and expect exception
    with pytest.raises(Exception, match="Database connection failed"):
        await trace_database_call(
            "find_by_id",
            "portfolio",
            mock_operation
        )
    
    mock_operation.assert_called_once()
    
    # Verify span was created with correct name and attributes
    mock_tracer_obj.start_as_current_span.assert_called_once_with(
        "db.portfolio.find_by_id",
        attributes={
            "db.system": "mongodb",
            "db.name": "portfolio_db",
            "db.collection.name": "portfolio",
            "db.operation": "find_by_id"
        }
    )
    
    # Verify span status was set to ERROR and exception was recorded
    mock_span.set_status.assert_called_once()
    status_call = mock_span.set_status.call_args[0][0]
    from opentelemetry import trace
    assert status_call.status_code == trace.StatusCode.ERROR
    assert status_call.description == str(test_error)
    mock_span.record_exception.assert_called_once_with(test_error)


@pytest.mark.asyncio
async def test_trace_database_call_count_operation(mock_tracer):
    """Test that count operations add result count attribute"""
    mock_tracer_obj, mock_span = mock_tracer
    
    # Mock count operation
    mock_count = 42
    mock_operation = AsyncMock(return_value=mock_count)
    
    # Execute traced database call
    result = await trace_database_call(
        "count",
        "portfolio",
        mock_operation
    )
    
    # Verify result
    assert result == mock_count
    
    # Verify span was created
    mock_tracer_obj.start_as_current_span.assert_called_once()
    
    # Verify span attributes include count
    mock_span.set_status.assert_called_once()
    status_call = mock_span.set_status.call_args[0][0]
    from opentelemetry import trace
    assert status_call.status_code == trace.StatusCode.OK
    mock_span.set_attribute.assert_called_once_with("db.result.count", 42)