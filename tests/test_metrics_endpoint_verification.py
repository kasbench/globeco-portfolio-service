"""
Verification tests for metrics endpoint compatibility.

This module provides simple verification tests to confirm that the /metrics
endpoint works correctly and includes the expected HTTP metrics.
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
import os

# Set test environment variables
os.environ['PROMETHEUS_DISABLE_CREATED_SERIES'] = 'True'

from app.monitoring import EnhancedHTTPMetricsMiddleware, clear_metrics_registry


def test_metrics_endpoint_basic_functionality():
    """Basic test to verify metrics endpoint works and includes HTTP metrics."""
    # Clear any existing metrics
    clear_metrics_registry()
    
    # Create minimal test app
    app = FastAPI()
    
    # Add metrics middleware
    app.add_middleware(EnhancedHTTPMetricsMiddleware, debug_logging=False)
    
    # Add Prometheus /metrics endpoint
    from prometheus_client import make_asgi_app
    metrics_app = make_asgi_app()
    app.mount("/metrics", metrics_app)
    
    # Add simple test endpoint
    @app.get("/test")
    async def test_endpoint():
        return {"status": "ok"}
    
    # Create test client
    client = TestClient(app)
    
    # Make a request to generate metrics
    response = client.get("/test")
    assert response.status_code == 200
    
    # Check metrics endpoint
    metrics_response = client.get("/metrics")
    assert metrics_response.status_code == 200
    
    metrics_text = metrics_response.text
    
    # Verify all three HTTP metrics are present
    assert "http_requests_total" in metrics_text
    assert "http_request_duration" in metrics_text
    assert "http_requests_in_flight" in metrics_text
    
    # Verify Prometheus format
    assert "# HELP" in metrics_text
    assert "# TYPE" in metrics_text
    
    # Verify specific metric entries for our test request
    assert 'method="GET"' in metrics_text
    assert 'path="/test"' in metrics_text
    assert 'status="200"' in metrics_text
    
    print("✓ Metrics endpoint verification successful")
    print("✓ All three HTTP metrics are present")
    print("✓ Prometheus text format is correct")
    print("✓ Metric labels are properly formatted")


def test_metrics_endpoint_opentelemetry_compatibility():
    """Test that metrics are compatible with OpenTelemetry Collector expectations."""
    # Clear any existing metrics
    clear_metrics_registry()
    
    # Create minimal test app
    app = FastAPI()
    app.add_middleware(EnhancedHTTPMetricsMiddleware, debug_logging=False)
    
    from prometheus_client import make_asgi_app
    metrics_app = make_asgi_app()
    app.mount("/metrics", metrics_app)
    
    @app.get("/api/v1/portfolio/{portfolio_id}")
    async def get_portfolio(portfolio_id: str):
        return {"portfolioId": portfolio_id}
    
    client = TestClient(app)
    
    # Make request with MongoDB ObjectId
    response = client.get("/api/v1/portfolio/507f1f77bcf86cd799439011")
    assert response.status_code == 200
    
    # Get metrics
    metrics_response = client.get("/metrics")
    metrics_text = metrics_response.text
    
    # Verify route parameterization (high cardinality prevention)
    assert 'path="/api/v1/portfolio/{portfolioId}"' in metrics_text
    assert "507f1f77bcf86cd799439011" not in metrics_text
    
    # Verify histogram buckets are in milliseconds (OTel compatibility)
    assert 'le="5.0"' in metrics_text  # 5ms bucket
    assert 'le="100.0"' in metrics_text  # 100ms bucket
    assert 'le="1000.0"' in metrics_text  # 1000ms bucket
    
    print("✓ OpenTelemetry Collector compatibility verified")
    print("✓ Route patterns are parameterized correctly")
    print("✓ Histogram buckets are in milliseconds")


if __name__ == "__main__":
    test_metrics_endpoint_basic_functionality()
    test_metrics_endpoint_opentelemetry_compatibility()
    print("\n🎉 All metrics endpoint verification tests passed!")