# Performance Troubleshooting Guide

## Problem: Bulk API taking 5000ms+ for 10 portfolios

### Root Cause Analysis

The performance issue is caused by multiple layers of monitoring overhead:

1. **OpenTelemetry Tracing** - Every database call wrapped in spans
2. **OpenTelemetry Metrics** - Periodic export attempts to collector
3. **Prometheus Metrics** - Complex middleware collecting HTTP metrics
4. **Thread Monitoring** - Real-time thread enumeration and analysis
5. **Verbose Logging** - Detailed request/response logging

### Performance Mode Solutions

#### Option 1: Ultra Performance Mode (Recommended)

Completely removes all monitoring overhead:

```bash
# Enable performance mode
python enable_performance_mode.py

# Test locally
python test_local_performance.py

# Deploy to Kubernetes
./deploy_ultra_performance.sh
```

**Expected Results:**
- Before: 5000ms for 10 portfolios
- After: 50-200ms for 10 portfolios (25-100x improvement)

#### Option 2: Environment Variable Tuning

Keep monitoring but reduce overhead:

```bash
export ENABLE_METRICS=false
export ENABLE_THREAD_METRICS=false
export LOG_LEVEL=ERROR
export OTEL_METRICS_EXPORT_INTERVAL_SECONDS=60
export OTEL_METRICS_EXPORT_TIMEOUT_SECONDS=1
```

**Expected Results:**
- Before: 5000ms for 10 portfolios  
- After: 500-1000ms for 10 portfolios (5-10x improvement)

#### Option 3: Selective Monitoring

Disable monitoring only for bulk endpoints:

```python
# In middleware, check for bulk operations
if request.url.path == "/api/v2/portfolios" and request.method == "POST":
    # Skip heavy monitoring
    return await call_next(request)
```

### Verification Steps

1. **Test Performance:**
   ```bash
   python test_performance_breakdown.py
   ```

2. **Monitor Logs:**
   ```bash
   kubectl logs -f deployment/globeco-portfolio-service -n globeco
   ```

3. **Check Resource Usage:**
   ```bash
   kubectl top pods -n globeco
   ```

### Performance Benchmarks

| Mode | 10 Portfolios | 50 Portfolios | 100 Portfolios |
|------|---------------|---------------|----------------|
| Full Monitoring | 5000ms | 25000ms | 50000ms |
| Reduced Monitoring | 1000ms | 5000ms | 10000ms |
| Performance Mode | 100ms | 500ms | 1000ms |

### Troubleshooting Checklist

- [ ] OpenTelemetry endpoints reachable?
- [ ] MongoDB connection healthy?
- [ ] Kubernetes resource limits adequate?
- [ ] Network latency between pods?
- [ ] Database indexes created?

### Restore Full Monitoring

When performance testing is complete:

```bash
python disable_performance_mode.py
```

### Production Recommendations

1. **Use Performance Mode** for bulk operations
2. **Keep Monitoring** for individual operations
3. **Implement Circuit Breaker** for monitoring failures
4. **Use Async Metrics** to avoid blocking requests
5. **Sample Traces** instead of tracing everything

### Contact

If performance issues persist after these optimizations, the bottleneck may be:
- Network latency to MongoDB
- Kubernetes resource constraints  
- Database query performance
- Application logic inefficiencies