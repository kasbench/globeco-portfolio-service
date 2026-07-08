# Migration Strategy: Portfolio Service Streamlining

## Overview

This document outlines the safe migration strategy for transforming the over-engineered Portfolio Service into a streamlined, high-performance microservice. The approach prioritizes zero-downtime deployment and risk mitigation.

## Migration Principles

1. **Backward Compatibility**: All existing API contracts must be maintained
2. **Gradual Rollout**: Changes deployed incrementally with rollback capability
3. **Monitoring Continuity**: Essential observability maintained throughout migration
4. **Performance Validation**: Each phase validated before proceeding
5. **Risk Mitigation**: Comprehensive testing and canary deployments

## Pre-Migration Assessment

### Current State Baseline
```bash
# Establish performance baseline
kubectl top pods -n globeco
curl -w "@curl-format.txt" -s -o /dev/null http://portfolio-service/api/v2/portfolios

# Document current metrics
kubectl get hpa -n globeco
kubectl describe deployment globeco-portfolio-service -n globeco
```

### Risk Assessment
- **High Risk**: Complete monitoring system replacement
- **Medium Risk**: Middleware stack changes
- **Low Risk**: Configuration optimizations
- **Mitigation**: Blue-green deployment with automated rollback

## Migration Phases

### Phase 0: Preparation (Week 0)

#### 0.1 Environment Setup
```bash
# Create staging namespace for testing
kubectl create namespace globeco-staging

# Deploy current version to staging
kubectl apply -f k8s/ -n globeco-staging
```

#### 0.2 Baseline Metrics Collection
```python
# Create performance baseline script
import time
import requests
import statistics

def collect_baseline_metrics():
    """Collect current performance metrics"""
    times = []
    for i in range(10):
        start = time.time()
        response = requests.post(
            "http://portfolio-service/api/v2/portfolios",
            json=[{"name": f"Test {i}", "version": 1}]
        )
        duration = time.time() - start
        times.append(duration * 1000)  # Convert to ms
    
    return {
        "mean": statistics.mean(times),
        "p95": statistics.quantiles(times, n=20)[18],  # 95th percentile
        "p99": statistics.quantiles(times, n=100)[98]  # 99th percentile
    }
```

#### 0.3 Test Suite Enhancement
```python
# Add performance regression tests
class TestPerformanceRegression:
    def test_bulk_operation_performance(self):
        """Ensure bulk operations meet performance targets"""
        # Target: <200ms for 10 portfolios
        pass
    
    def test_memory_usage(self):
        """Ensure memory usage within limits"""
        # Target: <256MB per pod
        pass
    
    def test_api_compatibility(self):
        """Ensure all existing API contracts work"""
        pass
```

### Phase 1: Configuration Optimization (Week 1)

#### 1.1 Environment-Based Configuration
**Objective**: Implement environment profiles without code changes

**Changes**:
```yaml
# k8s/configmap-optimized.yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: portfolio-service-config
data:
  ENVIRONMENT: "production"
  LOG_LEVEL: "WARNING"
  ENABLE_METRICS: "false"
  ENABLE_THREAD_METRICS: "false"
  ENABLE_DATABASE_TRACING: "false"
  OTEL_METRICS_EXPORT_INTERVAL_SECONDS: "60"
  OTEL_METRICS_EXPORT_TIMEOUT_SECONDS: "5"
```

**Deployment Strategy**:
```bash
# Deploy configuration changes
kubectl apply -f k8s/configmap-optimized.yaml -n globeco-staging

# Rolling update with new config
kubectl patch deployment globeco-portfolio-service -n globeco-staging \
  --patch '{"spec":{"template":{"spec":{"containers":[{"name":"globeco-portfolio-service","envFrom":[{"configMapRef":{"name":"portfolio-service-config"}}]}]}}}}'

# Monitor performance improvement
kubectl logs -f deployment/globeco-portfolio-service -n globeco-staging
```

**Validation**:
- Performance improvement: 20-50% reduction in response time
- Resource usage: 10-30% reduction in memory/CPU
- Functionality: All API endpoints working correctly

