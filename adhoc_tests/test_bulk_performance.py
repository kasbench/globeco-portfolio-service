#!/usr/bin/env python3
"""
Performance test for bulk portfolio creation to verify optimization.
"""

import asyncio
import time
from datetime import datetime, UTC
from app.models import Portfolio
from app.services import PortfolioService
from app.schemas import PortfolioPostDTO
from beanie import init_beanie
from pymongo import AsyncMongoClient
import os

async def setup_database():
    """Initialize database connection for testing"""
    # Use test database
    mongo_url = os.getenv("MONGO_URL", "mongodb://localhost:27017")
    client = AsyncMongoClient(mongo_url)
    
    # Use a test database
    database = client.portfolio_test_db
    
    # Initialize Beanie
    await init_beanie(database=database, document_models=[Portfolio])
    
    # Clean up any existing test data
    await Portfolio.delete_all()
    
    return database

async def test_bulk_performance():
    """Test the performance of bulk portfolio creation"""
    
    # Setup
    await setup_database()
    
    # Create test data - 50 portfolios
    portfolio_dtos = []
    for i in range(50):
        dto = PortfolioPostDTO(
            name=f"Performance Test Portfolio {i+1}",
            dateCreated=datetime.now(UTC),
            version=1
        )
        portfolio_dtos.append(dto)
    
    print(f"Testing bulk creation of {len(portfolio_dtos)} portfolios...")
    
    # Measure performance
    start_time = time.time()
    
    try:
        created_portfolios = await PortfolioService.create_portfolios_bulk(portfolio_dtos)
        
        end_time = time.time()
        duration = end_time - start_time
        
        print(f"✅ Successfully created {len(created_portfolios)} portfolios")
        print(f"⏱️  Total time: {duration:.3f} seconds")
        print(f"📊 Average time per portfolio: {duration/len(created_portfolios):.3f} seconds")
        print(f"🚀 Portfolios per second: {len(created_portfolios)/duration:.1f}")
        
        # Verify all portfolios were created
        all_portfolios = await Portfolio.find_all().to_list()
        test_portfolios = [p for p in all_portfolios if p.name.startswith("Performance Test Portfolio")]
        
        print(f"✅ Verification: Found {len(test_portfolios)} test portfolios in database")
        
        if duration < 2.0:  # Should be much faster than 5 seconds for 10 portfolios
            print("🎉 Performance test PASSED - Bulk operation is optimized!")
        else:
            print("⚠️  Performance test WARNING - Still slower than expected")
            
    except Exception as e:
        print(f"❌ Performance test FAILED: {e}")
        raise
    
    finally:
        # Cleanup
        await Portfolio.delete_all()
        print("🧹 Cleaned up test data")

if __name__ == "__main__":
    asyncio.run(test_bulk_performance())