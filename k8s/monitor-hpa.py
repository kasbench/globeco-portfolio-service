#!/usr/bin/env python3
"""
HPA monitoring script for Kubernetes deployments.
Monitors horizontal pod autoscaler metrics and scaling events.
"""

import subprocess
import json
import time
import sys
from datetime import datetime
from typing import Dict, Any, List

def run_kubectl(args: List[str], namespace: str = "globeco") -> Dict[str, Any]:
    """Run kubectl command and return JSON output."""
    cmd = ["kubectl", "-n", namespace] + args
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return json.loads(result.stdout) if result.stdout.strip() else {}
    except subprocess.CalledProcessError as e:
        print(f"Error running kubectl: {e}")
        return {}
    except json.JSONDecodeError as e:
        print(f"Error parsing JSON: {e}")
        return {}

def get_hpa_status(namespace: str = "globeco") -> Dict[str, Any]:
    """Get HPA status."""
    return run_kubectl(["get", "hpa", "globeco-portfolio-service-hpa", "-o", "json"], namespace)

def get_deployment_status(namespace: str = "globeco") -> Dict[str, Any]:
    """Get deployment status."""
    return run_kubectl(["get", "deployment", "globeco-portfolio-service", "-o", "json"], namespace)

def get_pod_metrics(namespace: str = "globeco") -> Dict[str, Any]:
    """Get pod metrics."""
    return run_kubectl(["top", "pods", "-l", "app=globeco-portfolio-service", "--no-headers"], namespace)

def format_metrics(hpa_data: Dict[str, Any], deployment_data: Dict[str, Any]) -> str:
    """Format HPA and deployment metrics for display."""
    if not hpa_data or not deployment_data:
        return "No data available"
    
    hpa_status = hpa_data.get("status", {})
    deployment_status = deployment_data.get("status", {})
    
    current_replicas = hpa_status.get("currentReplicas", 0)
    desired_replicas = hpa_status.get("desiredReplicas", 0)
    min_replicas = hpa_data.get("spec", {}).get("minReplicas", 0)
    max_replicas = hpa_data.get("spec", {}).get("maxReplicas", 0)
    
    ready_replicas = deployment_status.get("readyReplicas", 0)
    available_replicas = deployment_status.get("availableReplicas", 0)
    
    metrics = hpa_status.get("currentMetrics", [])
    cpu_utilization = "N/A"
    memory_utilization = "N/A"
    
    for metric in metrics:
        if metric.get("type") == "Resource":
            resource = metric.get("resource", {})
            if resource.get("name") == "cpu":
                cpu_utilization = f"{resource.get('current', {}).get('averageUtilization', 'N/A')}%"
            elif resource.get("name") == "memory":
                memory_utilization = f"{resource.get('current', {}).get('averageUtilization', 'N/A')}%"
    
    return f"""
HPA Status:
  Current Replicas: {current_replicas}
  Desired Replicas: {desired_replicas}
  Min/Max Replicas: {min_replicas}/{max_replicas}
  
Deployment Status:
  Ready Replicas: {ready_replicas}
  Available Replicas: {available_replicas}
  
Current Metrics:
  CPU Utilization: {cpu_utilization}
  Memory Utilization: {memory_utilization}
"""

def monitor_hpa(namespace: str = "globeco", interval: int = 30):
    """Monitor HPA continuously."""
    print(f"Monitoring HPA for globeco-portfolio-service in namespace: {namespace}")
    print(f"Update interval: {interval} seconds")
    print("Press Ctrl+C to stop monitoring\n")
    
    try:
        while True:
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            print(f"=== {timestamp} ===")
            
            hpa_data = get_hpa_status(namespace)
            deployment_data = get_deployment_status(namespace)
            
            metrics_output = format_metrics(hpa_data, deployment_data)
            print(metrics_output)
            
            # Get recent events
            events_cmd = [
                "get", "events", 
                "--field-selector", "involvedObject.name=globeco-portfolio-service-hpa",
                "--sort-by", ".lastTimestamp",
                "-o", "custom-columns=TIME:.lastTimestamp,REASON:.reason,MESSAGE:.message",
                "--no-headers"
            ]
            
            try:
                result = subprocess.run(
                    ["kubectl", "-n", namespace] + events_cmd,
                    capture_output=True, text=True, check=True
                )
                if result.stdout.strip():
                    print("Recent HPA Events:")
                    for line in result.stdout.strip().split('\n')[-5:]:  # Last 5 events
                        print(f"  {line}")
                    print()
            except subprocess.CalledProcessError:
                pass
            
            print("-" * 50)
            time.sleep(interval)
            
    except KeyboardInterrupt:
        print("\nMonitoring stopped.")

def main():
    """Main function."""
    if len(sys.argv) > 1:
        namespace = sys.argv[1]
    else:
        namespace = "globeco"
    
    if len(sys.argv) > 2:
        interval = int(sys.argv[2])
    else:
        interval = 30
    
    monitor_hpa(namespace, interval)

if __name__ == "__main__":
    main()