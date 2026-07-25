#!/usr/bin/env python3
"""
Test local performance improvements after enabling performance mode.
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

async def test_local_performance():
    """Test performance improvements locally"""
    
    print("🧪 Testing Local Performance...")
    print("=" * 50)
    
    # Setup database
    mongo_url = os.getenv("MONGODB_URI", "mongodb://localhost:27017")
    client = AsyncMongoClient(mongo_url)
    database = client.portfolio_performance_test
    await init_beanie(database=database, document_models=[Portfolio])
    
    # Clean up
    await Portfolio.delete_all()
    
    # Test different batch sizes
    test_sizes = [5, 10, 25, 50]
    
    for size in test_sizes:
        print(f"\n📊 Testing {size} portfolios:")
        
        # Create test data
        portfolio_dtos = []
        for i in range(size):
            dto = PortfolioPostDTO(
                name=f"Perf Test {i+1}",
                dateCreated=datetime.now(UTC),
                version=1
            )
            portfolio_dtos.append(dto)
        
        # Measure performance
        start_time = time.time()
        
        try:
            created_portfolios = await PortfolioService.create_portfolios_bulk(portfolio_dtos)
            
            duration_ms = (time.time() - start_time) * 1000
            per_portfolio_ms = duration_ms / size
            
            print(f"   ✅ Created: {len(created_portfolios)} portfolios")
            print(f"   ⏱️  Total: {duration_ms:.1f}ms")
            print(f"   📈 Per portfolio: {per_portfolio_ms:.1f}ms")
            print(f"   🚀 Rate: {size/duration_ms*1000:.1f} portfolios/sec")
            
            # Performance assessment
            if duration_ms < 100:
                print(f"   🎉 EXCELLENT: < 100ms")
            elif duration_ms < 500:
                print(f"   ✅ GOOD: < 500ms")
            elif duration_ms < 1000:
                print(f"   ⚠️  OK: < 1000ms")
            else:
                print(f"   ❌ SLOW: > 1000ms")
                
        except Exception as e:
            print(f"   ❌ FAILED: {e}")
        
        # Clean up for next test
        await Portfolio.delete_all()
    
    print(f"\n🧹 Test completed")

if __name__ == "__main__":
    asyncio.run(test_local_performance())