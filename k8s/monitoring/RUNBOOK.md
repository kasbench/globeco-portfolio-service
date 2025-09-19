# Portfolio Service v2.0.0 Operations Runbook

## Overview

This runbook provides operational procedures for the Portfolio Service v2.0.0, including troubleshooting, monitoring, and incident response.

## Service Architecture

- **Service**: GlobeCo Portfolio Service v2.0.0
- **Technology**: FastAPI + MongoDB + OpenTelemetry
- **Monitoring**: OpenTelemetry OTLP → Prometheus → Grafana + Alertmanager
- **Key Features**: Environment-based configuration, circuit breakers, validation caching

## Performance Targets

| Metric | Target | Alert Threshold |
|--------|--------|----------------|
| Bulk operations (10 portfolios) | <200ms | >200ms |
| Individual operations | <50ms | >50ms |
| Health checks | <10ms | >10ms |
| Memory usage per pod | <256MB | >90% of limit |
| CPU usage per pod | <200m | >90% of limit |
| Error rate | <1% | >5% |

## Alert Response Procedures

### Critical Alerts

#### PortfolioServiceHealthCheckFailing

**Severity**: Critical  
**Description**: Health check endpoints are failing

**Immediate Actions**:
1. Check pod status: `kubectl get pods -n globeco -l app=globeco-portfolio-service`
2. Check recent events: `kubectl get events -n globeco --sort-by='.lastTimestamp' | tail -20`
3. Check pod logs: `kubectl logs -n globeco -l app=globeco-portfolio-service --tail=100`

**Investigation Steps**:
1. Verify database connectivity
2. Check resource utilization
3. Review application logs for errors
4. Verify OpenTelemetry collector connectivity

**Resolution**:
- If pods are not running: Check deployment status and resource limits
- If database issues: Verify MongoDB connectivity and credentials
- If resource issues: Scale up or investigate memory/CPU usage
- If persistent: Consider rollback to previous version

#### PortfolioServiceHighErrorRate

**Severity**: Critical  
**Description**: Error rate >5% over 5 minutes

**Immediate Actions**:
1. Check error distribution: Review Grafana dashboard for error patterns
2. Check recent deployments: `kubectl rollout history deployment/globeco-portfolio-service -n globeco`
3. Review application logs for error details

**Investigation Steps**:
1. Identify error types (4xx vs 5xx)
2. Check database connection pool status
3. Verify circuit breaker states
4. Review recent configuration changes

**Resolution**:
- If deployment-related: Consider rollback
- If database-related: Check connection pool and database health
- If circuit breaker open: Investigate downstream dependencies
- If validation errors: Check input validation logic

#### PortfolioServiceLowAvailability

**Severity**: Critical  
**Description**: <80% of pods available

**Immediate Actions**:
1. Check pod status and ready state
2. Review HPA status: `kubectl get hpa -n globeco`
3. Check node resources and scheduling

**Investigation Steps**:
1. Verify resource requests vs limits
2. Check node capacity and scheduling constraints
3. Review pod disruption budget
4. Check for node issues or taints

**Resolution**:
- Scale up manually if needed
- Address node capacity issues
- Review resource allocation
- Check for anti-affinity conflicts

### Performance Alerts

#### PortfolioServiceBulkPerformanceRegression

**Severity**: Warning  
**Description**: Bulk operations >200ms (P95)

**Investigation Steps**:
1. Check database performance metrics
2. Review connection pool utilization
3. Verify validation cache hit rates
4. Check for resource constraints

**Resolution**:
- Optimize database queries if needed
- Increase connection pool size
- Review validation cache configuration
- Scale up if resource-constrained

#### PortfolioServiceSingleOperationSlow

**Severity**: Warning  
**Description**: Individual operations >50ms (P95)

**Investigation Steps**:
1. Identify slow endpoints from metrics
2. Check database query performance
3. Review middleware overhead
4. Verify caching effectiveness

**Resolution**:
- Optimize slow database operations
- Review middleware configuration
- Increase cache sizes if beneficial
- Consider query optimization

