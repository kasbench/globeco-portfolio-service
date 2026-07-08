#!/usr/bin/env python3
"""
Quick test to verify the bulk insert fix works correctly.
"""

import asyncio
from datetime import datetime, UTC
from app.models import Portfolio
from app.services import PortfolioService
from app.schemas import PortfolioPostDTO
from beanie import init_beanie
from motor.motor_asyncio import AsyncIOMotorClient
import os

async def test_bulk_fix():
    """Test that the bulk insert fix works"""
    
    # Setup database
    mongo_url = os.getenv("MONGO_URL", "mongodb://localhost:27017")
    client = AsyncIOMotorClient(mongo_url)
    database = client.portfolio_fix_test
    await init_beanie(database=database, document_models=[Portfolio])
    await Portfolio.delete_all()
    
    # Create test data
    portfolio_dtos = []
    for i in range(5):
        dto = PortfolioPostDTO(
            name=f"Fix Test Portfolio {i+1}",
            dateCreated=datetime.now(UTC),
            version=1
        )
        portfolio_dtos.append(dto)
    
    print(f"Testing bulk creation fix with {len(portfolio_dtos)} portfolios...")
    
    try:
        # Test the service method
        created_portfolios = await PortfolioService.create_portfolios_bulk(portfolio_dtos)
        
        print(f"✅ Successfully created {len(created_portfolios)} portfolios")
        
        # Verify they have IDs
        for i, portfolio in enumerate(created_portfolios):
            if portfolio.id:
                print(f"   Portfolio {i+1}: {portfolio.name} (ID: {portfolio.id})")
            else:
                print(f"   ❌ Portfolio {i+1}: {portfolio.name} (NO ID!)")
        
        # Verify in database
        db_portfolios = await Portfolio.find_all().to_list()
        test_portfolios = [p for p in db_portfolios if p.name.startswith("Fix Test Portfolio")]
        
        print(f"✅ Verification: Found {len(test_portfolios)} portfolios in database")
        
        if len(created_portfolios) == len(test_portfolios) == len(portfolio_dtos):
            print("🎉 Bulk insert fix SUCCESSFUL!")
        else:
            print("⚠️  Mismatch in portfolio counts")
            
    except Exception as e:
        print(f"❌ Test FAILED: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        # Cleanup
        await Portfolio.delete_all()
        print("🧹 Cleaned up test data")

if __name__ == "__main__":
    asyncio.run(test_bulk_fix())