#!/usr/bin/env python3
"""
Performance breakdown test to identify bottlenecks in the bulk API.
"""

import asyncio
import time
import httpx
import json
from datetime import datetime, UTC
from typing import List, Dict, Any

async def test_performance_breakdown():
    """Test different components to identify performance bottlenecks"""
    
    base_url = "http://localhost:8000"  # Adjust as needed
    
    # Create test data
    portfolios = []
    for i in range(10):
        portfolio = {
            "name": f"Performance Test Portfolio {i+1}",
            "dateCreated": datetime.now(UTC).isoformat(),
            "version": 1
        }
        portfolios.append(portfolio)
    
    print(f"Testing performance breakdown with {len(portfolios)} portfolios...")
    print("=" * 60)
    
    # Test 1: Measure JSON serialization overhead
    print("\n1. JSON Serialization Test:")
    start_time = time.time()
    json_data = json.dumps(portfolios)
    serialization_time = (time.time() - start_time) * 1000
    print(f"   JSON serialization: {serialization_time:.3f}ms")
    print(f"   Payload size: {len(json_data)} bytes")
    
    # Test 2: Measure network request overhead (without processing)
    print("\n2. Network Overhead Test:")
    async with httpx.AsyncClient(timeout=30.0) as client:
        # Test health endpoint for baseline
        start_time = time.time()
        try:
            response = await client.get(f"{base_url}/health")
            health_time = (time.time() - start_time) * 1000
            print(f"   Health endpoint: {health_time:.3f}ms (baseline)")
        except Exception as e:
            print(f"   Health endpoint failed: {e}")
            return
        
        # Test 3: Full bulk API call
        print("\n3. Full Bulk API Test:")
        start_time = time.time()
        try:
            response = await client.post(
                f"{base_url}/api/v2/portfolios",
                json=portfolios,
                headers={"Content-Type": "application/json"}
            )
            total_time = (time.time() - start_time) * 1000
            
            print(f"   Total API time: {total_time:.3f}ms")
            print(f"   Status code: {response.status_code}")
            
            if response.status_code == 201:
                response_data = response.json()
                print(f"   Created portfolios: {len(response_data)}")
                print(f"   Response size: {len(response.content)} bytes")
                
                # Calculate breakdown
                network_overhead = health_time
                processing_time = total_time - network_overhead - serialization_time
                
                print(f"\n   Performance Breakdown:")
                print(f"   - JSON serialization: {serialization_time:.3f}ms ({serialization_time/total_time*100:.1f}%)")
                print(f"   - Network overhead: {network_overhead:.3f}ms ({network_overhead/total_time*100:.1f}%)")
                print(f"   - Server processing: {processing_time:.3f}ms ({processing_time/total_time*100:.1f}%)")
                
                if total_time > 1000:
                    print(f"\n   ⚠️  SLOW: Total time {total_time:.0f}ms > 1000ms")
                    if processing_time > 800:
                        print(f"   🔍 Server processing is the bottleneck ({processing_time:.0f}ms)")
                    elif network_overhead > 500:
                        print(f"   🔍 Network overhead is high ({network_overhead:.0f}ms)")
                else:
                    print(f"\n   ✅ FAST: Total time {total_time:.0f}ms < 1000ms")
                
            else:
                print(f"   ❌ API call failed: {response.status_code}")
                print(f"   Response: {response.text}")
                
        except Exception as e:
            print(f"   ❌ API call failed: {e}")
    
    # Test 4: Multiple smaller requests vs one bulk request
    print("\n4. Bulk vs Individual Comparison:")
    async with httpx.AsyncClient(timeout=30.0) as client:
        # Individual requests
        start_time = time.time()
        individual_success = 0
        
        for portfolio in portfolios[:5]:  # Test with 5 for speed
            try:
                response = await client.post(
                    f"{base_url}/api/v1/portfolios",
                    json=portfolio
                )
                if response.status_code == 201:
                    individual_success += 1
            except Exception:
                pass
        
        individual_time = (time.time() - start_time) * 1000
        
        print(f"   Individual requests (5): {individual_time:.3f}ms")
        print(f"   Average per request: {individual_time/5:.3f}ms")
        print(f"   Successful: {individual_success}/5")
        
        # Bulk request
        start_time = time.time()
        try:
            response = await client.post(
                f"{base_url}/api/v2/portfolios",
                json=portfolios[:5]
            )
            bulk_time = (time.time() - start_time) * 1000
            bulk_success = len(response.json()) if response.status_code == 201 else 0
            
            print(f"   Bulk request (5): {bulk_time:.3f}ms")
            print(f"   Average per portfolio: {bulk_time/5:.3f}ms")
            print(f"   Successful: {bulk_success}/5")
            
            if individual_time > 0:
                improvement = individual_time / bulk_time
                print(f"   Improvement: {improvement:.1f}x faster")
                
        except Exception as e:
            print(f"   Bulk request failed: {e}")

if __name__ == "__main__":
    asyncio.run(test_performance_breakdown())