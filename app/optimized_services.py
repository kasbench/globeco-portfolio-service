"""
Optimized Portfolio Service with fast-path bulk operations.

This module provides performance-optimized service implementations that minimize
overhead while maintaining functionality and reliability.
"""

from app.models import Portfolio
from app.schemas import PortfolioPostDTO
from app.database import create_optimized_client, test_connection_health
from app.config import settings
from app.logging_config import get_logger
from typing import List, Set, Optional
from pymongo.errors import (
    DuplicateKeyError,
    BulkWriteError,
    ConnectionFailure,
    ServerSelectionTimeoutError,
    NetworkTimeout,
    AutoReconnect,
    WriteError,
    OperationFailure
)
from datetime import datetime, UTC
import asyncio
from motor.motor_asyncio import AsyncIOMotorClient

logger = get_logger(__name__)


class OptimizedPortfolioService:
    """
    Optimized Portfolio Service with fast-path bulk creation.
    
    Implements streamlined validation using set-based duplicate checking
    and direct insert_many operations without excessive logging.
    """
    
    def __init__(self):
        """Initialize optimized service with connection management."""
        self._client: Optional[AsyncIOMotorClient] = None
        self._db = None
        self._collection = None
    
    async def _ensure_connection(self) -> None:
        """Ensure database connection is established and healthy."""
        if self._client is None:
            self._client = create_optimized_client()
            self._db = self._client[settings.mongodb_db]
            self._collection = self._db.portfolio
            
            # Test connection health
            if not await test_connection_health(self._client):
                await self._close_connection()
                raise ConnectionFailure("Failed to establish healthy MongoDB connection")
    
    async def _close_connection(self) -> None:
        """Close database connection and cleanup resources."""
        if self._client:
            self._client.close()
            self._client = None
            self._db = None
            self._collection = None
    
    async def __aenter__(self):
        """Async context manager entry."""
        await self._ensure_connection()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self._close_connection()
    
    @staticmethod
    def _validate_bulk_request_fast(portfolio_dtos: List[PortfolioPostDTO]) -> None:
        """
        Fast validation for bulk request constraints.
        
        Args:
            portfolio_dtos: List of PortfolioPostDTO objects to validate
            
        Raises:
            ValueError: If validation fails with descriptive error message
        """
        # Quick size checks
        if not portfolio_dtos:
            raise ValueError("Request must contain at least 1 portfolio")
        
        if len(portfolio_dtos) > 100:
            raise ValueError("Request cannot contain more than 100 portfolios")
    
    @staticmethod
    def _check_duplicates_fast(portfolio_dtos: List[PortfolioPostDTO]) -> None:
        """
        Fast duplicate checking using set-based approach.
        
        Args:
            portfolio_dtos: List of PortfolioPostDTO objects to check
            
        Raises:
            ValueError: If duplicate names are found
        """
        # Use set for O(n) duplicate detection instead of O(n²)
        seen_names: Set[str] = set()
        duplicates: List[str] = []
        
        for dto in portfolio_dtos:
            # Normalize name for comparison (strip whitespace, lowercase)
            normalized_name = dto.name.strip().lower()
            
            if normalized_name in seen_names:
                if normalized_name not in duplicates:  # Avoid duplicate duplicates
                    duplicates.append(dto.name)
            else:
                seen_names.add(normalized_name)
        
        if duplicates:
            raise ValueError(f"Duplicate portfolio names found: {', '.join(duplicates)}")
    
    async def _check_existing_names_fast(self, portfolio_names: List[str]) -> List[str]:
        """
        Fast check for existing portfolio names in database.
        
        Args:
            portfolio_names: List of portfolio names to check
            
        Returns:
            List of names that already exist in database
        """
        if not portfolio_names:
            return []
        
        # Use $in query for efficient batch lookup
        normalized_names = [name.strip() for name in portfolio_names]
        
        # Create case-insensitive regex patterns for all names at once
        regex_patterns = [{"name": {"$regex": f"^{name}$", "$options": "i"}} for name in normalized_names]
        
        # Single query to check all names
        existing_docs = await self._collection.find(
            {"$or": regex_patterns},
            {"name": 1, "_id": 0}  # Only return name field
        ).to_list(length=len(portfolio_names))
        
        return [doc["name"] for doc in existing_docs]
    
    async def create_portfolios_bulk_fast(self, portfolio_dtos: List[PortfolioPostDTO]) -> List[Portfolio]:
        """
        Ultra-fast bulk portfolio creation with minimal overhead.
        
        Implements:
        - Streamlined validation using set-based duplicate checking
        - Direct insert_many operations without excessive logging
        - Fast-path execution with minimal tracing overhead
        
        Args:
            portfolio_dtos: List of PortfolioPostDTO objects to create
            
        Returns:
            List of created Portfolio objects
            
        Raises:
            ValueError: If validation fails
            Exception: If bulk operation fails
        """
        # Minimal logging for performance - only log start and completion
        logger.info(f"Starting fast bulk creation: count={len(portfolio_dtos) if portfolio_dtos else 0}")
        
        # Fast validation (no detailed logging)
        self._validate_bulk_request_fast(portfolio_dtos)
        self._check_duplicates_fast(portfolio_dtos)
        
        # Ensure connection
        await self._ensure_connection()
        
        # Check for existing names in database
        portfolio_names = [dto.name for dto in portfolio_dtos]
        existing_names = await self._check_existing_names_fast(portfolio_names)
        
        if existing_names:
            raise ValueError(f"Portfolios already exist: {', '.join(existing_names)}")
        
        # Convert DTOs to documents for direct insertion
        current_time = datetime.now(UTC)
        documents = []
        
        for dto in portfolio_dtos:
            doc = {
                "name": dto.name,
                "dateCreated": dto.dateCreated if dto.dateCreated else current_time,
                "version": dto.version if dto.version is not None else 1
            }
            documents.append(doc)
        
        # Execute fast bulk insert
        try:
            # Direct insert_many without Beanie overhead for maximum performance
            insert_result = await self._collection.insert_many(
                documents,
                ordered=False  # Allow partial success, better performance
            )
            
            # Convert inserted documents back to Portfolio objects
            portfolios = []
            for i, doc in enumerate(documents):
                doc["_id"] = insert_result.inserted_ids[i]
                # Create Portfolio object from document
                portfolio = Portfolio(
                    id=doc["_id"],
                    name=doc["name"],
                    dateCreated=doc["dateCreated"],
                    version=doc["version"]
                )
                portfolios.append(portfolio)
            
            # Minimal success logging
            logger.info(f"Fast bulk creation completed: created={len(portfolios)}")
            return portfolios
            
        except BulkWriteError as e:
            # Handle partial failures in bulk operations
            successful_count = len(e.details.get("writeErrors", []))
            total_count = len(documents)
            
            logger.error(
                f"Bulk write partial failure: successful={successful_count}, "
                f"total={total_count}, errors={len(e.details.get('writeErrors', []))}"
            )
            
            # Re-raise with simplified error message
            raise ValueError(f"Bulk operation partially failed: {successful_count}/{total_count} succeeded")
            
        except DuplicateKeyError as e:
            logger.error(f"Duplicate key error in bulk operation: {e}")
            raise ValueError("Duplicate portfolio names detected during insertion")
            
        except (ConnectionFailure, ServerSelectionTimeoutError, NetworkTimeout, AutoReconnect) as e:
            logger.error(f"Database connection error during bulk operation: {e}")
            raise ConnectionFailure(f"Database connection failed: {e}")
            
        except Exception as e:
            logger.error(f"Unexpected error in fast bulk creation: {e}")
            raise
    
    async def create_portfolios_bulk_with_retry(
        self, 
        portfolio_dtos: List[PortfolioPostDTO],
        max_retries: int = 2
    ) -> List[Portfolio]:
        """
        Fast bulk creation with minimal retry logic.
        
        Args:
            portfolio_dtos: List of PortfolioPostDTO objects to create
            max_retries: Maximum retry attempts (default: 2 for performance)
            
        Returns:
            List of created Portfolio objects
        """
        last_exception = None
        
        for attempt in range(max_retries + 1):
            try:
                return await self.create_portfolios_bulk_fast(portfolio_dtos)
                
            except (ConnectionFailure, ServerSelectionTimeoutError, NetworkTimeout, AutoReconnect) as e:
                last_exception = e
                
                if attempt >= max_retries:
                    logger.error(f"Fast bulk creation failed after {attempt + 1} attempts: {e}")
                    raise
                
                # Brief delay before retry (minimal for performance)
                delay = min(1.0 * (attempt + 1), 3.0)  # 1s, 2s, 3s max
                logger.warning(f"Retrying fast bulk creation: attempt={attempt + 1}, delay={delay}s")
                await asyncio.sleep(delay)
                
                # Reset connection for retry
                await self._close_connection()
                
            except (ValueError, DuplicateKeyError, WriteError, OperationFailure) as e:
                # Non-recoverable errors - don't retry
                logger.error(f"Non-recoverable error in fast bulk creation: {e}")
                raise
        
        # Should not reach here, but handle gracefully
        if last_exception:
            raise last_exception
        else:
            raise RuntimeError("Fast bulk creation failed without exception")


