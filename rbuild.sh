docker buildx build --platform linux/amd64,linux/arm64 -t kasbench/globeco-portfolio-service:latest --push .
kubectl rollout restart deployment/globeco-portfolio-service
