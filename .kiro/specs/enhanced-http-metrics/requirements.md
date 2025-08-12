# Enhanced HTTP Metrics Implementation Requirements

## Introduction

This feature implements standardized HTTP request metrics for the GlobeCo Portfolio Service to provide consistent observability across all microservices in the suite. The implementation will add three core HTTP metrics (requests total, request duration, and requests in flight) that complement the existing OpenTelemetry instrumentation without conflicting with it.

The service already has a `/metrics` endpoint via Prometheus client and sends metrics to the OpenTelemetry Collector. This enhancement will add the specific standardized HTTP metrics required by the GlobeCo microservices architecture while leveraging lessons learned from the implementation guide to avoid common pitfalls.

## Requirements

### Requirement 1

**User Story:** As a DevOps engineer, I want standardized HTTP request metrics collected from all microservices, so that I can monitor service performance consistently across the entire GlobeCo suite.

#### Acceptance Criteria

1. WHEN the service receives any HTTP request THEN the system SHALL increment the `http_requests_total` counter with labels for method, path, and status
2. WHEN the service processes any HTTP request THEN the system SHALL record the request duration in the `http_request_duration` histogram with labels for method, path, and status
3. WHEN the service begins processing an HTTP request THEN the system SHALL increment the `http_requests_in_flight` gauge
4. WHEN the service completes processing an HTTP request THEN the system SHALL decrement the `http_requests_in_flight` gauge
5. WHEN metrics are exported THEN the system SHALL use milliseconds as the base unit for duration metrics to ensure proper OpenTelemetry Collector interpretation

### Requirement 2

**User Story:** As a monitoring engineer, I want HTTP metrics to use consistent labeling and avoid high cardinality, so that the metrics remain efficient and don't overwhelm the monitoring system.

#### Acceptance Criteria

1. WHEN extracting the method label THEN the system SHALL use uppercase HTTP method names (GET, POST, PUT, DELETE, PATCH, HEAD, OPTIONS)
2. WHEN extracting the path label THEN the system SHALL use route patterns instead of actual URLs with parameters (e.g., "/api/v1/portfolio/{portfolioId}" instead of "/api/v1/portfolio/123")
3. WHEN extracting the status label THEN the system SHALL convert numeric HTTP status codes to strings ("200", "404", "500")
4. WHEN encountering unmatched routes THEN the system SHALL sanitize them to prevent high cardinality by parameterizing ID-like path segments
5. WHEN processing MongoDB ObjectIds in URLs THEN the system SHALL replace them with "{id}" parameter placeholders
6. WHEN processing UUID-format identifiers in URLs THEN the system SHALL replace them with "{id}" parameter placeholders

### Requirement 3

**User Story:** As a developer, I want the metrics collection to be implemented as middleware that doesn't interfere with existing functionality, so that the service continues to operate normally while providing enhanced observability.

#### Acceptance Criteria

1. WHEN implementing metrics collection THEN the system SHALL use FastAPI middleware that wraps all HTTP endpoints
2. WHEN metrics recording fails THEN the system SHALL log the error but continue processing the request normally
3. WHEN the middleware encounters exceptions during request processing THEN the system SHALL still record metrics with status "500"
4. WHEN the middleware processes requests THEN the system SHALL use high-precision timing (perf_counter) for millisecond accuracy
5. WHEN the middleware is added THEN the system SHALL ensure it doesn't conflict with existing OpenTelemetry instrumentation
6. WHEN the service starts up THEN the system SHALL pre-register metrics to prevent duplicate registration errors

### Requirement 4

**User Story:** As a site reliability engineer, I want the HTTP metrics to be compatible with the existing monitoring infrastructure, so that I can use them in dashboards and alerting without additional configuration.

#### Acceptance Criteria

1. WHEN metrics are exported THEN the system SHALL make them available via the existing `/metrics` endpoint using Prometheus format
2. WHEN the histogram metric is created THEN the system SHALL use buckets in milliseconds: [5, 10, 25, 50, 100, 250, 500, 1000, 2500, 5000, 10000]
3. WHEN metrics are collected THEN the system SHALL ensure they are compatible with the existing OpenTelemetry Collector configuration
4. WHEN the service is deployed THEN the system SHALL maintain single-process deployment to ensure consistent metrics (no multi-worker Gunicorn)
5. WHEN metrics are registered THEN the system SHALL use a global registry pattern to prevent duplicate registration during module reloads

### Requirement 5

**User Story:** As a developer, I want comprehensive error handling and logging for metrics collection, so that I can troubleshoot any issues with observability without affecting service functionality.

#### Acceptance Criteria

1. WHEN metrics collection encounters errors THEN the system SHALL log detailed error information including error type and context
2. WHEN duplicate metric registration occurs THEN the system SHALL handle it gracefully by creating dummy metrics to prevent service disruption
3. WHEN route pattern extraction fails THEN the system SHALL fall back to a safe default pattern to prevent metric collection failure
4. WHEN in-flight gauge operations fail THEN the system SHALL log the error and ensure the gauge doesn't become negative
5. WHEN debug logging is enabled THEN the system SHALL provide detailed information about metric recording for troubleshooting

### Requirement 6

**User Story:** As a quality assurance engineer, I want the metrics implementation to be thoroughly tested, so that I can verify the metrics are accurate and reliable.

#### Acceptance Criteria

1. WHEN unit tests are run THEN the system SHALL mock external metric exporters to prevent network calls during testing
2. WHEN integration tests are run THEN the system SHALL verify that all three metrics are created and registered correctly
3. WHEN load testing is performed THEN the system SHALL verify that metric counts match the actual number of requests processed
4. WHEN testing route pattern extraction THEN the system SHALL verify that portfolio-specific routes are properly parameterized
5. WHEN testing error scenarios THEN the system SHALL verify that metrics are still recorded for failed requests

### Requirement 7

**User Story:** As a service maintainer, I want the metrics implementation to be configurable, so that I can enable or disable metrics collection based on deployment requirements.

#### Acceptance Criteria

1. WHEN the `enable_metrics` configuration is set to false THEN the system SHALL skip metrics middleware setup
2. WHEN debug logging is enabled THEN the system SHALL provide verbose metrics collection information
3. WHEN the service starts THEN the system SHALL log the metrics configuration status
4. WHEN metrics are disabled THEN the system SHALL still maintain the `/metrics` endpoint for compatibility
5. WHEN configuration changes THEN the system SHALL not require code changes to enable or disable metrics collection