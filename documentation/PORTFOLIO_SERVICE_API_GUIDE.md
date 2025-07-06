# Portfolio Service API Guide for Order Service LLM

## Overview

This guide provides comprehensive documentation for the Order Service LLM to interact with the Portfolio Service v2 API. The Portfolio Service provides advanced search and retrieval capabilities for portfolio management with high-performance requirements.

## Service Information

- **Service Name**: Portfolio Service
- **Base URL**: `http://portfolio-service:8000` (internal service communication)
- **API Version**: v2 (recommended for new integrations)
- **Response Format**: JSON
- **Authentication**: None required (internal service)

## Key Features

### v2 API Capabilities
- **Advanced Search**: Case-insensitive exact and partial name matching
- **Pagination**: Efficient handling of large result sets
- **Performance Optimized**: Sub-second response times for all operations
- **Structured Responses**: Consistent object format with metadata
- **Backward Compatible**: v1 API remains unchanged

### Performance Guarantees
- **Exact name search**: < 200ms response time
- **Partial name search**: < 500ms response time  
- **Retrieve all portfolios**: < 300ms response time
- **Pagination**: < 400ms response time per page

## Primary Endpoint: Search Portfolios

### Endpoint
```
GET /api/v2/portfolios
```

### Use Cases for Order Service

1. **Portfolio Validation**: Verify portfolio exists before creating orders
2. **Portfolio Discovery**: Find portfolios by partial name for user assistance
3. **Portfolio Listing**: Display available portfolios with pagination
4. **Portfolio Search**: Help users find specific portfolios

## Request Parameters

### Search Parameters (Mutually Exclusive)

#### Exact Name Search
```
GET /api/v2/portfolios?name=TechGrowthPortfolio
```
- **Parameter**: `name`
- **Type**: String (1-200 characters)
- **Format**: Alphanumeric + spaces, hyphens, underscores only
- **Behavior**: Case-insensitive exact match
- **Use Case**: Validate specific portfolio exists

#### Partial Name Search  
```
GET /api/v2/portfolios?name_like=Tech
```
- **Parameter**: `name_like`
- **Type**: String (1-200 characters)
- **Format**: Alphanumeric + spaces, hyphens, underscores only
- **Behavior**: Case-insensitive substring search
- **Use Case**: Help users find portfolios by partial name

### Pagination Parameters

#### Limit Results
```
GET /api/v2/portfolios?limit=10
```
- **Parameter**: `limit`
- **Type**: Integer (1-1000)
- **Default**: 50
- **Use Case**: Control page size for UI display

#### Skip Results (Offset)
```
GET /api/v2/portfolios?offset=20
```
- **Parameter**: `offset`
- **Type**: Integer (≥0)
- **Default**: 0
- **Use Case**: Implement pagination (offset = page * limit)

### Combined Examples

```bash
# Get all portfolios (first page)
GET /api/v2/portfolios

# Search for portfolios containing "Tech" (first 5 results)
GET /api/v2/portfolios?name_like=Tech&limit=5

# Get second page of all portfolios (10 per page)
GET /api/v2/portfolios?limit=10&offset=10

# Validate specific portfolio exists
GET /api/v2/portfolios?name=ConservativeIncomePortfolio
```

## Response Format

### Success Response Structure
```json
{
  "portfolios": [
    {
      "portfolioId": "string",
      "name": "string", 
      "dateCreated": "string (ISO 8601)",
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

### Response Examples

#### Single Portfolio Found
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

#### Multiple Portfolios with Pagination
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
    }
  ],
  "pagination": {
    "totalElements": 15,
    "totalPages": 2,
    "currentPage": 0,
    "pageSize": 10,
    "hasNext": true,
    "hasPrevious": false
  }
}
```

#### No Results Found
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

## Integration Patterns for Order Service

### 1. Portfolio Validation Pattern

**Use Case**: Validate portfolio exists before creating an order

