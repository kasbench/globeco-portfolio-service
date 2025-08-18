# Thread Metrics Enhancement Implementation Plan

- [x] 1. Create core thread metrics with dual system support
  - Add four thread metrics using existing `_get_or_create_metric()` pattern in `app/monitoring.py`
  - Create Prometheus gauges: `http_workers_active`, `http_workers_total`, `http_workers_max_configured`, `http_requests_queued`
  - Create corresponding OpenTelemetry UpDownCounter metrics for collector export
  - Add comprehensive error handling and dummy metric fallbacks following existing patterns
  - Write unit tests for metric creation and registration
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 3.1, 3.2, 3.5_

- [x] 2. Implement Python threading detection and enumeration
  - Create `get_active_worker_count()` function to count threads with "RUNNING" or "BUSY" status
  - Create `get_total_worker_count()` function to count all threads in the thread pool
  - Implement `_enumerate_active_threads()` using Python's `threading.enumerate()`
  - Add `_is_worker_thread()` function to identify HTTP worker threads vs system threads
  - Add `_is_thread_active()` function to distinguish active vs idle threads
  - Write comprehensive unit tests for thread detection logic
  - _Requirements: 2.1, 2.2, 2.3, 4.1, 4.2_

- [x] 3. Implement thread pool configuration detection
  - Create `get_max_configured_workers()` function to detect maximum thread pool size
  - Implement `_detect_uvicorn_thread_pool()` to inspect Uvicorn's thread pool configuration
  - Add `_get_asyncio_thread_pool_info()` for asyncio thread pool executor details
  - Handle single-process uvicorn deployment architecture
  - Add fallback to reasonable defaults when detection fails
  - Write unit tests for thread pool configuration detection
  - _Requirements: 1.3, 4.3, 4.4_

- [x] 4. Implement request queue depth detection
  - Create `get_queued_requests_count()` function with multiple detection approaches
  - Implement `_detect_request_queue_depth()` with fallback mechanisms
  - Add `_estimate_queue_from_metrics()` using existing HTTP metrics correlation
  - Try Uvicorn server queue inspection, AsyncIO task queue analysis, and system-level detection
  - Implement graceful fallbacks when queue detection methods fail
  - Write unit tests for queue detection and estimation logic
  - _Requirements: 1.4, 4.4, 5.5_

- [x] 5. Create ThreadMetricsCollector class with update throttling
  - Implement `ThreadMetricsCollector` class that integrates with Prometheus collection mechanism
  - Add update throttling with configurable interval (default 1 second) to prevent excessive collection
  - Implement `collect()` method that updates both Prometheus and OpenTelemetry metrics
  - Add `_update_worker_metrics()` and `_update_queue_metrics()` methods
  - Handle OpenTelemetry UpDownCounter value tracking for proper delta updates
  - Write unit tests for collector behavior and throttling logic
  - _Requirements: 5.1, 5.2, 5.3, 7.5_

- [x] 6. Add comprehensive error handling and logging
  - Implement error handling for thread enumeration failures with safe fallbacks
  - Add error handling for thread state detection with conservative defaults
  - Implement fallback mechanisms for queue detection when all approaches fail
  - Add structured logging for thread metrics collection with debug mode support
  - Ensure thread metrics collection failures don't impact request processing
  - Write unit tests for error scenarios and fallback behavior
  - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5_

- [x] 7. Integrate with existing monitoring infrastructure
  - Register `ThreadMetricsCollector` with Prometheus registry in `app/monitoring.py`
  - Add `setup_thread_metrics()` function following existing monitoring setup patterns
  - Integrate thread metrics with existing configuration system in `app/config.py`
  - Add thread metrics configuration options: `enable_thread_metrics`, `thread_metrics_update_interval`, `thread_metrics_debug_logging`
  - Ensure thread metrics work with existing single-process uvicorn deployment
  - Write integration tests for monitoring infrastructure integration
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 6.1, 6.2, 6.3, 6.4_

- [x] 8. Add thread metrics to application startup
  - Modify `app/main.py` to call `setup_thread_metrics()` during application initialization
  - Add conditional setup based on `enable_thread_metrics` configuration setting
  - Ensure thread metrics are initialized after existing monitoring setup
  - Add startup logging to indicate thread metrics status (enabled/disabled)
  - Verify thread metrics appear in both `/metrics` endpoint and OpenTelemetry collector export
  - Write integration tests for application startup with thread metrics
  - _Requirements: 3.1, 3.4, 3.5_

- [x] 9. Create comprehensive unit tests for thread detection
  - Write tests for `_enumerate_active_threads()` with various thread scenarios
  - Test `_is_worker_thread()` identification logic with mock threads
  - Test `_is_thread_active()` detection with different thread states
  - Test thread counting functions with controlled thread pool scenarios
  - Test error handling when thread enumeration fails
  - Mock threading module to test edge cases and error conditions
  - _Requirements: 2.1, 2.2, 2.3, 4.1, 4.2, 7.1, 7.2_

- [ ] 10. Create integration tests for metrics collection
  - Write tests that verify thread metrics are updated correctly during collection
  - Test that both Prometheus and OpenTelemetry metrics receive the same values
  - Test metrics collection under concurrent request load
  - Verify thread metrics correlate with actual thread usage patterns
  - Test configuration options for enabling/disabling thread metrics
  - Test debug logging output for thread metrics collection
  - _Requirements: 5.1, 5.2, 5.3, 5.4, 6.1, 6.2, 6.3, 6.4_

- [ ] 11. Add performance optimization and caching
  - Implement result caching for expensive thread detection operations
  - Add performance monitoring for thread metrics collection overhead
  - Optimize thread enumeration and state detection for minimal CPU impact
  - Ensure thread metrics collection completes quickly to avoid blocking metrics export
  - Add performance tests to verify minimal overhead during high load
  - Document performance characteristics and resource usage
  - _Requirements: 5.1, 5.2, 7.4, 7.5_

- [ ] 12. Create end-to-end validation and documentation
  - Write end-to-end tests that verify thread metrics flow from collection to export
  - Test thread metrics appear correctly in `/metrics` endpoint for debugging
  - Verify thread metrics are sent to OpenTelemetry collector and appear in monitoring system
  - Create documentation for thread metrics interpretation and troubleshooting
  - Add example Prometheus queries for thread metrics analysis
  - Document capacity planning use cases for the new thread metrics
  - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5_