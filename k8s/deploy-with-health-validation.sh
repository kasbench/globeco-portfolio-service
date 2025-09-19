#!/bin/bash
"""
Deployment script with health check validation.
Deploys the application and validates health probe performance.
"""

set -euo pipefail

# Configuration
NAMESPACE="${NAMESPACE:-globeco}"
ENVIRONMENT="${ENVIRONMENT:-production}"
IMAGE_TAG="${IMAGE_TAG:-latest}"
HEALTH_CHECK_TIMEOUT="${HEALTH_CHECK_TIMEOUT:-300}"
HEALTH_CHECK_INTERVAL="${HEALTH_CHECK_INTERVAL:-5}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

log() {
    echo -e "${BLUE}[$(date +'%Y-%m-%d %H:%M:%S')]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[$(date +'%Y-%m-%d %H:%M:%S')] ✓${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[$(date +'%Y-%m-%d %H:%M:%S')] ⚠${NC} $1"
}

log_error() {
    echo -e "${RED}[$(date +'%Y-%m-%d %H:%M:%S')] ✗${NC} $1"
}

# Function to check if kubectl is available
check_kubectl() {
    if ! command -v kubectl &> /dev/null; then
        log_error "kubectl is not installed or not in PATH"
        exit 1
    fi
    
    if ! kubectl cluster-info &> /dev/null; then
        log_error "Cannot connect to Kubernetes cluster"
        exit 1
    fi
    
    log_success "kubectl is available and connected to cluster"
}

# Function to validate environment
validate_environment() {
    case $ENVIRONMENT in
        development|staging|production)
            log_success "Environment validated: $ENVIRONMENT"
            ;;
        *)
            log_error "Invalid environment: $ENVIRONMENT. Must be development, staging, or production"
            exit 1
            ;;
    esac
}

# Function to create namespace if it doesn't exist
ensure_namespace() {
    if kubectl get namespace "$NAMESPACE" &> /dev/null; then
        log_success "Namespace $NAMESPACE already exists"
    else
        log "Creating namespace $NAMESPACE"
        kubectl create namespace "$NAMESPACE"
        log_success "Namespace $NAMESPACE created"
    fi
}

# Function to validate resource configuration
validate_resources() {
    log "Validating resource configuration for $ENVIRONMENT environment"
    
    if python3 k8s/validate-resources.py; then
        log_success "Resource configuration validation passed"
    else
        log_error "Resource configuration validation failed"
        exit 1
    fi
}

# Function to deploy application
deploy_application() {
    log "Deploying application to $ENVIRONMENT environment"
    
    # Build kustomization
    local overlay_dir="k8s/overlays/$ENVIRONMENT"
    
    if [[ ! -d "$overlay_dir" ]]; then
        log_error "Environment overlay directory not found: $overlay_dir"
        exit 1
    fi
    
    # Update image tag if specified
    if [[ "$IMAGE_TAG" != "latest" ]]; then
        log "Setting image tag to: $IMAGE_TAG"
        cd "$overlay_dir"
        kustomize edit set image "kasbench/globeco-portfolio-service:$IMAGE_TAG"
        cd - > /dev/null
    fi
    
    # Apply configuration
    log "Applying Kubernetes configuration"
    kubectl apply -k "$overlay_dir"
    
    log_success "Application deployed"
}

# Function to wait for deployment rollout
wait_for_rollout() {
    log "Waiting for deployment rollout to complete"
    
    if kubectl rollout status deployment/globeco-portfolio-service -n "$NAMESPACE" --timeout=300s; then
        log_success "Deployment rollout completed"
    else
        log_error "Deployment rollout failed or timed out"
        
        # Show pod status for debugging
        log "Pod status:"
        kubectl get pods -n "$NAMESPACE" -l app=globeco-portfolio-service
        
        log "Recent events:"
        kubectl get events -n "$NAMESPACE" --sort-by='.lastTimestamp' | tail -10
        
        exit 1
    fi
}

# Function to get service endpoint
get_service_endpoint() {
    local service_type
    service_type=$(kubectl get service globeco-portfolio-service -n "$NAMESPACE" -o jsonpath='{.spec.type}')
    
    case $service_type in
        "LoadBalancer")
            local external_ip
            external_ip=$(kubectl get service globeco-portfolio-service -n "$NAMESPACE" -o jsonpath='{.status.loadBalancer.ingress[0].ip}')
            if [[ -n "$external_ip" ]]; then
                echo "http://$external_ip:8000"
            else
                log_warning "LoadBalancer external IP not yet assigned, using port-forward"
                echo "http://localhost:8000"
            fi
            ;;
        "NodePort")
            local node_port
            node_port=$(kubectl get service globeco-portfolio-service -n "$NAMESPACE" -o jsonpath='{.spec.ports[0].nodePort}')
            local node_ip
            node_ip=$(kubectl get nodes -o jsonpath='{.items[0].status.addresses[?(@.type=="ExternalIP")].address}')
            if [[ -z "$node_ip" ]]; then
                node_ip=$(kubectl get nodes -o jsonpath='{.items[0].status.addresses[?(@.type=="InternalIP")].address}')
            fi
            echo "http://$node_ip:$node_port"
            ;;
        *)
            log_warning "Service type $service_type requires port-forwarding"
            echo "http://localhost:8000"
            ;;
    esac
}

