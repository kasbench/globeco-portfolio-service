import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.models import Portfolio
from app.config import settings
from motor.motor_asyncio import AsyncIOMotorClient
from beanie import init_beanie
from datetime import datetime, UTC

@pytest.mark.asyncio
async def test_v2_api_basic_functionality(mongodb_container):
    """Test basic v2 API functionality with search and pagination"""
    # Initialize Beanie with the test MongoDB
    client = AsyncIOMotorClient(settings.mongodb_uri)
    await init_beanie(database=client[settings.mongodb_db], document_models=[Portfolio])

    # Clean up any existing portfolios
    await Portfolio.delete_all()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        # Create test portfolios
        portfolios_data = [
            {"name": "TechGrowthPortfolio"},
            {"name": "ConservativeIncomePortfolio"},
            {"name": "FinTechInnovationFund"},
            {"name": "TechDividendPortfolio"},
            {"name": "GlobalEquityFund"}
        ]
        
        created_portfolios = []
        for portfolio_data in portfolios_data:
            resp = await ac.post("/api/v1/portfolios", json=portfolio_data)
            assert resp.status_code == 201
            created_portfolios.append(resp.json())
        
        # Test v2 API - Get all portfolios with pagination
        resp = await ac.get("/api/v2/portfolios")
        assert resp.status_code == 200
        
        data = resp.json()
        assert "portfolios" in data
        assert "pagination" in data
        assert len(data["portfolios"]) == 5
        
        # Check pagination metadata
        pagination = data["pagination"]
        assert pagination["totalElements"] == 5
        assert pagination["totalPages"] == 1
        assert pagination["currentPage"] == 0
        assert pagination["pageSize"] == 50
        assert pagination["hasNext"] is False
        assert pagination["hasPrevious"] is False
        
        # Test exact name search
        resp = await ac.get("/api/v2/portfolios?name=TechGrowthPortfolio")
        assert resp.status_code == 200
        
        data = resp.json()
        assert len(data["portfolios"]) == 1
        assert data["portfolios"][0]["name"] == "TechGrowthPortfolio"
        
        # Test partial name search
        resp = await ac.get("/api/v2/portfolios?name_like=Tech")
        assert resp.status_code == 200
        
        data = resp.json()
        assert len(data["portfolios"]) == 3  # TechGrowthPortfolio, FinTechInnovationFund, TechDividendPortfolio
        
        portfolio_names = [p["name"] for p in data["portfolios"]]
        assert "TechGrowthPortfolio" in portfolio_names
        assert "FinTechInnovationFund" in portfolio_names
        assert "TechDividendPortfolio" in portfolio_names
        
        # Test pagination with limit
        resp = await ac.get("/api/v2/portfolios?limit=2")
        assert resp.status_code == 200
        
        data = resp.json()
        assert len(data["portfolios"]) == 2
        
        pagination = data["pagination"]
        assert pagination["totalElements"] == 5
        assert pagination["totalPages"] == 3  # ceil(5/2)
        assert pagination["currentPage"] == 0
        assert pagination["pageSize"] == 2
        assert pagination["hasNext"] is True
        assert pagination["hasPrevious"] is False
        
        # Test error cases
        # Conflicting search parameters
        resp = await ac.get("/api/v2/portfolios?name=Tech&name_like=Growth")
        assert resp.status_code == 400
        assert "Only one search parameter allowed" in resp.json()["detail"]
        
        # Empty search parameter
        resp = await ac.get("/api/v2/portfolios?name=")
        assert resp.status_code == 400
        assert "Search parameter cannot be empty" in resp.json()["detail"]
        
        # Invalid name format
        resp = await ac.get("/api/v2/portfolios?name=Invalid@Name!")
        assert resp.status_code == 400
        assert "Invalid portfolio name format" in resp.json()["detail"]

@pytest.mark.asyncio
async def test_v1_vs_v2_backward_compatibility(mongodb_container):
    """Test that v1 and v2 APIs are compatible and return consistent data"""
    # Initialize Beanie with the test MongoDB
    client = AsyncIOMotorClient(settings.mongodb_uri)
    await init_beanie(database=client[settings.mongodb_db], document_models=[Portfolio])

    # Clean up any existing portfolios
    await Portfolio.delete_all()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        # Create a test portfolio
        post_data = {"name": "BackwardCompatibilityTest"}
        resp = await ac.post("/api/v1/portfolios", json=post_data)
        assert resp.status_code == 201
        
        # Test v1 API returns array format
        v1_resp = await ac.get("/api/v1/portfolios")
        assert v1_resp.status_code == 200
        v1_data = v1_resp.json()
        assert isinstance(v1_data, list)
        assert len(v1_data) == 1
        
        # Test v2 API returns object with pagination
        v2_resp = await ac.get("/api/v2/portfolios")
        assert v2_resp.status_code == 200
        v2_data = v2_resp.json()
        assert isinstance(v2_data, dict)
        assert "portfolios" in v2_data
        assert "pagination" in v2_data
        assert len(v2_data["portfolios"]) == 1
        
        # Verify data consistency between v1 and v2
        v1_portfolio = v1_data[0]
        v2_portfolio = v2_data["portfolios"][0]
        
        assert v1_portfolio["portfolioId"] == v2_portfolio["portfolioId"]
        assert v1_portfolio["name"] == v2_portfolio["name"]
        assert v1_portfolio["dateCreated"] == v2_portfolio["dateCreated"]
        assert v1_portfolio["version"] == v2_portfolio["version"] 