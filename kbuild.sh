kubectl delete -f k8s/globeco-portfolio-service.yaml
docker buildx build --platform linux/amd64,linux/arm64 -t kasbench/globeco-portfolio-service:latest --push .
kubectl apply -f k8s/globeco-portfolio-service.yaml
