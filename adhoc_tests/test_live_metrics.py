#!/usr/bin/env python3
"""
Test script to trigger HTTP requests and verify metrics are being recorded and exported.
"""

import requests
import time
import sys

def test_live_metrics():
    """Test that metrics are being recorded and exported by making actual HTTP requests."""
    
    print("🔍 Testing live metrics recording and export...")
    
    # Configuration
    app_url = "http://localhost:8000"  # Adjust if needed
    collector_url = "http://localhost:8889"  # Adjust if needed
    
    # Step 1: Check initial collector state
    print("\n📊 Step 1: Checking initial collector metrics...")
    try:
        response = requests.get(f"{collector_url}/metrics", timeout=10)
        if response.status_code == 200:
            initial_metrics = response.text
            http_request_lines = [line for line in initial_metrics.split('\n') 
                                if 'http_request' in line and 'globeco-portfolio-service' in line]
            print(f"   Initial HTTP request metrics found: {len(http_request_lines)}")
            if http_request_lines:
                for line in http_request_lines[:3]:
                    print(f"     {line}")
        else:
            print(f"   ❌ Cannot access collector: HTTP {response.status_code}")
            return False
    except Exception as e:
        print(f"   ❌ Cannot access collector: {e}")
        return False
    
    # Step 2: Trigger HTTP requests to generate metrics
    print("\n🚀 Step 2: Triggering HTTP requests to generate metrics...")
    successful_requests = 0
    total_requests = 10
    
    for i in range(total_requests):
        try:
            # Make requests to different endpoints
            endpoints = ["/", "/health", f"/api/v1/portfolios?page={i}"]
            endpoint = endpoints[i % len(endpoints)]
            
            response = requests.get(f"{app_url}{endpoint}", timeout=5)
            if response.status_code in [200, 404]:  # 404 is OK for non-existent portfolios
                successful_requests += 1
                print(f"   Request {i+1}: {endpoint} -> {response.status_code}")
            else:
                print(f"   Request {i+1}: {endpoint} -> {response.status_code} (unexpected)")
        except Exception as e:
            print(f"   Request {i+1}: {endpoint} -> Error: {e}")
        
        time.sleep(0.5)  # Small delay between requests
    
    print(f"   Completed {successful_requests}/{total_requests} successful requests")
    
    # Step 3: Wait for metrics export
    print(f"\n⏳ Step 3: Waiting for metrics export (15 seconds)...")
    time.sleep(15)
    
    # Step 4: Check collector metrics again
    print("\n📈 Step 4: Checking collector metrics after requests...")
    try:
        response = requests.get(f"{collector_url}/metrics", timeout=10)
        if response.status_code == 200:
            final_metrics = response.text
            
            # Look for our specific metrics
            http_request_total_lines = [line for line in final_metrics.split('\n') 
                                      if 'http_requests_total' in line and 'globeco-portfolio-service' in line]
            http_request_duration_lines = [line for line in final_metrics.split('\n') 
                                         if 'http_request_duration' in line and 'globeco-portfolio-service' in line]
            http_requests_in_flight_lines = [line for line in final_metrics.split('\n') 
                                           if 'http_requests_in_flight' in line and 'globeco-portfolio-service' in line]
            
            print(f"   http_requests_total metrics: {len(http_request_total_lines)}")
            print(f"   http_request_duration metrics: {len(http_request_duration_lines)}")
            print(f"   http_requests_in_flight metrics: {len(http_requests_in_flight_lines)}")
            
            if http_request_total_lines:
                print("   Sample http_requests_total metrics:")
                for line in http_request_total_lines[:3]:
                    print(f"     {line}")
            
            if http_request_duration_lines:
                print("   Sample http_request_duration metrics:")
                for line in http_request_duration_lines[:3]:
                    print(f"     {line}")
            
            # Check if we have any metrics at all
            total_custom_metrics = len(http_request_total_lines) + len(http_request_duration_lines) + len(http_requests_in_flight_lines)
            
            if total_custom_metrics > 0:
                print(f"\n✅ SUCCESS: Found {total_custom_metrics} custom HTTP metrics in collector!")
                return True
            else:
                print(f"\n❌ ISSUE: No custom HTTP metrics found in collector after {successful_requests} requests")
                
                # Debug: Show what metrics we do have for this service
                service_lines = [line for line in final_metrics.split('\n') 
                               if 'globeco-portfolio-service' in line and not line.startswith('#')]
                print(f"   Total metrics for globeco-portfolio-service: {len(service_lines)}")
                if service_lines:
                    print("   Sample service metrics found:")
                    for line in service_lines[:5]:
                        print(f"     {line}")
                
                return False
        else:
            print(f"   ❌ Cannot access collector: HTTP {response.status_code}")
            return False
    except Exception as e:
        print(f"   ❌ Cannot access collector: {e}")
        return False

if __name__ == "__main__":
    success = test_live_metrics()
    if success:
        print("\n🎉 Metrics are working correctly!")
        sys.exit(0)
    else:
        print("\n💥 Metrics are not working as expected.")
        print("\nTroubleshooting steps:")
        print("1. Check if the application is accessible")
        print("2. Check if the collector is accessible") 
        print("3. Check application logs for metric recording errors")
        print("4. Check collector logs for metric processing errors")
        sys.exit(1)