### Resource Alerts

#### PortfolioServiceHighMemoryUsage

**Severity**: Warning  
**Description**: Memory usage >90% of limit

**Investigation Steps**:
1. Check memory usage patterns over time
2. Review cache sizes and configurations
3. Look for memory leaks in application logs
4. Verify garbage collection metrics

**Resolution**:
- Increase memory limits if justified
- Optimize cache configurations
- Investigate potential memory leaks
- Consider horizontal scaling

#### PortfolioServiceHighCPUUsage

**Severity**: Warning  
**Description**: CPU usage >90% of limit

**Investigation Steps**:
1. Check CPU usage patterns and spikes
2. Review request rate and processing time
3. Identify CPU-intensive operations
4. Check for inefficient algorithms

**Resolution**:
- Increase CPU limits if needed
- Optimize CPU-intensive operations
- Scale horizontally to distribute load
- Review algorithm efficiency

## Troubleshooting Procedures

### Database Issues

**Symptoms**: Connection errors, slow queries, timeouts

**Diagnosis**:
```bash
# Check database connectivity
kubectl exec -it deployment/globeco-portfolio-service -n globeco -- python -c "
from motor.motor_asyncio import AsyncIOMotorClient
import asyncio
async def test():
    client = AsyncIOMotorClient('mongodb://globeco-portfolio-service-mongodb:27017')
    try:
        await client.admin.command('ping')
        print('Database connection successful')
    except Exception as e:
        print(f'Database connection failed: {e}')
    finally:
        client.close()
asyncio.run(test())
"

# Check connection pool metrics
curl -s http://localhost:8080/health/detailed | jq '.checks.database'
```

**Resolution**:
1. Verify MongoDB service and pods are running
2. Check database credentials and connection string
3. Review connection pool configuration
4. Monitor database performance metrics

### Circuit Breaker Issues

**Symptoms**: Circuit breaker open, degraded service

**Diagnosis**:
```bash
# Check circuit breaker status
curl -s http://localhost:8080/health/detailed | jq '.checks.circuit_breakers'

# Review circuit breaker metrics in Grafana
# Look for circuit_breaker_state metrics
```

**Resolution**:
1. Identify which circuit breaker is open
2. Investigate underlying service health
3. Consider manual circuit breaker reset if appropriate
4. Review circuit breaker thresholds

### Performance Issues

**Symptoms**: Slow response times, high resource usage

**Diagnosis**:
```bash
# Check current performance metrics
curl -s http://localhost:8080/health/metrics

# Review resource usage
kubectl top pods -n globeco -l app=globeco-portfolio-service

# Check HPA status
kubectl get hpa -n globeco globeco-portfolio-service-hpa
```

**Resolution**:
1. Identify performance bottlenecks
2. Review caching effectiveness
3. Consider scaling up or out
4. Optimize slow operations

### OpenTelemetry Issues

**Symptoms**: Missing metrics, traces not appearing

**Diagnosis**:
```bash
# Check OpenTelemetry collector status
kubectl get pods -n globeco -l app=otel-collector
kubectl logs -n globeco -l app=otel-collector

# Verify OTLP endpoint connectivity
kubectl exec -it deployment/globeco-portfolio-service -n globeco -- curl -v http://localhost:4318/v1/metrics
```

**Resolution**:
1. Verify collector is running and healthy
2. Check OTLP endpoint configuration
3. Review collector configuration
4. Verify network connectivity

## Deployment Procedures

### Standard Deployment

```bash
# Deploy to staging
./k8s/deploy-optimized.sh staging

# Verify staging deployment
./k8s/deploy-optimized.sh staging --validate

# Deploy to production (with confirmation)
./k8s/deploy-optimized.sh production
```

### Emergency Rollback

```bash
# List deployment history
./k8s/rollback-deployment.sh production --list

# Rollback to previous version
./k8s/rollback-deployment.sh production

# Rollback to specific revision
./k8s/rollback-deployment.sh production 5
```

### Monitoring Deployment

