"""
Fast-path API endpoints with optimized request processing.

This module provides performance-optimized API endpoints that implement:
- Fast-path routing for bulk operations
- Request size validation and early rejection
- Optimized response serialization
- Minimal middleware overhead
"""

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from app.schemas import PortfolioPostDTO, PortfolioResponseDTO
from app.services import StreamlinedPortfolioService
from app.logging_config import get_logger
from app.environment_config import get_config_manager
from typing import List
import time
import json
from datetime import datetime

logger = get_logger(__name__)
router = APIRouter(prefix="/api/fast")


class FastPathProcessor:
    """
    Fast-path request processor with optimized validation and serialization.
    """
    
    # Request size limits for fast rejection
    MAX_BULK_SIZE = 100
    MAX_REQUEST_SIZE_BYTES = 1024 * 1024  # 1MB
    
    @staticmethod
    def validate_request_size_fast(request_data: bytes) -> None:
        """
        Fast request size validation with early rejection.
        
        Args:
            request_data: Raw request data bytes
            
        Raises:
            HTTPException: If request exceeds size limits
        """
        if len(request_data) > FastPathProcessor.MAX_REQUEST_SIZE_BYTES:
            raise HTTPException(
                status_code=413,
                detail=f"Request too large: {len(request_data)} bytes exceeds {FastPathProcessor.MAX_REQUEST_SIZE_BYTES} bytes"
            )
    
    @staticmethod
    def validate_bulk_size_fast(portfolio_count: int) -> None:
        """
        Fast bulk size validation with early rejection.
        
        Args:
            portfolio_count: Number of portfolios in request
            
        Raises:
            HTTPException: If bulk size exceeds limits
        """
        if portfolio_count == 0:
            raise HTTPException(
                status_code=400,
                detail="Request must contain at least 1 portfolio"
            )
        
        if portfolio_count > FastPathProcessor.MAX_BULK_SIZE:
            raise HTTPException(
                status_code=413,
                detail=f"Bulk request too large: {portfolio_count} portfolios exceeds {FastPathProcessor.MAX_BULK_SIZE} limit"
            )
    
    @staticmethod
    def serialize_response_fast(portfolios: List[PortfolioResponseDTO]) -> dict:
        """
        Optimized response serialization with minimal overhead.
        
        Args:
            portfolios: List of portfolio DTOs to serialize
            
        Returns:
            Dictionary ready for JSON serialization
        """
        # Direct dictionary construction for performance
        return {
            "portfolios": [
                {
                    "portfolioId": p.portfolioId,
                    "name": p.name,
                    "dateCreated": p.dateCreated.isoformat() if isinstance(p.dateCreated, datetime) else p.dateCreated,
                    "version": p.version
                }
                for p in portfolios
            ],
            "count": len(portfolios),
            "processingTimeMs": None  # Will be set by endpoint
        }


@router.post("/portfolios/bulk", status_code=201)
async def create_portfolios_bulk_fast(request: Request):
    """
    Fast-path bulk portfolio creation with optimized processing.
    
    Implements:
    - Request size validation and early rejection
    - Fast-path routing for bulk operations
    - Optimized response serialization
    - Minimal logging and tracing overhead
    
    Returns:
        JSON response with created portfolios and performance metrics
    """
    start_time = time.perf_counter()
    
    try:
        # Read raw request data for size validation
        request_data = await request.body()
        
        # Fast request size validation
        FastPathProcessor.validate_request_size_fast(request_data)
        
        # Parse JSON manually for performance
        try:
            request_json = json.loads(request_data)
        except json.JSONDecodeError as e:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid JSON: {str(e)}"
            )
        
        # Validate request structure
        if not isinstance(request_json, list):
            raise HTTPException(
                status_code=400,
                detail="Request must be a list of portfolios"
            )
        
        # Fast bulk size validation
        FastPathProcessor.validate_bulk_size_fast(len(request_json))
        
        # Convert to DTOs with minimal validation
        portfolio_dtos = []
        for i, item in enumerate(request_json):
            try:
                # Basic validation
                if not isinstance(item, dict):
                    raise ValueError(f"Item {i} must be an object")
                
                if "name" not in item or not item["name"]:
                    raise ValueError(f"Item {i} missing required field 'name'")
                
                # Create DTO with defaults
                dto = PortfolioPostDTO(
                    name=item["name"],
                    dateCreated=item.get("dateCreated"),
                    version=item.get("version", 1)
                )
                portfolio_dtos.append(dto)
                
            except Exception as e:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid portfolio at index {i}: {str(e)}"
                )
        
        # Use streamlined service for fast processing
        async with StreamlinedPortfolioService() as service:
            created_portfolios = await service.create_portfolios_bulk_direct(portfolio_dtos)
        
        # Convert to response DTOs
        response_dtos = [
            StreamlinedPortfolioService.portfolio_to_dto(p) 
            for p in created_portfolios
        ]
        
        # Calculate processing time
        end_time = time.perf_counter()
        processing_time_ms = (end_time - start_time) * 1000
        
        # Optimized response serialization
        response_data = FastPathProcessor.serialize_response_fast(response_dtos)
        response_data["processingTimeMs"] = round(processing_time_ms, 2)
        
        # Minimal success logging
        logger.info(
            f"Fast bulk creation completed: count={len(created_portfolios)}, "
            f"time={processing_time_ms:.2f}ms"
        )
        
        return JSONResponse(
            content=response_data,
            status_code=201,
            headers={
                "X-Processing-Time-Ms": str(round(processing_time_ms, 2)),
                "X-Portfolio-Count": str(len(created_portfolios))
            }
        )
        
    except HTTPException:
        # Re-raise HTTP exceptions
        raise
        
    except Exception as e:
        # Calculate error processing time
        end_time = time.perf_counter()
        processing_time_ms = (end_time - start_time) * 1000
        
        logger.error(
            f"Fast bulk creation failed: error={str(e)}, "
            f"time={processing_time_ms:.2f}ms"
        )
        
        raise HTTPException(
            status_code=500,
            detail="Internal server error during fast bulk creation"
        )


