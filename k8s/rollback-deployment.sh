#!/bin/bash

# Rollback script for Portfolio Service deployments
# Provides safe rollback functionality with validation

set -euo pipefail

# Script configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROLLBACK_TIMEOUT=300  # 5 minutes

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
Usage: $0 [OPTIONS] ENVIRONMENT [REVISION]

Rollback Portfolio Service deployment to previous or specific revision.

ENVIRONMENT:
    development     Rollback development environment
    staging         Rollback staging environment  
    production      Rollback production environment

REVISION:
    Optional revision number to rollback to (default: previous revision)

OPTIONS:
    -h, --help              Show this help message
    -n, --namespace NAME    Override namespace (default: environment-specific)
    -l, --list              List deployment history
    --dry-run               Show what would be rolled back without executing
    --timeout SECONDS       Rollback timeout in seconds (default: 300)

Examples:
    $0 production                     # Rollback to previous revision
    $0 staging 5                      # Rollback to revision 5
    $0 development --list             # Show deployment history
    $0 production --dry-run           # Show rollback plan

EOF
}

# Parse command line arguments
ENVIRONMENT=""
REVISION=""
NAMESPACE=""
LIST_HISTORY=false
DRY_RUN=false

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
        -l|--list)
            LIST_HISTORY=true
            shift
            ;;
        --dry-run)
            DRY_RUN=true
            shift
            ;;
        --timeout)
            ROLLBACK_TIMEOUT="$2"
            shift 2
            ;;
        development|staging|production)
            ENVIRONMENT="$1"
            shift
            ;;
        [0-9]*)
            REVISION="$1"
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

# Set environment-specific defaults
case "$ENVIRONMENT" in
    development)
        NAMESPACE="${NAMESPACE:-globeco-dev}"
        DEPLOYMENT_NAME="dev-globeco-portfolio-service"
        ;;
    staging)
        NAMESPACE="${NAMESPACE:-globeco-staging}"
        DEPLOYMENT_NAME="staging-globeco-portfolio-service"
        ;;
    production)
        NAMESPACE="${NAMESPACE:-globeco}"
        DEPLOYMENT_NAME="globeco-portfolio-service"
        ;;
    *)
        log_error "Invalid environment: $ENVIRONMENT"
        exit 1
        ;;
esac

# Check prerequisites
check_prerequisites() {
    log_info "Checking prerequisites..."
    
    # Check kubectl
    if ! command -v kubectl &> /dev/null; then
        log_error "kubectl is required but not installed"
        exit 1
    fi
    
    # Check cluster connectivity
    if ! kubectl cluster-info &> /dev/null; then
        log_error "Cannot connect to Kubernetes cluster"
        exit 1
    fi
    
    # Check if deployment exists
    if ! kubectl get deployment "$DEPLOYMENT_NAME" -n "$NAMESPACE" &> /dev/null; then
        log_error "Deployment '$DEPLOYMENT_NAME' not found in namespace '$NAMESPACE'"
        exit 1
    fi
    
    log_success "Prerequisites check passed"
}

# List deployment history
list_deployment_history() {
    log_info "Deployment history for $DEPLOYMENT_NAME in $NAMESPACE:"
    echo
    
    kubectl rollout history deployment/"$DEPLOYMENT_NAME" -n "$NAMESPACE"
    echo
    
    # Show current status
    log_info "Current deployment status:"
    kubectl get deployment "$DEPLOYMENT_NAME" -n "$NAMESPACE"
    echo
}

# Get current revision
get_current_revision() {
    kubectl get deployment "$DEPLOYMENT_NAME" -n "$NAMESPACE" -o jsonpath='{.metadata.annotations.deployment\.kubernetes\.io/revision}'
}

# Validate rollback target
validate_rollback_target() {
    local current_revision
    current_revision=$(get_current_revision)
    
    log_info "Current revision: $current_revision"
    
    if [[ -n "$REVISION" ]]; then
        log_info "Target revision: $REVISION"
        
        # Check if target revision exists
        if ! kubectl rollout history deployment/"$DEPLOYMENT_NAME" -n "$NAMESPACE" --revision="$REVISION" &> /dev/null; then
            log_error "Revision $REVISION not found in deployment history"
            exit 1
        fi
        
        # Check if target revision is the same as current
        if [[ "$REVISION" == "$current_revision" ]]; then
            log_warning "Target revision $REVISION is the same as current revision"
            read -p "Continue anyway? (y/N): " -n 1 -r
            echo
            if [[ ! $REPLY =~ ^[Yy]$ ]]; then
                log_info "Rollback cancelled"
                exit 0
            fi
        fi
    else
        log_info "Target: Previous revision"
        
        # Check if there's a previous revision
        local history_count
        history_count=$(kubectl rollout history deployment/"$DEPLOYMENT_NAME" -n "$NAMESPACE" | grep -c "^[0-9]" || echo "0")
        
        if [[ "$history_count" -lt 2 ]]; then
            log_error "No previous revision available for rollback"
            exit 1
        fi
    fi
}

