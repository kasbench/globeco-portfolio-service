# Bulk Portfolio Creation API - Client Guide

## Overview

The Bulk Portfolio Creation API allows you to create multiple portfolios in a single request. This endpoint processes all portfolios as a single transaction - either all portfolios are created successfully, or none are created if any validation or processing errors occur.

## Endpoint Details

**URL:** `POST /api/v2/portfolios`

**Content-Type:** `application/json`

**Authentication:** Not required (based on current implementation)

## Request Format

### Request Body

The request body must be a JSON array containing 1-100 portfolio objects.

```json
[
  {
    "name": "string",
    "dateCreated": "2024-01-15T10:30:00Z",
    "version": 1
  }
]
```

### Request Object Schema (PortfolioPostDTO)

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `name` | string | Yes | - | Portfolio name (1-200 characters, alphanumeric, spaces, hyphens, underscores only) |
| `dateCreated` | string (ISO 8601 datetime) | No | Current timestamp | When the portfolio was created |
| `version` | integer | No | 1 | Portfolio version number |

### Request Constraints

- **Minimum portfolios:** 1
- **Maximum portfolios:** 100
- **Name format:** 1-200 characters, alphanumeric characters, spaces, hyphens (-), and underscores (_) only
- **Duplicate names:** Not allowed within the same request (case-insensitive)

## Response Format

### Success Response (HTTP 201)

```json
[
  {
    "portfolioId": "507f1f77bcf86cd799439011",
    "name": "My Portfolio",
    "dateCreated": "2024-01-15T10:30:00Z",
    "version": 1
  }
]
```

### Response Object Schema (PortfolioResponseDTO)

| Field | Type | Description |
|-------|------|-------------|
| `portfolioId` | string | Unique identifier for the created portfolio |
| `name` | string | Portfolio name |
| `dateCreated` | string (ISO 8601 datetime) | When the portfolio was created |
| `version` | integer | Portfolio version number |

## Status Codes

| Status Code | Description | Response Body |
|-------------|-------------|---------------|
| 201 | Created - All portfolios created successfully | Array of PortfolioResponseDTO objects |
| 400 | Bad Request - Validation error | Error message with details |
| 500 | Internal Server Error - Database or system error | Generic error message |

## Error Conditions

### HTTP 400 - Bad Request

The following conditions will result in a 400 error:

1. **Empty Request**
   ```json
   {
     "detail": "Request must contain at least 1 portfolio"
   }
   ```

2. **Too Many Portfolios**
   ```json
   {
     "detail": "Request cannot contain more than 100 portfolios"
   }
   ```

3. **Duplicate Portfolio Names**
   ```json
   {
     "detail": "Duplicate portfolio names found in request: Portfolio A, Portfolio B"
   }
   ```

4. **Invalid Portfolio Name Format**
   - Names must be 1-200 characters
   - Only alphanumeric characters, spaces, hyphens, and underscores allowed
   - Names cannot be empty or contain only whitespace

### HTTP 500 - Internal Server Error

```json
{
  "detail": "An unexpected error occurred while creating portfolios"
}
```

This occurs when there are database connectivity issues, system errors, or other unexpected failures.

## Example Requests

### Single Portfolio

```bash
curl -X POST "https://your-api-domain.com/api/v2/portfolios" \
  -H "Content-Type: application/json" \
  -d '[
    {
      "name": "My New Portfolio",
      "version": 1
    }
  ]'
```

### Multiple Portfolios

```bash
curl -X POST "https://your-api-domain.com/api/v2/portfolios" \
  -H "Content-Type: application/json" \
  -d '[
    {
      "name": "Portfolio Alpha",
      "dateCreated": "2024-01-15T10:30:00Z",
      "version": 1
    },
    {
      "name": "Portfolio Beta",
      "version": 2
    },
    {
      "name": "Portfolio Gamma"
    }
  ]'
```

### Example Success Response

```json
[
  {
    "portfolioId": "507f1f77bcf86cd799439011",
    "name": "Portfolio Alpha",
    "dateCreated": "2024-01-15T10:30:00Z",
    "version": 1
  },
  {
    "portfolioId": "507f1f77bcf86cd799439012",
    "name": "Portfolio Beta",
    "dateCreated": "2024-01-15T10:31:00Z",
    "version": 2
  },
  {
    "portfolioId": "507f1f77bcf86cd799439013",
    "name": "Portfolio Gamma",
    "dateCreated": "2024-01-15T10:31:00Z",
    "version": 1
  }
]
```

## Implementation Notes

### Transaction Behavior

- All portfolios in a request are processed as a single database transaction
- If any portfolio fails validation or creation, the entire request fails
- No partial success - either all portfolios are created or none are created

### Performance Considerations

- Optimal batch size: 10-50 portfolios per request
- Large batches (50-100 portfolios) may take longer to process
- The API includes retry logic for transient database errors

### Rate Limiting

Currently, there are no explicit rate limits on this endpoint. However, consider implementing reasonable request frequency to avoid overwhelming the system.

## Error Handling Best Practices

1. **Always check the HTTP status code** before processing the response
2. **Handle 400 errors** by validating your request data and fixing validation issues
3. **Implement retry logic** for 500 errors with exponential backoff
4. **Log error responses** for debugging and monitoring purposes

## Support

For technical support or questions about this API, please contact your system administrator or API support team.

---

**API Version:** v2  
**Last Updated:** January 2024  
**Document Version:** 1.0