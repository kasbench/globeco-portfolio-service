#!/bin/bash

# Deploy monitoring and alerting for Portfolio Service v2.0.0
# Sets up OpenTelemetry collector, Prometheus rules, and Grafana dashboards

set -euo pipefail

# Script configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
NAMESPACE="globeco"

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
Usage: $0 [OPTIONS]

Deploy monitoring and alerting for Portfolio Service v2.0.0.

OPTIONS:
    -h, --help              Show this help message
    -n, --namespace NAME    Override namespace (default: globeco)
    -d, --dry-run           Perform dry-run without applying changes
    --skip-collector        Skip OpenTelemetry collector deployment
    --skip-rules            Skip Prometheus rules deployment
    --skip-dashboard        Skip Grafana dashboard deployment
    --skip-alerting         Skip Alertmanager configuration

Examples:
    $0                      # Deploy all monitoring components
    $0 --dry-run            # Show what would be deployed
    $0 --skip-collector     # Deploy everything except collector

EOF
}

# Parse command line arguments
DRY_RUN=false
SKIP_COLLECTOR=false
SKIP_RULES=false
SKIP_DASHBOARD=false
SKIP_ALERTING=false

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
        -d|--dry-run)
            DRY_RUN=true
            shift
            ;;
        --skip-collector)
            SKIP_COLLECTOR=true
            shift
            ;;
        --skip-rules)
            SKIP_RULES=true
            shift
            ;;
        --skip-dashboard)
            SKIP_DASHBOARD=true
            shift
            ;;
        --skip-alerting)
            SKIP_ALERTING=true
            shift
            ;;
        *)
            log_error "Unknown option: $1"
            usage
            exit 1
            ;;
    esac
done

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
    
    # Check if namespace exists
    if ! kubectl get namespace "$NAMESPACE" &> /dev/null; then
        log_error "Namespace '$NAMESPACE' does not exist"
        exit 1
    fi
    
    log_success "Prerequisites check passed"
}

# Deploy OpenTelemetry collector
deploy_otel_collector() {
    if [[ "$SKIP_COLLECTOR" == "true" ]]; then
        log_info "Skipping OpenTelemetry collector deployment"
        return 0
    fi
    
    log_info "Deploying OpenTelemetry collector..."
    
    local kubectl_args=()
    if [[ "$DRY_RUN" == "true" ]]; then
        kubectl_args+=(--dry-run=client)
    fi
    
    kubectl apply "${kubectl_args[@]}" -f "$SCRIPT_DIR/otel-collector-config.yaml"
    
    if [[ "$DRY_RUN" != "true" ]]; then
        # Wait for collector to be ready
        log_info "Waiting for OpenTelemetry collector to be ready..."
        kubectl rollout status daemonset/otel-collector -n "$NAMESPACE" --timeout=120s
        
        # Verify collector health
        log_info "Verifying collector health..."
        if kubectl get pods -n "$NAMESPACE" -l app=otel-collector | grep -q "Running"; then
            log_success "OpenTelemetry collector deployed and running"
        else
            log_warning "OpenTelemetry collector may not be fully ready"
        fi
    else
        log_info "Dry-run: OpenTelemetry collector configuration validated"
    fi
}

# Deploy Prometheus rules
deploy_prometheus_rules() {
    if [[ "$SKIP_RULES" == "true" ]]; then
        log_info "Skipping Prometheus rules deployment"
        return 0
    fi
    
    log_info "Deploying Prometheus rules..."
    
    local kubectl_args=()
    if [[ "$DRY_RUN" == "true" ]]; then
        kubectl_args+=(--dry-run=client)
    fi
    
    kubectl apply "${kubectl_args[@]}" -f "$SCRIPT_DIR/prometheus-rules.yaml"
    
    if [[ "$DRY_RUN" != "true" ]]; then
        # Verify rules are loaded
        if kubectl get prometheusrules -n "$NAMESPACE" globeco-portfolio-service-alerts &> /dev/null; then
            log_success "Prometheus rules deployed successfully"
        else
            log_warning "Prometheus rules may not be loaded correctly"
        fi
    else
        log_info "Dry-run: Prometheus rules configuration validated"
    fi
}

# Deploy ServiceMonitor
deploy_service_monitor() {
    log_info "Deploying ServiceMonitor..."
    
    local kubectl_args=()
    if [[ "$DRY_RUN" == "true" ]]; then
        kubectl_args+=(--dry-run=client)
    fi
    
    kubectl apply "${kubectl_args[@]}" -f "$SCRIPT_DIR/servicemonitor.yaml"
    
    if [[ "$DRY_RUN" != "true" ]]; then
        log_success "ServiceMonitor deployed successfully"
    else
        log_info "Dry-run: ServiceMonitor configuration validated"
    fi
}

# Deploy Alertmanager configuration
deploy_alertmanager_config() {
    if [[ "$SKIP_ALERTING" == "true" ]]; then
        log_info "Skipping Alertmanager configuration deployment"
        return 0
    fi
    
    log_info "Deploying Alertmanager configuration..."
    
    local kubectl_args=()
    if [[ "$DRY_RUN" == "true" ]]; then
        kubectl_args+=(--dry-run=client)
    fi
    
    kubectl apply "${kubectl_args[@]}" -f "$SCRIPT_DIR/alertmanager-config.yaml"
    
    if [[ "$DRY_RUN" != "true" ]]; then
        log_success "Alertmanager configuration deployed successfully"
        log_warning "Remember to update SMTP and Slack credentials in the secret"
    else
        log_info "Dry-run: Alertmanager configuration validated"
    fi
}

