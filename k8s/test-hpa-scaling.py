#!/usr/bin/env python3
"""
HPA scaling test script.
Generates load to test horizontal pod autoscaler behavior.
"""

import asyncio
import aiohttp
import time
import argparse
from typing import List, Dict
import statistics

async def make_request(session: aiohttp.ClientSession, url: str, payload: Dict = None) -> Dict:
    """Make a single HTTP request."""
    try:
        if payload:
            async with session.post(url, json=payload) as response:
                return {
                    "status": response.status,
                    "duration": time.time(),
                    "success": response.status < 400
                }
        else:
            async with session.get(url) as response:
                return {
                    "status": response.status,
                    "duration": time.time(),
                    "success": response.status < 400
                }
    except Exception as e:
        return {
            "status": 0,
            "duration": time.time(),
            "success": False,
            "error": str(e)
        }

async def generate_load(base_url: str, duration: int, requests_per_second: int, test_type: str = "get"):
    """Generate load for HPA testing."""
    print(f"Generating {test_type} load: {requests_per_second} req/s for {duration} seconds")
    print(f"Target URL: {base_url}")
    
    # Prepare test payloads for different test types
    bulk_payload = {
        "portfolios": [
            {
                "name": f"test-portfolio-{i}",
                "description": f"Test portfolio {i} for HPA scaling",
                "tags": ["test", "hpa", "scaling"]
            }
            for i in range(10)  # 10 portfolios per bulk request
        ]
    }
    
    results = []
    start_time = time.time()
    
    connector = aiohttp.TCPConnector(limit=100, limit_per_host=50)
    timeout = aiohttp.ClientTimeout(total=30)
    
    async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
        while time.time() - start_time < duration:
            batch_start = time.time()
            
            # Create batch of requests
            tasks = []
            for _ in range(requests_per_second):
                if test_type == "bulk":
                    url = f"{base_url}/api/v1/portfolios/bulk"
                    task = make_request(session, url, bulk_payload)
                elif test_type == "single":
                    url = f"{base_url}/api/v1/portfolios"
                    payload = {
                        "name": f"test-portfolio-{int(time.time() * 1000)}",
                        "description": "Single portfolio for HPA testing",
                        "tags": ["test", "hpa"]
                    }
                    task = make_request(session, url, payload)
                else:  # get requests
                    url = f"{base_url}/api/v1/portfolios"
                    task = make_request(session, url)
                
                tasks.append(task)
            
            # Execute batch
            batch_results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Process results
            for result in batch_results:
                if isinstance(result, dict):
                    result["timestamp"] = time.time()
                    results.append(result)
            
            # Wait for next second
            batch_duration = time.time() - batch_start
            if batch_duration < 1.0:
                await asyncio.sleep(1.0 - batch_duration)
    
    return results

def analyze_results(results: List[Dict]) -> Dict:
    """Analyze load test results."""
    if not results:
        return {"error": "No results to analyze"}
    
    successful_requests = [r for r in results if r.get("success", False)]
    failed_requests = [r for r in results if not r.get("success", False)]
    
    status_codes = {}
    for result in results:
        status = result.get("status", 0)
        status_codes[status] = status_codes.get(status, 0) + 1
    
    total_requests = len(results)
    success_rate = len(successful_requests) / total_requests * 100 if total_requests > 0 else 0
    
    return {
        "total_requests": total_requests,
        "successful_requests": len(successful_requests),
        "failed_requests": len(failed_requests),
        "success_rate": success_rate,
        "status_codes": status_codes,
        "duration": results[-1]["timestamp"] - results[0]["timestamp"] if results else 0
    }

async def run_scaling_test(base_url: str, test_phases: List[Dict]):
    """Run multi-phase scaling test."""
    print("Starting HPA scaling test...")
    print("=" * 50)
    
    all_results = []
    
    for i, phase in enumerate(test_phases, 1):
        print(f"\nPhase {i}: {phase['description']}")
        print(f"Load: {phase['rps']} req/s for {phase['duration']} seconds")
        print(f"Type: {phase['type']}")
        
        phase_results = await generate_load(
            base_url, 
            phase["duration"], 
            phase["rps"], 
            phase["type"]
        )
        
        analysis = analyze_results(phase_results)
        print(f"Results: {analysis['successful_requests']}/{analysis['total_requests']} "
              f"({analysis['success_rate']:.1f}% success)")
        
        all_results.extend(phase_results)
        
        # Wait between phases
        if i < len(test_phases):
            wait_time = phase.get("wait_after", 30)
            print(f"Waiting {wait_time} seconds before next phase...")
            await asyncio.sleep(wait_time)
    
    print("\n" + "=" * 50)
    print("Overall Test Results:")
    overall_analysis = analyze_results(all_results)
    print(f"Total Requests: {overall_analysis['total_requests']}")
    print(f"Success Rate: {overall_analysis['success_rate']:.1f}%")
    print(f"Status Codes: {overall_analysis['status_codes']}")
    print(f"Test Duration: {overall_analysis['duration']:.1f} seconds")

def main():
    """Main function."""
    parser = argparse.ArgumentParser(description="HPA scaling test")
    parser.add_argument("--url", default="http://localhost:8000", help="Base URL")
    parser.add_argument("--preset", choices=["light", "moderate", "heavy"], default="moderate", 
                       help="Test preset")
    
    args = parser.parse_args()
    
    # Define test presets
    presets = {
        "light": [
            {"description": "Baseline load", "rps": 5, "duration": 60, "type": "get", "wait_after": 30},
            {"description": "Light increase", "rps": 15, "duration": 120, "type": "get", "wait_after": 60},
            {"description": "Cool down", "rps": 2, "duration": 180, "type": "get"}
        ],
        "moderate": [
            {"description": "Baseline load", "rps": 10, "duration": 60, "type": "get", "wait_after": 30},
            {"description": "Moderate increase", "rps": 30, "duration": 120, "type": "single", "wait_after": 60},
            {"description": "High load", "rps": 50, "duration": 180, "type": "get", "wait_after": 60},
            {"description": "Cool down", "rps": 5, "duration": 120, "type": "get"}
        ],
        "heavy": [
            {"description": "Baseline load", "rps": 20, "duration": 60, "type": "get", "wait_after": 30},
            {"description": "Heavy load", "rps": 100, "duration": 180, "type": "get", "wait_after": 60},
            {"description": "Bulk operations", "rps": 10, "duration": 120, "type": "bulk", "wait_after": 60},
            {"description": "Cool down", "rps": 5, "duration": 300, "type": "get"}
        ]
    }
    
    test_phases = presets[args.preset]
    
    print(f"Running {args.preset} HPA scaling test")
    print(f"Target: {args.url}")
    print("Monitor HPA with: kubectl get hpa -w")
    print("Monitor pods with: kubectl get pods -l app=globeco-portfolio-service -w")
    
    asyncio.run(run_scaling_test(args.url, test_phases))

if __name__ == "__main__":
    main()