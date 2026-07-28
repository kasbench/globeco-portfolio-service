#!/bin/bash
set -e

VERSION="1.0.4"

echo "=== Building globeco-portfolio-service (standard) ==="
docker buildx build --platform linux/amd64,linux/arm64 \
  -t kasbench/globeco-portfolio-service:latest \
  -t kasbench/globeco-portfolio-service:${VERSION} \
  --push .

echo ""
echo "=== Building globeco-portfolio-service-high-cpu ==="
docker buildx build --platform linux/amd64,linux/arm64 \
  -f Dockerfile.high-cpu \
  -t kasbench/globeco-portfolio-service-high-cpu:latest \
  -t kasbench/globeco-portfolio-service-high-cpu:${VERSION} \
  --push .

echo ""
echo "=== Build complete ==="
echo "  Standard:  kasbench/globeco-portfolio-service:${VERSION}"
echo "  High-CPU:  kasbench/globeco-portfolio-service-high-cpu:${VERSION}"

k delete -f k8s/globeco-portfolio-service.yaml
k apply -f k8s/globeco-portfolio-service.yaml