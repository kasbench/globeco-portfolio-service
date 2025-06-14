import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.models import Portfolio
from app.config import settings
from motor.motor_asyncio import AsyncIOMotorClient
from beanie import init_beanie

@pytest.mark.asyncio
async def test_parameter_validation_comprehensive(mongodb_container):
    """Comprehensive unit tests for parameter validation"""
    # Initialize Beanie with the test MongoDB
    client = AsyncIOMotorClient(settings.mongodb_uri)
    await init_beanie(database=client[settings.mongodb_db], document_models=[Portfolio])
    
    # Clean up any existing portfolios
    await Portfolio.delete_all()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        
        # Test 1: Mutual Exclusivity - Both name and name_like provided
        response = await ac.get("/api/v2/portfolios?name=Test&name_like=Test")
        assert response.status_code == 400
        assert "Only one search parameter allowed: name or name_like" in response.json()["detail"]
        
        # Test 2: Empty name parameter
        response = await ac.get("/api/v2/portfolios?name=")
        assert response.status_code == 400
        assert "Search parameter cannot be empty" in response.json()["detail"]
        
        # Test 3: Empty name_like parameter
        response = await ac.get("/api/v2/portfolios?name_like=")
        assert response.status_code == 400
        assert "Search parameter cannot be empty" in response.json()["detail"]
        
        # Test 4: Whitespace-only name parameter
        response = await ac.get("/api/v2/portfolios?name=%20%20%20")  # URL encoded spaces
        assert response.status_code == 400
        assert "Search parameter cannot be empty" in response.json()["detail"]
        
        # Test 5: Name too long (201 characters)
        long_name = "a" * 201
        response = await ac.get(f"/api/v2/portfolios?name={long_name}")
        assert response.status_code == 400
        assert "Invalid portfolio name format" in response.json()["detail"]
        
        # Test 6: Invalid characters in name - special symbols
        response = await ac.get("/api/v2/portfolios?name=Invalid@Name!")
        assert response.status_code == 400
        assert "Invalid portfolio name format" in response.json()["detail"]
        
        # Test 7: Invalid characters in name - brackets
        response = await ac.get("/api/v2/portfolios?name=Invalid[Name]")
        assert response.status_code == 400
        assert "Invalid portfolio name format" in response.json()["detail"]
        
        # Test 8: Invalid characters in name - parentheses
        response = await ac.get("/api/v2/portfolios?name=Invalid(Name)")
        assert response.status_code == 400
        assert "Invalid portfolio name format" in response.json()["detail"]
        
        # Test 9: Valid characters - alphanumeric, spaces, hyphens, underscores
        response = await ac.get("/api/v2/portfolios?name=Valid-Portfolio_123 Name")
        assert response.status_code == 200  # Should be valid format
        
        # Test 10: Limit validation - zero
        response = await ac.get("/api/v2/portfolios?limit=0")
        assert response.status_code == 422  # FastAPI validation error
        
        # Test 11: Limit validation - negative
        response = await ac.get("/api/v2/portfolios?limit=-1")
        assert response.status_code == 422  # FastAPI validation error
        
        # Test 12: Limit validation - too large (1001)
        response = await ac.get("/api/v2/portfolios?limit=1001")
        assert response.status_code == 422  # FastAPI validation error
        
        # Test 13: Limit validation - valid boundary values
        response = await ac.get("/api/v2/portfolios?limit=1")
        assert response.status_code == 200
        
        response = await ac.get("/api/v2/portfolios?limit=1000")
        assert response.status_code == 200
        
        # Test 14: Offset validation - negative
        response = await ac.get("/api/v2/portfolios?offset=-1")
        assert response.status_code == 422  # FastAPI validation error
        
        # Test 15: Offset validation - valid boundary value
        response = await ac.get("/api/v2/portfolios?offset=0")
        assert response.status_code == 200
        
        # Test 16: Offset validation - large valid value
        response = await ac.get("/api/v2/portfolios?offset=999999")
        assert response.status_code == 200
        
        # Test 17: Non-integer limit
        response = await ac.get("/api/v2/portfolios?limit=abc")
        assert response.status_code == 422  # FastAPI validation error
        
        # Test 18: Non-integer offset
        response = await ac.get("/api/v2/portfolios?offset=xyz")
        assert response.status_code == 422  # FastAPI validation error
        
        # Test 19: Decimal limit
        response = await ac.get("/api/v2/portfolios?limit=10.5")
        assert response.status_code == 422  # FastAPI validation error
        
        # Test 20: Valid combination of all parameters
        response = await ac.get("/api/v2/portfolios?name=ValidName&limit=10&offset=0")
        assert response.status_code == 200

