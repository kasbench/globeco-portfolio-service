#!/usr/bin/env python3
"""
Compare sequential vs bulk insert performance for portfolio creation.
"""

import asyncio
import time
from datetime import datetime, UTC
from app.models import Portfolio
from app.schemas import PortfolioPostDTO
from beanie import init_beanie
from motor.motor_asyncio import AsyncIOMotorClient
import os

async def setup_database():
    """Initialize database connection for testing"""
    mongo_url = os.getenv("MONGO_URL", "mongodb://localhost:27017")
    client = AsyncIOMotorClient(mongo_url)
    database = client.portfolio_comparison_test
    await init_beanie(database=database, document_models=[Portfolio])
    await Portfolio.delete_all()
    return database

async def sequential_insert_method(portfolio_dtos):
    """Old method: Sequential inserts"""
    portfolios = []
    for dto in portfolio_dtos:
        portfolio = Portfolio(
            name=dto.name,
            dateCreated=dto.dateCreated if dto.dateCreated else datetime.now(UTC),
            version=dto.version if dto.version is not None else 1
        )
        portfolios.append(portfolio)
    
    # Sequential inserts (old method)
    created_portfolios = []
    for portfolio in portfolios:
        await portfolio.insert()
        created_portfolios.append(portfolio)
    
    return created_portfolios

async def bulk_insert_method(portfolio_dtos):
    """New method: Bulk insert"""
    portfolios = []
    for dto in portfolio_dtos:
        portfolio = Portfolio(
            name=dto.name,
            dateCreated=dto.dateCreated if dto.dateCreated else datetime.now(UTC),
            version=dto.version if dto.version is not None else 1
        )
        portfolios.append(portfolio)
    
    # Bulk insert (new method)
    insert_result = await Portfolio.insert_many(portfolios)
    # insert_many modifies the original portfolios with IDs, so return them
    return portfolios

async def run_comparison():
    """Run performance comparison"""
    await setup_database()
    
    # Test with different sizes
    test_sizes = [10, 25, 50]
    
    for size in test_sizes:
        print(f"\n{'='*60}")
        print(f"Testing with {size} portfolios")
        print(f"{'='*60}")
        
        # Create test data
        portfolio_dtos = []
        for i in range(size):
            dto = PortfolioPostDTO(
                name=f"Test Portfolio {i+1}",
                dateCreated=datetime.now(UTC),
                version=1
            )
            portfolio_dtos.append(dto)
        
        # Test sequential method
        await Portfolio.delete_all()
        print(f"\n📊 Sequential Insert Method ({size} portfolios):")
        start_time = time.time()
        
        try:
            sequential_result = await sequential_insert_method(portfolio_dtos)
            sequential_duration = time.time() - start_time
            
            print(f"   ✅ Created: {len(sequential_result)} portfolios")
            print(f"   ⏱️  Time: {sequential_duration:.3f} seconds")
            print(f"   📈 Rate: {len(sequential_result)/sequential_duration:.1f} portfolios/sec")
            
        except Exception as e:
            print(f"   ❌ Failed: {e}")
            sequential_duration = float('inf')
        
        # Test bulk method
        await Portfolio.delete_all()
        print(f"\n🚀 Bulk Insert Method ({size} portfolios):")
        start_time = time.time()
        
        try:
            bulk_result = await bulk_insert_method(portfolio_dtos)
            bulk_duration = time.time() - start_time
            
            print(f"   ✅ Created: {len(bulk_result)} portfolios")
            print(f"   ⏱️  Time: {bulk_duration:.3f} seconds")
            print(f"   📈 Rate: {len(bulk_result)/bulk_duration:.1f} portfolios/sec")
            
            # Calculate improvement
            if sequential_duration != float('inf') and bulk_duration > 0:
                improvement = sequential_duration / bulk_duration
                print(f"   🎯 Improvement: {improvement:.1f}x faster than sequential")
                
        except Exception as e:
            print(f"   ❌ Failed: {e}")
    
    # Cleanup
    await Portfolio.delete_all()
    print(f"\n🧹 Cleaned up test data")

if __name__ == "__main__":
    asyncio.run(run_comparison())