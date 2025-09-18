"""
Unit tests for the retry logic utility in PortfolioService.

Tests cover:
- Successful operations without retries
- Retry behavior with recoverable errors
- Immediate failure with non-recoverable errors
- Exponential backoff timing and maximum retry limits
- Various database error conditions
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, patch, MagicMock, PropertyMock
from datetime import datetime
from pymongo.errors import (
    ConnectionFailure,
    ServerSelectionTimeoutError,
    NetworkTimeout,
    AutoReconnect,
    DuplicateKeyError,
    WriteError,
    OperationFailure
)

from app.services import PortfolioService


class TestRetryLogicUtility:
    """Test suite for the _execute_with_retry method"""

    @pytest.mark.asyncio
    async def test_successful_operation_without_retries(self):
        """Test that successful operations complete without any retries"""
        # Arrange
        expected_result = "success"
        mock_operation = AsyncMock(return_value=expected_result)
        
        # Act
        result = await PortfolioService._execute_with_retry(
            operation=mock_operation,
            max_retries=3,
            operation_name="test_operation"
        )
        
        # Assert
        assert result == expected_result
        assert mock_operation.call_count == 1

    @pytest.mark.asyncio
    async def test_retry_with_connection_failure(self):
        """Test retry behavior with ConnectionFailure (recoverable error)"""
        # Arrange
        expected_result = "success_after_retry"
        mock_operation = AsyncMock()
        
        # First two calls fail with ConnectionFailure, third succeeds
        mock_operation.side_effect = [
            ConnectionFailure("Connection lost"),
            ConnectionFailure("Still no connection"),
            expected_result
        ]
        
        # Act
        with patch('asyncio.sleep', new_callable=AsyncMock) as mock_sleep:
            result = await PortfolioService._execute_with_retry(
                operation=mock_operation,
                max_retries=3,
                operation_name="test_connection_retry"
            )
        
        # Assert
        assert result == expected_result
        assert mock_operation.call_count == 3
        
        # Verify exponential backoff delays were used
        expected_delays = [1, 2]  # First retry after 1s, second after 2s
        actual_delays = [call.args[0] for call in mock_sleep.call_args_list]
        assert actual_delays == expected_delays

    @pytest.mark.asyncio
    async def test_retry_with_server_selection_timeout(self):
        """Test retry behavior with ServerSelectionTimeoutError (recoverable error)"""
        # Arrange
        expected_result = "success_after_timeout_retry"
        mock_operation = AsyncMock()
        
        # First call fails, second succeeds
        mock_operation.side_effect = [
            ServerSelectionTimeoutError("Server selection timeout"),
            expected_result
        ]
        
        # Act
        with patch('asyncio.sleep', new_callable=AsyncMock) as mock_sleep:
            result = await PortfolioService._execute_with_retry(
                operation=mock_operation,
                max_retries=3,
                operation_name="test_timeout_retry"
            )
        
        # Assert
        assert result == expected_result
        assert mock_operation.call_count == 2
        assert mock_sleep.call_count == 1
        assert mock_sleep.call_args[0][0] == 1  # First retry delay is 1 second

    @pytest.mark.asyncio
    async def test_retry_with_network_timeout(self):
        """Test retry behavior with NetworkTimeout (recoverable error)"""
        # Arrange
        expected_result = "success_after_network_retry"
        mock_operation = AsyncMock()
        mock_operation.side_effect = [NetworkTimeout("Network timeout"), expected_result]
        
        # Act
        with patch('asyncio.sleep', new_callable=AsyncMock):
            result = await PortfolioService._execute_with_retry(
                operation=mock_operation,
                max_retries=3,
                operation_name="test_network_retry"
            )
        
        # Assert
        assert result == expected_result
        assert mock_operation.call_count == 2

    @pytest.mark.asyncio
    async def test_retry_with_auto_reconnect(self):
        """Test retry behavior with AutoReconnect (recoverable error)"""
        # Arrange
        expected_result = "success_after_reconnect"
        mock_operation = AsyncMock()
        mock_operation.side_effect = [AutoReconnect("Auto reconnect"), expected_result]
        
        # Act
        with patch('asyncio.sleep', new_callable=AsyncMock):
            result = await PortfolioService._execute_with_retry(
                operation=mock_operation,
                max_retries=3,
                operation_name="test_reconnect_retry"
            )
        
        # Assert
        assert result == expected_result
        assert mock_operation.call_count == 2

    @pytest.mark.asyncio
    async def test_immediate_failure_with_duplicate_key_error(self):
        """Test immediate failure with DuplicateKeyError (non-recoverable error)"""
        # Arrange
        mock_operation = AsyncMock()
        duplicate_error = DuplicateKeyError("Duplicate key error")
        mock_operation.side_effect = duplicate_error
        
        # Act & Assert
        with pytest.raises(DuplicateKeyError) as exc_info:
            await PortfolioService._execute_with_retry(
                operation=mock_operation,
                max_retries=3,
                operation_name="test_duplicate_key"
            )
        
        assert exc_info.value == duplicate_error
        assert mock_operation.call_count == 1  # No retries

    @pytest.mark.asyncio
    async def test_immediate_failure_with_write_error(self):
        """Test immediate failure with WriteError (non-recoverable error)"""
        # Arrange
        mock_operation = AsyncMock()
        write_error = WriteError("Write operation failed")
        mock_operation.side_effect = write_error
        
        # Act & Assert
        with pytest.raises(WriteError) as exc_info:
            await PortfolioService._execute_with_retry(
                operation=mock_operation,
                max_retries=3,
                operation_name="test_write_error"
            )
        
        assert exc_info.value == write_error
        assert mock_operation.call_count == 1  # No retries

    @pytest.mark.asyncio
    async def test_immediate_failure_with_operation_failure_duplicate_key_code(self):
        """Test immediate failure with OperationFailure having duplicate key error code"""
        # Arrange
        mock_operation = AsyncMock()
        operation_error = OperationFailure("Duplicate key", code=11000)
        mock_operation.side_effect = operation_error
        
        # Act & Assert
        with pytest.raises(OperationFailure) as exc_info:
            await PortfolioService._execute_with_retry(
                operation=mock_operation,
                max_retries=3,
                operation_name="test_operation_failure_duplicate"
            )
        
        assert exc_info.value == operation_error
        assert mock_operation.call_count == 1  # No retries

    @pytest.mark.asyncio
    async def test_retry_with_operation_failure_timeout_code(self):
        """Test retry behavior with OperationFailure having timeout error code"""
        # Arrange
        expected_result = "success_after_timeout"
        mock_operation = AsyncMock()
        timeout_error = OperationFailure("Operation exceeded time limit", code=50)
        mock_operation.side_effect = [timeout_error, expected_result]
        
        # Act
        with patch('asyncio.sleep', new_callable=AsyncMock):
            result = await PortfolioService._execute_with_retry(
                operation=mock_operation,
                max_retries=3,
                operation_name="test_operation_timeout"
            )
        
        # Assert
        assert result == expected_result
        assert mock_operation.call_count == 2

    @pytest.mark.asyncio
    async def test_exponential_backoff_timing(self):
        """Test that exponential backoff uses correct delays: 1s, 2s, 4s"""
        # Arrange
        mock_operation = AsyncMock()
        mock_operation.side_effect = [
            ConnectionFailure("Fail 1"),
            ConnectionFailure("Fail 2"),
            ConnectionFailure("Fail 3"),
            "success"
        ]
        
        # Act
        with patch('asyncio.sleep', new_callable=AsyncMock) as mock_sleep:
            result = await PortfolioService._execute_with_retry(
                operation=mock_operation,
                max_retries=3,
                operation_name="test_backoff_timing"
            )
        
        # Assert
        assert result == "success"
        assert mock_operation.call_count == 4
        
        # Verify exact delay sequence
        expected_delays = [1, 2, 4]
        actual_delays = [call.args[0] for call in mock_sleep.call_args_list]
        assert actual_delays == expected_delays

    @pytest.mark.asyncio
    async def test_maximum_retry_limit_exhausted(self):
        """Test that operation fails after maximum retry attempts are exhausted"""
        # Arrange
        mock_operation = AsyncMock()
        connection_error = ConnectionFailure("Persistent connection failure")
        mock_operation.side_effect = connection_error
        
        # Act & Assert
        with patch('asyncio.sleep', new_callable=AsyncMock) as mock_sleep:
            with pytest.raises(ConnectionFailure) as exc_info:
                await PortfolioService._execute_with_retry(
                    operation=mock_operation,
                    max_retries=3,
                    operation_name="test_max_retries"
                )
        
        assert exc_info.value == connection_error
        assert mock_operation.call_count == 4  # Initial attempt + 3 retries
        assert mock_sleep.call_count == 3  # 3 retry delays

    @pytest.mark.asyncio
    async def test_custom_max_retries_parameter(self):
        """Test that custom max_retries parameter is respected"""
        # Arrange
        mock_operation = AsyncMock()
        mock_operation.side_effect = ConnectionFailure("Always fails")
        
        # Act & Assert
        with patch('asyncio.sleep', new_callable=AsyncMock) as mock_sleep:
            with pytest.raises(ConnectionFailure):
                await PortfolioService._execute_with_retry(
                    operation=mock_operation,
                    max_retries=1,  # Custom retry limit
                    operation_name="test_custom_retries"
                )
        
        assert mock_operation.call_count == 2  # Initial attempt + 1 retry
        assert mock_sleep.call_count == 1  # 1 retry delay

    @pytest.mark.asyncio
    async def test_unknown_error_not_retried(self):
        """Test that unknown errors are not retried (conservative approach)"""
        # Arrange
        mock_operation = AsyncMock()
        unknown_error = ValueError("Unknown error type")
        mock_operation.side_effect = unknown_error
        
        # Act & Assert
        with pytest.raises(ValueError) as exc_info:
            await PortfolioService._execute_with_retry(
                operation=mock_operation,
                max_retries=3,
                operation_name="test_unknown_error"
            )
        
        assert exc_info.value == unknown_error
        assert mock_operation.call_count == 1  # No retries for unknown errors

    @pytest.mark.asyncio
    async def test_operation_name_parameter_used_in_logging(self):
        """Test that operation_name parameter is used for logging purposes"""
        # Arrange
        mock_operation = AsyncMock(return_value="success")
        operation_name = "custom_operation_name"
        
        # Act
        with patch('app.services.logger') as mock_logger:
            result = await PortfolioService._execute_with_retry(
                operation=mock_operation,
                operation_name=operation_name
            )
        
        # Assert
        assert result == "success"
        # Verify that the operation name was used in logging calls
        debug_calls = [call for call in mock_logger.debug.call_args_list]
        assert any(operation_name in str(call) for call in debug_calls)

    @pytest.mark.asyncio
    async def test_retry_success_logging(self):
        """Test that successful retry attempts are properly logged"""
        # Arrange
        mock_operation = AsyncMock()
        mock_operation.side_effect = [ConnectionFailure("Temporary failure"), "success"]
        
        # Act
        with patch('asyncio.sleep', new_callable=AsyncMock):
            with patch('app.services.logger') as mock_logger:
                result = await PortfolioService._execute_with_retry(
                    operation=mock_operation,
                    operation_name="test_retry_logging"
                )
        
        # Assert
        assert result == "success"
        # Verify that retry success was logged
        info_calls = [call for call in mock_logger.info.call_args_list]
        assert any("succeeded after retry" in str(call) for call in info_calls)


class TestRecoverableErrorDetection:
    """Test suite for the _is_recoverable_error method"""

    def test_connection_failure_is_recoverable(self):
        """Test that ConnectionFailure is identified as recoverable"""
        error = ConnectionFailure("Connection lost")
        assert PortfolioService._is_recoverable_error(error) is True

    def test_server_selection_timeout_is_recoverable(self):
        """Test that ServerSelectionTimeoutError is identified as recoverable"""
        error = ServerSelectionTimeoutError("Server selection timeout")
        assert PortfolioService._is_recoverable_error(error) is True

    def test_network_timeout_is_recoverable(self):
        """Test that NetworkTimeout is identified as recoverable"""
        error = NetworkTimeout("Network timeout")
        assert PortfolioService._is_recoverable_error(error) is True

    def test_auto_reconnect_is_recoverable(self):
        """Test that AutoReconnect is identified as recoverable"""
        error = AutoReconnect("Auto reconnect")
        assert PortfolioService._is_recoverable_error(error) is True

    def test_duplicate_key_error_is_not_recoverable(self):
        """Test that DuplicateKeyError is identified as non-recoverable"""
        error = DuplicateKeyError("Duplicate key")
        assert PortfolioService._is_recoverable_error(error) is False

    def test_write_error_is_not_recoverable(self):
        """Test that WriteError is identified as non-recoverable"""
        error = WriteError("Write failed")
        assert PortfolioService._is_recoverable_error(error) is False

    def test_operation_failure_duplicate_key_code_not_recoverable(self):
        """Test that OperationFailure with duplicate key code is non-recoverable"""
        error = OperationFailure("Duplicate key", code=11000)
        assert PortfolioService._is_recoverable_error(error) is False

    def test_operation_failure_legacy_duplicate_key_code_not_recoverable(self):
        """Test that OperationFailure with legacy duplicate key code is non-recoverable"""
        error = OperationFailure("Duplicate key", code=11001)
        assert PortfolioService._is_recoverable_error(error) is False

    def test_operation_failure_bad_value_code_not_recoverable(self):
        """Test that OperationFailure with bad value code is non-recoverable"""
        error = OperationFailure("Bad value", code=16500)
        assert PortfolioService._is_recoverable_error(error) is False

    def test_operation_failure_unauthorized_code_not_recoverable(self):
        """Test that OperationFailure with unauthorized code is non-recoverable"""
        error = OperationFailure("Unauthorized", code=13)
        assert PortfolioService._is_recoverable_error(error) is False

    def test_operation_failure_authentication_failed_code_not_recoverable(self):
        """Test that OperationFailure with authentication failed code is non-recoverable"""
        error = OperationFailure("Authentication failed", code=18)
        assert PortfolioService._is_recoverable_error(error) is False

    def test_operation_failure_timeout_code_is_recoverable(self):
        """Test that OperationFailure with timeout code is recoverable"""
        error = OperationFailure("Exceeded time limit", code=50)
        assert PortfolioService._is_recoverable_error(error) is True

    def test_operation_failure_memory_limit_code_is_recoverable(self):
        """Test that OperationFailure with memory limit code is recoverable"""
        error = OperationFailure("Exceeded memory limit", code=216)
        assert PortfolioService._is_recoverable_error(error) is True

    def test_operation_failure_unknown_code_not_recoverable(self):
        """Test that OperationFailure with unknown code is non-recoverable (conservative)"""
        error = OperationFailure("Unknown error", code=99999)
        assert PortfolioService._is_recoverable_error(error) is False

    def test_operation_failure_without_specific_code_not_recoverable(self):
        """Test that OperationFailure without specific recoverable/non-recoverable code is non-recoverable"""
        # Create an OperationFailure with a code that's not in any specific category
        # This should default to non-recoverable (conservative approach)
        error = OperationFailure("Error with unrecognized code", code=99999)
        assert PortfolioService._is_recoverable_error(error) is False

    def test_unknown_exception_type_not_recoverable(self):
        """Test that unknown exception types are non-recoverable (conservative approach)"""
        error = ValueError("Unknown error type")
        assert PortfolioService._is_recoverable_error(error) is False

    def test_runtime_error_not_recoverable(self):
        """Test that RuntimeError is non-recoverable"""
        error = RuntimeError("Runtime error")
        assert PortfolioService._is_recoverable_error(error) is False

    def test_type_error_not_recoverable(self):
        """Test that TypeError is non-recoverable"""
        error = TypeError("Type error")
        assert PortfolioService._is_recoverable_error(error) is False