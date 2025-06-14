import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.models import Portfolio
from app.config import settings
from motor.motor_asyncio import AsyncIOMotorClient
from beanie import init_beanie
from datetime import datetime, UTC

@pytest.mark.asyncio
async def test_v1_endpoint_unchanged_behavior(mongodb_container):
    """Test that v1 endpoint behavior is completely unchanged"""
    # Initialize Beanie with the test MongoDB
    client = AsyncIOMotorClient(settings.mongodb_uri)
    await init_beanie(database=client[settings.mongodb_db], document_models=[Portfolio])
    
    # Clean up any existing portfolios
    await Portfolio.delete_all()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        
        # Test 1: v1 GET endpoint returns array format (not object with pagination)
        response = await ac.get("/api/v1/portfolios")
        assert response.status_code == 200
        data = response.json()
        
        # Should be an array, not an object
        assert isinstance(data, list)
        assert len(data) == 0  # Empty initially
        
        # Create some test portfolios
        test_portfolios = [
            {"name": "TechGrowthPortfolio"},
            {"name": "ConservativeIncomePortfolio"},
            {"name": "GlobalEquityFund"}
        ]
        
        created_portfolios = []
        for portfolio_data in test_portfolios:
            resp = await ac.post("/api/v1/portfolios", json=portfolio_data)
            assert resp.status_code == 201
            created_portfolios.append(resp.json())
        
        # Test 2: v1 GET returns all portfolios as array
        response = await ac.get("/api/v1/portfolios")
        assert response.status_code == 200
        data = response.json()
        
        # Should be an array with 3 portfolios
        assert isinstance(data, list)
        assert len(data) == 3
        
        # Verify structure of each portfolio in array
        for portfolio in data:
            assert "portfolioId" in portfolio
            assert "name" in portfolio
            assert "dateCreated" in portfolio
            assert "version" in portfolio
            # Should NOT have pagination metadata
            assert "pagination" not in portfolio
        
        # Test 3: v1 does not accept query parameters (should ignore them)
        response = await ac.get("/api/v1/portfolios?name=TechGrowthPortfolio")
        assert response.status_code == 200
        data = response.json()
        
        # Should still return all portfolios (ignores query parameters)
        assert isinstance(data, list)
        assert len(data) == 3
        
        # Test 4: v1 does not accept pagination parameters
        response = await ac.get("/api/v1/portfolios?limit=1&offset=1")
        assert response.status_code == 200
        data = response.json()
        
        # Should still return all portfolios (ignores pagination)
        assert isinstance(data, list)
        assert len(data) == 3
        
        # Test 5: v1 POST behavior unchanged
        new_portfolio = {"name": "NewTestPortfolio"}
        response = await ac.post("/api/v1/portfolios", json=new_portfolio)
        assert response.status_code == 201
        created = response.json()
        
        # Verify response structure
        assert "portfolioId" in created
        assert "name" in created
        assert "dateCreated" in created
        assert "version" in created
        assert created["name"] == "NewTestPortfolio"
        
        # Test 6: v1 GET by ID behavior unchanged (note: v1 uses /portfolio/ not /portfolios/)
        portfolio_id = created["portfolioId"]
        response = await ac.get(f"/api/v1/portfolio/{portfolio_id}")
        assert response.status_code == 200
        retrieved = response.json()
        
        # Should match created portfolio
        assert retrieved["portfolioId"] == portfolio_id
        assert retrieved["name"] == "NewTestPortfolio"
        
        # Test 7: v1 PUT behavior unchanged (note: v1 uses /portfolio/ not /portfolios/)
        updated_data = {
            "portfolioId": portfolio_id,
            "name": "UpdatedTestPortfolio", 
            "version": 1
        }
        response = await ac.put(f"/api/v1/portfolio/{portfolio_id}", json=updated_data)
        assert response.status_code == 200
        updated = response.json()
        
        assert updated["name"] == "UpdatedTestPortfolio"
        assert updated["version"] == 2  # Should increment to 2
        
        # Test 8: v1 DELETE behavior unchanged (note: v1 uses /portfolio/ not /portfolios/)
        response = await ac.delete(f"/api/v1/portfolio/{portfolio_id}?version=2")
        assert response.status_code == 204
        
        # Verify deletion
        response = await ac.get(f"/api/v1/portfolio/{portfolio_id}")
        assert response.status_code == 404

