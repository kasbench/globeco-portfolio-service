# GlobeCo Portfolio Service

The Portfolio Service is part of the **GlobeCo Suite**, a collection of applications designed for benchmarking Kubernetes autoscaling. It provides a RESTful API for managing investment portfolios, backed by MongoDB, with built-in observability via OpenTelemetry.

The service ships in two Docker image variants — a **standard** build and a **high-CPU** build — allowing researchers to evaluate autoscaler behavior under different per-request CPU profiles.

## Table of Contents

- [Architecture](#architecture)
- [Prerequisites](#prerequisites)
- [Getting Started](#getting-started)
- [API Reference](#api-reference)
  - [V1 API — CRUD](#v1-api--crud)
  - [V2 API — Search and Bulk Operations](#v2-api--search-and-bulk-operations)
  - [Fast-Path API — Performance-Optimized Endpoints](#fast-path-api--performance-optimized-endpoints)
  - [Health Endpoints](#health-endpoints)
- [Configuration](#configuration)
  - [Core Settings](#core-settings)
  - [OpenTelemetry Settings](#opentelemetry-settings)
  - [Metrics Settings](#metrics-settings)
  - [Database Settings](#database-settings)
  - [Environment Profiles](#environment-profiles)
- [Docker Images](#docker-images)
- [High-CPU Variant](#high-cpu-variant)
- [Kubernetes Deployment](#kubernetes-deployment)
  - [Horizontal Pod Autoscaler (HPA)](#horizontal-pod-autoscaler-hpa)
  - [Vertical Pod Autoscaler (VPA)](#vertical-pod-autoscaler-vpa)
- [Building](#building)
- [Development](#development)
- [License](#license)

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    FastAPI Application                        │
├─────────────────────────────────────────────────────────────┤
│  Middleware Stack                                             │
│  ┌─────────────┬──────────────┬────────────────────────┐    │
│  │ CORS        │ Security     │ CPU Burn (high-cpu      │    │
│  │ Headers     │ Headers      │ variant only)           │    │
│  │ Request ID  │ Error Handle │ Metrics Middleware      │    │
│  └─────────────┴──────────────┴────────────────────────┘    │
├─────────────────────────────────────────────────────────────┤
│  API Routers                                                 │
│  ┌─────────────┬──────────────┬────────────────────────┐    │
│  │ /api/v1     │ /api/v2      │ /api/fast              │    │
│  │ CRUD        │ Search/Bulk  │ Performance-optimized   │    │
│  └─────────────┴──────────────┴────────────────────────┘    │
├─────────────────────────────────────────────────────────────┤
│  Service Layer                                               │
│  ┌─────────────┬──────────────┬────────────────────────┐    │
│  │ Portfolio   │ Validation   │ Circuit Breaker         │    │
│  │ Service     │ Cache        │ Registry                │    │
│  └─────────────┴──────────────┴────────────────────────┘    │
├─────────────────────────────────────────────────────────────┤
│  Data Layer                                                  │
│  ┌─────────────────────────────────────────────────────┐    │
│  │ Beanie ODM → MongoDB (async, pooled, compressed)    │    │
│  └─────────────────────────────────────────────────────┘    │
├─────────────────────────────────────────────────────────────┤
│  Observability                                               │
│  ┌─────────────────────────────────────────────────────┐    │
│  │ OpenTelemetry (traces + metrics) → OTLP Collector   │    │
│  └─────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────┘
```

**Key technologies:**

| Component | Technology |
|-----------|-----------|
| Framework | FastAPI 0.115+ with Gunicorn/Uvicorn workers |
| ODM | Beanie 2.0+ (async MongoDB ODM built on Pydantic) |
| Database | MongoDB (async driver via PyMongo 4.10+) |
| Observability | OpenTelemetry SDK with OTLP exporter |
| Runtime | Python 3.13 |
| Container | Multi-stage Docker build (python:3.13-slim) |

## Prerequisites

- Python 3.13+
- MongoDB instance (local or remote)
- [uv](https://docs.astral.sh/uv/) package manager (recommended) or pip

## Getting Started

### Local Development

```bash
# Clone the repository
git clone https://github.com/kasbench/globeco-portfolio-service.git
cd globeco-portfolio-service

# Create virtual environment and install dependencies
python -m venv .venv
source .venv/bin/activate
uv pip install -e .

# Set required environment variables
export MONGODB_URI="mongodb://localhost:27017"
export LOG_LEVEL="DEBUG"

# Run with hot reload
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### Docker

```bash
# Standard image
docker build -t globeco-portfolio-service .
docker run -p 8000:8000 -e MONGODB_URI="mongodb://host.docker.internal:27017" globeco-portfolio-service

# High-CPU variant
docker build -f Dockerfile.high-cpu -t globeco-portfolio-service-high-cpu .
docker run -p 8000:8000 -e MONGODB_URI="mongodb://host.docker.internal:27017" globeco-portfolio-service-high-cpu
```

The service is available at `http://localhost:8000`. The root endpoint (`GET /`) returns service status information.

## API Reference

### Data Model

The **Portfolio** resource has the following schema:

| Field | Type | Description |
|-------|------|-------------|
| `portfolioId` | string | Unique identifier (MongoDB ObjectId) |
| `name` | string | Portfolio name (1–200 chars, alphanumeric, spaces, hyphens, underscores) |
| `dateCreated` | ISO 8601 datetime | Creation timestamp |
| `version` | integer | Optimistic locking version (starts at 1) |

### V1 API — CRUD

Base path: `/api/v1`

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/v1/portfolios` | List all portfolios |
| `GET` | `/api/v1/portfolio/{portfolioId}` | Get a single portfolio |
| `POST` | `/api/v1/portfolios` | Create a portfolio |
| `PUT` | `/api/v1/portfolio/{portfolioId}` | Update a portfolio (optimistic locking) |
| `DELETE` | `/api/v1/portfolio/{portfolioId}?version={v}` | Delete a portfolio (optimistic locking) |

#### Create Portfolio

```http
POST /api/v1/portfolios
Content-Type: application/json

{
  "name": "Growth Fund",
  "dateCreated": "2025-01-15T10:00:00Z",
  "version": 1
}
```

Response `201 Created`:
```json
{
  "portfolioId": "665a1b2c3d4e5f6a7b8c9d0e",
  "name": "Growth Fund",
  "dateCreated": "2025-01-15T10:00:00Z",
  "version": 1
}
```

#### Update Portfolio

Updates use optimistic locking — the `version` in the request body must match the current version. On success, the version is incremented.

```http
PUT /api/v1/portfolio/665a1b2c3d4e5f6a7b8c9d0e
Content-Type: application/json

{
  "portfolioId": "665a1b2c3d4e5f6a7b8c9d0e",
  "name": "Balanced Growth Fund",
  "version": 1
}
```

Returns `409 Conflict` if the version does not match.

#### Delete Portfolio

```http
DELETE /api/v1/portfolio/665a1b2c3d4e5f6a7b8c9d0e?version=2
```

Returns `204 No Content` on success, `409 Conflict` on version mismatch.

### V2 API — Search and Bulk Operations

Base path: `/api/v2`

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/v2/portfolios` | Search portfolios with pagination |
| `POST` | `/api/v2/portfolios` | Bulk create portfolios (up to 100) |

#### Search Portfolios

```http
GET /api/v2/portfolios?name_like=Growth&limit=20&offset=0
```

Query parameters:

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `name` | string | — | Exact name match (case-insensitive) |
| `name_like` | string | — | Partial name match (case-insensitive) |
| `limit` | int | 50 | Results per page (1–1000) |
| `offset` | int | 0 | Number of results to skip |

Only one of `name` or `name_like` may be provided.

Response:
```json
{
  "portfolios": [
    {
      "portfolioId": "665a1b2c3d4e5f6a7b8c9d0e",
      "name": "Growth Fund",
      "dateCreated": "2025-01-15T10:00:00Z",
      "version": 1
    }
  ],
  "pagination": {
    "totalElements": 42,
    "totalPages": 3,
    "currentPage": 0,
    "pageSize": 20,
    "hasNext": true,
    "hasPrevious": false
  }
}
```

#### Bulk Create Portfolios

```http
POST /api/v2/portfolios
Content-Type: application/json

[
  { "name": "Fund A" },
  { "name": "Fund B", "version": 1 },
  { "name": "Fund C", "dateCreated": "2025-06-01T00:00:00Z" }
]
```

- Accepts 1–100 portfolios per request.
- All-or-nothing semantics (all succeed or all fail).
- Returns `201 Created` with the list of created portfolios.

### Fast-Path API — Performance-Optimized Endpoints

Base path: `/api/fast`

These endpoints bypass some standard middleware for reduced latency. Useful for load testing and benchmarking.

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/fast/portfolios/bulk` | Fast bulk creation (raw JSON, max 1 MB) |
| `GET` | `/api/fast/portfolios/search` | Fast search with same params as v2 |
| `GET` | `/api/fast/health/fast` | Minimal health check |

The fast-path bulk endpoint returns additional performance metadata:

```json
{
  "portfolios": [...],
  "count": 50,
  "processingTimeMs": 12.34
}
```

Response headers include `X-Processing-Time-Ms` and `X-Portfolio-Count`.

### Health Endpoints

Designed for Kubernetes probes with sub-10ms response times.

| Endpoint | Purpose | Response |
|----------|---------|----------|
| `GET /health` | Basic health (load balancer) | Plain text `OK` |
| `GET /health/live` | Liveness probe | JSON with status |
| `GET /health/ready` | Readiness probe (checks DB) | JSON with status + DB health |
| `GET /health/startup` | Startup probe | JSON with startup status |
| `GET /health/detailed` | Detailed system info | JSON with full diagnostics |

Health check results are cached (liveness: 5s, readiness: 2s, startup: 1s) to minimize overhead.

## Configuration

All configuration is via environment variables.

### Core Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `MONGODB_URI` | `mongodb://globeco-portfolio-service-mongodb:27017` | MongoDB connection string |
| `LOG_LEVEL` | `INFO` | Logging level (DEBUG, INFO, WARNING, ERROR) |
| `ENVIRONMENT` | auto-detected | Environment profile: `development`, `staging`, or `production` |
| `PORTFOLIO_SERVICE_ENV` | — | Override for environment detection |

### OpenTelemetry Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `OTEL_SERVICE_NAME` | `globeco-portfolio-service` | Service name reported to collector |
| `OTEL_SERVICE_NAMESPACE` | `globeco` | Service namespace label |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | `localhost:4317` | OTLP gRPC collector endpoint |
| `OTEL_EXPORTER_OTLP_METRICS_ENDPOINT` | — | HTTP endpoint for metrics (e.g., `http://host:4318/v1/metrics`) |
| `OTEL_EXPORTER_OTLP_TRACES_ENDPOINT` | — | HTTP endpoint for traces |
| `OTEL_EXPORTER_OTLP_INSECURE` | `true` | Disable TLS for OTLP export |
| `OTEL_METRICS_EXPORT_INTERVAL_SECONDS` | `10` | Metrics export interval |
| `OTEL_METRICS_EXPORT_TIMEOUT_SECONDS` | `5` | Metrics export timeout |
| `OTEL_METRICS_LOGGING_ENABLED` | `false` | Log metrics export activity |

### Metrics Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `ENABLE_METRICS` | `true` | Enable HTTP metrics collection |
| `METRICS_DEBUG_LOGGING` | `false` | Debug logging for metrics |
| `ENABLE_THREAD_METRICS` | `true` | Enable thread worker metrics |
| `THREAD_METRICS_UPDATE_INTERVAL` | `1.0` | Thread metrics update interval (seconds) |
| `THREAD_METRICS_DEBUG_LOGGING` | `false` | Debug logging for thread metrics |
| `SERVICE_NAMESPACE` | `globeco` | Namespace label for metrics |
| `ENABLE_METRICS_MIDDLEWARE` | `false` | Enable metrics middleware |

### Database Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `MAX_POOL_SIZE` | `20` | Maximum MongoDB connection pool size |
| `MIN_POOL_SIZE` | `5` | Minimum connections maintained |
| `CONNECTION_TIMEOUT` | `30000` | Connection timeout in milliseconds |

The MongoDB client is configured with compression (zstd, zlib, snappy), retry writes/reads, streaming server monitoring, and optimized heartbeat intervals.

### Environment Profiles

The service auto-detects its environment and applies configuration profiles:

| Profile | Monitoring | Tracing | Sample Rate | Log Level | Pool Size |
|---------|-----------|---------|-------------|-----------|-----------|
| `development` | Full | Enabled | 100% | DEBUG | 50 |
| `staging` | Standard | Enabled | 50% | INFO | 30 |
| `production` | Minimal | Disabled | 10% | WARNING | 20 |

Detection priority: `PORTFOLIO_SERVICE_ENV` → `ENVIRONMENT` → `ENV` → Kubernetes namespace inspection → defaults to `production`.

## Docker Images

The project produces two multi-architecture (amd64/arm64) images:

| Image | Description |
|-------|-------------|
| `kasbench/globeco-portfolio-service` | Standard production image |
| `kasbench/globeco-portfolio-service-high-cpu` | High-CPU variant for autoscaling benchmarks |

Both use a multi-stage build (builder + runtime) based on `python:3.13-slim`, run as a non-root user, and start with Gunicorn (2 Uvicorn workers, preloaded, max 1000 requests per worker with jitter).

### Dockerfile Variants

| File | Use Case |
|------|----------|
| `Dockerfile` | Production image |
| `Dockerfile.high-cpu` | Production image with CPU burn middleware enabled |
| `Dockerfile.dev` | Development image with hot reload and debug tooling |

## High-CPU Variant

The **high-CPU variant** is designed for benchmarking Kubernetes autoscalers under increased per-request CPU load. It is identical to the standard image except it enables the `CPUBurnMiddleware`.

### How It Works

When `HIGH_CPU_MODE=true`, the service adds a middleware layer that performs CPU-intensive floating-point math (trigonometric functions, square roots, logarithms) after each API request completes. This artificially inflates the CPU time per request without altering response content or correctness.

Key characteristics:
- Burns CPU **after** the response is generated — latency increases but responses remain correct.
- Skips health check and metrics endpoints (`/health`, `/health/live`, `/health/ready`, `/health/startup`, `/metrics`, `/`) to avoid interfering with Kubernetes probes.
- Default burn duration: **50ms per request** — enough to push a pod to ~500m additional CPU under moderate load.
- Duration is tunable via `CPU_BURN_DURATION_MS` without rebuilding the image.

### Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `HIGH_CPU_MODE` | `false` | Enable CPU burn middleware (`true`, `1`, or `yes`) |
| `CPU_BURN_DURATION_MS` | `50` | Burn duration per request in milliseconds |

### Usage

```bash
# Run the pre-built high-cpu image
docker run -p 8000:8000 \
  -e MONGODB_URI="mongodb://mongo:27017" \
  kasbench/globeco-portfolio-service-high-cpu:latest

# Or enable high-cpu mode on the standard image
docker run -p 8000:8000 \
  -e MONGODB_URI="mongodb://mongo:27017" \
  -e HIGH_CPU_MODE=true \
  -e CPU_BURN_DURATION_MS=75 \
  kasbench/globeco-portfolio-service:latest
```

### Benchmarking Guidance

The high-CPU variant allows controlled evaluation of autoscaler responsiveness:

1. Deploy the high-CPU image to your Kubernetes cluster.
2. Configure HPA/VPA/KEDA with your desired scaling thresholds.
3. Apply load (e.g., with k6, Locust, or wrk) against the API endpoints.
4. Observe scaling behavior as CPU utilization rises proportionally with request rate.
5. Adjust `CPU_BURN_DURATION_MS` to simulate different CPU intensity profiles.

Because health probes are excluded from the burn, the autoscaler sees true workload-driven CPU increase without probe interference.

## Kubernetes Deployment

The service is deployed to the `globeco` namespace. Manifests are provided for both local and AWS environments.

### Resource Requests

| Environment | CPU Request | CPU Limit | Memory Request | Memory Limit |
|-------------|-------------|-----------|----------------|--------------|
| Local (`k8s/`) | 600m | 1000m | 400Mi | 800Mi |
| AWS (`k8s_aws/`) | 200m | 200m | 300Mi | 300Mi |

The AWS variant uses `requests == limits` for VPA compatibility.

### Probes

All probes target port 8000:

| Probe | Path | Period | Timeout | Failure Threshold |
|-------|------|--------|---------|-------------------|
| Liveness | `/` | 5s | 5s | 3 |
| Readiness | `/` | 5s | 5s | 3 |
| Startup | `/` | 2s | 5s | 30 |

### Horizontal Pod Autoscaler (HPA)

The HPA template (`k8s_aws/hpa.yaml`) scales on both CPU and memory utilization:

```yaml
metrics:
  - type: Resource
    resource:
      name: cpu
      target:
        type: Utilization
        averageUtilization: <configurable>
  - type: Resource
    resource:
      name: memory
      target:
        type: Utilization
        averageUtilization: <configurable>
```

Min/max replicas and target utilization percentages are templated via Helm values.

### Vertical Pod Autoscaler (VPA)

The VPA template (`k8s_aws/vpa.yaml`) uses `InPlaceOrRecreate` update mode:

- **Min allowed:** 100m CPU, 200Mi memory
- **Max allowed:** 2000m CPU, 2Gi memory
- **Controlled resources:** CPU and memory (requests and limits)

## Building

Use the provided `kbuild.sh` script to build and push both image variants:

```bash
./kbuild.sh
```

This builds multi-architecture images (`linux/amd64` + `linux/arm64`) and pushes them to Docker Hub under the `kasbench` organization:

- `kasbench/globeco-portfolio-service:<version>`
- `kasbench/globeco-portfolio-service-high-cpu:<version>`

To build locally without pushing:

```bash
# Standard image
docker build -t globeco-portfolio-service .

# High-CPU variant
docker build -f Dockerfile.high-cpu -t globeco-portfolio-service-high-cpu .
```

## Development

```bash
# Using the development Dockerfile (includes hot reload)
docker build -f Dockerfile.dev -t globeco-portfolio-service-dev .
docker run -p 8000:8000 -v $(pwd):/app -e MONGODB_URI="mongodb://host.docker.internal:27017" globeco-portfolio-service-dev

# Or run directly with uvicorn
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000 --log-level debug
```

The development image sets `ENVIRONMENT=development` which enables full observability, debug logging, and request/response logging.

### Project Structure

```
app/
├── main.py                  # Application entry point and lifespan management
├── api_v1.py                # V1 CRUD endpoints
├── api_v2.py                # V2 search and bulk endpoints
├── api_fast.py              # Fast-path optimized endpoints
├── config.py                # Core settings (pydantic-settings)
├── environment_config.py    # Environment profiles and feature flags
├── models.py                # Beanie document models
├── schemas.py               # Pydantic request/response DTOs
├── services.py              # Business logic layer
├── database.py              # MongoDB client and connection management
├── health_endpoints.py      # Kubernetes health probe endpoints
├── cpu_burn_middleware.py   # CPU burn middleware (high-cpu variant)
├── middleware_factory.py    # Conditional middleware loading
├── circuit_breaker.py       # Circuit breaker for external dependencies
├── validation_cache.py      # Validation result caching
├── unified_monitoring.py    # OpenTelemetry monitoring integration
└── logging_config.py        # Structured logging configuration
```

## License

See [LICENSE](LICENSE) for details.
