#!/usr/bin/env python3
"""
Resource validation script for Kubernetes deployments.
Validates that resource requests and limits are within acceptable ranges.
"""

import yaml
import sys
from pathlib import Path
from typing import Dict, Any, List, Tuple

# Resource limits per environment (in millicores and MiB)
RESOURCE_LIMITS = {
    "development": {
        "cpu_request_max": 100,  # 100m
        "cpu_limit_max": 500,    # 500m
        "memory_request_max": 128,  # 128Mi
        "memory_limit_max": 512,    # 512Mi
    },
    "staging": {
        "cpu_request_max": 150,  # 150m
        "cpu_limit_max": 300,    # 300m
        "memory_request_max": 128,  # 128Mi
        "memory_limit_max": 384,    # 384Mi
    },
    "production": {
        "cpu_request_max": 100,  # 100m
        "cpu_limit_max": 200,    # 200m
        "memory_request_max": 128,  # 128Mi
        "memory_limit_max": 256,    # 256Mi
    }
}

def parse_cpu(cpu_str: str) -> int:
    """Parse CPU string to millicores."""
    if cpu_str.endswith('m'):
        return int(cpu_str[:-1])
    else:
        return int(float(cpu_str) * 1000)

def parse_memory(memory_str: str) -> int:
    """Parse memory string to MiB."""
    if memory_str.endswith('Mi'):
        return int(memory_str[:-2])
    elif memory_str.endswith('Gi'):
        return int(memory_str[:-2]) * 1024
    elif memory_str.endswith('Ki'):
        return int(memory_str[:-2]) // 1024
    else:
        # Assume bytes
        return int(memory_str) // (1024 * 1024)

def validate_resources(deployment_path: Path, environment: str) -> List[str]:
    """Validate resource configuration for a deployment."""
    errors = []
    
    try:
        with open(deployment_path, 'r') as f:
            docs = list(yaml.safe_load_all(f))
        
        for doc in docs:
            if doc and doc.get('kind') == 'Deployment':
                containers = doc.get('spec', {}).get('template', {}).get('spec', {}).get('containers', [])
                
                for container in containers:
                    resources = container.get('resources', {})
                    requests = resources.get('requests', {})
                    limits = resources.get('limits', {})
                    
                    # Validate CPU requests
                    if 'cpu' in requests:
                        cpu_request = parse_cpu(requests['cpu'])
                        max_cpu_request = RESOURCE_LIMITS[environment]['cpu_request_max']
                        if cpu_request > max_cpu_request:
                            errors.append(f"CPU request {requests['cpu']} exceeds limit {max_cpu_request}m for {environment}")
                    
                    # Validate CPU limits
                    if 'cpu' in limits:
                        cpu_limit = parse_cpu(limits['cpu'])
                        max_cpu_limit = RESOURCE_LIMITS[environment]['cpu_limit_max']
                        if cpu_limit > max_cpu_limit:
                            errors.append(f"CPU limit {limits['cpu']} exceeds limit {max_cpu_limit}m for {environment}")
                    
                    # Validate memory requests
                    if 'memory' in requests:
                        memory_request = parse_memory(requests['memory'])
                        max_memory_request = RESOURCE_LIMITS[environment]['memory_request_max']
                        if memory_request > max_memory_request:
                            errors.append(f"Memory request {requests['memory']} exceeds limit {max_memory_request}Mi for {environment}")
                    
                    # Validate memory limits
                    if 'memory' in limits:
                        memory_limit = parse_memory(limits['memory'])
                        max_memory_limit = RESOURCE_LIMITS[environment]['memory_limit_max']
                        if memory_limit > max_memory_limit:
                            errors.append(f"Memory limit {limits['memory']} exceeds limit {max_memory_limit}Mi for {environment}")
                    
                    # Validate that requests <= limits
                    if 'cpu' in requests and 'cpu' in limits:
                        cpu_request = parse_cpu(requests['cpu'])
                        cpu_limit = parse_cpu(limits['cpu'])
                        if cpu_request > cpu_limit:
                            errors.append(f"CPU request {requests['cpu']} exceeds CPU limit {limits['cpu']}")
                    
                    if 'memory' in requests and 'memory' in limits:
                        memory_request = parse_memory(requests['memory'])
                        memory_limit = parse_memory(limits['memory'])
                        if memory_request > memory_limit:
                            errors.append(f"Memory request {requests['memory']} exceeds memory limit {limits['memory']}")
    
    except Exception as e:
        errors.append(f"Error parsing {deployment_path}: {e}")
    
    return errors

def main():
    """Main validation function."""
    k8s_dir = Path(__file__).parent
    environments = ['development', 'staging', 'production']
    
    all_errors = []
    
    for env in environments:
        overlay_dir = k8s_dir / 'overlays' / env
        deployment_patch = overlay_dir / 'deployment-patch.yaml'
        
        if deployment_patch.exists():
            print(f"Validating {env} environment...")
            errors = validate_resources(deployment_patch, env)
            if errors:
                all_errors.extend([f"{env}: {error}" for error in errors])
            else:
                print(f"✓ {env} environment resources are valid")
        else:
            all_errors.append(f"{env}: deployment-patch.yaml not found")
    
    if all_errors:
        print("\nValidation errors:")
        for error in all_errors:
            print(f"  ✗ {error}")
        sys.exit(1)
    else:
        print("\n✓ All environment resource configurations are valid!")

if __name__ == "__main__":
    main()