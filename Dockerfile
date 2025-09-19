# syntax=docker/dockerfile:1

# Multi-stage build for optimized production image
# Stage 1: Build stage with full Python environment
FROM python:3.13-slim as builder

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

# Create virtual environment and install dependencies
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Install dependencies using uv for speed
RUN uv pip install --no-cache-dir -e .

# Copy application code
COPY app/ ./app/

# Stage 2: Runtime stage with distroless image
FROM gcr.io/distroless/python3-debian12:latest as production

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
USER 65534:65534

# Expose port
EXPOSE 8000

# Health check for container orchestration
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD ["/opt/venv/bin/python", "-c", "import requests; requests.get('http://localhost:8000/health', timeout=5)"]

# Start the FastAPI app with optimized Gunicorn configuration
ENTRYPOINT ["/opt/venv/bin/gunicorn"]
CMD ["app.main:app", "-k", "uvicorn.workers.UvicornWorker", "-b", "0.0.0.0:8000", "--workers", "2", "--threads", "1", "--max-requests", "1000", "--max-requests-jitter", "100", "--preload"]