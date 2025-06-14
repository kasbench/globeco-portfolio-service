from fastapi import APIRouter, HTTPException, status
from app.models import Portfolio
from app.schemas import PortfolioResponseDTO, PortfolioPutDTO, PortfolioPostDTO
from app.services import PortfolioService
from bson import ObjectId
from typing import List
from datetime import datetime, UTC

router = APIRouter(prefix="/api/v1")

@router.get("/portfolios", response_model=List[PortfolioResponseDTO])
async def get_portfolios():
    """Get all portfolios - v1 API (backward compatibility)"""
    portfolios = await PortfolioService.get_all_portfolios()
    return [PortfolioService.portfolio_to_dto(p) for p in portfolios]

@router.get("/portfolio/{portfolioId}", response_model=PortfolioResponseDTO)
async def get_portfolio(portfolioId: str):
    """Get a single portfolio by ID - v1 API"""
    portfolio = await PortfolioService.get_portfolio_by_id(portfolioId)
    if not portfolio:
        raise HTTPException(status_code=404, detail="Portfolio not found")
    return PortfolioService.portfolio_to_dto(portfolio)

@router.post("/portfolios", response_model=PortfolioResponseDTO, status_code=status.HTTP_201_CREATED)
async def create_portfolio(dto: PortfolioPostDTO):
    """Create a new portfolio - v1 API"""
    portfolio = Portfolio(
        name=dto.name,
        dateCreated=dto.dateCreated or datetime.now(UTC),
        version=dto.version or 1
    )
    await PortfolioService.create_portfolio(portfolio)
    return PortfolioService.portfolio_to_dto(portfolio)

@router.put("/portfolio/{portfolioId}", response_model=PortfolioResponseDTO)
async def update_portfolio(portfolioId: str, dto: PortfolioPutDTO):
    """Update an existing portfolio - v1 API"""
    portfolio = await PortfolioService.get_portfolio_by_id(portfolioId)
    if not portfolio:
        raise HTTPException(status_code=404, detail="Portfolio not found")
    if portfolio.version != dto.version:
        raise HTTPException(status_code=409, detail="Version conflict")
    
    portfolio.name = dto.name
    portfolio.dateCreated = dto.dateCreated or portfolio.dateCreated
    portfolio.version += 1
    
    await PortfolioService.update_portfolio(portfolio)
    return PortfolioService.portfolio_to_dto(portfolio)

@router.delete("/portfolio/{portfolioId}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_portfolio(portfolioId: str, version: int):
    """Delete a portfolio - v1 API"""
    portfolio = await PortfolioService.get_portfolio_by_id(portfolioId)
    if not portfolio:
        raise HTTPException(status_code=404, detail="Portfolio not found")
    if portfolio.version != version:
        raise HTTPException(status_code=409, detail="Version conflict")
    
    await PortfolioService.delete_portfolio(portfolio)
    return None 