# Microservices HTTP Metrics Requirements

## Overview

All microservices must implement standardized HTTP request metrics that can be exported to the OpenTelemetry (Otel) Collector. These metrics provide consistent observability across services regardless of implementation language or framework.

## Required Metrics

### 1. HTTP Requests Total Counter

- **Metric Name**: `http_requests_total`
- **Type**: Counter
- **Description**: "Total number of HTTP requests"
- **Labels**:
    - `method`: HTTP method (GET, POST, PUT, DELETE, etc.)
    - `path`: Request path/route (e.g., "/api/users", "/health") _(Note: May be transformed from `endpoint` by OTel pipeline)_
    - `status`: HTTP status code as string (e.g., "200", "404", "500")
- **Behavior**: Increment by 1 for each completed HTTP request

### 2. HTTP Request Duration Histogram

- **Metric Name**: `http_request_duration`.  The OpenTelemetry Collector or Prometheus will rename this to http_request_duration_seconds or http_request_duration_milliseconds.  The behavior between the OpenTelemetry Collector and Prometheus are not consistent.  There are also differences between frameworks.  For example, Micrometer in Java seems to always produce metrics in milliseconds.  Rather than trying to force consistency, which has so far been unsuccessful, we will normalize in Grafana or further downstream.  **If possible, please generate this metrics in milliseconds.  In order for the OpenTelemetry Collector to interpret this as milliseconds, the base unit must be milliseconds.**
- **Type**: Histogram
- **Description**: "Duration of HTTP requests."
- **Labels**:
    - `method`: HTTP method (GET, POST, PUT, DELETE, etc.)
    - `path`: Request path/route (e.g., "/api/users", "/health") _(Note: May be transformed from `endpoint` by OTel pipeline)_
    - `status`: HTTP status code as string (e.g., "200", "404", "500")
- **Unit**: Seconds (floating point) or Milliseconds (see above.)
- **Buckets**: Use framework/library default histogram buckets or equivalent to: [0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10] in seconds or [5, 10, 25, 50, 100, 250, 500, 1000, 2500, 5000, 10000] in milliseconds (preferred)
- **Behavior**: Record the duration of each HTTP request from start to completion

### 3. HTTP Requests In Flight Gauge

- **Metric Name**: `http_requests_in_flight`
- **Type**: Gauge
- **Description**: "Number of HTTP requests currently being processed"
- **Labels**: None
- **Behavior**:
    - Increment when request processing begins
    - Decrement when request processing completes (regardless of success/failure)


### 4. If not already supported in the language, implement a metrics endpoint (/metrics) for the collector to scrape (note: we are currently feeding the OpenTelementry collector.  This is a backup, if needed.  Do not make changes to the Kubernetes manifest to support this.  I will do it later, if necessary.).  In Java, Spring Boot exposes an /actuator/prometheus endpoint, so this step is unnecessary.  Do not build anything custom if the language or tools already support this capability (most do).

