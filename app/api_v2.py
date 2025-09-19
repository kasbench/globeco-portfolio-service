from fastapi import APIRouter, HTTPException, Query
from app.schemas import PortfolioSearchResponseDTO, PortfolioPostDTO, PortfolioResponseDTO, BulkValidationError
from app.services import PortfolioService
from app.logging_config import get_logger
from typing import Optional, List
import re

logger = get_logger(__name__)
router = APIRouter(prefix="/api/v2")

@router.get("/portfolios", response_model=PortfolioSearchResponseDTO)
async def search_portfolios(
    name: Optional[str] = Query(None, description="Search by exact portfolio name (case-insensitive)"),
    name_like: Optional[str] = Query(None, description="Search by partial name match (case-insensitive)"),
    limit: int = Query(50, ge=1, le=1000, description="Maximum number of results (default: 50, max: 1000)"),
    offset: int = Query(0, ge=0, description="Number of results to skip for pagination (default: 0)")
):
    """
    Search portfolios with pagination - v2 API
    
    Query Parameters:
    - name: Search by exact portfolio name (case-insensitive)
    - name_like: Search by partial name match (case-insensitive)
    - limit: Maximum number of results (default: 50, max: 1000)
    - offset: Number of results to skip for pagination (default: 0)
    
    Note: Only one of 'name' or 'name_like' can be provided.
    """
    logger.debug("API v2: Search portfolios requested", 
               endpoint="/api/v2/portfolios",
               name=name,
               name_like=name_like,
               limit=limit,
               offset=offset)
    
    # Validate mutual exclusivity of search parameters
    if name and name_like:
        logger.warning("API v2: Both name and name_like provided", 
                      endpoint="/api/v2/portfolios",
                      name=name,
                      name_like=name_like)
        raise HTTPException(
            status_code=400,
            detail="Only one search parameter allowed: name or name_like"
        )
    
    # Validate name format if provided
    if name is not None:
        if not name.strip():
            logger.warning("API v2: Empty name parameter provided", 
                          endpoint="/api/v2/portfolios")
            raise HTTPException(
                status_code=400,
                detail="Search parameter cannot be empty"
            )
        if not _is_valid_name_format(name):
            logger.warning("API v2: Invalid name format", 
                          endpoint="/api/v2/portfolios",
                          name=name)
            raise HTTPException(
                status_code=400,
                detail="Invalid portfolio name format. Name must be 1-200 characters, alphanumeric, spaces, hyphens, and underscores only"
            )
    
    # Validate name_like format if provided
    if name_like is not None:
        if not name_like.strip():
            logger.warning("API v2: Empty name_like parameter provided", 
                          endpoint="/api/v2/portfolios")
            raise HTTPException(
                status_code=400,
                detail="Search parameter cannot be empty"
            )
        if not _is_valid_name_format(name_like):
            logger.warning("API v2: Invalid name_like format", 
                          endpoint="/api/v2/portfolios",
                          name_like=name_like)
            raise HTTPException(
                status_code=400,
                detail="Invalid portfolio name format. Name must be 1-200 characters, alphanumeric, spaces, hyphens, and underscores only"
            )
    
    try:
        # Search portfolios
        portfolios, total_count = await PortfolioService.search_portfolios(
            name=name,
            name_like=name_like,
            limit=limit,
            offset=offset
        )
        
        # Convert to DTOs
        portfolio_dtos = [PortfolioService.portfolio_to_dto(p) for p in portfolios]
        
        # Calculate current page
        current_page = offset // limit
        
        # Create pagination metadata
        pagination = PortfolioService.create_pagination_dto(
            total_elements=total_count,
            current_page=current_page,
            page_size=limit
        )
        
        result = PortfolioSearchResponseDTO(
            portfolios=portfolio_dtos,
            pagination=pagination
        )
        
        logger.debug("API v2: Successfully searched portfolios", 
                   endpoint="/api/v2/portfolios",
                   total_count=total_count,
                   returned_count=len(portfolio_dtos),
                   current_page=current_page,
                   limit=limit,
                   offset=offset)
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("API v2: Error searching portfolios", 
                    endpoint="/api/v2/portfolios",
                    name=name,
                    name_like=name_like,
                    error=str(e))
        raise HTTPException(
            status_code=500,
            detail="An unexpected error occurred while searching portfolios"
        )

