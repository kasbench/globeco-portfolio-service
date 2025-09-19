#!/usr/bin/env python3
"""
Health probe monitoring script for Kubernetes deployments.
Monitors health probe response times and success rates.
"""

import asyncio
import aiohttp
import time
import argparse
import statistics
from typing import List, Dict, Any
from datetime import datetime
import json


class HealthProbeMonitor:
    """Monitor health probe endpoints."""
    
    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip('/')
        self.endpoints = {
            'basic': '/health',
            'liveness': '/health/live',
            'readiness': '/health/ready',
            'startup': '/health/startup',
            'detailed': '/health/detailed',
            'metrics': '/health/metrics'
        }
        self.results = {endpoint: [] for endpoint in self.endpoints}
    
    async def check_endpoint(self, session: aiohttp.ClientSession, endpoint_name: str) -> Dict[str, Any]:
        """Check a single health endpoint."""
        url = f"{self.base_url}{self.endpoints[endpoint_name]}"
        start_time = time.perf_counter()
        
        try:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as response:
                response_time = (time.perf_counter() - start_time) * 1000  # Convert to ms
                content = await response.text()
                
                # Try to parse JSON response
                try:
                    json_content = json.loads(content)
                    server_response_time = json_content.get('response_time_ms', None)
                except json.JSONDecodeError:
                    json_content = None
                    server_response_time = None
                
                return {
                    'endpoint': endpoint_name,
                    'url': url,
                    'status_code': response.status,
                    'success': response.status < 400,
                    'client_response_time_ms': round(response_time, 2),
                    'server_response_time_ms': server_response_time,
                    'content_length': len(content),
                    'timestamp': datetime.now().isoformat(),
                    'cached': json_content.get('cached', False) if json_content else False,
                    'error': None
                }
        
        except Exception as e:
            response_time = (time.perf_counter() - start_time) * 1000
            return {
                'endpoint': endpoint_name,
                'url': url,
                'status_code': 0,
                'success': False,
                'client_response_time_ms': round(response_time, 2),
                'server_response_time_ms': None,
                'content_length': 0,
                'timestamp': datetime.now().isoformat(),
                'cached': False,
                'error': str(e)
            }
    
    async def run_checks(self, duration: int, interval: float) -> None:
        """Run health checks for specified duration."""
        print(f"Starting health probe monitoring for {duration} seconds")
        print(f"Target: {self.base_url}")
        print(f"Check interval: {interval} seconds")
        print("=" * 60)
        
        connector = aiohttp.TCPConnector(limit=10)
        timeout = aiohttp.ClientTimeout(total=30)
        
        async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
            start_time = time.time()
            
            while time.time() - start_time < duration:
                check_start = time.time()
                
                # Run all endpoint checks concurrently
                tasks = [
                    self.check_endpoint(session, endpoint_name)
                    for endpoint_name in self.endpoints
                ]
                
                results = await asyncio.gather(*tasks, return_exceptions=True)
                
                # Process results
                for result in results:
                    if isinstance(result, dict):
                        endpoint_name = result['endpoint']
                        self.results[endpoint_name].append(result)
                        
                        # Print real-time results
                        status_icon = "✓" if result['success'] else "✗"
                        cache_icon = "(cached)" if result.get('cached') else ""
                        
                        print(f"{status_icon} {endpoint_name:10} | "
                              f"Status: {result['status_code']:3} | "
                              f"Client: {result['client_response_time_ms']:6.2f}ms | "
                              f"Server: {result['server_response_time_ms'] or 'N/A':>6}ms | "
                              f"Size: {result['content_length']:4}B {cache_icon}")
                
                # Wait for next interval
                check_duration = time.time() - check_start
                if check_duration < interval:
                    await asyncio.sleep(interval - check_duration)
                
                print("-" * 60)
    
    def analyze_results(self) -> Dict[str, Any]:
        """Analyze monitoring results."""
        analysis = {}
        
        for endpoint_name, results in self.results.items():
            if not results:
                analysis[endpoint_name] = {"error": "No results"}
                continue
            
            successful_results = [r for r in results if r['success']]
            failed_results = [r for r in results if not r['success']]
            
            client_times = [r['client_response_time_ms'] for r in successful_results]
            server_times = [r['server_response_time_ms'] for r in successful_results 
                           if r['server_response_time_ms'] is not None]
            
            cached_results = [r for r in results if r.get('cached', False)]
            
            analysis[endpoint_name] = {
                'total_requests': len(results),
                'successful_requests': len(successful_results),
                'failed_requests': len(failed_results),
                'success_rate': len(successful_results) / len(results) * 100 if results else 0,
                'cached_requests': len(cached_results),
                'cache_hit_rate': len(cached_results) / len(results) * 100 if results else 0,
                'client_response_times': {
                    'min_ms': min(client_times) if client_times else 0,
                    'max_ms': max(client_times) if client_times else 0,
                    'avg_ms': statistics.mean(client_times) if client_times else 0,
                    'median_ms': statistics.median(client_times) if client_times else 0,
                    'p95_ms': statistics.quantiles(client_times, n=20)[18] if len(client_times) >= 20 else (max(client_times) if client_times else 0),
                    'p99_ms': statistics.quantiles(client_times, n=100)[98] if len(client_times) >= 100 else (max(client_times) if client_times else 0)
                },
                'server_response_times': {
                    'min_ms': min(server_times) if server_times else 0,
                    'max_ms': max(server_times) if server_times else 0,
                    'avg_ms': statistics.mean(server_times) if server_times else 0,
                    'median_ms': statistics.median(server_times) if server_times else 0,
                    'p95_ms': statistics.quantiles(server_times, n=20)[18] if len(server_times) >= 20 else (max(server_times) if server_times else 0),
                    'p99_ms': statistics.quantiles(server_times, n=100)[98] if len(server_times) >= 100 else (max(server_times) if server_times else 0)
                },
                'performance_targets': {
                    'under_10ms_server': len([t for t in server_times if t < 10]) / len(server_times) * 100 if server_times else 0,
                    'under_5ms_server': len([t for t in server_times if t < 5]) / len(server_times) * 100 if server_times else 0,
                    'under_50ms_client': len([t for t in client_times if t < 50]) / len(client_times) * 100 if client_times else 0
                }
            }
        
        return analysis
    
    def print_analysis(self) -> None:
        """Print analysis results."""
        analysis = self.analyze_results()
        
        print("\n" + "=" * 80)
        print("HEALTH PROBE MONITORING ANALYSIS")
        print("=" * 80)
        
        for endpoint_name, stats in analysis.items():
            if 'error' in stats:
                print(f"\n{endpoint_name.upper()}: {stats['error']}")
                continue
            
            print(f"\n{endpoint_name.upper()} ENDPOINT:")
            print(f"  Total Requests: {stats['total_requests']}")
            print(f"  Success Rate: {stats['success_rate']:.1f}%")
            print(f"  Cache Hit Rate: {stats['cache_hit_rate']:.1f}%")
            
            print(f"  Client Response Times:")
            print(f"    Min: {stats['client_response_times']['min_ms']:.2f}ms")
            print(f"    Avg: {stats['client_response_times']['avg_ms']:.2f}ms")
            print(f"    P95: {stats['client_response_times']['p95_ms']:.2f}ms")
            print(f"    Max: {stats['client_response_times']['max_ms']:.2f}ms")
            
            if stats['server_response_times']['avg_ms'] > 0:
                print(f"  Server Response Times:")
                print(f"    Min: {stats['server_response_times']['min_ms']:.2f}ms")
                print(f"    Avg: {stats['server_response_times']['avg_ms']:.2f}ms")
                print(f"    P95: {stats['server_response_times']['p95_ms']:.2f}ms")
                print(f"    Max: {stats['server_response_times']['max_ms']:.2f}ms")
                
                print(f"  Performance Targets:")
                print(f"    <10ms (server): {stats['performance_targets']['under_10ms_server']:.1f}%")
                print(f"    <5ms (server): {stats['performance_targets']['under_5ms_server']:.1f}%")
            
            print(f"    <50ms (client): {stats['performance_targets']['under_50ms_client']:.1f}%")
        
        print("\n" + "=" * 80)


async def main():
    """Main function."""
    parser = argparse.ArgumentParser(description="Health probe monitoring")
    parser.add_argument("--url", default="http://localhost:8000", help="Base URL")
    parser.add_argument("--duration", type=int, default=60, help="Monitoring duration in seconds")
    parser.add_argument("--interval", type=float, default=5.0, help="Check interval in seconds")
    
    args = parser.parse_args()
    
    monitor = HealthProbeMonitor(args.url)
    
    try:
        await monitor.run_checks(args.duration, args.interval)
    except KeyboardInterrupt:
        print("\nMonitoring interrupted by user")
    
    monitor.print_analysis()


if __name__ == "__main__":
    asyncio.run(main())