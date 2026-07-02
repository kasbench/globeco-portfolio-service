from fastapi import APIRouter, HTTPException, status
from app.models import Portfolio
from app.schemas import PortfolioResponseDTO, PortfolioPutDTO, PortfolioPostDTO
from bson import ObjectId
from bson.errors import InvalidId
from typing import List
from datetime import datetime, UTC

router = APIRouter(prefix="/api/v1")


def parse_portfolio_object_id(portfolioId: str):
    try:
        return ObjectId(portfolioId)
    except InvalidId:
        return None

@router.get("/portfolios", response_model=List[PortfolioResponseDTO])
async def get_portfolios():
    portfolios = await Portfolio.find_all().to_list()
    return [PortfolioResponseDTO(
        portfolioId=str(p.id),
        name=p.name,
        dateCreated=p.dateCreated,
        version=p.version
    ) for p in portfolios]

@router.get("/portfolio/{portfolioId}", response_model=PortfolioResponseDTO)
async def get_portfolio(portfolioId: str):
    object_id = parse_portfolio_object_id(portfolioId)
    if object_id is None:
        raise HTTPException(status_code=404, detail="Portfolio not found")
    portfolio = await Portfolio.get(object_id)
    if not portfolio:
        raise HTTPException(status_code=404, detail="Portfolio not found")
    return PortfolioResponseDTO(
        portfolioId=str(portfolio.id),
        name=portfolio.name,
        dateCreated=portfolio.dateCreated,
        version=portfolio.version
    )

@router.post("/portfolios", response_model=PortfolioResponseDTO, status_code=status.HTTP_201_CREATED)
async def create_portfolio(dto: PortfolioPostDTO):
    portfolio = Portfolio(
        name=dto.name,
        dateCreated=dto.dateCreated or datetime.now(UTC),
        version=dto.version or 1
    )
    await portfolio.insert()
    return PortfolioResponseDTO(
        portfolioId=str(portfolio.id),
        name=portfolio.name,
        dateCreated=portfolio.dateCreated,
        version=portfolio.version
    )

@router.put("/portfolio/{portfolioId}", response_model=PortfolioResponseDTO)
async def update_portfolio(portfolioId: str, dto: PortfolioPutDTO):
    object_id = parse_portfolio_object_id(portfolioId)
    if object_id is None:
        raise HTTPException(status_code=404, detail="Portfolio not found")
    portfolio = await Portfolio.get(object_id)
    if not portfolio:
        raise HTTPException(status_code=404, detail="Portfolio not found")
    if portfolio.version != dto.version:
        raise HTTPException(status_code=409, detail="Version conflict")
    portfolio.name = dto.name
    portfolio.dateCreated = dto.dateCreated or portfolio.dateCreated
    portfolio.version += 1
    await portfolio.save()
    return PortfolioResponseDTO(
        portfolioId=str(portfolio.id),
        name=portfolio.name,
        dateCreated=portfolio.dateCreated,
        version=portfolio.version
    )

@router.delete("/portfolio/{portfolioId}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_portfolio(portfolioId: str, version: int):
    object_id = parse_portfolio_object_id(portfolioId)
    if object_id is None:
        raise HTTPException(status_code=404, detail="Portfolio not found")
    portfolio = await Portfolio.get(object_id)
    if not portfolio:
        raise HTTPException(status_code=404, detail="Portfolio not found")
    if portfolio.version != version:
        raise HTTPException(status_code=409, detail="Version conflict")
    await portfolio.delete()
    return None
