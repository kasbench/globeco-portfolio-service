#!/usr/bin/env python3

"""
Test script specifically for API v2 POST endpoint with proper initialization.
"""

import asyncio
import sys
import os
from fastapi.testclient import TestClient
from httpx import AsyncClient

async def test_with_lifespan():
    """Test API v2 with proper lifespan initialization."""
    
    print("=== Testing API v2 with Lifespan ===")
    
    # Import the app
    from app.main import app
    
    # Use AsyncClient with lifespan
    async with AsyncClient(app=app, base_url="http://test") as client:
        
        # Test root endpoint
        response = await client.get("/")
        print(f"✓ Root endpoint: {response.status_code}")
        
        # Test health endpoint
        response = await client.get("/health")
        print(f"✓ Health endpoint: {response.status_code}")
        
        # Test API v2 GET
        response = await client.get("/api/v2/portfolios")
        print(f"✓ API v2 GET portfolios: {response.status_code}")
        
        # Test API v2 POST
        test_portfolio = {
            "name": "Test Portfolio",
            "dateCreated": "2024-01-01T00:00:00Z",
            "version": 1
        }
        
        response = await client.post("/api/v2/portfolios", json=[test_portfolio])
        print(f"✓ API v2 POST portfolios: {response.status_code}")
        
        if response.status_code == 201:
            data = response.json()
            print(f"  Created portfolio: {data[0]['name']} (ID: {data[0]['portfolioId']})")
        else:
            print(f"  Error response: {response.text}")

def test_simple_routes():
    """Test routes that don't require database."""
    
    print("\n=== Testing Simple Routes ===")
    
    from app.main import app
    client = TestClient(app)
    
    # Test root endpoint
    response = client.get("/")
    print(f"✓ Root endpoint: {response.status_code}")
    if response.status_code == 200:
        data = response.json()
        print(f"  Environment: {data.get('environment')}")
        print(f"  Version: {data.get('version')}")
    
    # Test health endpoint
    response = client.get("/health")
    print(f"✓ Health endpoint: {response.status_code}")
    
    # Test health endpoints that don't require database
    response = client.get("/health/live")
    print(f"✓ Health live: {response.status_code}")

if __name__ == "__main__":
    print("API v2 Test with Proper Initialization")
    print("=" * 50)
    
    # Test simple routes first
    test_simple_routes()
    
    # Test with lifespan
    try:
        asyncio.run(test_with_lifespan())
    except Exception as e:
        print(f"✗ Lifespan test failed: {e}")
        import traceback
        traceback.print_exc()
    
    print("\n=== Test Complete ===")