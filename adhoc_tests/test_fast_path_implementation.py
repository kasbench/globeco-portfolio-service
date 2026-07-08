#!/usr/bin/env python3
"""
Test script for fast-path implementation verification.

This script tests the streamlined service layer and fast-path API endpoints
to ensure they meet performance requirements and maintain functionality.
"""

import asyncio
import time
import json
from typing import List, Dict, Any
from datetime import datetime, UTC

# Test data
SAMPLE_PORTFOLIOS = [
    {"name": f"Test Portfolio {i}", "version": 1}
    for i in range(1, 11)  # 10 portfolios for bulk test
]

LARGE_BATCH_PORTFOLIOS = [
    {"name": f"Large Batch Portfolio {i}", "version": 1}
    for i in range(1, 51)  # 50 portfolios for performance test
]


async def test_streamlined_service():
    """Test the StreamlinedPortfolioService directly."""
    print("Testing StreamlinedPortfolioService...")
    
    try:
        from app.services import StreamlinedPortfolioService
        from app.schemas import PortfolioPostDTO
        
        # Convert test data to DTOs
        portfolio_dtos = [
            PortfolioPostDTO(
                name=p["name"],
                dateCreated=datetime.now(UTC),
                version=p["version"]
            )
            for p in SAMPLE_PORTFOLIOS[:5]  # Test with 5 portfolios
        ]
        
        # Test direct service operations
        start_time = time.perf_counter()
        
        async with StreamlinedPortfolioService() as service:
            # Test bulk creation
            created_portfolios = await service.create_portfolios_bulk_direct(portfolio_dtos)
            
            # Test search
            search_results, total_count = await service.search_portfolios_direct(
                name_like="Test",
                limit=10,
                offset=0
            )
            
            # Test individual operations
            if created_portfolios:
                first_portfolio = created_portfolios[0]
                retrieved = await service.get_portfolio_by_id_direct(str(first_portfolio.id))
                
                # Clean up - delete created portfolios
                for portfolio in created_portfolios:
                    await service.delete_portfolio_direct(portfolio)
        
        end_time = time.perf_counter()
        duration_ms = (end_time - start_time) * 1000
        
        print(f"✅ StreamlinedPortfolioService test completed:")
        print(f"   - Created: {len(created_portfolios)} portfolios")
        print(f"   - Search results: {len(search_results)} portfolios (total: {total_count})")
        print(f"   - Retrieved: {'✅' if retrieved else '❌'}")
        print(f"   - Duration: {duration_ms:.2f}ms")
        print(f"   - Performance: {'✅ PASS' if duration_ms < 500 else '❌ SLOW'} (<500ms target)")
        
        return True
        
    except Exception as e:
        print(f"❌ StreamlinedPortfolioService test failed: {e}")
        return False


async def test_fast_path_api():
    """Test the fast-path API endpoints."""
    print("\nTesting Fast-Path API...")
    
    try:
        import httpx
        
        # Test data for API
        test_portfolios = [
            {"name": f"API Test Portfolio {i}", "version": 1}
            for i in range(1, 6)  # 5 portfolios
        ]
        
        async with httpx.AsyncClient() as client:
            # Test fast-path bulk creation
            start_time = time.perf_counter()
            
            response = await client.post(
                "http://localhost:8000/api/fast/portfolios/bulk",
                json=test_portfolios,
                timeout=10.0
            )
            
            end_time = time.perf_counter()
            duration_ms = (end_time - start_time) * 1000
            
            if response.status_code == 201:
                result = response.json()
                created_count = result.get("count", 0)
                processing_time = result.get("processingTimeMs", 0)
                
                print(f"✅ Fast-path bulk creation test completed:")
                print(f"   - Status: {response.status_code}")
                print(f"   - Created: {created_count} portfolios")
                print(f"   - Processing time: {processing_time}ms")
                print(f"   - Total time: {duration_ms:.2f}ms")
                print(f"   - Performance: {'✅ PASS' if processing_time < 200 else '❌ SLOW'} (<200ms target)")
                
                # Test fast-path search
                search_response = await client.get(
                    "http://localhost:8000/api/fast/portfolios/search?name_like=API Test&limit=10"
                )
                
                if search_response.status_code == 200:
                    search_result = search_response.json()
                    search_time = search_result.get("processingTimeMs", 0)
                    found_count = len(search_result.get("portfolios", []))
                    
                    print(f"✅ Fast-path search test completed:")
                    print(f"   - Found: {found_count} portfolios")
                    print(f"   - Search time: {search_time}ms")
                    print(f"   - Performance: {'✅ PASS' if search_time < 100 else '❌ SLOW'} (<100ms target)")
                else:
                    print(f"❌ Fast-path search failed: {search_response.status_code}")
                    return False
                
                return True
            else:
                print(f"❌ Fast-path bulk creation failed: {response.status_code}")
                print(f"   Response: {response.text}")
                return False
                
    except Exception as e:
        print(f"❌ Fast-path API test failed: {e}")
        return False


