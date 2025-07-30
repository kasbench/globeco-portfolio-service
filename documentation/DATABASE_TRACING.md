# Database Tracing Implementation

## Overview

This document describes the database tracing implementation added to the Portfolio Service to enable better observability of database operations in Jaeger traces.

## Implementation

### Tracing Utility (`app/tracing.py`)

The `trace_database_call` function wraps database operations with OpenTelemetry spans to provide detailed tracing information:

- **Span naming**: Uses format `db.{collection_name}.{operation_name}` (e.g., `db.portfolio.find_all`)
- **Attributes**: Includes standard database attributes following OpenTelemetry semantic conventions
- **Error handling**: Captures exceptions and sets appropriate span status
- **Result metadata**: Adds result count for applicable operations

### Database Operations Traced

All database operations in `PortfolioService` are now traced:

1. **`get_all_portfolios()`** → `db.portfolio.find_all`
2. **`get_portfolio_by_id()`** → `db.portfolio.find_by_id`  
3. **`create_portfolio()`** → `db.portfolio.insert`
4. **`update_portfolio()`** → `db.portfolio.update`
5. **`delete_portfolio()`** → `db.portfolio.delete`
6. **`search_portfolios()`** → `db.portfolio.count` + `db.portfolio.find_with_pagination`

### Span Attributes

Each database span includes the following attributes:

- `db.system`: "mongodb"
- `db.name`: "portfolio_db"
- `db.collection.name`: Collection being accessed
- `db.operation`: Type of operation being performed
- `db.result.count`: Number of results (for applicable operations)
- `db.query.limit`: Query limit (for paginated operations)
- `db.query.offset`: Query offset (for paginated operations)

## Benefits for Jaeger Traces

### Before Implementation
- Only HTTP request spans were visible
- Database wait time was hidden within service method execution
- Difficult to identify database performance bottlenecks

### After Implementation
- Clear visibility into database operation timing
- Separate spans for each database call
- Easy identification of slow database operations
- Better understanding of the request flow:
  ```
  GET /api/v1/portfolios
  └── PortfolioService.get_all_portfolios
      └── db.portfolio.find_all  ← NEW: Database operation span
  ```

## Usage in Jaeger

When viewing traces for `GET /api/v1/portfolios` in Jaeger, you will now see:

1. **HTTP request span** - Overall request timing
2. **Service method span** - Business logic timing  
3. **Database operation span** - Database call timing

This allows you to easily identify:
- How much time is spent waiting on database calls
- Which specific database operations are slow
- Database connection or query performance issues

## Testing

Unit tests are provided in `tests/test_tracing.py` to verify:
- Spans are created with correct names and attributes
- Success scenarios set appropriate span status
- Error scenarios capture exceptions and set error status
- Result metadata is properly recorded