"""
Integration tests for metrics endpoint compatibility.

These tests verify that the /metrics endpoint includes new HTTP metrics,
outputs in correct Prometheus format, and is compatible with existing
OpenTelemetry Collector configuration.
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from unittest.mock import Mock, patch, MagicMock
import os
import re

# Set test environment variables
os.environ['PROMETHEUS_DISABLE_CREATED_SERIES'] = 'True'

from app.monitoring import (
    EnhancedHTTPMetricsMiddleware,
    HTTP_REQUESTS_TOTAL,
    HTTP_REQUEST_DURATION,
    HTTP_REQUESTS_IN_FLIGHT,
    clear_metrics_registry
)


class TestMetricsEndpointCompatibility:
    """Test metrics endpoint compatibility and format."""
    
    @pytest.fixture
    def test_app(self):
        """Create a test FastAPI app with metrics middleware and endpoint."""
        # Clear metrics before creating app to ensure clean state
        clear_metrics_registry()
        
        app = FastAPI()
        
        # Add metrics middleware
        app.add_middleware(EnhancedHTTPMetricsMiddleware, debug_logging=False)
        
        # Add Prometheus /metrics endpoint
        from prometheus_client import make_asgi_app
        metrics_app = make_asgi_app()
        app.mount("/metrics", metrics_app)
        
        # Add test endpoints
        @app.get("/test")
        async def test_endpoint():
            return {"message": "test"}
        
        @app.get("/health")
        async def health_endpoint():
            return {"status": "healthy"}
        
        @app.get("/api/v1/portfolio/{portfolio_id}")
        async def get_portfolio(portfolio_id: str):
            return {"portfolioId": portfolio_id, "name": "Test Portfolio"}
        
        @app.get("/api/v2/portfolios")
        async def search_portfolios():
            return {"portfolios": []}
        
        yield app
        
        # Cleanup
        clear_metrics_registry()
    
    def test_metrics_endpoint_exists(self, test_app):
        """Test that /metrics endpoint exists and returns data."""
        client = TestClient(test_app)
        
        # Make some requests to generate metrics
        client.get("/test")
        client.get("/health")
        
        # Check metrics endpoint
        response = client.get("/metrics")
        
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/plain")
        assert len(response.text) > 0
    
    def test_metrics_endpoint_includes_http_metrics(self, test_app):
        """Test that /metrics endpoint includes the new HTTP metrics."""
        client = TestClient(test_app)
        
        # Make requests to generate metrics
        client.get("/test")
        client.get("/health")
        client.get("/api/v1/portfolio/507f1f77bcf86cd799439011")
        
        # Get metrics output
        response = client.get("/metrics")
        metrics_text = response.text
        
        # Check for HTTP requests total metric
        assert "http_requests_total" in metrics_text
        assert 'method="GET"' in metrics_text
        assert 'path="/test"' in metrics_text
        assert 'status="200"' in metrics_text
        
        # Check for HTTP request duration metric
        assert "http_request_duration" in metrics_text
        assert "http_request_duration_bucket" in metrics_text
        assert "http_request_duration_count" in metrics_text
        assert "http_request_duration_sum" in metrics_text
        
        # Check for HTTP requests in flight metric
        assert "http_requests_in_flight" in metrics_text
    
    def test_metrics_prometheus_text_format(self, test_app):
        """Test that metrics output matches Prometheus text format expectations."""
        client = TestClient(test_app)
        
        # Make requests to generate metrics
        client.get("/test")
        client.get("/health")
        
        # Get metrics output
        response = client.get("/metrics")
        metrics_text = response.text
        
        # Check Prometheus text format patterns
        lines = metrics_text.split('\n')
        
        # Find HELP and TYPE comments for our metrics
        help_lines = [line for line in lines if line.startswith('# HELP')]
        type_lines = [line for line in lines if line.startswith('# TYPE')]
        
        # Check for HTTP requests total
        http_requests_total_help = any('http_requests_total' in line for line in help_lines)
        http_requests_total_type = any('http_requests_total counter' in line for line in type_lines)
        assert http_requests_total_help, "Missing HELP comment for http_requests_total"
        assert http_requests_total_type, "Missing TYPE comment for http_requests_total"
        
        # Check for HTTP request duration
        http_request_duration_help = any('http_request_duration' in line for line in help_lines)
        http_request_duration_type = any('http_request_duration histogram' in line for line in type_lines)
        assert http_request_duration_help, "Missing HELP comment for http_request_duration"
        assert http_request_duration_type, "Missing TYPE comment for http_request_duration"
        
        # Check for HTTP requests in flight
        http_requests_in_flight_help = any('http_requests_in_flight' in line for line in help_lines)
        http_requests_in_flight_type = any('http_requests_in_flight gauge' in line for line in type_lines)
        assert http_requests_in_flight_help, "Missing HELP comment for http_requests_in_flight"
        assert http_requests_in_flight_type, "Missing TYPE comment for http_requests_in_flight"
        
        # Check metric value format (should be: metric_name{labels} value)
        metric_lines = [line for line in lines if not line.startswith('#') and line.strip()]
        
        for line in metric_lines:
            if 'http_requests_total' in line or 'http_request_duration' in line or 'http_requests_in_flight' in line:
                # Should match pattern: metric_name{labels} value
                # Note: labels can contain curly braces in values (e.g., path="/api/v1/portfolio/{portfolioId}")
                assert re.match(r'^[a-zA-Z_:][a-zA-Z0-9_:]*(\{.*\})?\s+[0-9.+\-eE]+$', line), f"Invalid metric format: {line}"
    
    def test_metrics_histogram_buckets(self, test_app):
        """Test that histogram metrics include correct millisecond buckets."""
        client = TestClient(test_app)
        
        # Make requests to generate metrics
        client.get("/test")
        
        # Get metrics output
        response = client.get("/metrics")
        metrics_text = response.text
        
        # Check for histogram buckets in milliseconds
        expected_buckets = [5, 10, 25, 50, 100, 250, 500, 1000, 2500, 5000, 10000]
        
        for bucket in expected_buckets:
            bucket_pattern = f'http_request_duration_bucket{{.*le="{bucket}.*"}}'
            assert re.search(bucket_pattern, metrics_text), f"Missing bucket for {bucket}ms"
        
        # Check for +Inf bucket
        inf_pattern = r'http_request_duration_bucket\{.*le="\+Inf".*\}'
        assert re.search(inf_pattern, metrics_text), "Missing +Inf bucket"
    
    def test_metrics_route_patterns(self, test_app):
        """Test that route patterns are properly parameterized in metrics."""
        client = TestClient(test_app)
        
        # Make requests with different IDs
        client.get("/api/v1/portfolio/507f1f77bcf86cd799439011")  # MongoDB ObjectId
        client.get("/api/v1/portfolio/550e8400-e29b-41d4-a716-446655440000")  # UUID
        client.get("/api/v1/portfolio/12345")  # Numeric ID
        
        # Get metrics output
        response = client.get("/metrics")
        metrics_text = response.text
        
        # Should see parameterized route pattern, not actual IDs
        assert 'path="/api/v1/portfolio/{portfolioId}"' in metrics_text
        
        # Should NOT see actual IDs in metrics
        assert "507f1f77bcf86cd799439011" not in metrics_text
        assert "550e8400-e29b-41d4-a716-446655440000" not in metrics_text
        assert 'path="/api/v1/portfolio/12345"' not in metrics_text
    
    def test_metrics_label_consistency(self, test_app):
        """Test that metric labels are consistent and properly formatted."""
        client = TestClient(test_app)
        
        # Make requests with different methods and status codes
        client.get("/test")  # GET 200
        client.post("/test")  # POST 405 (method not allowed)
        
        # Get metrics output
        response = client.get("/metrics")
        metrics_text = response.text
        
        # Check method labels are uppercase
        assert 'method="GET"' in metrics_text
        assert 'method="POST"' in metrics_text
        assert 'method="get"' not in metrics_text  # Should not have lowercase
        
        # Check status labels are strings
        assert 'status="200"' in metrics_text
        assert 'status="405"' in metrics_text
        assert 'status=200' not in metrics_text  # Should not be numeric
        
        # Check path labels are consistent
        assert 'path="/test"' in metrics_text
    
    def test_metrics_counter_accuracy(self, test_app):
        """Test that counter metrics accurately reflect request counts."""
        client = TestClient(test_app)
        
        # Make specific number of requests
        for _ in range(3):
            client.get("/test")
        
        for _ in range(2):
            client.get("/health")
        
        # Get metrics output
        response = client.get("/metrics")
        metrics_text = response.text
        
        # Parse counter values - use more specific regex to avoid matching other metrics
        test_counter_match = re.search(r'http_requests_total\{method="GET",path="/test",status="200"\}\s+([0-9.]+)', metrics_text)
        health_counter_match = re.search(r'http_requests_total\{method="GET",path="/health",status="200"\}\s+([0-9.]+)', metrics_text)
        
        assert test_counter_match, "Could not find test endpoint counter"
        assert health_counter_match, "Could not find health endpoint counter"
        
        test_count = float(test_counter_match.group(1))
        health_count = float(health_counter_match.group(1))
        
        # Allow for some tolerance since metrics might be accumulated from other tests
        assert test_count >= 3, f"Expected at least 3 requests to /test, got {test_count}"
        assert health_count >= 2, f"Expected at least 2 requests to /health, got {health_count}"
    
    def test_metrics_histogram_consistency(self, test_app):
        """Test that histogram count matches counter values."""
        client = TestClient(test_app)
        
        # Make requests
        for _ in range(5):
            client.get("/test")
        
        # Get metrics output
        response = client.get("/metrics")
        metrics_text = response.text
        
        # Parse counter and histogram count values - use more specific regex
        counter_match = re.search(r'http_requests_total\{method="GET",path="/test",status="200"\}\s+([0-9.]+)', metrics_text)
        histogram_count_match = re.search(r'http_request_duration_count\{method="GET",path="/test",status="200"\}\s+([0-9.]+)', metrics_text)
        
        assert counter_match, "Could not find counter metric"
        assert histogram_count_match, "Could not find histogram count metric"
        
        counter_value = float(counter_match.group(1))
        histogram_count_value = float(histogram_count_match.group(1))
        
        assert counter_value == histogram_count_value, f"Counter ({counter_value}) and histogram count ({histogram_count_value}) should match"
        assert counter_value >= 5, f"Expected at least 5 requests, got {counter_value}"
    
    def test_metrics_in_flight_gauge(self, test_app):
        """Test that in-flight gauge returns to zero after requests complete."""
        client = TestClient(test_app)
        
        # Make a request
        client.get("/test")
        
        # Get metrics output - this request itself might be in flight
        response = client.get("/metrics")
        metrics_text = response.text
        
        # Parse in-flight gauge value
        in_flight_match = re.search(r'http_requests_in_flight\s+([0-9.]+)', metrics_text)
        
        assert in_flight_match, "Could not find in-flight gauge metric"
        
        in_flight_value = float(in_flight_match.group(1))
        
        # Should be 0 or 1 (if the /metrics request itself is being processed)
        # Since we're calling /metrics to get the gauge value, it might show 1
        assert in_flight_value <= 1.0, f"Expected in-flight gauge to be 0 or 1, got {in_flight_value}"
    
    def test_metrics_no_conflicts_with_existing_prometheus(self, test_app):
        """Test that new metrics don't conflict with existing prometheus_client usage."""
        client = TestClient(test_app)
        
        # Make requests to generate metrics
        client.get("/test")
        
        # Get metrics output
        response = client.get("/metrics")
        
        # Should succeed without errors
        assert response.status_code == 200
        
        # Should contain our metrics
        metrics_text = response.text
        assert "http_requests_total" in metrics_text
        assert "http_request_duration" in metrics_text
        assert "http_requests_in_flight" in metrics_text
        
        # Should not contain duplicate or conflicting metrics
        lines = metrics_text.split('\n')
        metric_names = set()
        
        for line in lines:
            if line.startswith('# TYPE'):
                parts = line.split()
                if len(parts) >= 3:
                    metric_name = parts[2]
                    assert metric_name not in metric_names, f"Duplicate metric type definition: {metric_name}"
                    metric_names.add(metric_name)
    
    def test_metrics_endpoint_content_type(self, test_app):
        """Test that /metrics endpoint returns correct content type."""
        client = TestClient(test_app)
        
        response = client.get("/metrics")
        
        assert response.status_code == 200
        
        # Prometheus metrics should be text/plain
        content_type = response.headers.get("content-type", "")
        assert content_type.startswith("text/plain"), f"Expected text/plain content type, got {content_type}"
    
    def test_metrics_endpoint_with_query_parameters(self, test_app):
        """Test that /metrics endpoint works with query parameters."""
        client = TestClient(test_app)
        
        # Make request to generate metrics
        client.get("/test")
        
        # Test metrics endpoint with query parameters (some collectors use these)
        response = client.get("/metrics?name[]=http_requests_total")
        
        assert response.status_code == 200
        assert "http_requests_total" in response.text
    
    def test_metrics_opentelemetry_collector_compatibility(self, test_app):
        """Test metrics format is compatible with OpenTelemetry Collector expectations."""
        client = TestClient(test_app)
        
        # Make requests to generate metrics
        client.get("/test")
        client.get("/health")
        
        # Get metrics output
        response = client.get("/metrics")
        metrics_text = response.text
        
        # OpenTelemetry Collector expects specific format for histograms
        # Check that histogram metrics include all required components
        
        # Should have histogram buckets
        assert "http_request_duration_bucket" in metrics_text
        
        # Should have histogram count
        assert "http_request_duration_count" in metrics_text
        
        # Should have histogram sum
        assert "http_request_duration_sum" in metrics_text
        
        # Duration should be in milliseconds (not seconds) for proper OTel interpretation
        # Check that sum values are reasonable for millisecond timing
        sum_matches = re.findall(r'http_request_duration_sum\{.*\}\s+([0-9.+\-eE]+)', metrics_text)
        
        for sum_value in sum_matches:
            duration_sum = float(sum_value)
            # Should be reasonable millisecond values (> 0.1ms, < 10000ms for simple requests)
            assert 0.1 <= duration_sum <= 10000, f"Duration sum {duration_sum}ms seems unreasonable"
    
    def test_metrics_consistency_across_requests(self, test_app):
        """Test that metrics remain consistent across multiple requests to /metrics endpoint."""
        client = TestClient(test_app)
        
        # Make some requests to generate metrics
        client.get("/test")
        client.get("/health")
        
        # Get metrics multiple times
        response1 = client.get("/metrics")
        response2 = client.get("/metrics")
        
        assert response1.status_code == 200
        assert response2.status_code == 200
        
        # Parse counter values from both responses - use more specific pattern
        counter_pattern = r'http_requests_total\{method="GET",path="/test",status="200"\}\s+([0-9.]+)'
        
        match1 = re.search(counter_pattern, response1.text)
        match2 = re.search(counter_pattern, response2.text)
        
        assert match1, "Could not find counter in first response"
        assert match2, "Could not find counter in second response"
        
        count1 = float(match1.group(1))
        count2 = float(match2.group(1))
        
        # Counter values should be the same (no additional requests to /test were made)
        # Note: /metrics requests themselves will increment counters for /metrics endpoint
        assert count1 == count2, f"Counter values should be consistent: {count1} vs {count2}"


