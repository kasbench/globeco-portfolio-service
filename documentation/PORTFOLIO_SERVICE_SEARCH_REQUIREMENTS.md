# Portfolio Service Search Enhancement Requirements

## Overview

The GlobeCo Order Service requires the ability to filter orders by portfolio name (e.g., `portfolio.name=TechGrowthPortfolio`). Currently, the Portfolio Service only supports lookup by `portfolioId`, but the Order Service needs to resolve human-readable portfolio names to portfolio IDs for database filtering.

## Execution Plan

### Phase 1: Core Implementation
- [x] Create new DTO schemas for v2 API with pagination response format
- [x] Implement query parameter validation (name, name_like, limit, offset)
- [x] Add search functionality to Portfolio model/repository layer
- [x] Create new GET /api/v2/portfolios endpoint with search capability
- [x] Keep existing GET /api/v1/portfolios endpoint unchanged for backward compatibility
- [x] Add MongoDB text index on portfolio name field for performance

### Phase 2: Testing & Validation
- [x] Write unit tests for parameter validation
- [x] Write integration tests for search functionality
- [x] Write backward compatibility tests for v1 endpoint
- [x] Performance testing for response time requirements
- [x] Test case-insensitive search behavior

### Phase 3: Documentation 
- [ ] Update API documentation/OpenAPI spec with v2 endpoints
- [ ] Create an API Guide for the Order Service LLM documenting the v2 API.

## Required Enhancement

### New Endpoint: GET /api/v2/portfolios

**IMPLEMENTATION STRATEGY**: This will be a new versioned endpoint (v2) with search functionality. The existing v1 endpoint will remain unchanged to maintain backward compatibility.

## API Specification

### Endpoint Details
```
GET /api/v2/portfolios
```

### Query Parameters

| Parameter | Type | Required | Description | Example |
|-----------|------|----------|-------------|---------|
| `name` | string | No | Search by exact portfolio name (case-insensitive) | `TechGrowthPortfolio` |
| `name_like` | string | No | Search by partial name match (case-insensitive) | `Tech` |
| `limit` | integer | No | Maximum number of results (default: 50, max: 1000) | `10` |
| `offset` | integer | No | Number of results to skip for pagination (default: 0) | `20` |

### Parameter Validation Rules

1. **Mutual Exclusivity**: Only one of `name` or `name_like` can be provided
2. **Name Format**: Must be 1-200 characters, alphanumeric, spaces, hyphens, and underscores only
3. **Limit Bounds**: Must be between 1 and 1000
4. **Offset Bounds**: Must be >= 0
5. **Default Behavior**: If no search parameters provided, return all portfolios with pagination

### Success Response (HTTP 200)

#### Content-Type: `application/json`