# Deploy Grafana dashboard
deploy_grafana_dashboard() {
    if [[ "$SKIP_DASHBOARD" == "true" ]]; then
        log_info "Skipping Grafana dashboard deployment"
        return 0
    fi
    
    log_info "Deploying Grafana dashboard..."
    
    # Create ConfigMap for Grafana dashboard
    local kubectl_args=()
    if [[ "$DRY_RUN" == "true" ]]; then
        kubectl_args+=(--dry-run=client)
    fi
    
    kubectl create configmap portfolio-service-dashboard \
        --from-file="$SCRIPT_DIR/grafana-dashboard.json" \
        -n "$NAMESPACE" \
        "${kubectl_args[@]}" \
        --dry-run=client -o yaml | kubectl apply "${kubectl_args[@]}" -f -
    
    # Label the ConfigMap for Grafana discovery
    if [[ "$DRY_RUN" != "true" ]]; then
        kubectl label configmap portfolio-service-dashboard \
            -n "$NAMESPACE" \
            grafana_dashboard=1 \
            --overwrite
        
        log_success "Grafana dashboard deployed successfully"
        log_info "Dashboard will be automatically discovered by Grafana"
    else
        log_info "Dry-run: Grafana dashboard configuration validated"
    fi
}

# Verify monitoring setup
verify_monitoring_setup() {
    if [[ "$DRY_RUN" == "true" ]]; then
        return 0
    fi
    
    log_info "Verifying monitoring setup..."
    
    # Check OpenTelemetry collector
    if [[ "$SKIP_COLLECTOR" != "true" ]]; then
        local collector_pods
        collector_pods=$(kubectl get pods -n "$NAMESPACE" -l app=otel-collector --no-headers | wc -l)
        if [[ "$collector_pods" -gt 0 ]]; then
            log_success "OpenTelemetry collector: $collector_pods pod(s) running"
        else
            log_error "OpenTelemetry collector: No pods running"
        fi
    fi
    
    # Check Prometheus rules
    if [[ "$SKIP_RULES" != "true" ]]; then
        if kubectl get prometheusrules -n "$NAMESPACE" globeco-portfolio-service-alerts &> /dev/null; then
            local rules_count
            rules_count=$(kubectl get prometheusrules -n "$NAMESPACE" globeco-portfolio-service-alerts -o jsonpath='{.spec.groups[*].rules[*].alert}' | wc -w)
            log_success "Prometheus rules: $rules_count alert rules configured"
        else
            log_error "Prometheus rules: Not found"
        fi
    fi
    
    # Check ServiceMonitor
    if kubectl get servicemonitor -n "$NAMESPACE" globeco-portfolio-service &> /dev/null; then
        log_success "ServiceMonitor: Configured"
    else
        log_error "ServiceMonitor: Not found"
    fi
    
    # Check Alertmanager config
    if [[ "$SKIP_ALERTING" != "true" ]]; then
        if kubectl get configmap -n "$NAMESPACE" portfolio-service-alertmanager-config &> /dev/null; then
            log_success "Alertmanager configuration: Deployed"
        else
            log_error "Alertmanager configuration: Not found"
        fi
    fi
    
    # Check Grafana dashboard
    if [[ "$SKIP_DASHBOARD" != "true" ]]; then
        if kubectl get configmap -n "$NAMESPACE" portfolio-service-dashboard &> /dev/null; then
            log_success "Grafana dashboard: Deployed"
        else
            log_error "Grafana dashboard: Not found"
        fi
    fi
}

# Show monitoring status
show_monitoring_status() {
    if [[ "$DRY_RUN" == "true" ]]; then
        return 0
    fi
    
    log_info "Monitoring setup status:"
    echo
    
    # OpenTelemetry collector status
    if [[ "$SKIP_COLLECTOR" != "true" ]]; then
        log_info "OpenTelemetry Collector:"
        kubectl get daemonset otel-collector -n "$NAMESPACE" 2>/dev/null || echo "  Not deployed"
        kubectl get pods -n "$NAMESPACE" -l app=otel-collector 2>/dev/null || echo "  No pods"
        echo
    fi
    
    # Prometheus rules status
    if [[ "$SKIP_RULES" != "true" ]]; then
        log_info "Prometheus Rules:"
        kubectl get prometheusrules -n "$NAMESPACE" 2>/dev/null || echo "  Not deployed"
        echo
    fi
    
    # ServiceMonitor status
    log_info "ServiceMonitor:"
    kubectl get servicemonitor -n "$NAMESPACE" 2>/dev/null || echo "  Not deployed"
    echo
    
    # ConfigMaps status
    log_info "Configuration:"
    kubectl get configmap -n "$NAMESPACE" -l app=globeco-portfolio-service 2>/dev/null || echo "  No monitoring configs"
    echo
}

# Main execution
main() {
    log_info "Starting Portfolio Service v2.0.0 monitoring deployment"
    log_info "Namespace: $NAMESPACE"
    log_info "Dry Run: $DRY_RUN"
    echo
    
    # Execute deployment steps
    check_prerequisites
    deploy_otel_collector
    deploy_prometheus_rules
    deploy_service_monitor
    deploy_alertmanager_config
    deploy_grafana_dashboard
    verify_monitoring_setup
    show_monitoring_status
    
    log_success "Portfolio Service monitoring deployment completed!"
    
    if [[ "$DRY_RUN" != "true" ]]; then
        echo
        log_info "Next steps:"
        log_info "1. Update Alertmanager SMTP and Slack credentials"
        log_info "2. Import Grafana dashboard from ConfigMap"
        log_info "3. Verify alerts are firing correctly"
        log_info "4. Test notification channels"
    fi
}

# Execute main function
main "$@"