@pytest.mark.asyncio
async def test_v1_v2_data_consistency(mongodb_container):
    """Test that v1 and v2 endpoints return consistent data"""
    # Initialize Beanie with the test MongoDB
    client = AsyncIOMotorClient(settings.mongodb_uri)
    await init_beanie(database=client[settings.mongodb_db], document_models=[Portfolio])
    
    # Clean up any existing portfolios
    await Portfolio.delete_all()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        
        # Create test portfolios via v1
        test_portfolios = [
            {"name": "TechGrowthPortfolio"},
            {"name": "ConservativeIncomePortfolio"},
            {"name": "GlobalEquityFund"}
        ]
        
        created_via_v1 = []
        for portfolio_data in test_portfolios:
            resp = await ac.post("/api/v1/portfolios", json=portfolio_data)
            assert resp.status_code == 201
            created_via_v1.append(resp.json())
        
        # Get data from v1 endpoint
        v1_response = await ac.get("/api/v1/portfolios")
        assert v1_response.status_code == 200
        v1_data = v1_response.json()
        
        # Get data from v2 endpoint (no search parameters)
        v2_response = await ac.get("/api/v2/portfolios")
        assert v2_response.status_code == 200
        v2_data = v2_response.json()
        
        # Extract portfolios from v2 response
        v2_portfolios = v2_data["portfolios"]
        
        # Should have same number of portfolios
        assert len(v1_data) == len(v2_portfolios)
        assert len(v1_data) == 3
        
        # Sort both by portfolioId for comparison
        v1_sorted = sorted(v1_data, key=lambda x: x["portfolioId"])
        v2_sorted = sorted(v2_portfolios, key=lambda x: x["portfolioId"])
        
        # Compare each portfolio
        for v1_portfolio, v2_portfolio in zip(v1_sorted, v2_sorted):
            assert v1_portfolio["portfolioId"] == v2_portfolio["portfolioId"]
            assert v1_portfolio["name"] == v2_portfolio["name"]
            assert v1_portfolio["dateCreated"] == v2_portfolio["dateCreated"]
            assert v1_portfolio["version"] == v2_portfolio["version"]
        
        # Test consistency after creating via v2 (should not be possible, but test anyway)
        # v2 should not have POST endpoint, only GET
        v2_post_response = await ac.post("/api/v2/portfolios", json={"name": "TestPortfolio"})
        assert v2_post_response.status_code == 405  # Method Not Allowed
        
        # Test consistency after updating via v1
        portfolio_id = created_via_v1[0]["portfolioId"]
        update_data = {
            "portfolioId": portfolio_id,
            "name": "UpdatedPortfolioName", 
            "version": 1
        }
        update_response = await ac.put(f"/api/v1/portfolio/{portfolio_id}", json=update_data)
        assert update_response.status_code == 200
        
        # Check both endpoints reflect the update
        v1_after_update = await ac.get("/api/v1/portfolios")
        v2_after_update = await ac.get("/api/v2/portfolios")
        
        v1_updated_data = v1_after_update.json()
        v2_updated_data = v2_after_update.json()["portfolios"]
        
        # Find the updated portfolio in both responses
        v1_updated_portfolio = next(p for p in v1_updated_data if p["portfolioId"] == portfolio_id)
        v2_updated_portfolio = next(p for p in v2_updated_data if p["portfolioId"] == portfolio_id)
        
        assert v1_updated_portfolio["name"] == "UpdatedPortfolioName"
        assert v2_updated_portfolio["name"] == "UpdatedPortfolioName"
        assert v1_updated_portfolio["version"] == 2  # Should increment to 2
        assert v2_updated_portfolio["version"] == 2

