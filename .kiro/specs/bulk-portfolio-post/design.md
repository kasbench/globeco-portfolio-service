# Design Document

## Overview

The bulk portfolio posting feature extends the existing API v2 with a new endpoint `POST /api/v2/portfolios` that accepts a list of up to 100 PortfolioPostDTO objects and returns a list of PortfolioResponseDTO objects. The implementation leverages MongoDB transactions to ensure atomicity and includes retry logic with exponential backoff for handling transient database errors.

## Architecture

The feature follows the existing layered architecture pattern:

```
API Layer (api_v2.py) 
    ↓
Service Layer (services.py)
    ↓  
Data Layer (models.py via Beanie ODM)
    ↓
MongoDB Database
```

### Key Components:
- **API Endpoint**: New POST route in `api_v2.py` 
- **Service Method**: New bulk creation method in `PortfolioService`
- **Transaction Management**: MongoDB session-based transactions
- **Retry Logic**: Exponential backoff for recoverable errors
- **Validation**: Request size limits and DTO validation

## Components and Interfaces

### API Layer (`app/api_v2.py`)

**New Endpoint:**
```python
@router.post("/portfolios", response_model=List[PortfolioResponseDTO], status_code=201)
async def create_portfolios_bulk(portfolios: List[PortfolioPostDTO])
```

**Input Validation:**
- List size: 1-100 portfolios
- Individual portfolio validation using existing PortfolioPostDTO
- Request payload size limits

**Response Handling:**
- Success: HTTP 201 with List[PortfolioResponseDTO]
- Validation errors: HTTP 400 with error details
- Server errors: HTTP 500 with generic message

### Service Layer (`app/services.py`)

**New Method:**
```python
@staticmethod
async def create_portfolios_bulk(portfolio_dtos: List[PortfolioPostDTO]) -> List[Portfolio]
```

**Transaction Management:**
- Uses MongoDB sessions for ACID transactions
- All-or-nothing semantics for the entire batch
- Proper session cleanup in finally blocks

**Retry Logic:**
```python
@staticmethod
async def _execute_with_retry(operation, max_retries=3) -> Any
```

- Exponential backoff: 1s, 2s, 4s delays
- Distinguishes recoverable vs non-recoverable errors
- Logs retry attempts for observability

### Data Models

**Existing Models (No Changes Required):**
- `Portfolio` model remains unchanged
- `PortfolioPostDTO` and `PortfolioResponseDTO` schemas remain unchanged

**Transaction Support:**
- Leverages MongoDB 4.0+ multi-document transactions
- Uses Beanie ODM's session support for transaction management

## Data Models

### Input Schema
```python
# Existing PortfolioPostDTO (no changes)
class PortfolioPostDTO(BaseModel):
    name: str = Field(...)
    dateCreated: Optional[datetime] = None
    version: Optional[int] = 1

# Request body: List[PortfolioPostDTO] (1-100 items)
```

### Output Schema
```python
# Existing PortfolioResponseDTO (no changes)
class PortfolioResponseDTO(BaseModel):
    portfolioId: str = Field(...)
    name: str = Field(...)
    dateCreated: Optional[datetime] = None
    version: int = Field(...)

# Response body: List[PortfolioResponseDTO]
```

### Error Schemas
```python
# Reuse existing FastAPI HTTPException format
# Consider creating BulkValidationError for detailed batch errors
class BulkValidationError(BaseModel):
    message: str
    errors: List[Dict[str, Any]]  # Per-portfolio validation errors
```

## Error Handling

### Validation Errors
- **Empty list**: HTTP 400 "Request must contain at least 1 portfolio"
- **Oversized list**: HTTP 400 "Request cannot contain more than 100 portfolios"
- **Invalid portfolio data**: HTTP 400 with detailed validation errors
- **Duplicate names in batch**: HTTP 400 "Duplicate portfolio names in request"

### Database Errors
- **Recoverable errors** (connection timeouts, temporary unavailability):
  - Retry up to 3 times with exponential backoff
  - Log each retry attempt
- **Non-recoverable errors** (constraint violations, authentication):
  - Fail immediately without retry
  - Return HTTP 500 with generic error message

### Transaction Failures
- **Rollback behavior**: All changes reverted on any failure
- **Partial success handling**: Not supported - all portfolios succeed or all fail
- **Timeout handling**: Configurable transaction timeout with appropriate error response

## Testing Strategy

### Unit Tests
- **Service layer tests**: Mock database operations, test retry logic
- **Validation tests**: Test input validation rules and edge cases
- **Error handling tests**: Test various error scenarios and retry behavior
- **Transaction tests**: Test rollback behavior on failures

### Integration Tests
- **Database integration**: Test actual MongoDB transactions
- **API endpoint tests**: Test full request/response cycle
- **Concurrent access tests**: Test behavior under concurrent requests
- **Performance tests**: Test with maximum payload size (100 portfolios)

### Test Data Scenarios
- **Valid batch**: 1-100 valid portfolios
- **Mixed validity**: Some valid, some invalid portfolios in batch
- **Duplicate names**: Within batch and against existing data
- **Large payloads**: Test at size limits
- **Database failures**: Simulate various database error conditions

## Implementation Considerations

### Performance
- **Batch size limit**: 100 portfolios balances usability and performance
- **Transaction scope**: Keep transactions short to minimize lock contention
- **Memory usage**: Process portfolios in single batch to maintain transaction integrity

### Monitoring and Observability
- **Metrics**: Track bulk operation success/failure rates, retry counts
- **Logging**: Structured logging for batch operations, retry attempts
- **Tracing**: Extend existing tracing to cover bulk operations

### Security
- **Input validation**: Leverage existing PortfolioPostDTO validation
- **Rate limiting**: Consider implementing rate limits for bulk endpoints
- **Authorization**: Reuse existing authentication/authorization patterns

### Backward Compatibility
- **No breaking changes**: Existing v1 and v2 endpoints remain unchanged
- **Schema compatibility**: Reuse existing DTOs for consistency
- **Error format consistency**: Maintain similar error response patterns