@router.get("/portfolios/search", response_model=dict)
async def search_portfolios_fast(
    name: str = None,
    name_like: str = None,
    limit: int = 50,
    offset: int = 0
):
    """
    Fast-path portfolio search with optimized processing.
    
    Implements:
    - Fast-path routing for search operations
    - Optimized database queries
    - Minimal response serialization overhead
    
    Args:
        name: Exact name search (case-insensitive)
        name_like: Partial name search (case-insensitive)
        limit: Maximum results (1-1000)
        offset: Results offset for pagination
        
    Returns:
        JSON response with search results and performance metrics
    """
    start_time = time.perf_counter()
    
    try:
        # Fast parameter validation
        if limit < 1 or limit > 1000:
            raise HTTPException(
                status_code=400,
                detail="Limit must be between 1 and 1000"
            )
        
        if offset < 0:
            raise HTTPException(
                status_code=400,
                detail="Offset must be non-negative"
            )
        
        if name and name_like:
            raise HTTPException(
                status_code=400,
                detail="Only one search parameter allowed: name or name_like"
            )
        
        # Use streamlined service for fast search
        async with StreamlinedPortfolioService() as service:
            portfolios, total_count = await service.search_portfolios_direct(
                name=name,
                name_like=name_like,
                limit=limit,
                offset=offset
            )
        
        # Convert to response DTOs
        response_dtos = [
            StreamlinedPortfolioService.portfolio_to_dto(p) 
            for p in portfolios
        ]
        
        # Calculate pagination
        current_page = offset // limit
        pagination = StreamlinedPortfolioService.create_pagination_dto(
            total_elements=total_count,
            current_page=current_page,
            page_size=limit
        )
        
        # Calculate processing time
        end_time = time.perf_counter()
        processing_time_ms = (end_time - start_time) * 1000
        
        # Optimized response
        response_data = {
            "portfolios": [
                {
                    "portfolioId": p.portfolioId,
                    "name": p.name,
                    "dateCreated": p.dateCreated.isoformat() if isinstance(p.dateCreated, datetime) else p.dateCreated,
                    "version": p.version
                }
                for p in response_dtos
            ],
            "pagination": {
                "totalElements": pagination.totalElements,
                "totalPages": pagination.totalPages,
                "currentPage": pagination.currentPage,
                "pageSize": pagination.pageSize,
                "hasNext": pagination.hasNext,
                "hasPrevious": pagination.hasPrevious
            },
            "processingTimeMs": round(processing_time_ms, 2)
        }
        
        return JSONResponse(
            content=response_data,
            headers={
                "X-Processing-Time-Ms": str(round(processing_time_ms, 2)),
                "X-Total-Count": str(total_count)
            }
        )
        
    except HTTPException:
        raise
        
    except Exception as e:
        end_time = time.perf_counter()
        processing_time_ms = (end_time - start_time) * 1000
        
        logger.error(
            f"Fast search failed: error={str(e)}, "
            f"time={processing_time_ms:.2f}ms"
        )
        
        raise HTTPException(
            status_code=500,
            detail="Internal server error during fast search"
        )


@router.get("/health/fast")
async def health_check_fast():
    """
    Fast health check endpoint with minimal overhead.
    
    Returns:
        Simple health status with response time
    """
    start_time = time.perf_counter()
    
    # Minimal health check
    response_data = {
        "status": "healthy",
        "service": "globeco-portfolio-service-fast",
        "timestamp": datetime.utcnow().isoformat()
    }
    
    end_time = time.perf_counter()
    processing_time_ms = (end_time - start_time) * 1000
    
    return JSONResponse(
        content=response_data,
        headers={
            "X-Processing-Time-Ms": str(round(processing_time_ms, 2))
        }
    )


# Performance monitoring endpoint
@router.get("/performance/stats")
async def get_performance_stats():
    """
    Get performance statistics for fast-path endpoints.
    
    Returns:
        Performance metrics and configuration information
    """
    try:
        config_manager = get_config_manager()
        
        stats = {
            "fastPath": {
                "enabled": True,
                "maxBulkSize": FastPathProcessor.MAX_BULK_SIZE,
                "maxRequestSizeBytes": FastPathProcessor.MAX_REQUEST_SIZE_BYTES
            },
            "environment": {
                "profile": config_manager.current_environment if config_manager else "unknown",
                "databaseTracing": config_manager.get_database_config().enable_tracing if config_manager else False
            },
            "endpoints": {
                "/api/fast/portfolios/bulk": "Fast bulk portfolio creation",
                "/api/fast/portfolios/search": "Fast portfolio search",
                "/api/fast/health/fast": "Fast health check"
            }
        }
        
        return JSONResponse(content=stats)
        
    except Exception as e:
        logger.error(f"Error getting performance stats: {e}")
        return JSONResponse(
            content={"error": "Failed to retrieve performance stats"},
            status_code=500
        )