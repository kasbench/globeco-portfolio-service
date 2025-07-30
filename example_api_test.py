#!/usr/bin/env python3
"""
Example script showing how to test the API and observe structured logging
"""

import asyncio
import httpx
import json
from datetime import datetime, timezone

async def test_api_with_logging():
    """Test API endpoints to demonstrate structured logging"""
    
    base_url = "http://localhost:8000"
    
    # Add correlation ID header for request tracing
    correlation_id = f"test-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}"
    headers = {
        "x-correlation-id": correlation_id,
        "content-type": "application/json"
    }
    
    print(f"Testing API with correlation ID: {correlation_id}")
    print("Watch the application logs to see structured JSON logging in action!\n")
    
    async with httpx.AsyncClient() as client:
        
        # Test health endpoint
        print("1. Testing health endpoint...")
        response = await client.get(f"{base_url}/health", headers=headers)
        print(f"   Status: {response.status_code}")
        print(f"   Response: {response.json()}")
        print(f"   Request ID: {response.headers.get('x-request-id', 'N/A')}\n")
        
        # Test get all portfolios (v1)
        print("2. Testing GET /api/v1/portfolios...")
        response = await client.get(f"{base_url}/api/v1/portfolios", headers=headers)
        print(f"   Status: {response.status_code}")
        portfolios = response.json()
        print(f"   Found {len(portfolios)} portfolios")
        print(f"   Request ID: {response.headers.get('x-request-id', 'N/A')}\n")
        
        # Test create portfolio (v1)
        print("3. Testing POST /api/v1/portfolios...")
        portfolio_data = {
            "name": f"Test Portfolio {datetime.now(timezone.utc).strftime('%H:%M:%S')}",
            "version": 1
        }
        response = await client.post(
            f"{base_url}/api/v1/portfolios", 
            json=portfolio_data,
            headers=headers
        )
        print(f"   Status: {response.status_code}")
        if response.status_code == 201:
            created_portfolio = response.json()
            print(f"   Created portfolio: {created_portfolio['name']}")
            print(f"   Portfolio ID: {created_portfolio['portfolioId']}")
            portfolio_id = created_portfolio['portfolioId']
        print(f"   Request ID: {response.headers.get('x-request-id', 'N/A')}\n")
        
        # Test search portfolios (v2)
        print("4. Testing GET /api/v2/portfolios with search...")
        response = await client.get(
            f"{base_url}/api/v2/portfolios?name_like=Test&limit=10&offset=0", 
            headers=headers
        )
        print(f"   Status: {response.status_code}")
        if response.status_code == 200:
            search_result = response.json()
            print(f"   Found {len(search_result['portfolios'])} portfolios")
            print(f"   Total: {search_result['pagination']['totalElements']}")
        print(f"   Request ID: {response.headers.get('x-request-id', 'N/A')}\n")
        
        # Test error case - invalid portfolio ID
        print("5. Testing error case - invalid portfolio ID...")
        response = await client.get(
            f"{base_url}/api/v1/portfolio/invalid-id", 
            headers=headers
        )
        print(f"   Status: {response.status_code}")
        print(f"   Error: {response.json()['detail']}")
        print(f"   Request ID: {response.headers.get('x-request-id', 'N/A')}\n")
        
    print("API testing completed!")
    print(f"All requests used correlation ID: {correlation_id}")
    print("Check the application logs to see:")
    print("- Structured JSON format")
    print("- Request/response logging")
    print("- Database operation logging")
    print("- Error logging with context")
    print("- Consistent correlation ID across all operations")

if __name__ == "__main__":
    print("This script tests the API endpoints to demonstrate structured logging.")
    print("Make sure the application is running on http://localhost:8000")
    print("Run with: python example_api_test.py\n")
    
    try:
        asyncio.run(test_api_with_logging())
    except Exception as e:
        print(f"Error: {e}")
        print("Make sure the application is running and accessible.")