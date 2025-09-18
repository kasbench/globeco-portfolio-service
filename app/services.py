from app.models import Portfolio
from app.schemas import PortfolioResponseDTO, PaginationDTO, PortfolioSearchResponseDTO, PortfolioPostDTO
from app.tracing import trace_database_call
from app.logging_config import get_logger
from bson import ObjectId
from typing import List, Optional, Tuple, Any, Callable
from pymongo.errors import (
    ConnectionFailure, 
    ServerSelectionTimeoutError, 
    NetworkTimeout, 
    AutoReconnect,
    DuplicateKeyError,
    WriteError,
    OperationFailure
)
from beanie import WriteRules
from datetime import datetime, UTC
import re
import math
import asyncio

logger = get_logger(__name__)


class PortfolioService:
    
    @staticmethod
    async def _execute_with_retry(
        operation: Callable[[], Any], 
        max_retries: int = 3,
        operation_name: str = "database_operation"
    ) -> Any:
        """
        Execute a database operation with exponential backoff retry logic.
        
        Args:
            operation: Async callable to execute
            max_retries: Maximum number of retry attempts (default: 3)
            operation_name: Name of the operation for logging purposes
            
        Returns:
            Result of the operation
            
        Raises:
            The last exception encountered if all retries are exhausted
        """
        # Exponential backoff delays: 1s, 2s, 4s
        delays = [1, 2, 4]
        last_exception = None
        
        for attempt in range(max_retries + 1):  # +1 for initial attempt
            try:
                logger.debug(
                    "Executing database operation",
                    operation=operation_name,
                    attempt=attempt + 1,
                    max_attempts=max_retries + 1
                )
                
                result = await operation()
                
                if attempt > 0:  # Log successful retry
                    logger.info(
                        "Database operation succeeded after retry",
                        operation=operation_name,
                        attempt=attempt + 1,
                        total_attempts=attempt + 1
                    )
                
                return result
                
            except Exception as e:
                last_exception = e
                
                # Check if this is a recoverable error
                is_recoverable = PortfolioService._is_recoverable_error(e)
                
                logger.warning(
                    "Database operation failed",
                    operation=operation_name,
                    attempt=attempt + 1,
                    max_attempts=max_retries + 1,
                    error=str(e),
                    error_type=type(e).__name__,
                    is_recoverable=is_recoverable
                )
                
                # If not recoverable or we've exhausted retries, raise the exception
                if not is_recoverable or attempt >= max_retries:
                    if not is_recoverable:
                        logger.error(
                            "Database operation failed with non-recoverable error",
                            operation=operation_name,
                            error=str(e),
                            error_type=type(e).__name__
                        )
                    else:
                        logger.error(
                            "Database operation failed after all retry attempts",
                            operation=operation_name,
                            total_attempts=attempt + 1,
                            error=str(e),
                            error_type=type(e).__name__
                        )
                    raise e
                
                # Wait before retrying (exponential backoff)
                if attempt < max_retries:
                    delay = delays[min(attempt, len(delays) - 1)]
                    logger.info(
                        "Retrying database operation after delay",
                        operation=operation_name,
                        attempt=attempt + 1,
                        next_attempt=attempt + 2,
                        delay_seconds=delay
                    )
                    await asyncio.sleep(delay)
        
        # This should never be reached, but just in case
        if last_exception:
            raise last_exception
        else:
            raise RuntimeError(f"Operation {operation_name} failed without exception")
    
    @staticmethod
    def _is_recoverable_error(error: Exception) -> bool:
        """
        Determine if a database error is recoverable and should be retried.
        
        Args:
            error: The exception to check
            
        Returns:
            True if the error is recoverable, False otherwise
        """
        # Recoverable errors - typically transient network/connection issues
        recoverable_errors = (
            ConnectionFailure,
            ServerSelectionTimeoutError,
            NetworkTimeout,
            AutoReconnect,
        )
        
        # Non-recoverable errors - typically application/data issues
        non_recoverable_errors = (
            DuplicateKeyError,
            WriteError,
        )
        
        # Check for specific recoverable errors
        if isinstance(error, recoverable_errors):
            return True
            
        # Check for specific non-recoverable errors
        if isinstance(error, non_recoverable_errors):
            return False
            
        # Handle OperationFailure - check error code for specific cases
        if isinstance(error, OperationFailure):
            # Common non-recoverable error codes
            non_recoverable_codes = {
                11000,  # DuplicateKey
                11001,  # DuplicateKey (legacy)
                16500,  # BadValue
                2,      # BadValue
                14,     # TypeMismatch
                9,      # FailedToParse
                40,     # ConflictingUpdateOperators
                16837,  # InvalidOptions
                13,     # Unauthorized
                18,     # AuthenticationFailed
            }
            
            if hasattr(error, 'code') and error.code in non_recoverable_codes:
                return False
                
            # Timeout-related operation failures are recoverable
            timeout_codes = {
                50,     # ExceededTimeLimit
                216,    # ExceededMemoryLimit
            }
            
            if hasattr(error, 'code') and error.code in timeout_codes:
                return True
        
        # For unknown errors, default to non-recoverable to avoid infinite retries
        # This is a conservative approach - better to fail fast than retry indefinitely
        return False
    
    @staticmethod
    async def get_all_portfolios() -> List[Portfolio]:
        """Get all portfolios for v1 API (backward compatibility)"""
        logger.debug("Fetching all portfolios", operation="get_all_portfolios")
        portfolios = await trace_database_call(
            "find_all",
            "portfolio", 
            lambda: Portfolio.find_all().to_list()
        )
        logger.debug("Successfully fetched all portfolios", 
                   operation="get_all_portfolios", 
                   count=len(portfolios))
        return portfolios
    
    @staticmethod
    async def get_portfolio_by_id(portfolio_id: str) -> Optional[Portfolio]:
        """Get a single portfolio by ID"""
        logger.debug("Fetching portfolio by ID", 
                   operation="get_portfolio_by_id", 
                   portfolio_id=portfolio_id)
        try:
            portfolio = await trace_database_call(
                "find_by_id",
                "portfolio",
                lambda: Portfolio.get(ObjectId(portfolio_id))
            )
            if portfolio:
                logger.debug("Successfully found portfolio", 
                           operation="get_portfolio_by_id", 
                           portfolio_id=portfolio_id,
                           portfolio_name=portfolio.name)
            else:
                logger.warning("Portfolio not found", 
                              operation="get_portfolio_by_id", 
                              portfolio_id=portfolio_id)
            return portfolio
        except Exception as e:
            logger.error("Error fetching portfolio by ID", 
                        operation="get_portfolio_by_id", 
                        portfolio_id=portfolio_id,
                        error=str(e))
            return None
    
    @staticmethod
    async def create_portfolio(portfolio: Portfolio) -> Portfolio:
        """Create a new portfolio"""
        logger.debug("Creating new portfolio", 
                   operation="create_portfolio", 
                   portfolio_name=portfolio.name)
        try:
            await trace_database_call(
                "insert",
                "portfolio",
                lambda: portfolio.insert()
            )
            logger.debug("Successfully created portfolio", 
                       operation="create_portfolio", 
                       portfolio_id=str(portfolio.id),
                       portfolio_name=portfolio.name)
            return portfolio
        except Exception as e:
            logger.error("Error creating portfolio", 
                        operation="create_portfolio", 
                        portfolio_name=portfolio.name,
                        error=str(e))
            raise
    
    @staticmethod
    async def update_portfolio(portfolio: Portfolio) -> Portfolio:
        """Update an existing portfolio"""
        logger.debug("Updating portfolio", 
                   operation="update_portfolio", 
                   portfolio_id=str(portfolio.id),
                   portfolio_name=portfolio.name,
                   version=portfolio.version)
        try:
            await trace_database_call(
                "update",
                "portfolio",
                lambda: portfolio.save()
            )
            logger.debug("Successfully updated portfolio", 
                       operation="update_portfolio", 
                       portfolio_id=str(portfolio.id),
                       portfolio_name=portfolio.name,
                       version=portfolio.version)
            return portfolio
        except Exception as e:
            logger.error("Error updating portfolio", 
                        operation="update_portfolio", 
                        portfolio_id=str(portfolio.id),
                        error=str(e))
            raise
    
    @staticmethod
    async def delete_portfolio(portfolio: Portfolio) -> None:
        """Delete a portfolio"""
        logger.debug("Deleting portfolio", 
                   operation="delete_portfolio", 
                   portfolio_id=str(portfolio.id),
                   portfolio_name=portfolio.name)
        try:
            await trace_database_call(
                "delete",
                "portfolio",
                lambda: portfolio.delete()
            )
            logger.debug("Successfully deleted portfolio", 
                       operation="delete_portfolio", 
                       portfolio_id=str(portfolio.id),
                       portfolio_name=portfolio.name)
        except Exception as e:
            logger.error("Error deleting portfolio", 
                        operation="delete_portfolio", 
                        portfolio_id=str(portfolio.id),
                        error=str(e))
            raise
    
    @staticmethod
    async def search_portfolios(
        name: Optional[str] = None,
        name_like: Optional[str] = None,
        limit: int = 50,
        offset: int = 0
    ) -> Tuple[List[Portfolio], int]:
        """
        Search portfolios with pagination for v2 API
        Returns tuple of (portfolios, total_count)
        """
        logger.debug("Searching portfolios", 
                   operation="search_portfolios",
                   name=name,
                   name_like=name_like,
                   limit=limit,
                   offset=offset)
        
        query = {}
        
        if name:
            # Exact match (case-insensitive)
            query["name"] = {"$regex": f"^{re.escape(name)}$", "$options": "i"}
        elif name_like:
            # Partial match (case-insensitive)
            query["name"] = {"$regex": re.escape(name_like), "$options": "i"}
        
        try:
            # Get total count for pagination
            total_count = await trace_database_call(
                "count",
                "portfolio",
                lambda: Portfolio.find(query).count()
            )
            
            # Get paginated results, sorted by dateCreated descending
            portfolios = await trace_database_call(
                "find_with_pagination",
                "portfolio",
                lambda: Portfolio.find(query).sort(-Portfolio.dateCreated).skip(offset).limit(limit).to_list(),
                **{"db.query.limit": limit, "db.query.offset": offset}
            )
            
            logger.debug("Successfully searched portfolios", 
                       operation="search_portfolios",
                       total_count=total_count,
                       returned_count=len(portfolios),
                       limit=limit,
                       offset=offset)
            
            return portfolios, total_count
            
        except Exception as e:
            logger.error("Error searching portfolios", 
                        operation="search_portfolios",
                        name=name,
                        name_like=name_like,
                        error=str(e))
            raise
    
    @staticmethod
    def create_pagination_dto(
        total_elements: int,
        current_page: int,
        page_size: int
    ) -> PaginationDTO:
        """Create pagination metadata"""
        total_pages = math.ceil(total_elements / page_size) if total_elements > 0 else 0
        has_next = current_page < total_pages - 1
        has_previous = current_page > 0
        
        return PaginationDTO(
            totalElements=total_elements,
            totalPages=total_pages,
            currentPage=current_page,
            pageSize=page_size,
            hasNext=has_next,
            hasPrevious=has_previous
        )
    
    @staticmethod
    def _validate_bulk_request(portfolio_dtos: List[PortfolioPostDTO]) -> None:
        """
        Validate bulk request constraints including list size limits.
        
        Args:
            portfolio_dtos: List of PortfolioPostDTO objects to validate
            
        Raises:
            ValueError: If validation fails with descriptive error message
        """
        # Check for empty request
        if not portfolio_dtos or len(portfolio_dtos) == 0:
            logger.warning(
                "Bulk request validation failed: empty request",
                operation="_validate_bulk_request",
                portfolio_count=0
            )
            raise ValueError("Request must contain at least 1 portfolio")
        
        # Check for oversized request
        if len(portfolio_dtos) > 100:
            logger.warning(
                "Bulk request validation failed: oversized request",
                operation="_validate_bulk_request",
                portfolio_count=len(portfolio_dtos),
                max_allowed=100
            )
            raise ValueError("Request cannot contain more than 100 portfolios")
        
        logger.debug(
            "Bulk request size validation passed",
            operation="_validate_bulk_request",
            portfolio_count=len(portfolio_dtos)
        )
    
    @staticmethod
    def _check_duplicate_names(portfolio_dtos: List[PortfolioPostDTO]) -> None:
        """
        Check for duplicate portfolio names within the batch.
        
        Args:
            portfolio_dtos: List of PortfolioPostDTO objects to check
            
        Raises:
            ValueError: If duplicate names are found with details
        """
        # Track names (case-insensitive) and their positions
        name_positions = {}
        duplicates = []
        
        for i, dto in enumerate(portfolio_dtos):
            # Normalize name for comparison (strip whitespace, lowercase)
            normalized_name = dto.name.strip().lower()
            
            if normalized_name in name_positions:
                # Found duplicate
                original_position = name_positions[normalized_name]
                duplicate_info = {
                    "name": dto.name,
                    "positions": [original_position, i],
                    "normalized_name": normalized_name
                }
                
                # Check if we already recorded this duplicate
                existing_duplicate = next(
                    (d for d in duplicates if d["normalized_name"] == normalized_name), 
                    None
                )
                
                if existing_duplicate:
                    # Add this position to existing duplicate record
                    existing_duplicate["positions"].append(i)
                else:
                    # New duplicate found
                    duplicates.append(duplicate_info)
            else:
                # First occurrence of this name
                name_positions[normalized_name] = i
        
        if duplicates:
            # Create detailed error message
            duplicate_names = [d["name"] for d in duplicates]
            error_msg = f"Duplicate portfolio names found in request: {', '.join(duplicate_names)}"
            
            logger.warning(
                "Bulk request validation failed: duplicate names",
                operation="_check_duplicate_names",
                duplicate_count=len(duplicates),
                duplicate_names=duplicate_names,
                duplicate_details=duplicates
            )
            
            raise ValueError(error_msg)
        
        logger.debug(
            "Duplicate name validation passed",
            operation="_check_duplicate_names",
            portfolio_count=len(portfolio_dtos),
            unique_names=len(name_positions)
        )
    
    @staticmethod
    async def create_portfolios_bulk(portfolio_dtos: List[PortfolioPostDTO]) -> List[Portfolio]:
        """
        Create multiple portfolios in a single transaction with retry logic.
        
        Args:
            portfolio_dtos: List of PortfolioPostDTO objects to create
            
        Returns:
            List of created Portfolio objects
            
        Raises:
            ValueError: If validation fails (empty request, oversized request, duplicates)
            Exception: If the bulk operation fails after all retries
        """
        logger.info(
            "Starting bulk portfolio creation",
            operation="create_portfolios_bulk",
            portfolio_count=len(portfolio_dtos) if portfolio_dtos else 0
        )
        
        # Log the request details for debugging
        if portfolio_dtos:
            request_summary = []
            for i, dto in enumerate(portfolio_dtos):
                request_summary.append({
                    "index": i,
                    "name": dto.name,
                    "dateCreated": dto.dateCreated.isoformat() if dto.dateCreated else None,
                    "version": dto.version
                })
            
            logger.info(
                "Bulk portfolio creation request details",
                operation="create_portfolios_bulk",
                request_summary=request_summary
            )
        
        # Validate bulk request constraints
        PortfolioService._validate_bulk_request(portfolio_dtos)
        
        # Check for duplicate names within the batch
        PortfolioService._check_duplicate_names(portfolio_dtos)
        
        # Convert DTOs to Portfolio model objects with proper defaults
        portfolios = []
        for dto in portfolio_dtos:
            portfolio = Portfolio(
                name=dto.name,
                dateCreated=dto.dateCreated if dto.dateCreated else datetime.now(UTC),
                version=dto.version if dto.version is not None else 1
            )
            portfolios.append(portfolio)
        
        logger.debug(
            "Converted DTOs to Portfolio objects",
            operation="create_portfolios_bulk",
            portfolio_count=len(portfolios),
            portfolio_names=[p.name for p in portfolios]
        )
        
        # Define the bulk operation - simplified without transactions for now
        async def bulk_create_operation():
            """Execute the bulk creation"""
            logger.debug(
                "Starting bulk portfolio creation",
                operation="bulk_create_operation",
                portfolio_count=len(portfolios)
            )
            
            try:
                # Insert all portfolios sequentially
                created_portfolios = []
                for i, portfolio in enumerate(portfolios):
                    try:
                        logger.debug(
                            "Inserting portfolio",
                            operation="bulk_create_operation",
                            portfolio_index=i,
                            portfolio_name=portfolio.name
                        )
                        
                        await portfolio.insert()
                        created_portfolios.append(portfolio)
                        
                        logger.debug(
                            "Portfolio inserted successfully",
                            operation="bulk_create_operation",
                            portfolio_index=i,
                            portfolio_name=portfolio.name,
                            portfolio_id=str(portfolio.id)
                        )
                    except Exception as e:
                        logger.error(
                            "Failed to insert portfolio",
                            operation="bulk_create_operation",
                            portfolio_index=i,
                            portfolio_name=portfolio.name,
                            error=str(e),
                            error_type=type(e).__name__
                        )
                        # Re-raise to trigger retry logic
                        raise
                
                logger.info(
                    "All portfolios inserted successfully",
                    operation="bulk_create_operation",
                    portfolio_count=len(created_portfolios)
                )
                
                return created_portfolios
                        
            except Exception as e:
                logger.error(
                    "Error in bulk create operation",
                    operation="bulk_create_operation",
                    error=str(e),
                    error_type=type(e).__name__
                )
                raise
        
        # Execute the bulk operation with retry logic
        try:
            result = await PortfolioService._execute_with_retry(
                operation=bulk_create_operation,
                max_retries=3,
                operation_name="bulk_portfolio_creation"
            )
            
            logger.info(
                "Bulk portfolio creation completed successfully",
                operation="create_portfolios_bulk",
                portfolio_count=len(result),
                created_portfolio_ids=[str(p.id) for p in result]
            )
            
            return result
            
        except Exception as e:
            logger.error(
                "Bulk portfolio creation failed after all retries",
                operation="create_portfolios_bulk",
                portfolio_count=len(portfolio_dtos),
                error=str(e),
                error_type=type(e).__name__
            )
            raise
    
    @staticmethod
    def portfolio_to_dto(portfolio: Portfolio) -> PortfolioResponseDTO:
        """Convert Portfolio model to DTO"""
        return PortfolioResponseDTO(
            portfolioId=str(portfolio.id),
            name=portfolio.name,
            dateCreated=portfolio.dateCreated,
            version=portfolio.version
        ) 