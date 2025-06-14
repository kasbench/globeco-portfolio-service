import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.models import Portfolio
from app.config import settings
from motor.motor_asyncio import AsyncIOMotorClient
from beanie import init_beanie
from datetime import datetime, UTC

@pytest.mark.asyncio
async def test_exact_name_search_comprehensive(mongodb_container):
    """Comprehensive integration tests for exact name search"""
    # Initialize Beanie with the test MongoDB
    client = AsyncIOMotorClient(settings.mongodb_uri)
    await init_beanie(database=client[settings.mongodb_db], document_models=[Portfolio])
    
    # Clean up any existing portfolios
    await Portfolio.delete_all()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        
        # Create test portfolios with various names
        test_portfolios = [
            "TechGrowthPortfolio",
            "techgrowthportfolio",  # Different case
            "TECHGROWTHPORTFOLIO",  # All caps
            "Tech Growth Portfolio",  # With spaces
            "Tech-Growth-Portfolio",  # With hyphens
            "Tech_Growth_Portfolio",  # With underscores
            "TechGrowthPortfolio123",  # With numbers
            "FinTechInnovationFund",  # Similar but different
            "ConservativeIncomePortfolio"
        ]
        
        created_portfolios = []
        for name in test_portfolios:
            resp = await ac.post("/api/v1/portfolios", json={"name": name})
            assert resp.status_code == 201
            created_portfolios.append(resp.json())
        
        # Test 1: Exact match - case insensitive (finds all case variations)
        response = await ac.get("/api/v2/portfolios?name=TechGrowthPortfolio")
        assert response.status_code == 200
        data = response.json()
        # Should find all case-insensitive matches
        assert len(data["portfolios"]) == 3  # TechGrowthPortfolio, techgrowthportfolio, TECHGROWTHPORTFOLIO
        found_names = [p["name"] for p in data["portfolios"]]
        assert "TechGrowthPortfolio" in found_names
        assert "techgrowthportfolio" in found_names
        assert "TECHGROWTHPORTFOLIO" in found_names
        
        # Test 2: Exact match - lowercase input finds all case variations
        response = await ac.get("/api/v2/portfolios?name=techgrowthportfolio")
        assert response.status_code == 200
        data = response.json()
        # Should find all case-insensitive matches
        assert len(data["portfolios"]) == 3
        found_names = [p["name"] for p in data["portfolios"]]
        assert "TechGrowthPortfolio" in found_names
        assert "techgrowthportfolio" in found_names
        assert "TECHGROWTHPORTFOLIO" in found_names
        
        # Test 3: Exact match - uppercase input finds all case variations
        response = await ac.get("/api/v2/portfolios?name=TECHGROWTHPORTFOLIO")
        assert response.status_code == 200
        data = response.json()
        # Should find all case-insensitive matches
        assert len(data["portfolios"]) == 3
        found_names = [p["name"] for p in data["portfolios"]]
        assert "TechGrowthPortfolio" in found_names
        assert "techgrowthportfolio" in found_names
        assert "TECHGROWTHPORTFOLIO" in found_names
        
        # Test 4: Exact match with spaces
        response = await ac.get("/api/v2/portfolios?name=Tech Growth Portfolio")
        assert response.status_code == 200
        data = response.json()
        assert len(data["portfolios"]) == 1
        assert data["portfolios"][0]["name"] == "Tech Growth Portfolio"
        
        # Test 5: Exact match with hyphens
        response = await ac.get("/api/v2/portfolios?name=Tech-Growth-Portfolio")
        assert response.status_code == 200
        data = response.json()
        assert len(data["portfolios"]) == 1
        assert data["portfolios"][0]["name"] == "Tech-Growth-Portfolio"
        
        # Test 6: Exact match with underscores
        response = await ac.get("/api/v2/portfolios?name=Tech_Growth_Portfolio")
        assert response.status_code == 200
        data = response.json()
        assert len(data["portfolios"]) == 1
        assert data["portfolios"][0]["name"] == "Tech_Growth_Portfolio"
        
        # Test 7: Exact match with numbers
        response = await ac.get("/api/v2/portfolios?name=TechGrowthPortfolio123")
        assert response.status_code == 200
        data = response.json()
        assert len(data["portfolios"]) == 1
        assert data["portfolios"][0]["name"] == "TechGrowthPortfolio123"
        
        # Test 8: No match found
        response = await ac.get("/api/v2/portfolios?name=NonExistentPortfolio")
        assert response.status_code == 200
        data = response.json()
        assert len(data["portfolios"]) == 0
        assert data["pagination"]["totalElements"] == 0