class TestMetricsEndpointErrorHandling:
    """Test error handling in metrics endpoint."""
    
    @pytest.fixture
    def test_app_with_errors(self):
        """Create a test app that can generate errors."""
        # Clear metrics before creating app to ensure clean state
        clear_metrics_registry()
        
        app = FastAPI()
        
        # Add metrics middleware
        app.add_middleware(EnhancedHTTPMetricsMiddleware, debug_logging=False)
        
        # Add Prometheus /metrics endpoint
        from prometheus_client import make_asgi_app
        metrics_app = make_asgi_app()
        app.mount("/metrics", metrics_app)
        
        # Add endpoint that raises an error
        @app.get("/error")
        async def error_endpoint():
            raise ValueError("Test error")
        
        # Add endpoint that returns 404
        @app.get("/notfound")
        async def notfound_endpoint():
            from fastapi import HTTPException
            raise HTTPException(status_code=404, detail="Not found")
        
        yield app
        
        # Cleanup
        clear_metrics_registry()
    
    def test_metrics_include_error_responses(self, test_app_with_errors):
        """Test that metrics include error responses with correct status codes."""
        client = TestClient(test_app_with_errors)
        
        # Make requests that will generate errors - catch exceptions for 500 errors
        try:
            response_error = client.get("/error")
        except Exception:
            # The middleware should still record metrics even if the request fails
            pass
        
        response_notfound = client.get("/notfound")
        assert response_notfound.status_code == 404
        
        # Get metrics output
        response = client.get("/metrics")
        metrics_text = response.text
        
        # Should include metrics for error responses
        assert 'status="500"' in metrics_text
        assert 'status="404"' in metrics_text
        
        # Should still record duration for error responses
        assert re.search(r'http_request_duration_count\{.*status="500".*\}\s+[0-9.]+', metrics_text)
        assert re.search(r'http_request_duration_count\{.*status="404".*\}\s+[0-9.]+', metrics_text)
    
    def test_metrics_endpoint_survives_metric_errors(self, test_app_with_errors):
        """Test that /metrics endpoint works even if some metrics have errors."""
        client = TestClient(test_app_with_errors)
        
        # Make a normal request first
        client.get("/notfound")
        
        # Mock one of the metrics to raise an error during collection
        with patch('app.monitoring.HTTP_REQUESTS_TOTAL') as mock_counter:
            # Make the counter raise an error during collection
            mock_counter.collect.side_effect = Exception("Metric collection error")
            
            # Metrics endpoint should still work
            response = client.get("/metrics")
            
            # Should still return 200 (prometheus_client handles collection errors gracefully)
            assert response.status_code == 200