- **Description**: "Endpoint for the collector to scrape metrics"
- **Behavior**: Return the metrics in a format compatible with the Otel Collector (e.g., Prometheus text format)
- **Sample**:
    ```
    # HELP go_sched_gomaxprocs_threads The current runtime.GOMAXPROCS setting, or the number of operating system threads that can execute user-level Go code simultaneously. Sourced from /sched/gomaxprocs:threads.
    # TYPE go_sched_gomaxprocs_threads gauge
    go_sched_gomaxprocs_threads 16
    # HELP go_threads Number of OS threads created.
    # TYPE go_threads gauge
    go_threads 12
    # HELP http_request_duration_milliseconds Duration of HTTP requests in milliseconds
    # TYPE http_request_duration_milliseconds histogram
    http_request_duration_milliseconds_bucket{endpoint="/healthz",method="GET",status="200",le="0.005"} 0
    http_request_duration_milliseconds_bucket{endpoint="/healthz",method="GET",status="200",le="0.01"} 0
    http_request_duration_milliseconds_bucket{endpoint="/healthz",method="GET",status="200",le="0.025"} 0
    http_request_duration_milliseconds_bucket{endpoint="/healthz",method="GET",status="200",le="0.05"} 0
    http_request_duration_milliseconds_bucket{endpoint="/healthz",method="GET",status="200",le="0.1"} 15
    http_request_duration_milliseconds_bucket{endpoint="/healthz",method="GET",status="200",le="0.25"} 88
    http_request_duration_milliseconds_bucket{endpoint="/healthz",method="GET",status="200",le="0.5"} 90
    http_request_duration_milliseconds_bucket{endpoint="/healthz",method="GET",status="200",le="1"} 90
    http_request_duration_milliseconds_bucket{endpoint="/healthz",method="GET",status="200",le="2.5"} 90
    http_request_duration_milliseconds_bucket{endpoint="/healthz",method="GET",status="200",le="5"} 90
    http_request_duration_milliseconds_bucket{endpoint="/healthz",method="GET",status="200",le="10"} 90
    http_request_duration_milliseconds_bucket{endpoint="/healthz",method="GET",status="200",le="+Inf"} 90
    http_request_duration_milliseconds_sum{endpoint="/healthz",method="GET",status="200"} 11.186017999999999
    http_request_duration_milliseconds_count{endpoint="/healthz",method="GET",status="200"} 90
    http_request_duration_milliseconds_bucket{endpoint="/readyz",method="GET",status="200",le="0.005"} 0
    http_request_duration_milliseconds_bucket{endpoint="/readyz",method="GET",status="200",le="0.01"} 0
    http_request_duration_milliseconds_bucket{endpoint="/readyz",method="GET",status="200",le="0.025"} 0
    http_request_duration_milliseconds_bucket{endpoint="/readyz",method="GET",status="200",le="0.05"} 0
    http_request_duration_milliseconds_bucket{endpoint="/readyz",method="GET",status="200",le="0.1"} 0
    http_request_duration_milliseconds_bucket{endpoint="/readyz",method="GET",status="200",le="0.25"} 0
    http_request_duration_milliseconds_bucket{endpoint="/readyz",method="GET",status="200",le="0.5"} 0
    http_request_duration_milliseconds_bucket{endpoint="/readyz",method="GET",status="200",le="1"} 26
    http_request_duration_milliseconds_bucket{endpoint="/readyz",method="GET",status="200",le="2.5"} 82
    http_request_duration_milliseconds_bucket{endpoint="/readyz",method="GET",status="200",le="5"} 82
    http_request_duration_milliseconds_bucket{endpoint="/readyz",method="GET",status="200",le="10"} 91
    http_request_duration_milliseconds_bucket{endpoint="/readyz",method="GET",status="200",le="+Inf"} 91
    http_request_duration_milliseconds_sum{endpoint="/readyz",method="GET",status="200"} 153.43765100000005
    http_request_duration_milliseconds_count{endpoint="/readyz",method="GET",status="200"} 91
    # HELP http_requests_in_flight Number of HTTP requests currently being processed
    # TYPE http_requests_in_flight gauge
    http_requests_in_flight 1
    # HELP http_requests_total Total number of HTTP requests
    # TYPE http_requests_total counter
    http_requests_total{endpoint="/healthz",method="GET",status="200"} 90
    http_requests_total{endpoint="/readyz",method="GET",status="200"} 91
    # HELP process_cpu_seconds_total Total user and system CPU time spent in seconds.
    # TYPE process_cpu_seconds_total counter
    process_cpu_seconds_total 0.69
    # HELP process_max_fds Maximum number of open file descriptors.
    # TYPE process_max_fds gauge
    process_max_fds 1.048576e+06
    # HELP process_network_receive_bytes_total Number of bytes received by the process over the network.
    # TYPE process_network_receive_bytes_total counter
    process_network_receive_bytes_total 145714
    # HELP process_network_transmit_bytes_total Number of bytes sent by the process over the network.
    # TYPE process_network_transmit_bytes_total counter
    process_network_transmit_bytes_total 296914
    # HELP process_open_fds Number of open file descriptors.
    # TYPE process_open_fds gauge
    process_open_fds 10
    # HELP process_resident_memory_bytes Resident memory size in bytes.
    # TYPE process_resident_memory_bytes gauge
    process_resident_memory_bytes 2.226176e+07
    # HELP process_start_time_seconds Start time of the process since unix epoch in seconds.
    # TYPE process_start_time_seconds gauge
    process_start_time_seconds 1.75432015523e+09
    # HELP process_virtual_memory_bytes Virtual memory size in bytes.
    # TYPE process_virtual_memory_bytes gauge
    process_virtual_memory_bytes 1.276624896e+09
    # HELP process_virtual_memory_max_bytes Maximum amount of virtual memory available in bytes.
    # TYPE process_virtual_memory_max_bytes gauge
    process_virtual_memory_max_bytes 1.8446744073709552e+19
    # HELP promhttp_metric_handler_requests_in_flight Current number of scrapes being served.
    # TYPE promhttp_metric_handler_requests_in_flight gauge
    promhttp_metric_handler_requests_in_flight 1
    # HELP promhttp_metric_handler_requests_total Total number of scrapes by HTTP status code.
    # TYPE promhttp_metric_handler_requests_total counter
    promhttp_metric_handler_requests_total{code="200"} 0
    promhttp_metric_handler_requests_total{code="500"} 0
    promhttp_metric_handler_requests_total{code="503"} 0
    ```