@pytest.mark.asyncio
async def test_partial_name_search_comprehensive(mongodb_container):
    """Comprehensive integration tests for partial name search"""
    # Initialize Beanie with the test MongoDB
    client = AsyncIOMotorClient(settings.mongodb_uri)
    await init_beanie(database=client[settings.mongodb_db], document_models=[Portfolio])
    
    # Clean up any existing portfolios
    await Portfolio.delete_all()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        
        # Create test portfolios for partial search testing
        test_portfolios = [
            "TechGrowthPortfolio",
            "FinTechInnovationFund",
            "TechDividendPortfolio",
            "HealthcareTechFund",
            "ConservativeIncomePortfolio",
            "GlobalEquityFund",
            "TechStartupVenture",
            "BiotechResearchFund",
            "CleanTechEnergyPortfolio"
        ]
        
        for name in test_portfolios:
            resp = await ac.post("/api/v1/portfolios", json={"name": name})
            assert resp.status_code == 201
        
        # Test 1: Prefix search - "Tech"
        response = await ac.get("/api/v2/portfolios?name_like=Tech")
        assert response.status_code == 200
        data = response.json()
        found_names = [p["name"] for p in data["portfolios"]]
        expected_tech = ["TechGrowthPortfolio", "TechDividendPortfolio", "TechStartupVenture"]
        for expected in expected_tech:
            assert expected in found_names
        assert len(data["portfolios"]) >= 3
        
        # Test 2: Suffix search - "Fund"
        response = await ac.get("/api/v2/portfolios?name_like=Fund")
        assert response.status_code == 200
        data = response.json()
        found_names = [p["name"] for p in data["portfolios"]]
        expected_fund = ["FinTechInnovationFund", "HealthcareTechFund", "GlobalEquityFund", "BiotechResearchFund"]
        for expected in expected_fund:
            assert expected in found_names
        
        # Test 3: Infix search - "Tech" (should find all with Tech anywhere)
        response = await ac.get("/api/v2/portfolios?name_like=Tech")
        assert response.status_code == 200
        data = response.json()
        found_names = [p["name"] for p in data["portfolios"]]
        # Should find: TechGrowthPortfolio, FinTechInnovationFund, TechDividendPortfolio, 
        # HealthcareTechFund, TechStartupVenture, BiotechResearchFund, CleanTechEnergyPortfolio
        assert len(data["portfolios"]) >= 7
        
        # Test 4: Case insensitive partial search
        response = await ac.get("/api/v2/portfolios?name_like=tech")
        assert response.status_code == 200
        data = response.json()
        # Should find same results as uppercase "Tech"
        assert len(data["portfolios"]) >= 7
        
        # Test 5: Case insensitive partial search - mixed case
        response = await ac.get("/api/v2/portfolios?name_like=TeChFuNd")
        assert response.status_code == 200
        data = response.json()
        found_names = [p["name"] for p in data["portfolios"]]
        # Should find portfolios containing "techfund" case-insensitively
        assert any("TechFund" in name or "techfund" in name.lower() for name in found_names)
        
        # Test 6: Single character search
        response = await ac.get("/api/v2/portfolios?name_like=T")
        assert response.status_code == 200
        data = response.json()
        # Should find all portfolios with 'T' or 't'
        assert len(data["portfolios"]) >= 6
        
        # Test 7: No matches
        response = await ac.get("/api/v2/portfolios?name_like=XYZ")
        assert response.status_code == 200
        data = response.json()
        assert len(data["portfolios"]) == 0
        
        # Test 8: Empty result with valid search term
        response = await ac.get("/api/v2/portfolios?name_like=NonExistent")
        assert response.status_code == 200
        data = response.json()
        assert len(data["portfolios"]) == 0
        assert data["pagination"]["totalElements"] == 0

@pytest.mark.asyncio
async def test_case_sensitivity_behavior(mongodb_container):
    """Test case-insensitive search behavior comprehensively"""
    # Initialize Beanie with the test MongoDB
    client = AsyncIOMotorClient(settings.mongodb_uri)
    await init_beanie(database=client[settings.mongodb_db], document_models=[Portfolio])
    
    # Clean up any existing portfolios
    await Portfolio.delete_all()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        
        # Create portfolios with various case combinations
        test_cases = [
            "TechPortfolio",
            "techportfolio", 
            "TECHPORTFOLIO",
            "TeCHPoRtFoLiO",
            "Tech Portfolio",
            "TECH PORTFOLIO",
            "tech portfolio"
        ]
        
        for name in test_cases:
            resp = await ac.post("/api/v1/portfolios", json={"name": name})
            assert resp.status_code == 201
        
        # Test exact search case insensitivity
        search_terms = ["techportfolio", "TECHPORTFOLIO", "TechPortfolio", "tEcHpOrTfOlIo"]
        
        for search_term in search_terms:
            response = await ac.get(f"/api/v2/portfolios?name={search_term}")
            assert response.status_code == 200
            data = response.json()
            # Should find the exact case-insensitive match
            found = False
            for portfolio in data["portfolios"]:
                if portfolio["name"].lower() == search_term.lower():
                    found = True
                    break
            assert found, f"Should find case-insensitive match for {search_term}"
        
        # Test partial search case insensitivity
        partial_terms = ["tech", "TECH", "Tech", "tEcH", "portfolio", "PORTFOLIO"]
        
        for term in partial_terms:
            response = await ac.get(f"/api/v2/portfolios?name_like={term}")
            assert response.status_code == 200
            data = response.json()
            # Should find multiple matches regardless of case
            assert len(data["portfolios"]) >= 3
            
            # Verify all results contain the search term (case-insensitive)
            for portfolio in data["portfolios"]:
                assert term.lower() in portfolio["name"].lower()

