# GlobeCo Portfolio Service - Architecture & Design

## Overview

The GlobeCo Portfolio Service is a high-performance, cloud-native microservice designed for benchmarking Kubernetes autoscaling capabilities. Built with Python 3.13 and FastAPI, it provides portfolio management functionality with optimized bulk operations and comprehensive observability.

## Service Architecture

### Core Components

• **FastAPI Application** - Asynchronous web framework providing REST API endpoints
• **MongoDB Database** - Document-based storage with optimized connection pooling
• **OpenTelemetry Monitoring** - Unified observability with metrics and tracing
• **Circuit Breaker Pattern** - Resilience for external dependencies
• **Validation Caching** - Performance optimization for input validation
• **Environment-based Configuration** - Adaptive behavior across deployment environments

### API Structure

• **v1 API** (`/api/v1`) - Legacy endpoints for backward compatibility
• **v2 API** (`/api/v2`) - Enhanced endpoints with pagination and bulk operations
• **Fast API** (`/api/fast`) - Optimized endpoints for high-performance scenarios
• **Health Endpoints** - Comprehensive health checks and monitoring

## Architectural Dependencies

### Core Libraries

• **FastAPI** (≥0.115.12) - Web framework with automatic OpenAPI documentation
• **Beanie** (≥1.29.0) - Async MongoDB ODM built on Pydantic
• **Motor** (≥3.7.1) - Async MongoDB driver
• **Pydantic** - Data validation and settings management
• **Gunicorn** (≥23.0.0) - WSGI HTTP server for production deployment

### Observability Stack

• **OpenTelemetry API/SDK** (≥1.34.0) - Unified telemetry framework
• **OTLP Exporters** - Metrics and traces export to collector
• **FastAPI Instrumentation** - Automatic HTTP request tracing
• **Logging Instrumentation** - Structured logging integration

### Infrastructure Dependencies

• **MongoDB** - Primary data store (via `globeco-portfolio-service-mongodb:27017`)
• **OpenTelemetry Collector** - Metrics and traces aggregation (via `NODE_IP:4317/4318`)
• **Kubernetes** - Container orchestration platform
• **Prometheus** - Metrics collection (via collector export)

## Database Design

### Data Model

```
Portfolio Document:
├── _id: ObjectId (Primary Key)
├── name: String (Indexed, Case-insensitive search)
├── dateCreated: DateTime (UTC, Indexed for sorting)
└── version: Integer (Default: 1)
```

### Database Optimizations

• **Connection Pooling** - Optimized pool sizes (min: 5-10, max: 20-50)
• **Indexes** - Text index on name field, compound index on (name, dateCreated)
• **Compression** - zstd/zlib/snappy compression enabled
• **Write Concerns** - Optimized for performance (w=1, journal=false)
• **Read Preferences** - Primary reads for consistency

### State Management

• **Stateless Design** - No local state, all data persisted in MongoDB
• **Connection Caching** - Reused database connections across requests
• **Validation Caching** - In-memory cache for input validation (1000-2000 entries)
• **Circuit Breaker State** - Tracks external dependency health

## Performance Characteristics

### CPU Load Profile

• **Base Load** - 100-200m CPU for idle service
• **Normal Operations** - 300-600m CPU for standard API requests
• **Bulk Operations** - 600-1000m CPU during high-throughput scenarios
• **Monitoring Overhead** - 50-100m CPU for telemetry collection

### Memory Usage

• **Base Memory** - 200-400Mi for application and dependencies
• **Connection Pools** - 50-100Mi for database connections
• **Caching** - 20-50Mi for validation and operational caches
• **Peak Usage** - 400-800Mi during bulk processing

### Network Load

• **API Traffic** - HTTP/1.1 and HTTP/2 support on port 8000
• **Database Traffic** - MongoDB wire protocol with compression
• **Telemetry Export** - OTLP over gRPC to collector (5-10s intervals)
• **Health Checks** - Kubernetes probes every 5-10 seconds

### Throughput Capabilities

• **Single Operations** - 1000+ requests/second
• **Bulk Operations** - 100+ portfolios/request with 25x performance improvement
• **Database Operations** - 1000+ ops/second with optimized queries
• **Search Operations** - Sub-100ms response times with proper indexing

