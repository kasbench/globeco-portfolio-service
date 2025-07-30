# Structured JSON Logging Implementation

This document describes the structured JSON logging implementation for the GlobeCo Portfolio Service.

## Overview

The application now implements comprehensive structured JSON logging that captures all API requests, database operations, and application events in a format suitable for log aggregation systems like ELK Stack, Splunk, or cloud logging services.

## Features

### Required Fields Implemented

All log entries include the following fields as applicable:

- **timestamp**: ISO 8601 formatted timestamp with timezone
- **level**: Log level (info, warning, error, critical, debug)
- **msg**: Human-readable log message
- **application**: Service name (globeco-portfolio-service)
- **server**: Hostname of the server
- **location**: Code location (module:function:line)

### HTTP Request Fields

For API requests, additional fields are captured:

- **method**: HTTP method (GET, POST, PUT, DELETE)
- **path**: Request path
- **status**: HTTP status code
- **ip_address**: Client IP address
- **remote_addr**: Same as ip_address for consistency
- **user_agent**: Client user agent string
- **bytes**: Response size in bytes
- **duration**: Request processing time in milliseconds
- **request_id**: Unique request identifier
- **correlation_id**: Correlation ID from headers or generated

### Database Operation Fields

Database operations include:

- **operation**: Database operation type (find_all, find_by_id, insert, update, delete)
- **collection**: MongoDB collection name
- **count**: Number of records affected/returned
- **portfolio_id**: Portfolio ID when applicable
- **portfolio_name**: Portfolio name when applicable

## Configuration

### Environment Variables

- `LOG_LEVEL`: Set logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
  - Default: INFO
- `OTEL_METRICS_LOGGING_ENABLED`: Enable OpenTelemetry metrics logging
  - Default: False

### Example Configuration

```bash
export LOG_LEVEL=INFO
export OTEL_METRICS_LOGGING_ENABLED=true
```

## Usage

### Automatic Logging

The following are logged automatically:

1. **All HTTP Requests**: Every API call is logged at INFO level or higher
2. **Database Operations**: All CRUD operations with timing and context
3. **Application Lifecycle**: Startup, shutdown, and health checks
4. **Errors**: All exceptions with full context

### Manual Logging

Use the structured logger in your code:

```python
from app.logging_config import get_logger

logger = get_logger(__name__)

# Basic logging
logger.info("Operation completed")

# Logging with additional fields
logger.info("User action performed", 
           user_id="12345",
           action="create_portfolio",
           duration=123.45)

# Error logging
logger.error("Operation failed", 
            error=str(e),
            user_id="12345",
            operation="update_portfolio")
```

## Log Format Examples

### HTTP Request Log

```json
{
  "timestamp": "2025-01-30T10:30:45.123456+00:00",
  "level": "info",
  "msg": "Completed GET /api/v1/portfolios - 200",
  "application": "globeco-portfolio-service",
  "server": "portfolio-service-pod-abc123",
  "location": "app.logging_config:dispatch:89",
  "method": "GET",
  "path": "/api/v1/portfolios",
  "status": 200,
  "ip_address": "192.168.1.100",
  "remote_addr": "192.168.1.100",
  "user_agent": "Mozilla/5.0 (compatible; API-Client/1.0)",
  "bytes": 2048,
  "duration": 123.45,
  "request_id": "req-550e8400-e29b-41d4-a716-446655440000",
  "correlation_id": "corr-550e8400-e29b-41d4-a716-446655440001"
}
```

### Database Operation Log

```json
{
  "timestamp": "2025-01-30T10:30:45.123456+00:00",
  "level": "info",
  "msg": "Successfully fetched all portfolios",
  "application": "globeco-portfolio-service",
  "server": "portfolio-service-pod-abc123",
  "location": "app.services:get_all_portfolios:25",
  "operation": "get_all_portfolios",
  "count": 150,
  "request_id": "req-550e8400-e29b-41d4-a716-446655440000",
  "correlation_id": "corr-550e8400-e29b-41d4-a716-446655440001"
}
```

### Error Log

```json
{
  "timestamp": "2025-01-30T10:30:45.123456+00:00",
  "level": "error",
  "msg": "Error updating portfolio",
  "application": "globeco-portfolio-service",
  "server": "portfolio-service-pod-abc123",
  "location": "app.services:update_portfolio:78",
  "operation": "update_portfolio",
  "portfolio_id": "507f1f77bcf86cd799439011",
  "error": "Version conflict: expected 2, got 1",
  "request_id": "req-550e8400-e29b-41d4-a716-446655440000",
  "correlation_id": "corr-550e8400-e29b-41d4-a716-446655440001"
}
```

## Integration with Log Aggregation

### ELK Stack

The JSON format is ready for Elasticsearch ingestion. Configure Logstash or Filebeat to parse the JSON logs.

### Kubernetes

Logs are written to stdout and can be collected by Kubernetes logging solutions:

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: fluent-bit-config
data:
  parsers.conf: |
    [PARSER]
        Name        portfolio_json
        Format      json
        Time_Key    timestamp
        Time_Format %Y-%m-%dT%H:%M:%S.%L%z
```

### Cloud Logging

The structured format works with:
- AWS CloudWatch Logs
- Google Cloud Logging
- Azure Monitor Logs

## Monitoring and Alerting

### Key Metrics to Monitor

1. **Error Rate**: Count of error/critical level logs
2. **Response Time**: Duration field in request logs
3. **Request Volume**: Count of INFO level API logs
4. **Database Performance**: Duration in database operation logs

### Sample Queries

**Elasticsearch/Kibana:**
```json
{
  "query": {
    "bool": {
      "must": [
        {"term": {"level": "error"}},
        {"term": {"application": "globeco-portfolio-service"}},
        {"range": {"timestamp": {"gte": "now-1h"}}}
      ]
    }
  }
}
```

**Splunk:**
```
index=portfolio-service level=error earliest=-1h
| stats count by location, error
```

## Testing

Run the test script to verify logging functionality:

```bash
python test_logging.py
```

This will generate sample log entries demonstrating all the structured logging features.

## Performance Considerations

- JSON formatting adds minimal overhead (~1-2ms per log entry)
- Logs are written asynchronously to stdout
- Context variables use Python's contextvars for thread safety
- Log level filtering reduces unnecessary processing

## Security

- No sensitive data (passwords, tokens) is logged
- IP addresses are logged for audit purposes
- Request/correlation IDs enable request tracing without exposing user data
- All logs are structured to prevent log injection attacks