def test_request_size_validation():
    """Test request size validation logic."""
    print("\nTesting Request Size Validation...")
    
    try:
        from app.api_fast import FastPathProcessor
        
        # Test valid request size
        small_data = b"small request"
        try:
            FastPathProcessor.validate_request_size_fast(small_data)
            print("✅ Small request validation passed")
        except Exception as e:
            print(f"❌ Small request validation failed: {e}")
            return False
        
        # Test bulk size validation
        try:
            FastPathProcessor.validate_bulk_size_fast(10)
            print("✅ Valid bulk size validation passed")
        except Exception as e:
            print(f"❌ Valid bulk size validation failed: {e}")
            return False
        
        # Test oversized bulk
        try:
            FastPathProcessor.validate_bulk_size_fast(150)
            print("❌ Oversized bulk validation should have failed")
            return False
        except Exception:
            print("✅ Oversized bulk validation correctly rejected")
        
        # Test response serialization
        from app.schemas import PortfolioResponseDTO
        from datetime import datetime, UTC
        
        test_portfolios = [
            PortfolioResponseDTO(
                portfolioId="test123",
                name="Test Portfolio",
                dateCreated=datetime.now(UTC),
                version=1
            )
        ]
        
        serialized = FastPathProcessor.serialize_response_fast(test_portfolios)
        
        if "portfolios" in serialized and "count" in serialized:
            print("✅ Response serialization test passed")
            return True
        else:
            print("❌ Response serialization test failed")
            return False
            
    except Exception as e:
        print(f"❌ Request size validation test failed: {e}")
        return False


async def performance_comparison_test():
    """Compare performance between standard and streamlined services."""
    print("\nRunning Performance Comparison...")
    
    try:
        from app.services import PortfolioService, StreamlinedPortfolioService
        from app.schemas import PortfolioPostDTO
        from datetime import datetime, UTC
        
        # Prepare test data
        portfolio_dtos = [
            PortfolioPostDTO(
                name=f"Perf Test Portfolio {i}",
                dateCreated=datetime.now(UTC),
                version=1
            )
            for i in range(1, 21)  # 20 portfolios
        ]
        
        # Test standard service
        print("Testing standard PortfolioService...")
        start_time = time.perf_counter()
        
        try:
            standard_result = await PortfolioService.create_portfolios_bulk(portfolio_dtos)
            standard_time = (time.perf_counter() - start_time) * 1000
            
            # Clean up standard results
            for portfolio in standard_result:
                await PortfolioService.delete_portfolio(portfolio)
                
        except Exception as e:
            print(f"Standard service test failed: {e}")
            standard_time = float('inf')
        
        # Test streamlined service
        print("Testing StreamlinedPortfolioService...")
        start_time = time.perf_counter()
        
        async with StreamlinedPortfolioService() as service:
            streamlined_result = await service.create_portfolios_bulk_direct(portfolio_dtos)
            streamlined_time = (time.perf_counter() - start_time) * 1000
            
            # Clean up streamlined results
            for portfolio in streamlined_result:
                await service.delete_portfolio_direct(portfolio)
        
        # Compare results
        improvement = ((standard_time - streamlined_time) / standard_time) * 100 if standard_time != float('inf') else 100
        
        print(f"📊 Performance Comparison Results:")
        print(f"   - Standard service: {standard_time:.2f}ms")
        print(f"   - Streamlined service: {streamlined_time:.2f}ms")
        print(f"   - Improvement: {improvement:.1f}%")
        print(f"   - Target met: {'✅ YES' if streamlined_time < 200 else '❌ NO'} (<200ms for 20 portfolios)")
        
        return streamlined_time < 200
        
    except Exception as e:
        print(f"❌ Performance comparison test failed: {e}")
        return False


async def main():
    """Run all fast-path implementation tests."""
    print("🚀 Fast-Path Implementation Test Suite")
    print("=" * 50)
    
    tests = [
        ("Request Size Validation", test_request_size_validation),
        ("Streamlined Service", test_streamlined_service),
        ("Performance Comparison", performance_comparison_test),
        # Note: API test requires running server
        # ("Fast-Path API", test_fast_path_api),
    ]
    
    results = []
    
    for test_name, test_func in tests:
        print(f"\n🧪 Running {test_name} test...")
        try:
            if asyncio.iscoroutinefunction(test_func):
                result = await test_func()
            else:
                result = test_func()
            results.append((test_name, result))
        except Exception as e:
            print(f"❌ {test_name} test crashed: {e}")
            results.append((test_name, False))
    
    # Summary
    print("\n" + "=" * 50)
    print("📋 Test Results Summary:")
    
    passed = 0
    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"   - {test_name}: {status}")
        if result:
            passed += 1
    
    print(f"\n🎯 Overall: {passed}/{len(results)} tests passed")
    
    if passed == len(results):
        print("🎉 All tests passed! Fast-path implementation is ready.")
    else:
        print("⚠️  Some tests failed. Review implementation before deployment.")
    
    return passed == len(results)


if __name__ == "__main__":
    asyncio.run(main())