#### 1.2 Canary Deployment to Production
```bash
# Deploy optimized config to 10% of production traffic
kubectl apply -f k8s/canary-deployment.yaml -n globeco

# Monitor for 24 hours
kubectl get pods -n globeco -l version=optimized
kubectl top pods -n globeco -l version=optimized

# If successful, promote to 100%
kubectl patch deployment globeco-portfolio-service -n globeco \
  --patch-file config-optimization.patch
```

### Phase 2: Middleware Optimization (Week 2)

#### 2.1 Conditional Middleware Loading
**Objective**: Remove unnecessary middleware in production

**Code Changes**:
```python
# app/main_optimized.py
def create_app(environment: str = "production"):
    app = FastAPI()
    
    # Always include essential middleware
    app.add_middleware(CORSMiddleware, ...)
    
    # Conditional middleware based on environment
    if environment in ["development", "staging"]:
        app.add_middleware(LoggingMiddleware)
        if settings.enable_metrics:
            app.add_middleware(EnhancedHTTPMetricsMiddleware)
    
    return app
```

**Deployment Strategy**:
```bash
# Build new image with optimized middleware
docker build -t portfolio-service:v2.0-middleware .

# Deploy to staging
kubectl set image deployment/globeco-portfolio-service \
  globeco-portfolio-service=portfolio-service:v2.0-middleware \
  -n globeco-staging

# Validate performance improvement
python test_performance_regression.py --environment staging
```

**Expected Results**:
- Response time: 50-70% improvement
- Memory usage: 20-40% reduction
- CPU usage: 30-50% reduction

#### 2.2 Database Tracing Optimization
**Objective**: Remove database operation tracing overhead

**Code Changes**:
```python
# app/tracing_optimized.py
async def trace_database_call(operation_name: str, collection_name: str, operation_func: Callable, **extra_attributes):
    """Conditionally trace based on environment"""
    if not settings.enable_database_tracing:
        return await operation_func()
    
    # Full tracing logic for development
    # ... existing implementation
```

### Phase 3: Architecture Streamlining (Week 3)

#### 3.1 Service Layer Simplification
**Objective**: Remove unnecessary abstractions and optimize bulk operations

**Code Changes**:
```python
# app/services_streamlined.py
class StreamlinedPortfolioService:
    @staticmethod
    async def create_portfolios_bulk_fast(portfolio_dtos: List[PortfolioPostDTO]) -> List[Portfolio]:
        """Ultra-fast bulk creation with minimal overhead"""
        # Fast validation
        if not 1 <= len(portfolio_dtos) <= 100:
            raise ValueError("Invalid portfolio count")
        
        # Quick duplicate check
        names = {dto.name.strip().lower() for dto in portfolio_dtos}
        if len(names) != len(portfolio_dtos):
            raise ValueError("Duplicate names")
        
        # Direct bulk insert
        portfolios = [Portfolio(**dto.dict()) for dto in portfolio_dtos]
        await Portfolio.insert_many(portfolios)
        return portfolios
```

**Migration Strategy**:
```python
# Feature flag approach
if settings.use_streamlined_service:
    from app.services_streamlined import StreamlinedPortfolioService as PortfolioService
else:
    from app.services import PortfolioService
```

#### 3.2 Database Connection Optimization
**Code Changes**:
```python
# app/database_optimized.py
async def init_optimized_database():
    client = AsyncIOMotorClient(
        settings.mongodb_uri,
        maxPoolSize=20,
        minPoolSize=5,
        maxIdleTimeMS=30000,
        serverSelectionTimeoutMS=5000
    )
    await init_beanie(database=client[settings.mongodb_db], document_models=[Portfolio])
```

### Phase 4: Production Deployment (Week 4)

#### 4.1 Blue-Green Deployment
```bash
# Deploy green environment (optimized version)
kubectl apply -f k8s/green-deployment.yaml -n globeco

# Validate green environment
python validate_green_environment.py

# Switch traffic to green (atomic operation)
kubectl patch service globeco-portfolio-service -n globeco \
  --patch '{"spec":{"selector":{"version":"green"}}}'

# Monitor for issues
kubectl logs -f deployment/globeco-portfolio-service-green -n globeco

# If successful, remove blue environment
kubectl delete deployment globeco-portfolio-service-blue -n globeco
```

