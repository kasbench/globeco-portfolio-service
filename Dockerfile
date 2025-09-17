# syntax=docker/dockerfile:1
FROM python:3.13-slim

# Define build arguments for multi-arch support
ARG BUILDPLATFORM
ARG TARGETPLATFORM
ARG TARGETOS
ARG TARGETARCH

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install uv (universal package manager)
RUN pip install --no-cache-dir uv

# Set workdir
WORKDIR /app

# Copy project files
COPY . .

# Install Python dependencies
RUN pip install --upgrade pip setuptools wheel
RUN pip install .
RUN pip show opentelemetry-sdk opentelemetry-api

# Expose port
EXPOSE 8000

# Set environment variables
ENV PYTHONUNBUFFERED=1

# Start the FastAPI app with Uvicorn
# CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"] 
# CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"] 
CMD ["gunicorn", "app.main:app", 
     "-k", "uvicorn.workers.UvicornWorker", 
     "-b", "0.0.0.0:8000", 
     "--workers", "4", 
     "--threads", "1"]