from fastapi import APIRouter, HTTPException, status
from app.models import Portfolio
from app.schemas import PortfolioResponseDTO, PortfolioPutDTO, PortfolioPostDTO
from app.services import PortfolioService
from app.logging_config import get_logger
from bson import ObjectId
from typing import List
from datetime import datetime, UTC

logger = get_logger(__name__)

router = APIRouter(prefix="/api/v1")

@router.get("/portfolios", response_model=List[PortfolioResponseDTO])
async def get_portfolios():
    """Get all portfolios - v1 API (backward compatibility)"""
    logger.info("API v1: Get all portfolios requested", endpoint="/api/v1/portfolios")
    try:
        portfolios = await PortfolioService.get_all_portfolios()
        result = [PortfolioService.portfolio_to_dto(p) for p in portfolios]
        logger.info("API v1: Successfully returned all portfolios", 
                   endpoint="/api/v1/portfolios", 
                   count=len(result))
        return result
    except Exception as e:
        logger.error("API v1: Error getting all portfolios", 
                    endpoint="/api/v1/portfolios", 
                    error=str(e))
        raise HTTPException(status_code=500, detail="Internal server error")

@router.get("/portfolio/{portfolioId}", response_model=PortfolioResponseDTO)
async def get_portfolio(portfolioId: str):
    """Get a single portfolio by ID - v1 API"""
    logger.info("API v1: Get portfolio by ID requested", 
               endpoint=f"/api/v1/portfolio/{portfolioId}", 
               portfolio_id=portfolioId)
    try:
        portfolio = await PortfolioService.get_portfolio_by_id(portfolioId)
        if not portfolio:
            logger.warning("API v1: Portfolio not found", 
                          endpoint=f"/api/v1/portfolio/{portfolioId}", 
                          portfolio_id=portfolioId)
            raise HTTPException(status_code=404, detail="Portfolio not found")
        
        result = PortfolioService.portfolio_to_dto(portfolio)
        logger.info("API v1: Successfully returned portfolio", 
                   endpoint=f"/api/v1/portfolio/{portfolioId}", 
                   portfolio_id=portfolioId,
                   portfolio_name=portfolio.name)
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error("API v1: Error getting portfolio by ID", 
                    endpoint=f"/api/v1/portfolio/{portfolioId}", 
                    portfolio_id=portfolioId,
                    error=str(e))
        raise HTTPException(status_code=500, detail="Internal server error")

@router.post("/portfolios", response_model=PortfolioResponseDTO, status_code=status.HTTP_201_CREATED)
async def create_portfolio(dto: PortfolioPostDTO):
    """Create a new portfolio - v1 API"""
    logger.info("API v1: Create portfolio requested", 
               endpoint="/api/v1/portfolios", 
               portfolio_name=dto.name)
    try:
        portfolio = Portfolio(
            name=dto.name,
            dateCreated=dto.dateCreated or datetime.now(UTC),
            version=dto.version or 1
        )
        await PortfolioService.create_portfolio(portfolio)
        result = PortfolioService.portfolio_to_dto(portfolio)
        logger.info("API v1: Successfully created portfolio", 
                   endpoint="/api/v1/portfolios", 
                   portfolio_id=str(portfolio.id),
                   portfolio_name=portfolio.name)
        return result
    except Exception as e:
        logger.error("API v1: Error creating portfolio", 
                    endpoint="/api/v1/portfolios", 
                    portfolio_name=dto.name,
                    error=str(e))
        raise HTTPException(status_code=500, detail="Internal server error")

@router.put("/portfolio/{portfolioId}", response_model=PortfolioResponseDTO)
async def update_portfolio(portfolioId: str, dto: PortfolioPutDTO):
    """Update an existing portfolio - v1 API"""
    logger.info("API v1: Update portfolio requested", 
               endpoint=f"/api/v1/portfolio/{portfolioId}", 
               portfolio_id=portfolioId,
               new_name=dto.name,
               version=dto.version)
    try:
        portfolio = await PortfolioService.get_portfolio_by_id(portfolioId)
        if not portfolio:
            logger.warning("API v1: Portfolio not found for update", 
                          endpoint=f"/api/v1/portfolio/{portfolioId}", 
                          portfolio_id=portfolioId)
            raise HTTPException(status_code=404, detail="Portfolio not found")
        
        if portfolio.version != dto.version:
            logger.warning("API v1: Version conflict during update", 
                          endpoint=f"/api/v1/portfolio/{portfolioId}", 
                          portfolio_id=portfolioId,
                          current_version=portfolio.version,
                          requested_version=dto.version)
            raise HTTPException(status_code=409, detail="Version conflict")
        
        old_name = portfolio.name
        portfolio.name = dto.name
        portfolio.dateCreated = dto.dateCreated or portfolio.dateCreated
        portfolio.version += 1
        
        await PortfolioService.update_portfolio(portfolio)
        result = PortfolioService.portfolio_to_dto(portfolio)
        logger.info("API v1: Successfully updated portfolio", 
                   endpoint=f"/api/v1/portfolio/{portfolioId}", 
                   portfolio_id=portfolioId,
                   old_name=old_name,
                   new_name=portfolio.name,
                   new_version=portfolio.version)
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error("API v1: Error updating portfolio", 
                    endpoint=f"/api/v1/portfolio/{portfolioId}", 
                    portfolio_id=portfolioId,
                    error=str(e))
        raise HTTPException(status_code=500, detail="Internal server error")

@router.delete("/portfolio/{portfolioId}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_portfolio(portfolioId: str, version: int):
    """Delete a portfolio - v1 API"""
    logger.info("API v1: Delete portfolio requested", 
               endpoint=f"/api/v1/portfolio/{portfolioId}", 
               portfolio_id=portfolioId,
               version=version)
    try:
        portfolio = await PortfolioService.get_portfolio_by_id(portfolioId)
        if not portfolio:
            logger.warning("API v1: Portfolio not found for deletion", 
                          endpoint=f"/api/v1/portfolio/{portfolioId}", 
                          portfolio_id=portfolioId)
            raise HTTPException(status_code=404, detail="Portfolio not found")
        
        if portfolio.version != version:
            logger.warning("API v1: Version conflict during deletion", 
                          endpoint=f"/api/v1/portfolio/{portfolioId}", 
                          portfolio_id=portfolioId,
                          current_version=portfolio.version,
                          requested_version=version)
            raise HTTPException(status_code=409, detail="Version conflict")
        
        await PortfolioService.delete_portfolio(portfolio)
        logger.info("API v1: Successfully deleted portfolio", 
                   endpoint=f"/api/v1/portfolio/{portfolioId}", 
                   portfolio_id=portfolioId,
                   portfolio_name=portfolio.name)
        return None
    except HTTPException:
        raise
    except Exception as e:
        logger.error("API v1: Error deleting portfolio", 
                    endpoint=f"/api/v1/portfolio/{portfolioId}", 
                    portfolio_id=portfolioId,
                    error=str(e))
        raise HTTPException(status_code=500, detail="Internal server error") 