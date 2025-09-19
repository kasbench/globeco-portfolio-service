#!/bin/bash

# Optimized deployment script for Portfolio Service v2.0.0
# Supports environment-specific deployments with validation and health checks

set -euo pipefail

# Script configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
DEPLOYMENT_TIMEOUT=300  # 5 minutes
HEALTH_CHECK_TIMEOUT=120  # 2 minutes

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Logging functions
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Usage function
usage() {
    cat << EOF
Usage: $0 [OPTIONS] ENVIRONMENT

Deploy Portfolio Service v2.0.0 to Kubernetes with optimized configuration.

ENVIRONMENT:
    development     Deploy to development environment
    staging         Deploy to staging environment  
    production      Deploy to production environment

OPTIONS:
    -h, --help              Show this help message
    -n, --namespace NAME    Override namespace (default: environment-specific)
    -i, --image TAG         Override image tag (default: environment-specific)
    -d, --dry-run           Perform dry-run without applying changes
    -v, --validate          Validate configuration without deploying
    -w, --wait              Wait for deployment to be ready (default: true)
    --skip-health-check     Skip health check validation
    --timeout SECONDS       Deployment timeout in seconds (default: 300)

Examples:
    $0 development                    # Deploy to development
    $0 staging --dry-run              # Dry-run staging deployment
    $0 production --validate          # Validate production config
    $0 production -i v2.0.1           # Deploy production with specific image

EOF
}

# Parse command line arguments
ENVIRONMENT=""
NAMESPACE=""
IMAGE_TAG=""
DRY_RUN=false
VALIDATE_ONLY=false
WAIT_FOR_READY=true
SKIP_HEALTH_CHECK=false

while [[ $# -gt 0 ]]; do
    case $1 in
        -h|--help)
            usage
            exit 0
            ;;
        -n|--namespace)
            NAMESPACE="$2"
            shift 2
            ;;
        -i|--image)
            IMAGE_TAG="$2"
            shift 2
            ;;
        -d|--dry-run)
            DRY_RUN=true
            shift
            ;;
        -v|--validate)
            VALIDATE_ONLY=true
            shift
            ;;
        -w|--wait)
            WAIT_FOR_READY=true
            shift
            ;;
        --skip-health-check)
            SKIP_HEALTH_CHECK=true
            shift
            ;;
        --timeout)
            DEPLOYMENT_TIMEOUT="$2"
            shift 2
            ;;
        development|staging|production)
            ENVIRONMENT="$1"
            shift
            ;;
        *)
            log_error "Unknown option: $1"
            usage
            exit 1
            ;;
    esac
done

# Validate required arguments
if [[ -z "$ENVIRONMENT" ]]; then
    log_error "Environment is required"
    usage
    exit 1
fi

# Validate environment
case "$ENVIRONMENT" in
    development|staging|production)
        ;;
    *)
        log_error "Invalid environment: $ENVIRONMENT"
        log_error "Valid environments: development, staging, production"
        exit 1
        ;;
esac

# Set environment-specific defaults
case "$ENVIRONMENT" in
    development)
        NAMESPACE="${NAMESPACE:-globeco-dev}"
        IMAGE_TAG="${IMAGE_TAG:-development}"
        ;;
    staging)
        NAMESPACE="${NAMESPACE:-globeco-staging}"
        IMAGE_TAG="${IMAGE_TAG:-staging}"
        ;;
    production)
        NAMESPACE="${NAMESPACE:-globeco}"
        IMAGE_TAG="${IMAGE_TAG:-v2.0.0}"
        ;;
esac

