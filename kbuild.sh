docker buildx build --platform linux/amd64,linux/arm64 \
-t kasbench/globeco-portfolio-service:latest \
-t kasbench/globeco-portfolio-service:1.0.3 \
-t kasbench/globeco-portfolio-service-high-cpu:1.0.3 \
--push .
kubectl delete -f k8s/globeco-portfolio-service.yaml
kubectl apply -f k8s/globeco-portfolio-service.yaml