@pytest.mark.asyncio
async def test_name_format_edge_cases(mongodb_container):
    """Test edge cases for name format validation"""
    # Initialize Beanie with the test MongoDB
    client = AsyncIOMotorClient(settings.mongodb_uri)
    await init_beanie(database=client[settings.mongodb_db], document_models=[Portfolio])
    
    # Clean up any existing portfolios
    await Portfolio.delete_all()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        
        # Test 1: Single character name (minimum length)
        response = await ac.get("/api/v2/portfolios?name=A")
        assert response.status_code == 200
        
        # Test 2: Maximum length name (200 characters)
        max_name = "a" * 200
        response = await ac.get(f"/api/v2/portfolios?name={max_name}")
        assert response.status_code == 200
        
        # Test 3: Name with only numbers
        response = await ac.get("/api/v2/portfolios?name=123456")
        assert response.status_code == 200
        
        # Test 4: Name with only hyphens and underscores
        response = await ac.get("/api/v2/portfolios?name=---___")
        assert response.status_code == 200
        
        # Test 5: Name with mixed valid characters
        response = await ac.get("/api/v2/portfolios?name=Portfolio-123_Test Name")
        assert response.status_code == 200
        
        # Test 6: Name with leading/trailing spaces (should be trimmed by validation)
        response = await ac.get("/api/v2/portfolios?name= TestName ")
        assert response.status_code == 200
        
        # Test 7: Unicode characters (should be invalid)
        response = await ac.get("/api/v2/portfolios?name=Portfolio™")
        assert response.status_code == 400
        
        # Test 8: Emoji characters (should be invalid)
        response = await ac.get("/api/v2/portfolios?name=Portfolio😀")
        assert response.status_code == 400

@pytest.mark.asyncio
async def test_pagination_parameter_combinations(mongodb_container):
    """Test various combinations of pagination parameters"""
    # Initialize Beanie with the test MongoDB
    client = AsyncIOMotorClient(settings.mongodb_uri)
    await init_beanie(database=client[settings.mongodb_db], document_models=[Portfolio])
    
    # Clean up any existing portfolios
    await Portfolio.delete_all()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        
        # Create test data
        for i in range(10):
            await ac.post("/api/v1/portfolios", json={"name": f"Portfolio{i}"})
        
        # Test 1: Default pagination (no parameters)
        response = await ac.get("/api/v2/portfolios")
        assert response.status_code == 200
        data = response.json()
        assert data["pagination"]["pageSize"] == 50
        assert data["pagination"]["currentPage"] == 0
        
        # Test 2: Custom limit only
        response = await ac.get("/api/v2/portfolios?limit=5")
        assert response.status_code == 200
        data = response.json()
        assert len(data["portfolios"]) == 5
        assert data["pagination"]["pageSize"] == 5
        assert data["pagination"]["currentPage"] == 0
        
        # Test 3: Custom offset only
        response = await ac.get("/api/v2/portfolios?offset=3")
        assert response.status_code == 200
        data = response.json()
        assert data["pagination"]["currentPage"] == 0  # offset 3 / default limit 50 = 0
        
        # Test 4: Both limit and offset
        response = await ac.get("/api/v2/portfolios?limit=3&offset=6")
        assert response.status_code == 200
        data = response.json()
        assert len(data["portfolios"]) == 3
        assert data["pagination"]["pageSize"] == 3
        assert data["pagination"]["currentPage"] == 2  # offset 6 / limit 3 = 2
        
        # Test 5: Offset larger than total results
        response = await ac.get("/api/v2/portfolios?offset=100")
        assert response.status_code == 200
        data = response.json()
        assert len(data["portfolios"]) == 0
        assert data["pagination"]["totalElements"] == 10 