#### Response Schema
```json
{
  "portfolios": [
    {
      "portfolioId": "string (MongoDB ObjectId)",
      "name": "string",
      "dateCreated": "string (ISO 8601 datetime)",
      "version": integer
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

**All portfolios:**
```bash
GET /api/v2/portfolios
```
```json
{
  "portfolios": [
    {
      "portfolioId": "507f1f77bcf86cd799439011",
      "name": "TechGrowthPortfolio",
      "dateCreated": "2024-01-15T10:30:00Z",
      "version": 1
    },
    {
      "portfolioId": "507f1f77bcf86cd799439012", 
      "name": "ConservativeIncomePortfolio",
      "dateCreated": "2024-01-20T14:45:00Z",
      "version": 2
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

**Exact name search:**
```bash
GET /api/v2/portfolios?name=TechGrowthPortfolio
```
```json
{
  "portfolios": [
    {
      "portfolioId": "507f1f77bcf86cd799439011",
      "name": "TechGrowthPortfolio", 
      "dateCreated": "2024-01-15T10:30:00Z",
      "version": 1
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

**Partial name search:**
```bash
GET /api/v2/portfolios?name_like=Tech&limit=5
```
```json
{
  "portfolios": [
    {
      "portfolioId": "507f1f77bcf86cd799439011",
      "name": "TechGrowthPortfolio",
      "dateCreated": "2024-01-15T10:30:00Z", 
      "version": 1
    },
    {
      "portfolioId": "507f1f77bcf86cd799439013",
      "name": "FinTechInnovationFund",
      "dateCreated": "2024-02-01T09:15:00Z",
      "version": 1
    },
    {
      "portfolioId": "507f1f77bcf86cd799439014",
      "name": "TechDividendPortfolio", 
      "dateCreated": "2024-02-10T16:20:00Z",
      "version": 1
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
GET /api/v2/portfolios?name=NonExistentPortfolio
```
```json
{
  "portfolios": [],
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

## Backward Compatibility

### Existing v1 Endpoint
The existing `GET /api/v1/portfolios` endpoint will remain **completely unchanged**:

```bash
GET /api/v1/portfolios
```
```json
[
  {
    "portfolioId": "507f1f77bcf86cd799439011",
    "name": "TechGrowthPortfolio",
    "dateCreated": "2024-01-15T10:30:00Z",
    "version": 1
  },
  {
    "portfolioId": "507f1f77bcf86cd799439012",
    "name": "ConservativeIncomePortfolio", 
    "dateCreated": "2024-01-20T14:45:00Z",
    "version": 2
  }
]
```

### Migration Strategy
1. **Immediate**: Deploy v2 endpoint alongside existing v1 endpoint
2. **Order Service Integration**: Update Order Service to use v2 endpoint for search functionality
3. **Client Migration**: Existing clients continue using v1 endpoint until they choose to migrate
4. **Future Deprecation**: v1 endpoint can be deprecated in a future release cycle with proper notice

## Error Handling

### HTTP 400 - Bad Request

#### Conflicting Search Parameters
```json
{
  "detail": "Only one search parameter allowed: name or name_like"
}
```

#### Invalid Name Format
```json
{
  "detail": "Invalid portfolio name format. Name must be 1-200 characters, alphanumeric, spaces, hyphens, and underscores only"
}
```

#### Invalid Pagination Parameters
```json
{
  "detail": "Invalid pagination parameters. Limit must be between 1 and 1000, offset must be >= 0"
}
```

#### Empty Search Parameter
```json
{
  "detail": "Search parameter cannot be empty"
}
```

### HTTP 500 - Internal Server Error
```json
{
  "detail": "An unexpected error occurred while searching portfolios"
}
```

## Technical Implementation Requirements

### API Versioning Implementation
1. **Router Structure**: Create separate routers for v1 and v2 endpoints
2. **Shared Logic**: Use common service layer for both versions
3. **Response Transformation**: v1 returns array, v2 returns object with pagination
4. **URL Structure**: 
   - v1: `/api/v1/portfolios` (existing, unchanged)
   - v2: `/api/v2/portfolios` (new, with search)

### MongoDB Implementation Details
1. **Text Index**: Create a text index on the `name` field for efficient searching:
   ```javascript
   db.portfolio.createIndex({ "name": "text" })
   ```
2. **Case-Insensitive Search**: Use MongoDB's `$regex` with `$options: "i"` for case-insensitive matching
3. **Exact Match Query**: 
   ```python
   Portfolio.find(Portfolio.name == name, ignore_case=True)
   ```
4. **Partial Match Query**:
   ```python
   Portfolio.find({"name": {"$regex": name_like, "$options": "i"}})
   ```

### Performance Requirements
1. **Response Time**: < 200ms for exact name lookup
2. **Response Time**: < 500ms for partial name search with pagination
3. **Response Time**: < 300ms for retrieving all portfolios
4. **Database Indexing**: Ensure name field is indexed for fast searching
5. **Case Insensitivity**: All name comparisons must be case-insensitive

### Search Behavior
1. **No Parameters**:
   - Return all portfolios with pagination
   - Default sorting by dateCreated descending (newest first)

2. **Exact Match (`name`)**:
   - Case-insensitive exact match
   - Should typically return 0 or 1 result (names should be unique)
   - Fastest search operation

3. **Partial Match (`name_like`)**:
   - Case-insensitive substring search
   - Should support prefix, suffix, and infix matching
   - Results ordered by relevance (exact matches first, then alphabetical by name)

### Database Considerations
1. **Indexing**: Create database index on name field for case-insensitive searching
2. **Pagination**: Use efficient pagination with skip/limit
3. **Connection Pooling**: Ensure proper database connection management
4. **Unique Constraints**: Consider enforcing portfolio name uniqueness (case-insensitive)

### Integration Points
1. **Order Service Integration**: Order Service will use the new v2 endpoint for search functionality
2. **Caching**: Consider implementing response caching for frequently searched portfolio names
3. **Rate Limiting**: Implement appropriate rate limiting to prevent abuse
4. **Authentication**: Maintain existing authentication requirements for both v1 and v2

### Testing Requirements
1. **v1 Backward Compatibility Tests**: Ensure v1 endpoint behavior is completely unchanged
2. **v2 Functionality Tests**: Test all v2 search and pagination features
3. **Unit Tests**: Test all parameter validation scenarios
4. **Integration Tests**: Test database search functionality
5. **Performance Tests**: Verify response time requirements for all scenarios
6. **Edge Case Tests**: Test with special characters, very long names, empty results
7. **Case Sensitivity Tests**: Verify case-insensitive searching works correctly

### Logging Requirements
1. **Request Logging**: Log all requests with version (v1 vs v2) and parameters
2. **Performance Logging**: Log response times for monitoring different query types
3. **Error Logging**: Detailed logging for all error scenarios
4. **Usage Analytics**: Track usage patterns between v1 and v2 endpoints
5. **Migration Monitoring**: Track adoption of v2 endpoint over time

## Migration and Deployment Strategy

### Phase 1: v2 Endpoint Deployment
- [ ] Deploy v2 endpoint alongside existing v1 endpoint
- [ ] Ensure v1 endpoint continues working without any changes
- [ ] Monitor performance impact and usage patterns

### Phase 2: Order Service Integration
- [ ] Update Order Service to use the new v2 endpoint for search capability
- [ ] Test end-to-end filtering functionality
- [ ] Monitor search usage patterns

### Phase 3: Optimization and Future Planning
- [ ] Optimize database queries based on usage patterns
- [ ] Implement caching if needed
- [ ] Plan v1 deprecation timeline (future release cycle)
- [ ] Add monitoring and alerting

## Security Considerations
1. **Input Validation**: Strict validation of all search parameters to prevent injection attacks
2. **Rate Limiting**: Prevent abuse of search functionality on both v1 and v2 endpoints
3. **Access Control**: Maintain existing access control mechanisms for both versions
4. **Audit Logging**: Log search activities for security monitoring

## Future Enhancements (Out of Scope)
- Full-text search on portfolio descriptions
- Advanced filtering by date ranges
- Bulk portfolio name resolution endpoint
- Portfolio search by manager or category
- Export/import functionality for portfolio searches
- v1 endpoint deprecation and removal (future release cycle) 