def _is_valid_name_format(name: str) -> bool:
    """
    Validate portfolio name format using cached validation:
    - 1-200 characters
    - Alphanumeric, spaces, hyphens, and underscores only
    """
    from app.validation_cache import is_valid_name_format
    return is_valid_name_format(name)

@router.post("/portfolios", response_model=List[PortfolioResponseDTO], status_code=201)
async def create_portfolios_bulk(portfolios: List[PortfolioPostDTO]):
    """
    Create multiple portfolios in a single batch operation - v2 API
    
    Request Body:
    - List of PortfolioPostDTO objects (1-100 portfolios)
    - All portfolios are processed as a single transaction (all succeed or all fail)
    
    Returns:
    - List of PortfolioResponseDTO objects on success (HTTP 201)
    - Validation errors on invalid input (HTTP 400)
    - Server errors on database failures (HTTP 500)
    """
    logger.info(
        "API v2: Bulk portfolio creation requested",
        endpoint="/api/v2/portfolios",
        method="POST",
        portfolio_count=len(portfolios) if portfolios else 0
    )
    
    # Log the full request details for debugging
    if portfolios:
        request_details = []
        for i, portfolio in enumerate(portfolios):
            request_details.append({
                "index": i,
                "name": portfolio.name,
                "dateCreated": portfolio.dateCreated.isoformat() if portfolio.dateCreated else None,
                "version": portfolio.version
            })
        
        logger.info(
            "API v2: Request details for bulk portfolio creation",
            endpoint="/api/v2/portfolios",
            method="POST",
            request_details=request_details
        )
    
    try:
        # Validate request payload
        if not portfolios:
            logger.warning(
                "API v2: Empty portfolio list provided",
                endpoint="/api/v2/portfolios",
                method="POST"
            )
            raise HTTPException(
                status_code=400,
                detail="Request must contain at least 1 portfolio"
            )
        
        # Log portfolio names for debugging (truncated for large batches)
        portfolio_names = [p.name for p in portfolios[:10]]  # First 10 names
        if len(portfolios) > 10:
            portfolio_names.append(f"... and {len(portfolios) - 10} more")
        
        logger.debug(
            "API v2: Processing bulk portfolio creation",
            endpoint="/api/v2/portfolios",
            method="POST",
            portfolio_count=len(portfolios),
            portfolio_names=portfolio_names
        )
        
        # Create portfolios using service layer (includes validation and retry logic)
        created_portfolios = await PortfolioService.create_portfolios_bulk(portfolios)
        
        # Convert to response DTOs
        response_dtos = [PortfolioService.portfolio_to_dto(p) for p in created_portfolios]
        
        logger.info(
            "API v2: Bulk portfolio creation completed successfully",
            endpoint="/api/v2/portfolios",
            method="POST",
            portfolio_count=len(response_dtos),
            created_portfolio_ids=[dto.portfolioId for dto in response_dtos]
        )
        
        return response_dtos
        
    except ValueError as e:
        # Validation errors (empty request, oversized request, duplicates)
        logger.warning(
            "API v2: Bulk portfolio creation validation failed",
            endpoint="/api/v2/portfolios",
            method="POST",
            portfolio_count=len(portfolios) if portfolios else 0,
            validation_error=str(e)
        )
        raise HTTPException(
            status_code=400,
            detail=str(e)
        )
        
    except HTTPException:
        # Re-raise HTTP exceptions (already have proper status codes)
        raise
        
    except Exception as e:
        # Database errors and other unexpected errors
        logger.error(
            "API v2: Bulk portfolio creation failed with unexpected error",
            endpoint="/api/v2/portfolios",
            method="POST",
            portfolio_count=len(portfolios) if portfolios else 0,
            error=str(e),
            error_type=type(e).__name__
        )
        raise HTTPException(
            status_code=500,
            detail="An unexpected error occurred while creating portfolios"
        )