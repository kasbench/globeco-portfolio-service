# Security Service Search Enhancement Requirements

## Overview

The GlobeCo Order Service requires the ability to filter orders by security ticker (e.g., `security.ticker=AAPL`). Currently, the Security Service only supports lookup by `securityId`, but the Order Service needs to resolve human-readable tickers to security IDs for database filtering.

This enhancement will add a new v2 API endpoint with advanced search capabilities while maintaining full backward compatibility with the existing v1 API.

## Implementation Phases

### Phase 1: Core Implementation
- [ ] Implement v2 API endpoint with search functionality
- [ ] Add parameter validation and error handling
- [ ] Maintain v1 API backward compatibility
- [ ] Create database indexes for performance
- [ ] Implement basic testing

### Phase 2: Testing and Validation
- [ ] Write unit tests for parameter validation
- [ ] Write integration tests for search functionality
- [ ] Write backward compatibility tests for v1 endpoint
- [ ] Performance testing for response time requirements
- [ ] Test case-insensitive search behavior

### Phase 3: Documentation
- [ ] Update API documentation/OpenAPI spec with v2 endpoints
- [ ] Create an API Guide for the Order Service LLM documenting the v2 API

## Required Enhancement

### New Endpoint: GET /api/v2/securities

**IMPLEMENTATION STRATEGY**: This will be a new versioned endpoint (v2) with search functionality. The existing v1 endpoint will remain unchanged to maintain backward compatibility.

## API Specification

### Endpoint Details
```
GET /api/v2/securities
```

### Query Parameters

| Parameter | Type | Required | Description | Example |
|-----------|------|----------|-------------|---------|
| `ticker` | string | No | Search by exact ticker symbol (case-insensitive) | `AAPL` |
| `ticker_like` | string | No | Search by partial ticker match (case-insensitive) | `APP` |
| `limit` | integer | No | Maximum number of results (default: 50, max: 1000) | `10` |
| `offset` | integer | No | Number of results to skip for pagination (default: 0) | `20` |

### Parameter Validation Rules

1. **Mutual Exclusivity**: Only one of `ticker` or `ticker_like` can be provided
2. **Ticker Format**: Must be 1-50 characters, alphanumeric, dots, and hyphens only
3. **Limit Bounds**: Must be between 1 and 1000
4. **Offset Bounds**: Must be >= 0
5. **Default Behavior**: If no search parameters provided, return all securities with pagination

### Success Response (HTTP 200)

#### Content-Type: `application/json`

#### Response Schema
```json
{
  "securities": [
    {
      "securityId": "string (UUID)",
      "ticker": "string",
      "description": "string",
      "securityTypeId": "string (UUID)",
      "version": integer,
      "securityType": {
        "securityTypeId": "string (UUID)",
        "abbreviation": "string",
        "description": "string",
        "version": integer
      }
    }
  ],
  "pagination": {
    "totalElements": integer,
    "totalPages": integer,
    "currentPage": integer,
    "pageSize": integer,
    "hasNext": boolean,
    "hasPrevious": boolean
  }
}
```

#### Example Responses

**All securities:**
```bash
GET /api/v2/securities
```
```json
{
  "securities": [
    {
      "securityId": "550e8400-e29b-41d4-a716-446655440000",
      "ticker": "AAPL",
      "description": "Apple Inc. Common Stock",
      "securityTypeId": "sec-type-001",
      "version": 1,
      "securityType": {
        "securityTypeId": "sec-type-001",
        "abbreviation": "CS",
        "description": "Common Stock",
        "version": 1
      }
    },
    {
      "securityId": "550e8400-e29b-41d4-a716-446655440001",
      "ticker": "MSFT",
      "description": "Microsoft Corporation Common Stock",
      "securityTypeId": "sec-type-001",
      "version": 1,
      "securityType": {
        "securityTypeId": "sec-type-001",
        "abbreviation": "CS",
        "description": "Common Stock",
        "version": 1
      }
    }
  ],
  "pagination": {
    "totalElements": 2,
    "totalPages": 1,
    "currentPage": 0,
    "pageSize": 50,
    "hasNext": false,
    "hasPrevious": false
  }
}
```

**Exact ticker search:**
```bash
GET /api/v2/securities?ticker=AAPL
```
```json
{
  "securities": [
    {
      "securityId": "550e8400-e29b-41d4-a716-446655440000",
      "ticker": "AAPL",
      "description": "Apple Inc. Common Stock",
      "securityTypeId": "sec-type-001",
      "version": 1,
      "securityType": {
        "securityTypeId": "sec-type-001",
        "abbreviation": "CS",
        "description": "Common Stock",
        "version": 1
      }
    }
  ],
  "pagination": {
    "totalElements": 1,
    "totalPages": 1,
    "currentPage": 0,
    "pageSize": 50,
    "hasNext": false,
    "hasPrevious": false
  }
}
```