```python
async def validate_portfolio_exists(portfolio_name: str) -> bool:
    """Validate that a portfolio exists by exact name match."""
    url = f"http://portfolio-service:8000/api/v2/portfolios"
    params = {"name": portfolio_name}
    
    async with httpx.AsyncClient() as client:
        response = await client.get(url, params=params)
        
        if response.status_code == 200:
            data = response.json()
            return len(data["portfolios"]) > 0
        
        return False

# Usage in order creation
if not await validate_portfolio_exists(order_request.portfolio_name):
    raise ValueError(f"Portfolio '{order_request.portfolio_name}' not found")
```

### 2. Portfolio Discovery Pattern

**Use Case**: Help users find portfolios by partial name

```python
async def find_portfolios_by_partial_name(partial_name: str, limit: int = 10) -> List[Dict]:
    """Find portfolios matching partial name for user assistance."""
    url = f"http://portfolio-service:8000/api/v2/portfolios"
    params = {
        "name_like": partial_name,
        "limit": limit
    }
    
    async with httpx.AsyncClient() as client:
        response = await client.get(url, params=params)
        
        if response.status_code == 200:
            data = response.json()
            return data["portfolios"]
        
        return []

# Usage in user assistance
suggestions = await find_portfolios_by_partial_name("Tech", limit=5)
if suggestions:
    print("Did you mean one of these portfolios?")
    for portfolio in suggestions:
        print(f"- {portfolio['name']}")
```

### 3. Portfolio Listing Pattern

**Use Case**: Display available portfolios with pagination

```python
async def get_portfolios_page(page: int = 0, page_size: int = 20) -> Dict:
    """Get a page of portfolios for display."""
    url = f"http://portfolio-service:8000/api/v2/portfolios"
    params = {
        "limit": page_size,
        "offset": page * page_size
    }
    
    async with httpx.AsyncClient() as client:
        response = await client.get(url, params=params)
        
        if response.status_code == 200:
            return response.json()
        
        return {"portfolios": [], "pagination": {}}

# Usage in UI pagination
page_data = await get_portfolios_page(page=1, page_size=10)
portfolios = page_data["portfolios"]
pagination = page_data["pagination"]

print(f"Showing {len(portfolios)} of {pagination['totalElements']} portfolios")
print(f"Page {pagination['currentPage'] + 1} of {pagination['totalPages']}")
```

### 4. Portfolio ID Extraction Pattern

**Use Case**: Extract portfolio ID for order processing

```python
async def get_portfolio_id_by_name(portfolio_name: str) -> Optional[str]:
    """Get portfolio ID by exact name match."""
    url = f"http://portfolio-service:8000/api/v2/portfolios"
    params = {"name": portfolio_name}
    
    async with httpx.AsyncClient() as client:
        response = await client.get(url, params=params)
        
        if response.status_code == 200:
            data = response.json()
            if data["portfolios"]:
                return data["portfolios"][0]["portfolioId"]
        
        return None

# Usage in order processing
portfolio_id = await get_portfolio_id_by_name("TechGrowthPortfolio")
if portfolio_id:
    # Proceed with order creation using portfolio_id
    pass
```

## Error Handling

### HTTP Status Codes

- **200 OK**: Search completed successfully (even if no results)
- **400 Bad Request**: Invalid parameters (mutual exclusivity, format errors)
- **422 Unprocessable Entity**: Validation errors
- **500 Internal Server Error**: Service unavailable

### Error Response Format

```json
{
  "detail": "Error message description"
}
```

### Common Error Scenarios

#### 1. Mutual Exclusivity Error
```json
{
  "detail": "Only one of 'name' or 'name_like' parameters can be provided"
}
```

#### 2. Invalid Name Format
```json
{
  "detail": "Name must be 1-200 characters and contain only alphanumeric characters, spaces, hyphens, and underscores"
}
```

#### 3. Validation Error
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

### Error Handling Pattern

