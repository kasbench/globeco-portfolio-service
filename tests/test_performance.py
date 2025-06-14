import pytest
import time
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.models import Portfolio
from app.config import settings
from motor.motor_asyncio import AsyncIOMotorClient
from beanie import init_beanie
from datetime import datetime, UTC

@pytest.mark.asyncio
async def test_exact_name_lookup_performance(mongodb_container):
    """Test that exact name lookup meets < 200ms requirement"""
    # Initialize Beanie with the test MongoDB
    client = AsyncIOMotorClient(settings.mongodb_uri)
    await init_beanie(database=client[settings.mongodb_db], document_models=[Portfolio])
    
    # Clean up any existing portfolios
    await Portfolio.delete_all()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        
        # Create a substantial number of portfolios to test performance
        portfolio_names = []
        for i in range(100):
            name = f"Portfolio{i:03d}"
            portfolio_names.append(name)
            resp = await ac.post("/api/v1/portfolios", json={"name": name})
            assert resp.status_code == 201
        
        # Add a specific portfolio to search for
        target_name = "SpecificTargetPortfolio"
        resp = await ac.post("/api/v1/portfolios", json={"name": target_name})
        assert resp.status_code == 201
        
        # Perform multiple exact name searches and measure time
        search_times = []
        for _ in range(5):  # Run 5 times to get average
            start_time = time.time()
            response = await ac.get(f"/api/v2/portfolios?name={target_name}")
            end_time = time.time()
            
            assert response.status_code == 200
            data = response.json()
            assert len(data["portfolios"]) == 1
            assert data["portfolios"][0]["name"] == target_name
            
            search_time_ms = (end_time - start_time) * 1000
            search_times.append(search_time_ms)
        
        # Calculate average response time
        avg_time_ms = sum(search_times) / len(search_times)
        max_time_ms = max(search_times)
        
        print(f"Exact name search - Average: {avg_time_ms:.2f}ms, Max: {max_time_ms:.2f}ms")
        
        # Requirement: < 200ms for exact name lookup
        assert avg_time_ms < 200, f"Average response time {avg_time_ms:.2f}ms exceeds 200ms requirement"
        assert max_time_ms < 300, f"Max response time {max_time_ms:.2f}ms is too high (should be well under 200ms)"

@pytest.mark.asyncio
async def test_partial_name_search_performance(mongodb_container):
    """Test that partial name search meets < 500ms requirement"""
    # Initialize Beanie with the test MongoDB
    client = AsyncIOMotorClient(settings.mongodb_uri)
    await init_beanie(database=client[settings.mongodb_db], document_models=[Portfolio])
    
    # Clean up any existing portfolios
    await Portfolio.delete_all()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        
        # Create a larger dataset for performance testing
        portfolio_names = []
        
        # Create portfolios with various patterns
        for i in range(200):
            if i % 10 == 0:
                name = f"TechGrowthPortfolio{i}"
            elif i % 7 == 0:
                name = f"ConservativeIncomePortfolio{i}"
            elif i % 5 == 0:
                name = f"GlobalEquityFund{i}"
            else:
                name = f"RandomPortfolio{i}"
            
            portfolio_names.append(name)
            resp = await ac.post("/api/v1/portfolios", json={"name": name})
            assert resp.status_code == 201
        
        # Test partial search performance with different patterns
        search_patterns = [
            ("Tech", "prefix search"),
            ("Portfolio", "suffix search"),
            ("Growth", "infix search"),
            ("Equity", "less common term")
        ]
        
        for pattern, description in search_patterns:
            search_times = []
            
            for _ in range(3):  # Run 3 times for each pattern
                start_time = time.time()
                response = await ac.get(f"/api/v2/portfolios?name_like={pattern}")
                end_time = time.time()
                
                assert response.status_code == 200
                data = response.json()
                # Should find some results
                assert len(data["portfolios"]) > 0
                
                search_time_ms = (end_time - start_time) * 1000
                search_times.append(search_time_ms)
            
            avg_time_ms = sum(search_times) / len(search_times)
            max_time_ms = max(search_times)
            
            print(f"Partial search '{pattern}' ({description}) - Average: {avg_time_ms:.2f}ms, Max: {max_time_ms:.2f}ms")
            
            # Requirement: < 500ms for partial name search
            assert avg_time_ms < 500, f"Average response time {avg_time_ms:.2f}ms exceeds 500ms requirement for '{pattern}'"
            assert max_time_ms < 750, f"Max response time {max_time_ms:.2f}ms is too high for '{pattern}'"

