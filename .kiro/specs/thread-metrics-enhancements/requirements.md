# Thread Metrics Enhancement Requirements

## Introduction

This feature implements thread worker metrics for the GlobeCo Portfolio Service to provide visibility into thread pool utilization and request queuing behavior. These metrics will help understand service capacity and identify when the service can no longer process incoming requests due to thread exhaustion.

The service already has HTTP request metrics and a `/metrics` endpoint via Prometheus client. This enhancement adds four specific thread-related metrics that complement the existing monitoring infrastructure while leveraging the existing scaffolding to avoid breaking current metrics or pipelines.  These new metrics will be visible on /metrics and exported to the OpenTelemetry Collector.  This is the way all custom metrics work currently.

## Requirements

### Requirement 1

**User Story:** As a DevOps engineer, I want to monitor thread pool utilization in real-time, so that I can understand when the service is approaching capacity limits and may start rejecting requests.

#### Acceptance Criteria

1. WHEN the service is running THEN the system SHALL expose `http.workers.active` metric showing the number of threads currently executing requests
2. WHEN the service is running THEN the system SHALL expose `http.workers.total` metric showing the total number of threads currently alive in the thread pool
3. WHEN the service is running THEN the system SHALL expose `http.workers.max_configured` metric showing the maximum number of threads that can be created
4. WHEN requests are queued waiting for available threads THEN the system SHALL expose `http_requests_queued` metric showing the number of pending requests
5. WHEN metrics are collected THEN the system SHALL use the existing Prometheus client and `/metrics` endpoint infrastructure

### Requirement 2

**User Story:** As a site reliability engineer, I want accurate thread state detection, so that I can distinguish between threads that are actively processing work versus threads that are idle and waiting for work.

#### Acceptance Criteria

1. WHEN counting active workers THEN the system SHALL only count threads with status "RUNNING" or "BUSY" that are actively processing requests
2. WHEN counting total workers THEN the system SHALL count all threads in the pool regardless of state (idle, busy, waiting, blocked)
3. WHEN determining thread activity THEN the system SHALL exclude threads that are waiting for work or in idle state from the active count
4. WHEN a thread accepts a connection and begins processing THEN the system SHALL include it in the active worker count
5. WHEN a thread completes request processing and returns to idle THEN the system SHALL exclude it from the active worker count

### Requirement 3

**User Story:** As a monitoring engineer, I want thread metrics to integrate seamlessly with existing monitoring infrastructure, so that I can use them in dashboards and alerting without additional configuration changes.

#### Acceptance Criteria

1. WHEN thread metrics are implemented THEN the system SHALL use the existing Prometheus client library and metrics registry
2. WHEN thread metrics are exposed THEN the system SHALL make them available via the existing `/metrics` endpoint
3. WHEN thread metrics are collected THEN the system SHALL ensure compatibility with the existing OpenTelemetry Collector configuration
4. WHEN thread metrics are added THEN the system SHALL not break or interfere with existing HTTP request metrics
5. WHEN the service starts THEN the system SHALL register thread metrics using the same patterns as existing custom metrics

### Requirement 4

**User Story:** As a developer, I want thread metrics implementation to work with Python's threading model and FastAPI/Uvicorn architecture, so that the metrics accurately reflect the actual thread pool behavior.

#### Acceptance Criteria

1. WHEN implementing thread detection THEN the system SHALL work with Python's threading module and thread enumeration
2. WHEN detecting active threads THEN the system SHALL identify threads that are processing HTTP requests or performing work
3. WHEN counting thread pool size THEN the system SHALL account for Uvicorn's thread pool management
4. WHEN measuring queue depth THEN the system SHALL detect requests waiting for thread assignment
5. WHEN the service uses single-process deployment THEN the system SHALL provide accurate thread counts for that process

### Requirement 5

**User Story:** As a performance analyst, I want thread metrics to update frequently enough to detect capacity issues, so that I can identify thread exhaustion scenarios before they impact service availability.

#### Acceptance Criteria

1. WHEN thread metrics are collected THEN the system SHALL update them at least every time the `/metrics` endpoint is scraped
2. WHEN thread state changes occur THEN the system SHALL reflect these changes in the next metrics collection cycle
3. WHEN all threads are busy THEN the system SHALL accurately report `http.workers.active` equals `http.workers.total`
4. WHEN requests are queued THEN the system SHALL increment `http_requests_queued` to reflect pending work
5. WHEN queued requests are assigned to threads THEN the system SHALL decrement `http_requests_queued` accordingly

### Requirement 6

**User Story:** As a system administrator, I want thread metrics to provide actionable insights for capacity planning, so that I can make informed decisions about scaling and resource allocation.

#### Acceptance Criteria

1. WHEN `http.workers.active` approaches `http.workers.max_configured` THEN the system SHALL provide early warning of capacity limits
2. WHEN `http_requests_queued` is greater than zero THEN the system SHALL indicate that requests are waiting for available threads
3. WHEN thread utilization is high THEN the system SHALL provide data to support scaling decisions
4. WHEN comparing `http.workers.total` to `http.workers.max_configured` THEN the system SHALL show current vs maximum thread pool size
5. WHEN analyzing thread metrics over time THEN the system SHALL provide data suitable for capacity planning and trend analysis

### Requirement 7

**User Story:** As a service maintainer, I want thread metrics implementation to be robust and handle edge cases gracefully, so that metrics collection doesn't impact service stability or performance.

#### Acceptance Criteria

1. WHEN thread enumeration fails THEN the system SHALL log the error and return safe default values
2. WHEN thread state detection encounters errors THEN the system SHALL continue metrics collection for other thread metrics
3. WHEN the thread pool is in transition states THEN the system SHALL handle temporary inconsistencies gracefully
4. WHEN metrics collection takes too long THEN the system SHALL not block request processing
5. WHEN debugging is needed THEN the system SHALL provide detailed logging about thread detection and counting logic