class TestMetricsImplementationGuideConsistency:
    """Test consistency with the HTTP metrics implementation guide."""
    
    @pytest.fixture
    def test_app(self):
        """Create a test app for implementation guide consistency tests."""
        # Clear metrics before creating app to ensure clean state
        clear_metrics_registry()
        
        app = FastAPI()
        
        # Add metrics middleware
        app.add_middleware(EnhancedHTTPMetricsMiddleware, debug_logging=False)
        
        # Add Prometheus /metrics endpoint
        from prometheus_client import make_asgi_app
        metrics_app = make_asgi_app()
        app.mount("/metrics", metrics_app)
        
        # Add test endpoints
        @app.get("/test")
        async def test_endpoint():
            return {"message": "test"}
        
        yield app
        
        # Cleanup
        clear_metrics_registry()
    
    def test_millisecond_buckets_consistency(self, test_app):
        """Test that histogram buckets match implementation guide specification."""
        client = TestClient(test_app)
        
        # Make request to generate metrics
        client.get("/test")
        
        # Get metrics output
        response = client.get("/metrics")
        metrics_text = response.text
        
        # Implementation guide specifies these exact buckets in milliseconds
        expected_buckets = [5, 10, 25, 50, 100, 250, 500, 1000, 2500, 5000, 10000]
        
        for bucket in expected_buckets:
            bucket_pattern = f'http_request_duration_bucket{{.*le="{bucket}.*"}}'
            assert re.search(bucket_pattern, metrics_text), f"Missing bucket for {bucket}ms as specified in implementation guide"
    
    def test_metric_names_consistency(self, test_app):
        """Test that metric names match implementation guide specification."""
        client = TestClient(test_app)
        
        # Make request to generate metrics
        client.get("/test")
        
        # Get metrics output
        response = client.get("/metrics")
        metrics_text = response.text
        
        # Implementation guide specifies these exact metric names
        assert "http_requests_total" in metrics_text, "Missing http_requests_total as specified in implementation guide"
        assert "http_request_duration" in metrics_text, "Missing http_request_duration as specified in implementation guide"
        assert "http_requests_in_flight" in metrics_text, "Missing http_requests_in_flight as specified in implementation guide"
    
    def test_label_format_consistency(self, test_app):
        """Test that label formats match implementation guide specification."""
        client = TestClient(test_app)
        
        # Make request to generate metrics
        client.get("/test")
        
        # Get metrics output
        response = client.get("/metrics")
        metrics_text = response.text
        
        # Implementation guide specifies method, path, status labels for counter and histogram
        counter_pattern = r'http_requests_total\{method="[A-Z]+",path="[^"]+",status="\d+"\}'
        histogram_pattern = r'http_request_duration_\w+\{method="[A-Z]+",path="[^"]+",status="\d+"\}'
        
        assert re.search(counter_pattern, metrics_text), "Counter labels don't match implementation guide format"
        assert re.search(histogram_pattern, metrics_text), "Histogram labels don't match implementation guide format"
        
        # In-flight gauge should have no labels as per implementation guide
        gauge_pattern = r'http_requests_in_flight\s+\d+(?:\.\d+)?'
        assert re.search(gauge_pattern, metrics_text), "In-flight gauge format doesn't match implementation guide"