from app.models import Portfolio
from app.schemas import PortfolioResponseDTO, PaginationDTO, PortfolioSearchResponseDTO
from app.tracing import trace_database_call
from bson import ObjectId
from typing import List, Optional, Tuple
import re
import math
import logging


class PortfolioService:
    
    @staticmethod
    async def get_all_portfolios() -> List[Portfolio]:
        """Get all portfolios for v1 API (backward compatibility)"""
        return await trace_database_call(
            "find_all",
            "portfolio", 
            lambda: Portfolio.find_all().to_list()
        )
    
    @staticmethod
    async def get_portfolio_by_id(portfolio_id: str) -> Optional[Portfolio]:
        """Get a single portfolio by ID"""
        try:
            return await trace_database_call(
                "find_by_id",
                "portfolio",
                lambda: Portfolio.get(ObjectId(portfolio_id))
            )
        except:
            return None
    
    @staticmethod
    async def create_portfolio(portfolio: Portfolio) -> Portfolio:
        """Create a new portfolio"""
        await trace_database_call(
            "insert",
            "portfolio",
            lambda: portfolio.insert()
        )
        return portfolio
    
    @staticmethod
    async def update_portfolio(portfolio: Portfolio) -> Portfolio:
        """Update an existing portfolio"""
        logger = logging.getLogger(__name__)
        logger.info(f"Updating portfolio object: {portfolio}")
        await trace_database_call(
            "update",
            "portfolio",
            lambda: portfolio.save()
        )
        return portfolio
    
    @staticmethod
    async def delete_portfolio(portfolio: Portfolio) -> None:
        """Delete a portfolio"""
        await trace_database_call(
            "delete",
            "portfolio",
            lambda: portfolio.delete()
        )
    
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
        query = {}
        
        if name:
            # Exact match (case-insensitive)
            query["name"] = {"$regex": f"^{re.escape(name)}$", "$options": "i"}
        elif name_like:
            # Partial match (case-insensitive)
            query["name"] = {"$regex": re.escape(name_like), "$options": "i"}
        
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
        
        return portfolios, total_count
    
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
    def portfolio_to_dto(portfolio: Portfolio) -> PortfolioResponseDTO:
        """Convert Portfolio model to DTO"""
        return PortfolioResponseDTO(
            portfolioId=str(portfolio.id),
            name=portfolio.name,
            dateCreated=portfolio.dateCreated,
            version=portfolio.version
        ) 