# Convenience function for direct usage
async def create_portfolios_optimized(portfolio_dtos: List[PortfolioPostDTO]) -> List[Portfolio]:
    """
    Convenience function for optimized bulk portfolio creation.
    
    Args:
        portfolio_dtos: List of PortfolioPostDTO objects to create
        
    Returns:
        List of created Portfolio objects
    """
    async with OptimizedPortfolioService() as service:
        return await service.create_portfolios_bulk_with_retry(portfolio_dtos)


# Performance comparison function for testing
async def compare_bulk_performance(
    portfolio_dtos: List[PortfolioPostDTO],
    use_optimized: bool = True
) -> dict:
    """
    Compare performance between optimized and standard bulk operations.
    
    Args:
        portfolio_dtos: List of PortfolioPostDTO objects to create
        use_optimized: Whether to use optimized service
        
    Returns:
        Dictionary with performance metrics
    """
    import time
    
    start_time = time.perf_counter()
    
    try:
        if use_optimized:
            result = await create_portfolios_optimized(portfolio_dtos)
        else:
            from app.services import PortfolioService
            result = await PortfolioService.create_portfolios_bulk(portfolio_dtos)
        
        end_time = time.perf_counter()
        duration_ms = (end_time - start_time) * 1000
        
        return {
            "success": True,
            "duration_ms": duration_ms,
            "portfolios_created": len(result),
            "service_type": "optimized" if use_optimized else "standard",
            "throughput_per_second": len(result) / (duration_ms / 1000) if duration_ms > 0 else 0
        }
        
    except Exception as e:
        end_time = time.perf_counter()
        duration_ms = (end_time - start_time) * 1000
        
        return {
            "success": False,
            "duration_ms": duration_ms,
            "error": str(e),
            "service_type": "optimized" if use_optimized else "standard"
        }