## Implementation Requirements

### Middleware/Filter Integration

- Implement as HTTP middleware, filter, or interceptor that wraps all HTTP endpoints
- Ensure metrics are recorded for ALL HTTP requests, including:
    - API endpoints
    - Health checks
    - Static file serving
    - Error responses (4xx, 5xx)

### Timing Accuracy

- Start timing when the request enters the application layer
- Stop timing when the response is fully written
- Use high-precision timing (microsecond accuracy where possible)

### Label Value Guidelines

- **Method**: Use uppercase HTTP method names (GET, POST, PUT, DELETE, PATCH, HEAD, OPTIONS)
- **Endpoint**:
    - Use the route pattern, not the actual URL with parameters
    - Example: Use "/api/users/{id}" instead of "/api/users/123"
    - For frameworks that don't provide route patterns, use the actual path but sanitize sensitive data
    - **Note**: This label may be transformed to `path` by the OpenTelemetry pipeline
- **Status**: Convert numeric HTTP status codes to strings ("200", "404", "500")

### Error Handling

- Metrics recording must not interfere with normal request processing
- If metric recording fails, log the error but continue processing the request
- Ensure metrics are recorded even for requests that result in exceptions/errors

### Performance Considerations

- Minimize overhead of metrics collection
- Use efficient label value extraction
- Avoid creating high-cardinality metrics (limit unique endpoint values)

### Export Configuration

- Metrics must be exportable to the existing Otel Collector
- Follow OpenTelemetry semantic conventions where applicable
- Ensure metrics are properly registered/initialized at application startup

## Framework-Specific Notes

### Go (chi/gorilla/gin/echo)

- Implement as HTTP middleware function
- Use request context for timing and in-flight tracking

### Python (FastAPI/Flask/Django)

- Implement as ASGI/WSGI middleware or decorator
- Consider async/await patterns for proper timing

### Java (Spring Boot)

- Implement as Filter or HandlerInterceptor
- Use Spring's built-in metrics integration where possible
- Consider MeterRegistry for metric registration

### JavaScript/TypeScript (Next.js/Express)

- Implement as middleware function
- Handle both API routes and page requests
- Consider Next.js specific routing patterns

## Validation Requirements

### Testing

Each implementation must be tested to verify:

1. All three metrics are created and registered
2. Counter increments correctly for each request
3. Histogram records accurate durations
4. Gauge properly tracks concurrent requests
5. Labels contain correct values
6. Metrics are exported to Otel Collector

### Monitoring

Once deployed, verify metrics are:

- Appearing in monitoring dashboards
- Showing expected patterns and values
- Compatible with existing alerting rules
- Properly aggregated across service instances

## Example Expected Metrics Output

```
# HELP http_requests_total Total number of HTTP requests
# TYPE http_requests_total counter
http_requests_total{method="GET",path="/api/health",status="200"} 1523
http_requests_total{method="POST",path="/api/users",status="201"} 45
http_requests_total{method="GET",path="/api/users/{id}",status="404"} 12

# HELP http_request_duration_seconds Duration of HTTP requests in seconds
# TYPE http_request_duration_seconds histogram
http_request_duration_seconds_bucket{method="GET",path="/api/health",status="200",le="0.005"} 1200
http_request_duration_seconds_bucket{method="GET",path="/api/health",status="200",le="0.01"} 1520
# ... additional buckets

# HELP http_requests_in_flight Number of HTTP requests currently being processed
# TYPE http_requests_in_flight gauge
http_requests_in_flight 3
```

This standardization ensures consistent observability and monitoring capabilities across all microservices in the system.

## Accessing Metrics

### Spring Boot Applications

For Spring Boot applications with Actuator enabled, metrics are available at multiple endpoints:

1. **`/actuator/prometheus`** - Full Prometheus format metrics (recommended for scraping)
2. **`/actuator/metrics`** - JSON format metrics with individual metric details
3. **`/metrics`** - Custom simplified metrics endpoint (if implemented)

### Troubleshooting Metrics Visibility

If HTTP metrics don't appear immediately:

1. **Make HTTP requests**: Metrics are created lazily when first used
2. **Check pre-registration**: Ensure metrics are pre-registered with sample tags
3. **Verify filter registration**: Confirm the HTTP filter is properly registered
4. **Check logs**: Look for any metric registration errors

### Example Commands

```bash
# Check if metrics are available
curl http://your-service:8082/actuator/prometheus | grep http_requests

# Make a request to generate metrics
curl http://your-service:8082/health

# Check metrics again
curl http://your-service:8082/actuator/prometheus | grep http_requests
```