# syntax=docker/dockerfile:1

# Multi-stage build for optimized production image
# Stage 1: Build stage with full Python environment
FROM python:3.13-slim AS builder

# Define build arguments for multi-arch support
ARG BUILDPLATFORM
ARG TARGETPLATFORM
ARG TARGETOS
ARG TARGETARCH

# Install system dependencies needed for building
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Install uv for faster dependency resolution
RUN pip install --no-cache-dir uv

# Set workdir
WORKDIR /app

# Copy dependency files first for better layer caching
COPY pyproject.toml ./
COPY README.md ./

# Create virtual environment
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Extract and install dependencies only (not the package itself)
RUN uv pip install --no-cache-dir \
    beanie>=1.29.0 \
    dnspython>=2.7.0 \
    "fastapi[standard]>=0.115.12" \
    gunicorn>=23.0.0 \
    mongo-migrate>=0.1.2 \
    pydantic-settings>=2.9.1 \
    pytest-asyncio>=0.26.0 \
    pytest>=8.3.5 \
    "testcontainers[mongodb]>=4.10.0" \
    opentelemetry-api>=1.34.0 \
    opentelemetry-sdk>=1.34.0 \
    opentelemetry-instrumentation>=0.55b1 \
    opentelemetry-exporter-otlp>=1.34.0 \
    opentelemetry-instrumentation-fastapi>=0.55b1 \
    opentelemetry-instrumentation-grpc>=0.55b1 \
    opentelemetry-instrumentation-logging>=0.55b1 \
    opentelemetry-instrumentation-requests>=0.55b1 \
    opentelemetry-instrumentation-httpx>=0.55b1 \
    motor>=3.7.1

# Copy application code
COPY app/ ./app/

# Stage 2: Runtime stage with minimal Python image
FROM python:3.13-slim AS production

# Install minimal runtime dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy virtual environment from builder stage
COPY --from=builder /opt/venv /opt/venv

# Copy application code from builder stage
COPY --from=builder /app /app

# Set working directory
WORKDIR /app

# Set environment variables for production
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV PATH="/opt/venv/bin:$PATH"
ENV PYTHONPATH="/app"

# Create non-root user for security
RUN groupadd -r appuser && useradd -r -g appuser appuser
USER appuser

# Expose port
EXPOSE 8000

# Health check for container orchestration
# Note: Kubernetes will use the /health/live endpoint instead
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Start the FastAPI app with optimized Gunicorn configuration
CMD ["/opt/venv/bin/gunicorn", "app.main:app", "-k", "uvicorn.workers.UvicornWorker", "-b", "0.0.0.0:8000", "--workers", "2", "--threads", "1", "--max-requests", "1000", "--max-requests-jitter", "100", "--preload"]