**Partial ticker search:**
```bash
GET /api/v2/securities?ticker_like=APP&limit=5
```
```json
{
  "securities": [
    {
      "securityId": "550e8400-e29b-41d4-a716-446655440000",
      "ticker": "AAPL",
      "description": "Apple Inc. Common Stock",
      "securityTypeId": "sec-type-001",
      "version": 1,
      "securityType": {
        "securityTypeId": "sec-type-001",
        "abbreviation": "CS",
        "description": "Common Stock",
        "version": 1
      }
    },
    {
      "securityId": "550e8400-e29b-41d4-a716-446655440001",
      "ticker": "APPN",
      "description": "Appian Corporation Common Stock",
      "securityTypeId": "sec-type-001",
      "version": 1,
      "securityType": {
        "securityTypeId": "sec-type-001",
        "abbreviation": "CS",
        "description": "Common Stock",
        "version": 1
      }
    },
    {
      "securityId": "550e8400-e29b-41d4-a716-446655440002",
      "ticker": "APP.TO",
      "description": "AppLovin Corporation Common Stock (Toronto)",
      "securityTypeId": "sec-type-001",
      "version": 1,
      "securityType": {
        "securityTypeId": "sec-type-001",
        "abbreviation": "CS",
        "description": "Common Stock",
        "version": 1
      }
    }
  ],
  "pagination": {
    "totalElements": 3,
    "totalPages": 1,
    "currentPage": 0,
    "pageSize": 5,
    "hasNext": false,
    "hasPrevious": false
  }
}
```

**No results found:**
```bash
GET /api/v2/securities?ticker=NONEXISTENT
```
```json
{
  "securities": [],
  "pagination": {
    "totalElements": 0,
    "totalPages": 0,
    "currentPage": 0,
    "pageSize": 50,
    "hasNext": false,
    "hasPrevious": false
  }
}
```

## Error Handling

### HTTP 400 - Bad Request

#### Conflicting Search Parameters
```json
{
  "detail": "Only one of 'ticker' or 'ticker_like' parameters can be provided"
}
```

#### Invalid Ticker Format
```json
{
  "detail": "Ticker must be 1-50 characters and contain only alphanumeric characters, dots, and hyphens"
}
```

#### Invalid Pagination Parameters
```json
{
  "detail": [
    {
      "loc": ["query", "limit"],
      "msg": "Ensure this value is less than or equal to 1000",
      "type": "value_error.number.not_le"
    }
  ]
}
```

### HTTP 422 - Validation Error
```json
{
  "detail": [
    {
      "loc": ["query", "ticker"],
      "msg": "String should match pattern '^[A-Za-z0-9.-]{1,50}$'",
      "type": "string_pattern_mismatch"
    }
  ]
}
```

### HTTP 500 - Internal Server Error
```json
{
  "detail": "Internal server error"
}
```

## Backward Compatibility

### Existing v1 Endpoint
The existing `GET /api/v1/securities` endpoint will remain **completely unchanged**:

```bash
GET /api/v1/securities
```
```json
[
  {
    "securityId": "550e8400-e29b-41d4-a716-446655440000",
    "ticker": "AAPL",
    "description": "Apple Inc. Common Stock",
    "securityTypeId": "sec-type-001",
    "version": 1,
    "securityType": {
      "securityTypeId": "sec-type-001",
      "abbreviation": "CS",
      "description": "Common Stock",
      "version": 1
    }
  }
]
```

### Individual Security Lookup
The existing `GET /api/v1/security/{securityId}` endpoint remains unchanged:

```bash
GET /api/v1/security/550e8400-e29b-41d4-a716-446655440000
```
```json
{
  "securityId": "550e8400-e29b-41d4-a716-446655440000",
  "ticker": "AAPL",
  "description": "Apple Inc. Common Stock",
  "securityTypeId": "sec-type-001",
  "version": 1,
  "securityType": {
    "securityTypeId": "sec-type-001",
    "abbreviation": "CS",
    "description": "Common Stock",
    "version": 1
  }
}
```

## Performance Requirements

### Response Time Targets
1. **Exact ticker lookup**: < 200ms response time
2. **Partial ticker search**: < 500ms response time
3. **Retrieve all securities**: < 300ms response time
4. **Pagination**: < 400ms response time per page

### Database Optimization
1. **Indexing**: Create database index on ticker field for fast searching
2. **Case Insensitivity**: Use database-specific case-insensitive search (e.g., ILIKE in PostgreSQL, regex with options in MongoDB)
3. **Connection Pooling**: Ensure proper database connection management

## Search Behavior

### Exact Match (`ticker`)
- Case-insensitive exact match
- Should typically return 0 or 1 result (tickers should be unique)
- Fastest search operation