# Validate prerequisites
check_prerequisites() {
    log_info "Checking prerequisites..."
    
    # Check kubectl
    if ! command -v kubectl &> /dev/null; then
        log_error "kubectl is required but not installed"
        exit 1
    fi
    
    # Check kustomize
    if ! command -v kustomize &> /dev/null; then
        log_error "kustomize is required but not installed"
        exit 1
    fi
    
    # Check cluster connectivity
    if ! kubectl cluster-info &> /dev/null; then
        log_error "Cannot connect to Kubernetes cluster"
        exit 1
    fi
    
    # Check if overlay directory exists
    OVERLAY_DIR="$SCRIPT_DIR/overlays/$ENVIRONMENT"
    if [[ ! -d "$OVERLAY_DIR" ]]; then
        log_error "Overlay directory not found: $OVERLAY_DIR"
        exit 1
    fi
    
    log_success "Prerequisites check passed"
}

# Validate configuration
validate_configuration() {
    log_info "Validating configuration for $ENVIRONMENT environment..."
    
    cd "$OVERLAY_DIR"
    
    # Validate kustomization
    if ! kustomize build . > /dev/null; then
        log_error "Kustomization validation failed"
        exit 1
    fi
    
    # Check resource limits
    local resources
    resources=$(kustomize build . | grep -A 10 "resources:" | grep -E "(cpu|memory):" || true)
    
    if [[ "$ENVIRONMENT" == "production" ]]; then
        # Validate production resource limits match requirements
        if ! echo "$resources" | grep -q "100m"; then
            log_warning "Production CPU request should be 100m"
        fi
        if ! echo "$resources" | grep -q "128Mi"; then
            log_warning "Production memory request should be 128Mi"
        fi
    fi
    
    log_success "Configuration validation passed"
}

# Create namespace if it doesn't exist
ensure_namespace() {
    log_info "Ensuring namespace '$NAMESPACE' exists..."
    
    if ! kubectl get namespace "$NAMESPACE" &> /dev/null; then
        log_info "Creating namespace '$NAMESPACE'..."
        kubectl create namespace "$NAMESPACE"
        
        # Add environment label
        kubectl label namespace "$NAMESPACE" environment="$ENVIRONMENT" --overwrite
        
        log_success "Namespace '$NAMESPACE' created"
    else
        log_info "Namespace '$NAMESPACE' already exists"
    fi
}

# Deploy application
deploy_application() {
    log_info "Deploying Portfolio Service v2.0.0 to $ENVIRONMENT environment..."
    
    cd "$OVERLAY_DIR"
    
    # Build and apply configuration
    local kubectl_args=()
    
    if [[ "$DRY_RUN" == "true" ]]; then
        kubectl_args+=(--dry-run=client)
        log_info "Performing dry-run deployment..."
    fi
    
    # Apply the configuration
    kustomize build . | kubectl apply "${kubectl_args[@]}" -f -
    
    if [[ "$DRY_RUN" == "true" ]]; then
        log_success "Dry-run deployment completed successfully"
        return 0
    fi
    
    log_success "Application deployed successfully"
}

# Wait for deployment to be ready
wait_for_deployment() {
    if [[ "$WAIT_FOR_READY" != "true" ]] || [[ "$DRY_RUN" == "true" ]]; then
        return 0
    fi
    
    log_info "Waiting for deployment to be ready (timeout: ${DEPLOYMENT_TIMEOUT}s)..."
    
    local deployment_name
    case "$ENVIRONMENT" in
        development)
            deployment_name="dev-globeco-portfolio-service"
            ;;
        staging)
            deployment_name="staging-globeco-portfolio-service"
            ;;
        production)
            deployment_name="globeco-portfolio-service"
            ;;
    esac
    
    if kubectl rollout status deployment/"$deployment_name" -n "$NAMESPACE" --timeout="${DEPLOYMENT_TIMEOUT}s"; then
        log_success "Deployment is ready"
    else
        log_error "Deployment failed to become ready within ${DEPLOYMENT_TIMEOUT}s"
        
        # Show pod status for debugging
        log_info "Pod status:"
        kubectl get pods -n "$NAMESPACE" -l app=globeco-portfolio-service
        
        # Show recent events
        log_info "Recent events:"
        kubectl get events -n "$NAMESPACE" --sort-by='.lastTimestamp' | tail -10
        
        exit 1
    fi
}