## Scalability Features

### Horizontal Scaling

• **Stateless Design** - Multiple replicas can run simultaneously
• **Load Balancing** - Kubernetes Service distributes traffic
• **Database Sharing** - All instances share single MongoDB cluster
• **Session Independence** - No session affinity required

### Vertical Scaling

• **Resource Limits** - CPU: 1000m, Memory: 800Mi maximum
• **Connection Pooling** - Scales with available resources
• **Async Processing** - Non-blocking I/O for high concurrency
• **Batch Processing** - Efficient bulk operations reduce resource usage

### Auto-scaling Triggers

• **CPU Utilization** - Target 70% CPU usage
• **Memory Pressure** - Scale before 80% memory usage
• **Request Queue Depth** - Scale on request backlog
• **Response Time** - Scale when latency exceeds thresholds

## Resiliency Features

### Circuit Breaker Pattern

• **Database Circuit Breaker** - Protects against MongoDB failures
  - Failure threshold: 5 failures
  - Recovery timeout: 30 seconds
  - Success threshold: 3 successes

• **OTLP Export Circuit Breaker** - Protects telemetry export
  - Failure threshold: 3 failures
  - Recovery timeout: 60 seconds
  - Success threshold: 2 successes

### Retry Mechanisms

• **Database Operations** - Exponential backoff (1s, 2s, 4s)
• **Bulk Operations** - Reduced retries (1 attempt) for performance
• **Telemetry Export** - Configurable retry with jitter
• **Health Checks** - Built-in retry for dependency checks

### Graceful Degradation

• **Monitoring Failures** - Service continues without telemetry
• **Cache Misses** - Falls back to direct validation
• **Database Slowdown** - Circuit breaker prevents cascade failures
• **Partial Bulk Failures** - Transactional rollback for data consistency

### Health Monitoring

• **Startup Probe** - 30 attempts × 10s intervals for initialization
• **Liveness Probe** - Every 10s with 240s timeout
• **Readiness Probe** - Every 5s with 5s timeout
• **Custom Health Endpoints** - `/health/live`, `/health/ready`, `/health/detailed`

## Deployment Architecture

### Kubernetes Resources

• **Deployment** - Single replica with rolling update strategy
• **Service** - ClusterIP for internal communication
• **ConfigMap** - Environment-specific configuration
• **Secrets** - Sensitive configuration data (if needed)

### Container Configuration

• **Base Image** - Python 3.13-slim for minimal footprint
• **Multi-stage Build** - Optimized production image
• **Non-root User** - Security hardening
• **Health Checks** - Container-level health monitoring

### Environment Profiles

• **Development** - Enhanced logging, hot reload, single worker
• **Production** - Optimized performance, multiple workers, minimal logging
• **Testing** - Isolated resources, comprehensive monitoring

## Observability Architecture

### Metrics Collection

• **HTTP Metrics** - Request count, duration, in-flight requests
• **Database Metrics** - Connection pool stats, query performance
• **Application Metrics** - Business logic performance, error rates
• **Runtime Metrics** - Python GC, memory usage, thread counts

### Distributed Tracing

• **Request Tracing** - End-to-end request flow
• **Database Tracing** - Query execution traces
• **External Service Tracing** - Dependency call traces
• **Sampling Strategy** - Environment-based sampling rates

### Logging Strategy

• **Structured Logging** - JSON format for machine processing
• **Log Levels** - Environment-appropriate verbosity
• **Correlation IDs** - Request tracking across services
• **Performance Logging** - Timing and resource usage

## Security Considerations

• **Input Validation** - Pydantic models with strict validation
• **SQL Injection Prevention** - MongoDB ODM with parameterized queries
• **CORS Configuration** - Controlled cross-origin access
• **Security Headers** - Standard HTTP security headers
• **Container Security** - Non-root user, minimal attack surface

## Future Scalability Considerations

• **Database Sharding** - Horizontal MongoDB scaling
• **Read Replicas** - Separate read/write workloads
• **Caching Layer** - Redis for frequently accessed data
• **Message Queues** - Async processing for heavy operations
• **Service Mesh** - Advanced traffic management and security

This architecture provides a robust foundation for high-performance portfolio management while maintaining operational excellence through comprehensive observability and resilience patterns.