```bash
# Deploy all monitoring components
./k8s/monitoring/deploy-monitoring.sh

# Deploy specific components
./k8s/monitoring/deploy-monitoring.sh --skip-collector
```

## Maintenance Procedures

### Scaling Operations

```bash
# Manual scaling
kubectl scale deployment globeco-portfolio-service -n globeco --replicas=5

# Update HPA limits
kubectl patch hpa globeco-portfolio-service-hpa -n globeco -p '{"spec":{"maxReplicas":15}}'
```

### Configuration Updates

```bash
# Update environment-specific configuration
kubectl patch deployment globeco-portfolio-service -n globeco -p '{"spec":{"template":{"spec":{"containers":[{"name":"globeco-portfolio-service","env":[{"name":"LOG_LEVEL","value":"INFO"}]}]}}}}'

# Restart deployment to pick up config changes
kubectl rollout restart deployment/globeco-portfolio-service -n globeco
```

### Cache Management

```bash
# Clear validation cache (requires application restart)
kubectl rollout restart deployment/globeco-portfolio-service -n globeco

# Check cache statistics
curl -s http://localhost:8080/health/detailed | jq '.checks.validation_cache'
```

## Monitoring and Observability

### Key Dashboards

1. **Portfolio Service Performance Dashboard**: Overall service health and performance
2. **RED Metrics Dashboard**: Request rate, error rate, duration
3. **Resource Utilization Dashboard**: CPU, memory, database connections
4. **Business Metrics Dashboard**: Portfolio creation rates, validation metrics

### Key Metrics to Monitor

- `http_request_duration_seconds`: Request latency
- `http_requests_total`: Request rate and status codes
- `portfolio_bulk_operation_duration_seconds`: Bulk operation performance
- `validation_cache_hit_rate`: Cache effectiveness
- `circuit_breaker_state`: Circuit breaker health
- `mongodb_connection_pool_active`: Database connection usage

### Log Analysis

```bash
# View recent application logs
kubectl logs -n globeco -l app=globeco-portfolio-service --tail=100 -f

# Search for specific errors
kubectl logs -n globeco -l app=globeco-portfolio-service | grep -i error

# View structured logs with jq
kubectl logs -n globeco -l app=globeco-portfolio-service | jq 'select(.level == "ERROR")'
```

## Contact Information

- **On-Call Engineer**: oncall@globeco.com
- **DevOps Team**: devops@globeco.com
- **Performance Team**: performance-team@globeco.com
- **Database Team**: database-team@globeco.com

## Escalation Procedures

1. **Level 1**: On-call engineer responds within 15 minutes
2. **Level 2**: DevOps team lead engaged for complex issues
3. **Level 3**: Engineering manager and architect involved
4. **Level 4**: CTO notification for business-critical issues

## Change Management

All changes to production must follow the change management process:

1. Create change request with impact assessment
2. Get approval from change advisory board
3. Schedule maintenance window if needed
4. Execute change with rollback plan ready
5. Verify change success and monitor for issues
6. Document lessons learned

## Disaster Recovery

### Backup Procedures

- Database backups are automated daily
- Configuration is stored in version control
- Container images are tagged and stored in registry

### Recovery Procedures

1. **Service Recovery**: Redeploy from known good configuration
2. **Database Recovery**: Restore from latest backup
3. **Configuration Recovery**: Deploy from version control
4. **Full Environment Recovery**: Use infrastructure as code

## Performance Optimization

### Regular Maintenance Tasks

1. **Weekly**: Review performance metrics and trends
2. **Monthly**: Analyze cache hit rates and optimize sizes
3. **Quarterly**: Review resource allocation and scaling policies
4. **Annually**: Conduct performance testing and capacity planning

### Optimization Checklist

- [ ] Validation cache hit rate >80%
- [ ] Database connection pool utilization <80%
- [ ] Circuit breakers in closed state
- [ ] Memory usage <80% of limits
- [ ] CPU usage <70% of limits
- [ ] Error rate <1%
- [ ] P95 response time within targets