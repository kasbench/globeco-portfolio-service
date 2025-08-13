# Implementation Plan

- [x] 1. Configure settings and validate deployment for consistent metrics
  - Add `enable_metrics` configuration setting to Settings class in `app/config.py`
  - Verify current deployment uses single-process uvicorn (not multi-worker gunicorn) to prevent inconsistent metrics
  - Add environment variable support for metrics configuration
  - Review #[[file:documentation/http-metrics-implementation-guide-python.md]] for consistency.
  - _Requirements: 4.4, 7.1, 7.3_

- [x] 2. Create core monitoring module with metrics registry system
  - Create `app/monitoring.py` module with global metrics registry to prevent duplicate registration
  - Implement `_get_or_create_metric()` function with duplicate registration error handling
  - Create dummy metric class for graceful fallback when registration fails
  - Add comprehensive error logging for metric creation issues
  - Write unit tests for metrics registry system and duplicate handling
  - Review #[[file:documentation/http-metrics-implementation-guide-python.md]] for consistency.
  - _Requirements: 3.6, 5.2, 5.3_

- [x] 3. Implement core HTTP metrics with Prometheus client
  - Define `HTTP_REQUESTS_TOTAL` counter with method, path, status labels
  - Define `HTTP_REQUEST_DURATION` histogram with millisecond buckets [5, 10, 25, 50, 100, 250, 500, 1000, 2500, 5000, 10000]
  - Define `HTTP_REQUESTS_IN_FLIGHT` gauge without labels
  - Use global registry system to create metrics safely
  - Write unit tests to verify metric creation and properties
  - Review #[[file:documentation/http-metrics-implementation-guide-python.md]] for consistency.
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 4.2_

- [x] 4. Implement portfolio-specific route pattern extraction
  - Create `_extract_route_pattern()` method with portfolio service specific patterns
  - Implement `_extract_portfolio_v1_route_pattern()` for `/api/v1/portfolio/{portfolioId}` routes
  - Implement `_extract_portfolio_v2_route_pattern()` for `/api/v2/portfolios` routes
  - Handle health check, metrics, and root endpoints
  - Add fallback to `_sanitize_unmatched_route()` for unknown patterns
  - Write comprehensive unit tests for all route pattern scenarios
  - Review #[[file:documentation/http-metrics-implementation-guide-python.md]] for consistency.
  - _Requirements: 2.2, 2.5, 2.6_

- [x] 5. Implement ID detection and sanitization logic
  - Create `_looks_like_id()` method to detect MongoDB ObjectIds (24-char hex)
  - Add UUID detection (with and without hyphens)
  - Add numeric ID detection
  - Add alphanumeric ID detection for long identifiers
  - Implement `_sanitize_unmatched_route()` with ID parameterization
  - Write unit tests for ID detection with various formats
  - Review #[[file:documentation/http-metrics-implementation-guide-python.md]] for consistency.
  - _Requirements: 2.2, 2.5, 2.6_

- [x] 6. Implement label formatting and validation
  - Create `_get_method_label()` method to format HTTP methods as uppercase
  - Create `_format_status_code()` method to convert status codes to strings
  - Add validation for method and status code ranges
  - Implement error handling with fallback to safe defaults
  - Write unit tests for label formatting edge cases
  - Review #[[file:documentation/http-metrics-implementation-guide-python.md]] for consistency.
  - _Requirements: 2.1, 2.3, 5.4_

- [x] 7. Create EnhancedHTTPMetricsMiddleware class
  - Implement `BaseHTTPMiddleware` subclass for metrics collection
  - Add high-precision timing using `time.perf_counter()` for millisecond accuracy
  - Implement in-flight gauge increment/decrement with error protection
  - Add exception handling to ensure metrics are recorded for failed requests
  - Create `_record_metrics()` method with comprehensive error handling
  - Write unit tests for middleware timing and error scenarios
  - Review #[[file:documentation/http-metrics-implementation-guide-python.md]] for consistency.
  - _Requirements: 1.4, 3.1, 3.3, 3.4, 5.1, 5.4_

- [x] 8. Implement metrics recording with error handling
  - Complete `_record_metrics()` method to record all three metrics safely
  - Add try-catch blocks around each metric recording operation
  - Implement detailed error logging with context information
  - Add debug logging for successful metric recording
  - Ensure metrics are recorded even when individual operations fail
  - Write unit tests for metric recording error scenarios
  - Review #[[file:documentation/http-metrics-implementation-guide-python.md]] for consistency.
  - _Requirements: 3.2, 5.1, 5.5_

- [ ] 9. Integrate middleware with FastAPI application
  - Modify `app/main.py` to add `EnhancedHTTPMetricsMiddleware` after `LoggingMiddleware`
  - Add conditional middleware registration based on `enable_metrics` setting
  - Ensure middleware is positioned before existing OpenTelemetry instrumentation
  - Verify middleware applies to all endpoints including health checks
  - Write integration tests to verify middleware is properly registered
  - Review #[[file:documentation/http-metrics-implementation-guide-python.md]] for consistency.
  - _Requirements: 3.1, 3.5, 7.1, 7.4_

- [ ] 10. Verify metrics endpoint compatibility
  - Confirm existing `/metrics` endpoint includes new HTTP metrics
  - Test metrics output format matches Prometheus text format expectations
  - Verify metrics are compatible with existing OpenTelemetry Collector configuration
  - Ensure no conflicts with existing prometheus_client usage
  - Write integration tests to validate `/metrics` endpoint output
  - Review #[[file:documentation/http-metrics-implementation-guide-python.md]] for consistency.
  - _Requirements: 4.1, 4.3_

- [ ] 11. Add comprehensive error handling and logging
  - Implement structured logging for all metrics operations using existing `get_logger`
  - Add debug logging configuration support via `metrics_debug_logging` setting
  - Ensure all error scenarios are logged with appropriate context
  - Add slow request detection and logging (>1000ms)
  - Write tests to verify logging behavior in various scenarios
  - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 7.2_

- [ ] 12. Create unit tests for metrics collection
  - Write tests for middleware request processing with mocked metrics
  - Test route pattern extraction for all portfolio service endpoints
  - Test error handling scenarios including metric recording failures
  - Test in-flight gauge increment/decrement behavior
  - Mock external dependencies to prevent network calls during testing
  - _Requirements: 6.1, 6.2, 6.4_

- [ ] 13. Create integration tests for end-to-end validation
  - Write tests that make actual HTTP requests and verify metric recording
  - Test all portfolio service endpoints (v1 and v2 APIs)
  - Verify metric counts match actual request counts
  - Test concurrent request handling and metric accuracy
  - Validate `/metrics` endpoint returns expected metric data
  - _Requirements: 6.2, 6.3, 6.5_

- [ ] 14. Add configuration documentation and validation
  - Document all new configuration options in code comments
  - Add validation for configuration values
  - Ensure graceful handling when metrics are disabled
  - Test configuration changes don't require code modifications
  - Write tests for configuration validation and edge cases
  - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5_

- [ ] 15. Final integration and deployment validation
  - Verify single-process deployment configuration is maintained
  - Test metrics collection under load to ensure accuracy
  - Validate metrics are properly exported to OpenTelemetry Collector
  - Confirm no performance degradation from metrics collection
  - Document any deployment considerations or requirements
  - _Requirements: 4.4, 6.3_