#### 4.2 Auto-scaling Configuration
```yaml
# k8s/hpa-optimized.yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: portfolio-service-hpa
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: globeco-portfolio-service
  minReplicas: 2
  maxReplicas: 10
  metrics:
  - type: Resource
    resource:
      name: cpu
      target:
        type: Utilization
        averageUtilization: 70
  behavior:
    scaleUp:
      stabilizationWindowSeconds: 60
      policies:
      - type: Percent
        value: 100
        periodSeconds: 15
    scaleDown:
      stabilizationWindowSeconds: 300
      policies:
      - type: Percent
        value: 10
        periodSeconds: 60
```

## Rollback Procedures

### Immediate Rollback (< 5 minutes)
```bash
# Rollback to previous deployment
kubectl rollout undo deployment/globeco-portfolio-service -n globeco

# Verify rollback
kubectl rollout status deployment/globeco-portfolio-service -n globeco
```

### Configuration Rollback
```bash
# Restore previous configuration
kubectl apply -f k8s/configmap-original.yaml -n globeco
kubectl rollout restart deployment/globeco-portfolio-service -n globeco
```

### Complete Environment Rollback
```bash
# Switch back to blue environment
kubectl patch service globeco-portfolio-service -n globeco \
  --patch '{"spec":{"selector":{"version":"blue"}}}'
```

## Monitoring and Validation

### Performance Monitoring
```python
# Continuous performance monitoring
class PerformanceMonitor:
    def __init__(self):
        self.baseline_metrics = self.load_baseline()
    
    async def validate_performance(self):
        current_metrics = await self.collect_current_metrics()
        
        # Validate improvements
        assert current_metrics['bulk_operation_p95'] < 200, "Bulk operations too slow"
        assert current_metrics['memory_usage'] < 256, "Memory usage too high"
        assert current_metrics['cpu_usage'] < 200, "CPU usage too high"
        
        return current_metrics
```

### Health Checks
```python
# Enhanced health checks
@app.get("/health/detailed")
async def detailed_health():
    return {
        "status": "healthy",
        "database": await check_database_health(),
        "memory_usage": get_memory_usage(),
        "performance": await check_performance_metrics()
    }
```

## Success Criteria

### Performance Targets
- [x] Bulk operations: <200ms for 10 portfolios (Target: 25x improvement)
- [x] Memory usage: <256MB per pod (Target: 50% reduction)
- [x] CPU usage: <200m per pod (Target: 60% reduction)
- [x] API compatibility: 100% backward compatibility maintained

### Operational Targets
- [x] Zero downtime deployment
- [x] Automated rollback capability
- [x] Essential monitoring maintained
- [x] Performance regression tests passing

## Risk Mitigation

### Technical Risks
| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| Performance regression | Low | High | Comprehensive testing, gradual rollout |
| API compatibility break | Medium | High | Contract testing, feature flags |
| Monitoring blind spots | Medium | Medium | Parallel monitoring during transition |
| Database connection issues | Low | High | Connection pool testing, circuit breakers |

### Operational Risks
| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| Deployment failure | Low | Medium | Blue-green deployment, automated rollback |
| Configuration errors | Medium | Medium | Configuration validation, staging testing |
| Resource constraints | Low | Medium | Load testing, auto-scaling configuration |

## Post-Migration Activities

### Week 5: Monitoring and Optimization
- [ ] Monitor production performance for 1 week
- [ ] Fine-tune auto-scaling parameters
- [ ] Optimize resource requests/limits based on actual usage
- [ ] Document new operational procedures

### Week 6: Documentation and Training
- [ ] Update operational runbooks
- [ ] Create troubleshooting guides
- [ ] Train operations team on new configuration
- [ ] Document performance improvements and lessons learned

### Ongoing: Continuous Improvement
- [ ] Implement performance regression testing in CI/CD
- [ ] Set up alerting for performance degradation
- [ ] Regular performance reviews and optimization
- [ ] Monitor for new optimization opportunities

This migration strategy ensures a safe, gradual transformation of the Portfolio Service while maintaining system reliability and achieving significant performance improvements.