@pytest.mark.asyncio
async def test_retrieve_all_portfolios_performance(mongodb_container):
    """Test that retrieving all portfolios meets < 300ms requirement"""
    # Initialize Beanie with the test MongoDB
    client = AsyncIOMotorClient(settings.mongodb_uri)
    await init_beanie(database=client[settings.mongodb_db], document_models=[Portfolio])
    
    # Clean up any existing portfolios
    await Portfolio.delete_all()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        
        # Create a moderate number of portfolios
        for i in range(150):
            name = f"Portfolio{i:03d}"
            resp = await ac.post("/api/v1/portfolios", json={"name": name})
            assert resp.status_code == 201
        
        # Test retrieving all portfolios performance
        retrieve_times = []
        
        for _ in range(5):  # Run 5 times
            start_time = time.time()
            response = await ac.get("/api/v2/portfolios")
            end_time = time.time()
            
            assert response.status_code == 200
            data = response.json()
            assert len(data["portfolios"]) == 50  # Default limit
            assert data["pagination"]["totalElements"] == 150
            
            retrieve_time_ms = (end_time - start_time) * 1000
            retrieve_times.append(retrieve_time_ms)
        
        avg_time_ms = sum(retrieve_times) / len(retrieve_times)
        max_time_ms = max(retrieve_times)
        
        print(f"Retrieve all portfolios - Average: {avg_time_ms:.2f}ms, Max: {max_time_ms:.2f}ms")
        
        # Requirement: < 300ms for retrieving all portfolios
        assert avg_time_ms < 300, f"Average response time {avg_time_ms:.2f}ms exceeds 300ms requirement"
        assert max_time_ms < 450, f"Max response time {max_time_ms:.2f}ms is too high"

@pytest.mark.asyncio
async def test_pagination_performance(mongodb_container):
    """Test pagination performance with various page sizes"""
    # Initialize Beanie with the test MongoDB
    client = AsyncIOMotorClient(settings.mongodb_uri)
    await init_beanie(database=client[settings.mongodb_db], document_models=[Portfolio])
    
    # Clean up any existing portfolios
    await Portfolio.delete_all()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        
        # Create a large dataset for pagination testing
        for i in range(500):
            name = f"Portfolio{i:04d}"
            resp = await ac.post("/api/v1/portfolios", json={"name": name})
            assert resp.status_code == 201
        
        # Test different pagination scenarios
        pagination_tests = [
            (10, 0, "small page, first page"),
            (50, 0, "medium page, first page"),
            (100, 0, "large page, first page"),
            (50, 100, "medium page, middle"),
            (50, 400, "medium page, near end"),
            (1000, 0, "max page size")
        ]
        
        for limit, offset, description in pagination_tests:
            start_time = time.time()
            response = await ac.get(f"/api/v2/portfolios?limit={limit}&offset={offset}")
            end_time = time.time()
            
            assert response.status_code == 200
            data = response.json()
            
            # Verify pagination works correctly
            expected_count = min(limit, max(0, 500 - offset))
            assert len(data["portfolios"]) == expected_count
            
            response_time_ms = (end_time - start_time) * 1000
            
            print(f"Pagination {description} (limit={limit}, offset={offset}) - Time: {response_time_ms:.2f}ms")
            
            # All pagination should be fast
            assert response_time_ms < 400, f"Pagination response time {response_time_ms:.2f}ms is too slow for {description}"

@pytest.mark.asyncio
async def test_concurrent_search_performance(mongodb_container):
    """Test performance under concurrent search requests"""
    # Initialize Beanie with the test MongoDB
    client = AsyncIOMotorClient(settings.mongodb_uri)
    await init_beanie(database=client[settings.mongodb_db], document_models=[Portfolio])
    
    # Clean up any existing portfolios
    await Portfolio.delete_all()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        
        # Create test data
        for i in range(100):
            name = f"TechPortfolio{i}" if i % 2 == 0 else f"FinancePortfolio{i}"
            resp = await ac.post("/api/v1/portfolios", json={"name": name})
            assert resp.status_code == 201
        
        # Simulate concurrent requests
        import asyncio
        
        async def search_request(search_term):
            start_time = time.time()
            response = await ac.get(f"/api/v2/portfolios?name_like={search_term}")
            end_time = time.time()
            
            assert response.status_code == 200
            return (end_time - start_time) * 1000
        
        # Run concurrent searches
        search_terms = ["Tech", "Finance", "Portfolio", "Tech", "Finance"] * 2  # 10 concurrent requests
        
        start_time = time.time()
        response_times = await asyncio.gather(*[search_request(term) for term in search_terms])
        total_time = (time.time() - start_time) * 1000
        
        avg_response_time = sum(response_times) / len(response_times)
        max_response_time = max(response_times)
        
        print(f"Concurrent searches - Total time: {total_time:.2f}ms, Avg per request: {avg_response_time:.2f}ms, Max: {max_response_time:.2f}ms")
        
        # Under concurrent load, individual requests should still be reasonably fast
        assert avg_response_time < 600, f"Average response time under load {avg_response_time:.2f}ms is too slow"
        assert max_response_time < 1000, f"Max response time under load {max_response_time:.2f}ms is too slow"