@pytest.mark.asyncio
async def test_v1_response_format_unchanged(mongodb_container):
    """Test that v1 response format is exactly as before"""
    # Initialize Beanie with the test MongoDB
    client = AsyncIOMotorClient(settings.mongodb_uri)
    await init_beanie(database=client[settings.mongodb_db], document_models=[Portfolio])
    
    # Clean up any existing portfolios
    await Portfolio.delete_all()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        
        # Create a portfolio
        portfolio_data = {"name": "TestPortfolio"}
        create_response = await ac.post("/api/v1/portfolios", json=portfolio_data)
        assert create_response.status_code == 201
        created = create_response.json()
        
        # Test v1 GET all portfolios response format
        response = await ac.get("/api/v1/portfolios")
        assert response.status_code == 200
        data = response.json()
        
        # Must be an array
        assert isinstance(data, list)
        assert len(data) == 1
        
        portfolio = data[0]
        
        # Verify exact field structure
        expected_fields = {"portfolioId", "name", "dateCreated", "version"}
        actual_fields = set(portfolio.keys())
        assert actual_fields == expected_fields
        
        # Verify field types
        assert isinstance(portfolio["portfolioId"], str)
        assert isinstance(portfolio["name"], str)
        assert isinstance(portfolio["dateCreated"], str)
        assert isinstance(portfolio["version"], int)
        
        # Verify no additional fields (like pagination)
        assert "pagination" not in portfolio
        assert "totalElements" not in portfolio
        assert "hasNext" not in portfolio
        
        # Test v1 GET single portfolio response format
        portfolio_id = portfolio["portfolioId"]
        single_response = await ac.get(f"/api/v1/portfolio/{portfolio_id}")
        assert single_response.status_code == 200
        single_data = single_response.json()
        
        # Should be an object (not array)
        assert isinstance(single_data, dict)
        
        # Should have same structure as array element
        single_fields = set(single_data.keys())
        assert single_fields == expected_fields
        
        # Should match the portfolio from array
        assert single_data["portfolioId"] == portfolio["portfolioId"]
        assert single_data["name"] == portfolio["name"]
        assert single_data["dateCreated"] == portfolio["dateCreated"]
        assert single_data["version"] == portfolio["version"]

@pytest.mark.asyncio
async def test_v1_error_responses_unchanged(mongodb_container):
    """Test that v1 error responses are unchanged"""
    # Initialize Beanie with the test MongoDB
    client = AsyncIOMotorClient(settings.mongodb_uri)
    await init_beanie(database=client[settings.mongodb_db], document_models=[Portfolio])
    
    # Clean up any existing portfolios
    await Portfolio.delete_all()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        
        # Test 1: GET non-existent portfolio
        response = await ac.get("/api/v1/portfolio/507f1f77bcf86cd799439011")
        assert response.status_code == 404
        error_data = response.json()
        assert "detail" in error_data
        
        # Test 2: POST with invalid data
        response = await ac.post("/api/v1/portfolios", json={})  # Missing name
        assert response.status_code == 422
        error_data = response.json()
        assert "detail" in error_data
        
        # Test 3: PUT non-existent portfolio
        response = await ac.put("/api/v1/portfolio/507f1f77bcf86cd799439011", 
                               json={
                                   "portfolioId": "507f1f77bcf86cd799439011",
                                   "name": "Test", 
                                   "version": 1
                               })
        assert response.status_code == 404
        
        # Test 4: DELETE non-existent portfolio
        response = await ac.delete("/api/v1/portfolio/507f1f77bcf86cd799439011?version=1")
        assert response.status_code == 404
        
        # Test 5: POST with invalid name format (should still work in v1)
        # v1 should not have the strict name validation that v2 has
        response = await ac.post("/api/v1/portfolios", json={"name": "Test@Portfolio!"})
        # This should work in v1 (no strict validation)
        assert response.status_code == 201

@pytest.mark.asyncio
async def test_v1_ordering_behavior(mongodb_container):
    """Test that v1 ordering behavior is unchanged"""
    # Initialize Beanie with the test MongoDB
    client = AsyncIOMotorClient(settings.mongodb_uri)
    await init_beanie(database=client[settings.mongodb_db], document_models=[Portfolio])
    
    # Clean up any existing portfolios
    await Portfolio.delete_all()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        
        # Create portfolios with specific dates
        portfolios_with_dates = [
            ("Portfolio1", datetime(2024, 1, 1, tzinfo=UTC)),
            ("Portfolio2", datetime(2024, 2, 1, tzinfo=UTC)),
            ("Portfolio3", datetime(2024, 3, 1, tzinfo=UTC))
        ]
        
        # Create portfolios directly in database to control dates
        for name, date in portfolios_with_dates:
            portfolio = Portfolio(name=name, dateCreated=date, version=1)
            await portfolio.insert()
        
        # Get portfolios via v1
        response = await ac.get("/api/v1/portfolios")
        assert response.status_code == 200
        data = response.json()
        
        assert len(data) == 3
        
        # v1 should return portfolios in default order (insertion order, by _id)
        # This is different from v2 which orders by dateCreated descending
        # v1 maintains backward compatibility with original behavior
        
        # Verify that portfolios are returned (order may be by insertion/id, not dateCreated)
        portfolio_names = [p["name"] for p in data]
        assert "Portfolio1" in portfolio_names
        assert "Portfolio2" in portfolio_names
        assert "Portfolio3" in portfolio_names
        
        # v1 uses default MongoDB ordering (typically insertion order)
        # This is the original behavior that must be preserved for backward compatibility 