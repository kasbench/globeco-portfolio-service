#!/usr/bin/env python3

"""
Simple test script to verify API routes are working correctly.
"""

import asyncio
import sys
from fastapi.testclient import TestClient

# Import the app
try:
    from app.main import app
    print("✓ Successfully imported app")
except Exception as e:
    print(f"✗ Failed to import app: {e}")
    sys.exit(1)

def test_routes():
    """Test that all routes are properly registered."""
    
    print("\n=== Testing Route Registration ===")
    
    # Create test client
    client = TestClient(app)
    
    # Test root endpoint
    try:
        response = client.get("/")
        print(f"✓ Root endpoint: {response.status_code}")
        if response.status_code == 200:
            data = response.json()
            print(f"  Environment: {data.get('environment', 'unknown')}")
            print(f"  Version: {data.get('version', 'unknown')}")
    except Exception as e:
        print(f"✗ Root endpoint failed: {e}")
    
    # Test health endpoint
    try:
        response = client.get("/health")
        print(f"✓ Health endpoint: {response.status_code}")
    except Exception as e:
        print(f"✗ Health endpoint failed: {e}")
    
    # Test API v1 routes
    try:
        response = client.get("/api/v1/portfolios")
        print(f"✓ API v1 portfolios: {response.status_code}")
    except Exception as e:
        print(f"✗ API v1 portfolios failed: {e}")
    
    # Test API v2 routes
    try:
        response = client.get("/api/v2/portfolios")
        print(f"✓ API v2 portfolios: {response.status_code}")
    except Exception as e:
        print(f"✗ API v2 portfolios failed: {e}")
    
    # Test API fast routes
    try:
        response = client.get("/api/fast/health")
        print(f"✓ API fast health: {response.status_code}")
    except Exception as e:
        print(f"✗ API fast health failed: {e}")
    
    # List all registered routes
    print("\n=== Registered Routes ===")
    for route in app.routes:
        if hasattr(route, 'path') and hasattr(route, 'methods'):
            methods = ', '.join(route.methods) if route.methods else 'N/A'
            print(f"  {methods:10} {route.path}")
    
    print(f"\nTotal routes: {len(app.routes)}")

def test_api_v2_post():
    """Test the specific API v2 POST endpoint that's failing."""
    
    print("\n=== Testing API v2 POST Endpoint ===")
    
    client = TestClient(app)
    
    # Test data
    test_portfolio = {
        "name": "Test Portfolio",
        "dateCreated": "2024-01-01T00:00:00Z",
        "version": 1
    }
    
    try:
        response = client.post("/api/v2/portfolios", json=[test_portfolio])
        print(f"✓ API v2 POST portfolios: {response.status_code}")
        
        if response.status_code != 201:
            print(f"  Response: {response.text}")
            
    except Exception as e:
        print(f"✗ API v2 POST portfolios failed: {e}")

if __name__ == "__main__":
    print("Portfolio Service Route Test")
    print("=" * 40)
    
    test_routes()
    test_api_v2_post()
    
    print("\n=== Test Complete ===")