# Function to setup port forwarding if needed
setup_port_forward() {
    local endpoint="$1"
    
    if [[ "$endpoint" == "http://localhost:8000" ]]; then
        log "Setting up port forwarding"
        kubectl port-forward service/globeco-portfolio-service 8000:8000 -n "$NAMESPACE" &
        local port_forward_pid=$!
        
        # Wait for port forward to be ready
        sleep 5
        
        # Return the PID so we can clean it up later
        echo "$port_forward_pid"
    fi
}

# Function to validate health endpoints
validate_health_endpoints() {
    local endpoint="$1"
    local port_forward_pid="$2"
    
    log "Validating health endpoints at $endpoint"
    
    # Test basic connectivity first
    local max_attempts=30
    local attempt=1
    
    while [[ $attempt -le $max_attempts ]]; do
        if curl -s -f "$endpoint/health" > /dev/null; then
            log_success "Basic health endpoint is responding"
            break
        fi
        
        log "Attempt $attempt/$max_attempts: Waiting for service to be ready..."
        sleep 5
        ((attempt++))
    done
    
    if [[ $attempt -gt $max_attempts ]]; then
        log_error "Service failed to become ready within timeout"
        [[ -n "$port_forward_pid" ]] && kill "$port_forward_pid" 2>/dev/null || true
        exit 1
    fi
    
    # Run comprehensive health probe monitoring
    log "Running health probe performance validation"
    
    if python3 k8s/monitor-health-probes.py --url "$endpoint" --duration 60 --interval 2; then
        log_success "Health probe validation completed successfully"
    else
        log_error "Health probe validation failed"
        [[ -n "$port_forward_pid" ]] && kill "$port_forward_pid" 2>/dev/null || true
        exit 1
    fi
    
    # Clean up port forward if we started it
    if [[ -n "$port_forward_pid" ]]; then
        log "Cleaning up port forwarding"
        kill "$port_forward_pid" 2>/dev/null || true
    fi
}

# Function to validate HPA configuration
validate_hpa() {
    log "Validating HPA configuration"
    
    if kubectl get hpa globeco-portfolio-service-hpa -n "$NAMESPACE" &> /dev/null; then
        local hpa_status
        hpa_status=$(kubectl get hpa globeco-portfolio-service-hpa -n "$NAMESPACE" -o jsonpath='{.status.conditions[?(@.type=="AbleToScale")].status}')
        
        if [[ "$hpa_status" == "True" ]]; then
            log_success "HPA is configured and able to scale"
            
            # Show HPA status
            kubectl get hpa globeco-portfolio-service-hpa -n "$NAMESPACE"
        else
            log_warning "HPA is configured but may not be ready to scale yet"
            kubectl describe hpa globeco-portfolio-service-hpa -n "$NAMESPACE"
        fi
    else
        log_warning "HPA not found - this may be expected for some environments"
    fi
}

# Function to show deployment summary
show_deployment_summary() {
    log "Deployment Summary"
    echo "=================="
    echo "Environment: $ENVIRONMENT"
    echo "Namespace: $NAMESPACE"
    echo "Image Tag: $IMAGE_TAG"
    echo ""
    
    log "Pod Status:"
    kubectl get pods -n "$NAMESPACE" -l app=globeco-portfolio-service -o wide
    
    echo ""
    log "Service Status:"
    kubectl get service globeco-portfolio-service -n "$NAMESPACE"
    
    echo ""
    log "HPA Status:"
    kubectl get hpa -n "$NAMESPACE" 2>/dev/null || echo "No HPA configured"
    
    echo ""
    log_success "Deployment completed successfully!"
}

# Main execution
main() {
    log "Starting deployment with health validation"
    log "Environment: $ENVIRONMENT"
    log "Namespace: $NAMESPACE"
    log "Image Tag: $IMAGE_TAG"
    
    # Pre-deployment validation
    check_kubectl
    validate_environment
    ensure_namespace
    validate_resources
    
    # Deploy application
    deploy_application
    wait_for_rollout
    
    # Post-deployment validation
    local endpoint
    endpoint=$(get_service_endpoint)
    
    local port_forward_pid=""
    if [[ "$endpoint" == "http://localhost:8000" ]]; then
        port_forward_pid=$(setup_port_forward "$endpoint")
    fi
    
    validate_health_endpoints "$endpoint" "$port_forward_pid"
    validate_hpa
    
    # Show summary
    show_deployment_summary
}

# Handle script interruption
trap 'log_error "Deployment interrupted"; exit 1' INT TERM

# Run main function
main "$@"