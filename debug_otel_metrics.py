#!/usr/bin/env python3
"""
Debug script to verify OpenTelemetry metrics flow from application to collector.
This script helps diagnose why custom metrics aren't reaching Prometheus.
"""

import asyncio
import aiohttp
import json
import sys
from typing import Dict, Any, List
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class OTelMetricsDebugger:
    def __init__(self, app_url: str = "http://localhost:8000", collector_url: str = "http://localhost:8889"):
        self.app_url = app_url
        self.collector_url = collector_url
        
    async def check_app_metrics_endpoint(self) -> Dict[str, Any]:
        """Check the application's /metrics endpoint for custom metrics."""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{self.app_url}/metrics") as response:
                    if response.status == 200:
                        content = await response.text()
                        
                        # Look for custom metrics
                        custom_metrics = []
                        for line in content.split('\n'):
                            if any(metric in line for metric in ['http_requests_total', 'http_request_duration', 'http_requests_in_flight']):
                                if not line.startswith('#') and line.strip():
                                    custom_metrics.append(line.strip())
                        
                        return {
                            "status": "success",
                            "metrics_found": len(custom_metrics),
                            "custom_metrics": custom_metrics[:10],  # First 10 for brevity
                            "total_lines": len(content.split('\n'))
                        }
                    else:
                        return {"status": "error", "message": f"HTTP {response.status}"}
        except Exception as e:
            return {"status": "error", "message": str(e)}
    
    async def check_collector_metrics(self) -> Dict[str, Any]:
        """Check the OpenTelemetry collector's Prometheus endpoint."""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{self.collector_url}/metrics") as response:
                    if response.status == 200:
                        content = await response.text()
                        
                        # Look for our custom metrics
                        otel_metrics = []
                        for line in content.split('\n'):
                            if any(metric in line for metric in ['http_requests_total', 'http_request_duration', 'http_requests_in_flight']):
                                if not line.startswith('#') and line.strip():
                                    otel_metrics.append(line.strip())
                        
                        return {
                            "status": "success",
                            "otel_metrics_found": len(otel_metrics),
                            "otel_metrics": otel_metrics[:10],  # First 10 for brevity
                            "total_lines": len(content.split('\n'))
                        }
                    else:
                        return {"status": "error", "message": f"HTTP {response.status}"}
        except Exception as e:
            return {"status": "error", "message": str(e)}
    
    async def trigger_test_requests(self, count: int = 5) -> Dict[str, Any]:
        """Trigger test requests to generate metrics."""
        results = []
        try:
            async with aiohttp.ClientSession() as session:
                for i in range(count):
                    try:
                        async with session.get(f"{self.app_url}/") as response:
                            results.append({
                                "request": i + 1,
                                "status": response.status,
                                "success": response.status == 200
                            })
                    except Exception as e:
                        results.append({
                            "request": i + 1,
                            "status": "error",
                            "error": str(e),
                            "success": False
                        })
                        
            return {
                "status": "success",
                "requests_made": count,
                "successful_requests": sum(1 for r in results if r.get("success")),
                "results": results
            }
        except Exception as e:
            return {"status": "error", "message": str(e)}
    
    async def run_full_diagnostic(self) -> Dict[str, Any]:
        """Run complete diagnostic check."""
        logger.info("Starting OpenTelemetry metrics diagnostic...")
        
        # Step 1: Check initial state
        logger.info("Step 1: Checking initial metrics state...")
        initial_app_metrics = await self.check_app_metrics_endpoint()
        initial_collector_metrics = await self.check_collector_metrics()
        
        # Step 2: Trigger test requests
        logger.info("Step 2: Triggering test requests...")
        test_requests = await self.trigger_test_requests(5)
        
        # Step 3: Wait a bit for metrics to propagate
        logger.info("Step 3: Waiting for metrics to propagate...")
        await asyncio.sleep(15)  # Wait for export interval
        
        # Step 4: Check final state
        logger.info("Step 4: Checking final metrics state...")
        final_app_metrics = await self.check_app_metrics_endpoint()
        final_collector_metrics = await self.check_collector_metrics()
        
        return {
            "diagnostic_summary": {
                "app_metrics_working": final_app_metrics.get("status") == "success",
                "collector_metrics_working": final_collector_metrics.get("status") == "success",
                "custom_metrics_in_app": final_app_metrics.get("metrics_found", 0) > 0,
                "custom_metrics_in_collector": final_collector_metrics.get("otel_metrics_found", 0) > 0,
                "test_requests_successful": test_requests.get("successful_requests", 0) > 0
            },
            "initial_state": {
                "app_metrics": initial_app_metrics,
                "collector_metrics": initial_collector_metrics
            },
            "test_requests": test_requests,
            "final_state": {
                "app_metrics": final_app_metrics,
                "collector_metrics": final_collector_metrics
            }
        }