@pytest.mark.asyncio
async def test_database_index_effectiveness(mongodb_container):
    """Test that database indexes are effective for search performance"""
    # Initialize Beanie with the test MongoDB
    client = AsyncIOMotorClient(settings.mongodb_uri)
    await init_beanie(database=client[settings.mongodb_db], document_models=[Portfolio])
    
    # Clean up any existing portfolios
    await Portfolio.delete_all()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        
        # Create a large dataset to test index effectiveness
        for i in range(1000):
            # Create diverse names to test index performance
            if i % 100 == 0:
                name = f"UniqueSpecialPortfolio{i}"
            else:
                name = f"CommonPortfolio{i:04d}"
            
            resp = await ac.post("/api/v1/portfolios", json={"name": name})
            assert resp.status_code == 201
        
        # Test search for unique item (should be very fast with index)
        start_time = time.time()
        response = await ac.get("/api/v2/portfolios?name=UniqueSpecialPortfolio0")
        end_time = time.time()
        
        assert response.status_code == 200
        data = response.json()
        assert len(data["portfolios"]) == 1
        
        unique_search_time = (end_time - start_time) * 1000
        
        # Test partial search (should also benefit from index)
        start_time = time.time()
        response = await ac.get("/api/v2/portfolios?name_like=UniqueSpecial")
        end_time = time.time()
        
        assert response.status_code == 200
        data = response.json()
        assert len(data["portfolios"]) >= 10  # Should find all UniqueSpecialPortfolio entries
        
        partial_search_time = (end_time - start_time) * 1000
        
        print(f"Index effectiveness - Unique search: {unique_search_time:.2f}ms, Partial search: {partial_search_time:.2f}ms")
        
        # With proper indexing, even with 1000 records, searches should be fast
        assert unique_search_time < 100, f"Unique search time {unique_search_time:.2f}ms suggests index is not effective"
        assert partial_search_time < 300, f"Partial search time {partial_search_time:.2f}ms suggests index is not effective"

@pytest.mark.asyncio
async def test_memory_usage_stability(mongodb_container):
    """Test that repeated searches don't cause memory leaks or performance degradation"""
    # Initialize Beanie with the test MongoDB
    client = AsyncIOMotorClient(settings.mongodb_uri)
    await init_beanie(database=client[settings.mongodb_db], document_models=[Portfolio])
    
    # Clean up any existing portfolios
    await Portfolio.delete_all()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        
        # Create test data
        for i in range(50):
            name = f"TestPortfolio{i}"
            resp = await ac.post("/api/v1/portfolios", json={"name": name})
            assert resp.status_code == 201
        
        # Perform many repeated searches to test for memory leaks/degradation
        search_times = []
        
        for i in range(50):  # 50 repeated searches
            start_time = time.time()
            response = await ac.get("/api/v2/portfolios?name_like=Test")
            end_time = time.time()
            
            assert response.status_code == 200
            data = response.json()
            assert len(data["portfolios"]) == 50
            
            search_time_ms = (end_time - start_time) * 1000
            search_times.append(search_time_ms)
        
        # Check for performance degradation over time
        first_10_avg = sum(search_times[:10]) / 10
        last_10_avg = sum(search_times[-10:]) / 10
        
        print(f"Memory stability - First 10 searches avg: {first_10_avg:.2f}ms, Last 10 searches avg: {last_10_avg:.2f}ms")
        
        # Performance should not degrade significantly over repeated requests
        degradation_ratio = last_10_avg / first_10_avg
        assert degradation_ratio < 1.5, f"Performance degraded by {degradation_ratio:.2f}x, suggesting memory leak or other issues"
        
        # All searches should still be reasonably fast
        assert last_10_avg < 400, f"Performance degraded to {last_10_avg:.2f}ms average" 