# Perform health checks
perform_health_checks() {
    if [[ "$SKIP_HEALTH_CHECK" == "true" ]] || [[ "$DRY_RUN" == "true" ]]; then
        return 0
    fi
    
    log_info "Performing health checks..."
    
    # Get service endpoint
    local service_name
    case "$ENVIRONMENT" in
        development)
            service_name="dev-globeco-portfolio-service"
            ;;
        staging)
            service_name="staging-globeco-portfolio-service"
            ;;
        production)
            service_name="globeco-portfolio-service"
            ;;
    esac
    
    # Port forward for health check
    log_info "Setting up port forward for health check..."
    kubectl port-forward -n "$NAMESPACE" "service/$service_name" 8080:8000 &
    local port_forward_pid=$!
    
    # Wait for port forward to be ready
    sleep 5
    
    # Cleanup function
    cleanup_port_forward() {
        if [[ -n "${port_forward_pid:-}" ]]; then
            kill "$port_forward_pid" 2>/dev/null || true
        fi
    }
    trap cleanup_port_forward EXIT
    
    # Health check endpoints
    local endpoints=("/health/live" "/health/ready" "/health/startup")
    local health_check_failed=false
    
    for endpoint in "${endpoints[@]}"; do
        log_info "Checking health endpoint: $endpoint"
        
        local attempts=0
        local max_attempts=12  # 2 minutes with 10s intervals
        
        while [[ $attempts -lt $max_attempts ]]; do
            if curl -sf "http://localhost:8080$endpoint" > /dev/null 2>&1; then
                log_success "Health check passed: $endpoint"
                break
            fi
            
            attempts=$((attempts + 1))
            if [[ $attempts -eq $max_attempts ]]; then
                log_error "Health check failed: $endpoint"
                health_check_failed=true
                break
            fi
            
            log_info "Health check attempt $attempts/$max_attempts failed, retrying in 10s..."
            sleep 10
        done
    done
    
    # Cleanup port forward
    cleanup_port_forward
    trap - EXIT
    
    if [[ "$health_check_failed" == "true" ]]; then
        log_error "Health checks failed"
        exit 1
    fi
    
    log_success "All health checks passed"
}

# Show deployment status
show_deployment_status() {
    if [[ "$DRY_RUN" == "true" ]]; then
        return 0
    fi
    
    log_info "Deployment status for $ENVIRONMENT environment:"
    echo
    
    # Show deployment status
    kubectl get deployments -n "$NAMESPACE" -l app=globeco-portfolio-service
    echo
    
    # Show pod status
    kubectl get pods -n "$NAMESPACE" -l app=globeco-portfolio-service
    echo
    
    # Show HPA status
    kubectl get hpa -n "$NAMESPACE" -l app=globeco-portfolio-service
    echo
    
    # Show service status
    kubectl get services -n "$NAMESPACE" -l app=globeco-portfolio-service
    echo
}

# Main execution
main() {
    log_info "Starting Portfolio Service v2.0.0 deployment"
    log_info "Environment: $ENVIRONMENT"
    log_info "Namespace: $NAMESPACE"
    log_info "Image Tag: $IMAGE_TAG"
    log_info "Dry Run: $DRY_RUN"
    log_info "Validate Only: $VALIDATE_ONLY"
    echo
    
    # Execute deployment steps
    check_prerequisites
    validate_configuration
    
    if [[ "$VALIDATE_ONLY" == "true" ]]; then
        log_success "Configuration validation completed successfully"
        exit 0
    fi
    
    ensure_namespace
    deploy_application
    wait_for_deployment
    perform_health_checks
    show_deployment_status
    
    log_success "Portfolio Service v2.0.0 deployment completed successfully!"
    log_info "Environment: $ENVIRONMENT"
    log_info "Namespace: $NAMESPACE"
    log_info "Image: kasbench/globeco-portfolio-service:$IMAGE_TAG"
}

# Execute main function
main "$@"