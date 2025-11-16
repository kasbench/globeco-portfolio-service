docker buildx build --platform linux/amd64,linux/arm64 \
-t kasbench/globeco-portfolio-service:latest \
-t kasbench/globeco-portfolio-service:1.0.1 \
--push .
kubectl delete -f k8s/globeco-portfolio-service.yaml
kubectl apply -f k8s/globeco-portfolio-service.yaml