@pytest.mark.asyncio
async def test_search_with_special_characters(mongodb_container):
    """Test search behavior with special characters in portfolio names"""
    # Initialize Beanie with the test MongoDB
    client = AsyncIOMotorClient(settings.mongodb_uri)
    await init_beanie(database=client[settings.mongodb_db], document_models=[Portfolio])
    
    # Clean up any existing portfolios
    await Portfolio.delete_all()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        
        # Create portfolios with valid special characters
        valid_names = [
            "Tech-Growth-Portfolio",
            "Tech_Growth_Portfolio", 
            "Tech Growth Portfolio",
            "Portfolio-123",
            "Portfolio_456",
            "Portfolio 789",
            "Multi-Word_Portfolio Name",
            "ABC-123_XYZ Portfolio"
        ]
        
        for name in valid_names:
            resp = await ac.post("/api/v1/portfolios", json={"name": name})
            assert resp.status_code == 201
        
        # Test exact search with hyphens
        response = await ac.get("/api/v2/portfolios?name=Tech-Growth-Portfolio")
        assert response.status_code == 200
        data = response.json()
        assert len(data["portfolios"]) == 1
        assert data["portfolios"][0]["name"] == "Tech-Growth-Portfolio"
        
        # Test exact search with underscores
        response = await ac.get("/api/v2/portfolios?name=Tech_Growth_Portfolio")
        assert response.status_code == 200
        data = response.json()
        assert len(data["portfolios"]) == 1
        assert data["portfolios"][0]["name"] == "Tech_Growth_Portfolio"
        
        # Test partial search with hyphens
        response = await ac.get("/api/v2/portfolios?name_like=Tech-Growth")
        assert response.status_code == 200
        data = response.json()
        found_names = [p["name"] for p in data["portfolios"]]
        assert "Tech-Growth-Portfolio" in found_names
        
        # Test partial search with underscores
        response = await ac.get("/api/v2/portfolios?name_like=Tech_Growth")
        assert response.status_code == 200
        data = response.json()
        found_names = [p["name"] for p in data["portfolios"]]
        assert "Tech_Growth_Portfolio" in found_names
        
        # Test partial search with numbers
        response = await ac.get("/api/v2/portfolios?name_like=123")
        assert response.status_code == 200
        data = response.json()
        found_names = [p["name"] for p in data["portfolios"]]
        assert "Portfolio-123" in found_names
        assert "ABC-123_XYZ Portfolio" in found_names

@pytest.mark.asyncio
async def test_search_result_ordering(mongodb_container):
    """Test that search results are properly ordered by dateCreated descending"""
    # Initialize Beanie with the test MongoDB
    client = AsyncIOMotorClient(settings.mongodb_uri)
    await init_beanie(database=client[settings.mongodb_db], document_models=[Portfolio])
    
    # Clean up any existing portfolios
    await Portfolio.delete_all()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        
        # Create portfolios with specific dates (newest to oldest)
        portfolios_with_dates = [
            ("TechPortfolio1", datetime(2024, 3, 1, tzinfo=UTC)),
            ("TechPortfolio2", datetime(2024, 2, 1, tzinfo=UTC)),
            ("TechPortfolio3", datetime(2024, 1, 1, tzinfo=UTC)),
            ("OtherPortfolio", datetime(2024, 2, 15, tzinfo=UTC))
        ]
        
        # Create portfolios in random order
        for name, date in portfolios_with_dates:
            portfolio = Portfolio(name=name, dateCreated=date, version=1)
            await portfolio.insert()
        
        # Test ordering with partial search
        response = await ac.get("/api/v2/portfolios?name_like=Tech")
        assert response.status_code == 200
        data = response.json()
        
        # Should find 3 TechPortfolio entries
        assert len(data["portfolios"]) == 3
        
        # Verify they are ordered by dateCreated descending (newest first)
        portfolios = data["portfolios"]
        assert portfolios[0]["name"] == "TechPortfolio1"  # 2024-03-01 (newest)
        assert portfolios[1]["name"] == "TechPortfolio2"  # 2024-02-01
        assert portfolios[2]["name"] == "TechPortfolio3"  # 2024-01-01 (oldest)
        
        # Test ordering with all portfolios
        response = await ac.get("/api/v2/portfolios")
        assert response.status_code == 200
        data = response.json()
        
        # Should find all 4 portfolios ordered by date
        assert len(data["portfolios"]) == 4
        portfolios = data["portfolios"]
        
        # Verify chronological order (newest first)
        dates = [datetime.fromisoformat(p["dateCreated"].replace('Z', '+00:00')) for p in portfolios]
        for i in range(len(dates) - 1):
            assert dates[i] >= dates[i + 1], "Results should be ordered by dateCreated descending" 