```python
async def safe_portfolio_search(name: str = None, name_like: str = None) -> Dict:
    """Safely search portfolios with error handling."""
    url = f"http://portfolio-service:8000/api/v2/portfolios"
    params = {}
    
    if name:
        params["name"] = name
    elif name_like:
        params["name_like"] = name_like
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(url, params=params)
            
            if response.status_code == 200:
                return response.json()
            elif response.status_code == 400:
                error_data = response.json()
                raise ValueError(f"Invalid request: {error_data['detail']}")
            elif response.status_code == 422:
                error_data = response.json()
                raise ValueError(f"Validation error: {error_data['detail']}")
            else:
                raise Exception(f"Portfolio service error: {response.status_code}")
                
    except httpx.RequestError as e:
        raise Exception(f"Portfolio service unavailable: {e}")
```

## Performance Considerations

### 1. Response Time Expectations
- All operations complete within documented time limits
- No need for timeout handling beyond standard HTTP timeouts
- Service is optimized for high-frequency calls

### 2. Caching Recommendations
- Portfolio data changes infrequently
- Consider caching portfolio validation results for 5-10 minutes
- Cache portfolio lists for 2-5 minutes for UI performance

### 3. Pagination Best Practices
- Use reasonable page sizes (10-50 items) for UI display
- Implement pagination for any list that could exceed 100 items
- Use `hasNext`/`hasPrevious` flags for navigation controls

## Data Ordering

### v2 API Ordering
- **Default**: Results ordered by `dateCreated` descending (newest first)
- **Consistent**: Same ordering across all search types
- **Predictable**: Pagination maintains consistent ordering

### Comparison with v1 API
- **v1**: Uses default MongoDB ordering (insertion order)
- **v2**: Uses explicit `dateCreated` descending ordering
- **Recommendation**: Use v2 for consistent, predictable results

## Backward Compatibility

### v1 API Still Available
- **Endpoint**: `GET /api/v1/portfolios`
- **Response**: Simple array format
- **Use Case**: Legacy integrations only
- **Recommendation**: Migrate to v2 for new features

### Migration Path
1. **Phase 1**: Use v2 for new features (search, pagination)
2. **Phase 2**: Gradually migrate existing v1 calls to v2
3. **Phase 3**: Deprecate v1 usage (future consideration)

## Testing and Validation

### Health Check
```bash
# Verify service is available
curl -X GET "http://portfolio-service:8000/api/v2/portfolios?limit=1"
```

### Performance Validation
```bash
# Test exact name search performance
time curl -X GET "http://portfolio-service:8000/api/v2/portfolios?name=TechGrowthPortfolio"

# Test partial name search performance  
time curl -X GET "http://portfolio-service:8000/api/v2/portfolios?name_like=Tech"
```

### Integration Testing
```python
async def test_portfolio_integration():
    """Test portfolio service integration."""
    # Test 1: Validate existing portfolio
    assert await validate_portfolio_exists("TechGrowthPortfolio")
    
    # Test 2: Validate non-existent portfolio
    assert not await validate_portfolio_exists("NonExistentPortfolio")
    
    # Test 3: Search functionality
    results = await find_portfolios_by_partial_name("Tech")
    assert len(results) > 0
    
    # Test 4: Pagination
    page_data = await get_portfolios_page(page=0, page_size=5)
    assert "portfolios" in page_data
    assert "pagination" in page_data
```

## Summary

The Portfolio Service v2 API provides a robust, high-performance interface for portfolio search and retrieval. Key benefits for the Order Service:

- **Fast Validation**: Sub-200ms portfolio existence checks
- **User-Friendly Search**: Partial name matching for user assistance  
- **Scalable Pagination**: Efficient handling of large portfolio lists
- **Consistent Responses**: Structured format with comprehensive metadata
- **Error Resilience**: Clear error messages and status codes

Use the provided integration patterns and error handling approaches to ensure reliable communication between the Order Service and Portfolio Service. 