# Perform rollback
perform_rollback() {
    log_info "Starting rollback for $DEPLOYMENT_NAME in $NAMESPACE..."
    
    # Build rollback command
    local rollback_cmd="kubectl rollout undo deployment/$DEPLOYMENT_NAME -n $NAMESPACE"
    
    if [[ -n "$REVISION" ]]; then
        rollback_cmd="$rollback_cmd --to-revision=$REVISION"
    fi
    
    if [[ "$DRY_RUN" == "true" ]]; then
        log_info "Dry-run mode: Would execute: $rollback_cmd"
        return 0
    fi
    
    # Execute rollback
    if eval "$rollback_cmd"; then
        log_success "Rollback initiated successfully"
    else
        log_error "Rollback initiation failed"
        exit 1
    fi
}

# Wait for rollback to complete
wait_for_rollback() {
    if [[ "$DRY_RUN" == "true" ]]; then
        return 0
    fi
    
    log_info "Waiting for rollback to complete (timeout: ${ROLLBACK_TIMEOUT}s)..."
    
    if kubectl rollout status deployment/"$DEPLOYMENT_NAME" -n "$NAMESPACE" --timeout="${ROLLBACK_TIMEOUT}s"; then
        log_success "Rollback completed successfully"
    else
        log_error "Rollback failed to complete within ${ROLLBACK_TIMEOUT}s"
        
        # Show pod status for debugging
        log_info "Pod status:"
        kubectl get pods -n "$NAMESPACE" -l app=globeco-portfolio-service
        
        # Show recent events
        log_info "Recent events:"
        kubectl get events -n "$NAMESPACE" --sort-by='.lastTimestamp' | tail -10
        
        exit 1
    fi
}

# Verify rollback
verify_rollback() {
    if [[ "$DRY_RUN" == "true" ]]; then
        return 0
    fi
    
    log_info "Verifying rollback..."
    
    # Check deployment status
    local ready_replicas
    ready_replicas=$(kubectl get deployment "$DEPLOYMENT_NAME" -n "$NAMESPACE" -o jsonpath='{.status.readyReplicas}')
    local desired_replicas
    desired_replicas=$(kubectl get deployment "$DEPLOYMENT_NAME" -n "$NAMESPACE" -o jsonpath='{.spec.replicas}')
    
    if [[ "$ready_replicas" == "$desired_replicas" ]]; then
        log_success "All replicas are ready ($ready_replicas/$desired_replicas)"
    else
        log_warning "Not all replicas are ready ($ready_replicas/$desired_replicas)"
    fi
    
    # Basic health check
    log_info "Performing basic health check..."
    
    # Port forward for health check
    kubectl port-forward -n "$NAMESPACE" "deployment/$DEPLOYMENT_NAME" 8080:8000 &
    local port_forward_pid=$!
    
    # Cleanup function
    cleanup_port_forward() {
        if [[ -n "${port_forward_pid:-}" ]]; then
            kill "$port_forward_pid" 2>/dev/null || true
        fi
    }
    trap cleanup_port_forward EXIT
    
    # Wait for port forward
    sleep 5
    
    # Check health endpoint
    if curl -sf "http://localhost:8080/health" > /dev/null 2>&1; then
        log_success "Health check passed"
    else
        log_warning "Health check failed - service may still be starting"
    fi
    
    # Cleanup
    cleanup_port_forward
    trap - EXIT
}

# Show rollback status
show_rollback_status() {
    if [[ "$DRY_RUN" == "true" ]]; then
        return 0
    fi
    
    log_info "Rollback status for $ENVIRONMENT environment:"
    echo
    
    # Show deployment status
    kubectl get deployment "$DEPLOYMENT_NAME" -n "$NAMESPACE"
    echo
    
    # Show current revision
    local new_revision
    new_revision=$(get_current_revision)
    log_info "New revision: $new_revision"
    echo
    
    # Show pod status
    kubectl get pods -n "$NAMESPACE" -l app=globeco-portfolio-service
    echo
}

# Confirm production rollback
confirm_production_rollback() {
    if [[ "$ENVIRONMENT" == "production" ]] && [[ "$DRY_RUN" != "true" ]]; then
        log_warning "You are about to rollback the PRODUCTION environment!"
        log_warning "This will affect live traffic and users."
        echo
        
        read -p "Are you sure you want to proceed? Type 'yes' to continue: " -r
        echo
        
        if [[ "$REPLY" != "yes" ]]; then
            log_info "Rollback cancelled"
            exit 0
        fi
        
        log_info "Production rollback confirmed"
    fi
}

# Main execution
main() {
    log_info "Starting Portfolio Service rollback"
    log_info "Environment: $ENVIRONMENT"
    log_info "Namespace: $NAMESPACE"
    log_info "Deployment: $DEPLOYMENT_NAME"
    if [[ -n "$REVISION" ]]; then
        log_info "Target Revision: $REVISION"
    else
        log_info "Target: Previous revision"
    fi
    log_info "Dry Run: $DRY_RUN"
    echo
    
    # Execute rollback steps
    check_prerequisites
    
    if [[ "$LIST_HISTORY" == "true" ]]; then
        list_deployment_history
        exit 0
    fi
    
    validate_rollback_target
    confirm_production_rollback
    perform_rollback
    wait_for_rollback
    verify_rollback
    show_rollback_status
    
    log_success "Portfolio Service rollback completed successfully!"
    log_info "Environment: $ENVIRONMENT"
    log_info "Deployment: $DEPLOYMENT_NAME"
}

# Execute main function
main "$@"