from app.models import Portfolio
from app.schemas import PortfolioResponseDTO, PaginationDTO, PortfolioSearchResponseDTO
from app.tracing import trace_database_call
from app.logging_config import get_logger
from bson import ObjectId
from typing import List, Optional, Tuple
import re
import math

logger = get_logger(__name__)


class PortfolioService:
    
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
    def portfolio_to_dto(portfolio: Portfolio) -> PortfolioResponseDTO:
        """Convert Portfolio model to DTO"""
        return PortfolioResponseDTO(
            portfolioId=str(portfolio.id),
            name=portfolio.name,
            dateCreated=portfolio.dateCreated,
            version=portfolio.version
        ) 