#!/usr/bin/env python3
"""
Script to check Prometheus configuration and verify it's scraping the collector.
"""

import requests
import json
import sys
from typing import Dict, List

def check_prometheus_targets(prometheus_url: str) -> Dict:
    """Check Prometheus targets to see if collector is being scraped."""
    try:
        response = requests.get(f"{prometheus_url}/api/v1/targets", timeout=10)
        if response.status_code == 200:
            data = response.json()
            targets = data.get('data', {}).get('activeTargets', [])
            
            collector_targets = []
            for target in targets:
                if 'otel-collector' in target.get('labels', {}).get('job', '') or \
                   '8889' in target.get('scrapeUrl', ''):
                    collector_targets.append({
                        'job': target.get('labels', {}).get('job', 'unknown'),
                        'instance': target.get('labels', {}).get('instance', 'unknown'),
                        'scrapeUrl': target.get('scrapeUrl', 'unknown'),
                        'health': target.get('health', 'unknown'),
                        'lastError': target.get('lastError', '')
                    })
            
            return {
                'status': 'success',
                'total_targets': len(targets),
                'collector_targets': collector_targets
            }
        else:
            return {'status': 'error', 'message': f'HTTP {response.status_code}'}
    except Exception as e:
        return {'status': 'error', 'message': str(e)}

def query_prometheus_metrics(prometheus_url: str, metric_name: str) -> Dict:
    """Query Prometheus for specific metrics."""
    try:
        response = requests.get(
            f"{prometheus_url}/api/v1/query",
            params={'query': metric_name},
            timeout=10
        )
        if response.status_code == 200:
            data = response.json()
            result = data.get('data', {}).get('result', [])
            return {
                'status': 'success',
                'metric_count': len(result),
                'samples': result[:5]  # First 5 samples
            }
        else:
            return {'status': 'error', 'message': f'HTTP {response.status_code}'}
    except Exception as e:
        return {'status': 'error', 'message': str(e)}

def main():
    """Main function to check Prometheus configuration."""
    prometheus_url = "http://localhost:9090"
    
    # Allow command line override
    if len(sys.argv) > 1:
        prometheus_url = sys.argv[1]
    
    print("🔍 Prometheus Configuration Check")
    print("=" * 40)
    print(f"Prometheus URL: {prometheus_url}")
    print()
    
    # Step 1: Check Prometheus targets
    print("📊 Step 1: Checking Prometheus targets...")
    targets_result = check_prometheus_targets(prometheus_url)
    
    if targets_result['status'] == 'success':
        print(f"  Total targets: {targets_result['total_targets']}")
        print(f"  Collector targets: {len(targets_result['collector_targets'])}")
        
        if targets_result['collector_targets']:
            print("  Collector target details:")
            for target in targets_result['collector_targets']:
                print(f"    Job: {target['job']}")
                print(f"    Instance: {target['instance']}")
                print(f"    URL: {target['scrapeUrl']}")
                print(f"    Health: {target['health']}")
                if target['lastError']:
                    print(f"    Last Error: {target['lastError']}")
                print()
        else:
            print("  ❌ No collector targets found!")
            print("     - Check Prometheus configuration")
            print("     - Ensure collector is configured as a scrape target")
    else:
        print(f"  ❌ Error checking targets: {targets_result['message']}")
        return 1
    
    # Step 2: Query for custom metrics
    print("📈 Step 2: Querying for custom metrics...")
    
    custom_metrics = [
        'otel_http_requests_total',
        'http_requests_total{service_namespace="globeco"}',
        'otel_http_request_duration',
        'http_request_duration{service_namespace="globeco"}'
    ]
    
    found_metrics = 0
    for metric in custom_metrics:
        print(f"  Checking: {metric}")
        result = query_prometheus_metrics(prometheus_url, metric)
        
        if result['status'] == 'success':
            if result['metric_count'] > 0:
                print(f"    ✅ Found {result['metric_count']} series")
                found_metrics += 1
                # Show sample
                if result['samples']:
                    sample = result['samples'][0]
                    labels = sample.get('metric', {})
                    value = sample.get('value', ['', ''])[1]
                    print(f"    Sample: {labels} = {value}")
            else:
                print(f"    ❌ No data found")
        else:
            print(f"    ❌ Query error: {result['message']}")
        print()
    
    # Step 3: Diagnosis
    print("🔍 DIAGNOSIS:")
    
    if not targets_result.get('collector_targets'):
        print("  ❌ CRITICAL: Prometheus is not scraping the collector")
        print("     - Add collector target to Prometheus configuration:")
        print("       job_name: 'otel-collector'")
        print("       static_configs:")
        print("         - targets: ['localhost:8889']")
        return 1
    
    collector_healthy = any(
        target['health'] == 'up' 
        for target in targets_result.get('collector_targets', [])
    )
    
    if not collector_healthy:
        print("  ❌ CRITICAL: Collector targets are not healthy")
        print("     - Check collector is running and accessible")
        print("     - Verify port 8889 is open")
        for target in targets_result.get('collector_targets', []):
            if target['lastError']:
                print(f"     - Error: {target['lastError']}")
        return 1
    
    if found_metrics == 0:
        print("  ❌ ISSUE: No custom metrics found in Prometheus")
        print("     - Metrics are being scraped but not the custom ones")
        print("     - Check collector logs for metric export issues")
        print("     - Verify OpenTelemetry metrics are being sent to collector")
        return 1
    
    print(f"  ✅ SUCCESS: Found {found_metrics}/{len(custom_metrics)} custom metrics!")
    print("     - Custom metrics are flowing correctly to Prometheus")
    return 0

if __name__ == "__main__":
    sys.exit(main())