async def main():
    """Main diagnostic function."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Debug OpenTelemetry metrics flow")
    parser.add_argument("--app-url", default="http://localhost:8000", help="Application URL")
    parser.add_argument("--collector-url", default="http://localhost:8889", help="Collector Prometheus endpoint URL")
    parser.add_argument("--json", action="store_true", help="Output results as JSON")
    
    args = parser.parse_args()
    
    debugger = OTelMetricsDebugger(args.app_url, args.collector_url)
    results = await debugger.run_full_diagnostic()
    
    if args.json:
        print(json.dumps(results, indent=2))
    else:
        # Pretty print results
        summary = results["diagnostic_summary"]
        
        print("\n" + "="*60)
        print("OPENTELEMETRY METRICS DIAGNOSTIC RESULTS")
        print("="*60)
        
        print(f"\n📊 SUMMARY:")
        print(f"  ✅ App /metrics endpoint: {'Working' if summary['app_metrics_working'] else '❌ Failed'}")
        print(f"  ✅ Collector /metrics endpoint: {'Working' if summary['collector_metrics_working'] else '❌ Failed'}")
        print(f"  ✅ Custom metrics in app: {'Found' if summary['custom_metrics_in_app'] else '❌ Not found'}")
        print(f"  ✅ Custom metrics in collector: {'Found' if summary['custom_metrics_in_collector'] else '❌ Not found'}")
        print(f"  ✅ Test requests: {'Successful' if summary['test_requests_successful'] else '❌ Failed'}")
        
        # Show metrics details
        final_app = results["final_state"]["app_metrics"]
        final_collector = results["final_state"]["collector_metrics"]
        
        if final_app.get("status") == "success":
            print(f"\n📈 APP METRICS ({final_app.get('metrics_found', 0)} custom metrics found):")
            for metric in final_app.get("custom_metrics", [])[:5]:
                print(f"  {metric}")
        
        if final_collector.get("status") == "success":
            print(f"\n🔄 COLLECTOR METRICS ({final_collector.get('otel_metrics_found', 0)} OTel metrics found):")
            for metric in final_collector.get("otel_metrics", [])[:5]:
                print(f"  {metric}")
        
        # Diagnosis
        print(f"\n🔍 DIAGNOSIS:")
        if summary["custom_metrics_in_app"] and not summary["custom_metrics_in_collector"]:
            print("  ❌ ISSUE: Custom metrics are in app but not reaching collector")
            print("     - Check OpenTelemetry exporter configuration")
            print("     - Verify collector endpoint connectivity")
            print("     - Check collector logs for errors")
        elif summary["custom_metrics_in_collector"]:
            print("  ✅ SUCCESS: Custom metrics are flowing to collector")
            print("     - Metrics should appear in Prometheus")
        else:
            print("  ❌ ISSUE: Custom metrics not found in app")
            print("     - Check if metrics middleware is enabled")
            print("     - Verify OpenTelemetry metrics initialization")

if __name__ == "__main__":
    asyncio.run(main())