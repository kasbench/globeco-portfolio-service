from fastapi import APIRouter, HTTPException, Query
from app.schemas import PortfolioSearchResponseDTO
from app.services import PortfolioService
from typing import Optional
import re

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
    
    # Validate mutual exclusivity of search parameters
    if name and name_like:
        raise HTTPException(
            status_code=400,
            detail="Only one search parameter allowed: name or name_like"
        )
    
    # Validate name format if provided
    if name is not None:
        if not name.strip():
            raise HTTPException(
                status_code=400,
                detail="Search parameter cannot be empty"
            )
        if not _is_valid_name_format(name):
            raise HTTPException(
                status_code=400,
                detail="Invalid portfolio name format. Name must be 1-200 characters, alphanumeric, spaces, hyphens, and underscores only"
            )
    
    # Validate name_like format if provided
    if name_like is not None:
        if not name_like.strip():
            raise HTTPException(
                status_code=400,
                detail="Search parameter cannot be empty"
            )
        if not _is_valid_name_format(name_like):
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
        
        return PortfolioSearchResponseDTO(
            portfolios=portfolio_dtos,
            pagination=pagination
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail="An unexpected error occurred while searching portfolios"
        )

def _is_valid_name_format(name: str) -> bool:
    """
    Validate portfolio name format:
    - 1-200 characters
    - Alphanumeric, spaces, hyphens, and underscores only
    """
    if not name or len(name) > 200:
        return False
    
    # Allow alphanumeric characters, spaces, hyphens, and underscores
    pattern = r'^[a-zA-Z0-9\s\-_]+$'
    return bool(re.match(pattern, name)) 