### Partial Match (`ticker_like`)
- Case-insensitive substring search
- Should support prefix, suffix, and infix matching
- Results ordered by ticker alphabetically

### Result Ordering
- **v2 API**: Results ordered by ticker ascending (alphabetical)
- **v1 API**: Results in default database order (for backward compatibility)

## Integration Points

### Order Service Integration
This endpoint will be called by the Order Service's filtering system to resolve tickers to security IDs for database queries.

**Example Integration Pattern**:
```python
# Order Service resolves ticker to securityId
async def resolve_ticker_to_security_id(ticker: str) -> Optional[str]:
    response = await security_service_client.get(
        f"/api/v2/securities?ticker={ticker}"
    )
    if response.status_code == 200:
        data = response.json()
        if data["securities"]:
            return data["securities"][0]["securityId"]
    return None
```

### Caching Strategy
- Consider implementing response caching for frequently searched tickers
- Cache TTL: 5-10 minutes for ticker searches
- Cache invalidation on security data updates

## Technical Implementation Details

### Database Schema Requirements
Assumes existing Security and SecurityType tables with the following structure:

```sql
-- Security table
CREATE TABLE security (
    security_id UUID PRIMARY KEY,
    ticker VARCHAR(50) NOT NULL,
    description TEXT,
    security_type_id UUID REFERENCES security_type(security_type_id),
    version INTEGER NOT NULL DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- SecurityType table  
CREATE TABLE security_type (
    security_type_id UUID PRIMARY KEY,
    abbreviation VARCHAR(10) NOT NULL,
    description TEXT,
    version INTEGER NOT NULL DEFAULT 1
);

-- Required indexes for performance
CREATE INDEX idx_security_ticker ON security (UPPER(ticker));
CREATE INDEX idx_security_ticker_like ON security USING gin (UPPER(ticker) gin_trgm_ops);
```

### Service Architecture
- **Service Layer**: SecurityService with search methods
- **Repository Layer**: SecurityRepository with database queries
- **API Layer**: v1 and v2 routers with parameter validation
- **DTO Layer**: Request/response schemas with validation

### Error Handling Strategy
- Use FastAPI's built-in validation for parameter checking
- Custom validation for mutual exclusivity rules
- Consistent error response format matching Portfolio Service
- Proper HTTP status codes (400, 422, 500)

## Testing Strategy

### Unit Tests
- Parameter validation scenarios (mutual exclusivity, format validation, bounds)
- Edge cases (empty strings, special characters, unicode)
- Error response format validation

### Integration Tests
- Database search functionality
- Case-insensitive behavior
- Pagination accuracy
- Result ordering verification

### Performance Tests
- Response time validation for all query types
- Concurrent request handling
- Database index effectiveness
- Memory usage under load

### Backward Compatibility Tests
- v1 endpoint behavior unchanged
- v1/v2 data consistency
- Response format validation

## Logging and Monitoring

### Request Logging
- Log all search requests with parameters (excluding sensitive data)
- Include request ID for tracing
- Log response times for performance monitoring

### Error Logging
- Detailed logging for all error scenarios
- Include stack traces for 500 errors
- Log validation failures with parameter details

### Usage Analytics
- Track most frequently searched tickers
- Monitor search performance metrics
- Alert on performance degradation

## Security Considerations

### Input Validation
- Strict parameter validation to prevent injection attacks
- Rate limiting to prevent abuse
- Input sanitization for logging

### Data Access
- No authentication required (internal service)
- Consider implementing API key authentication for external access
- Audit logging for compliance

## Future Enhancements (Out of Scope)

### Phase 4 Potential Features
- Full-text search on security descriptions
- Advanced filtering by security type
- Bulk ticker resolution endpoint
- Real-time ticker updates via WebSocket
- Fuzzy matching for typo tolerance
- Search result ranking by relevance

## Dependencies

### Required Libraries/Frameworks
- FastAPI for API framework
- Pydantic for data validation
- Database ORM (SQLAlchemy, Beanie, etc.)
- HTTP client library for testing
- Database-specific drivers

### Infrastructure Requirements
- Database with full-text search capabilities
- Application server with async support
- Monitoring and logging infrastructure
- Load balancer for high availability

## Acceptance Criteria

### Phase 1 Complete When:
- [ ] v2 API endpoint implemented and functional
- [ ] All parameter validation working correctly
- [ ] v1 API backward compatibility maintained
- [ ] Database indexes created and optimized
- [ ] Basic test suite passing

### Phase 2 Complete When:
- [ ] Comprehensive test suite implemented
- [ ] All performance requirements met
- [ ] Backward compatibility verified
- [ ] Error handling thoroughly tested

### Phase 3 Complete When:
- [ ] API documentation updated
- [ ] Integration guide created for Order Service
- [ ] All documentation reviewed and approved 