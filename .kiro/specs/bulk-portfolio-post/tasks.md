# Implementation Plan

- [x] 1. Add bulk validation error schema for detailed error reporting
  - Create BulkValidationError schema in schemas.py to handle batch-specific validation errors
  - Include fields for overall message and per-portfolio error details
  - _Requirements: 4.1, 4.2_

- [x] 2. Implement retry logic utility in services layer
  - Create _execute_with_retry static method in PortfolioService class
  - Implement exponential backoff with delays of 1s, 2s, 4s for up to 3 retry attempts
  - Add logic to distinguish between recoverable and non-recoverable database errors
  - Include comprehensive logging for retry attempts and failures
  - _Requirements: 3.1, 3.2, 3.3_

- [x] 3. Create bulk portfolio creation service method
  - Implement create_portfolios_bulk static method in PortfolioService class
  - Convert list of PortfolioPostDTO to Portfolio model objects with proper defaults
  - Integrate MongoDB transaction support using Beanie ODM sessions
  - Implement all-or-nothing batch processing with proper rollback on failures
  - Use the retry logic utility for database operations
  - _Requirements: 1.1, 2.1, 2.2, 3.1_

- [x] 4. Add input validation helper methods
  - Create _validate_bulk_request helper method to check list size constraints (1-100 portfolios)
  - Create _check_duplicate_names helper method to detect duplicate portfolio names within the batch
  - Add validation for empty requests and oversized requests
  - _Requirements: 1.1, 1.2, 1.3_

- [x] 5. Implement bulk portfolio POST endpoint in API v2
  - Add POST /api/v2/portfolios endpoint in api_v2.py that accepts List[PortfolioPostDTO]
  - Implement comprehensive input validation using helper methods
  - Add proper error handling with appropriate HTTP status codes (400, 500)
  - Return List[PortfolioResponseDTO] on success with HTTP 201 status
  - Include structured logging for all operations and error scenarios
  - _Requirements: 1.1, 2.3, 4.1, 4.2, 4.3, 5.1, 5.2, 5.3_

- [x] 6. Write unit tests for retry logic utility
  - Test successful operation without retries
  - Test retry behavior with recoverable errors (connection timeouts, temporary failures)
  - Test immediate failure with non-recoverable errors (authentication, constraint violations)
  - Test exponential backoff timing and maximum retry limits
  - Mock database operations to simulate various error conditions
  - _Requirements: 3.1, 3.2, 3.3_

- [x] 7. Write unit tests for bulk service method
  - Test successful bulk creation with valid portfolio data
  - Test transaction rollback behavior when individual portfolios fail validation
  - Test transaction rollback behavior when database operations fail
  - Test proper conversion from DTOs to model objects
  - Mock database sessions and transaction operations
  - _Requirements: 1.4, 2.1, 2.2_

- [ ] 8. Write unit tests for validation helper methods
  - Test list size validation with empty lists, valid sizes (1-100), and oversized lists (>100)
  - Test duplicate name detection within batches
  - Test edge cases with whitespace and case sensitivity in names
  - _Requirements: 1.1, 1.2, 1.3_

- [ ] 9. Write integration tests for bulk API endpoint
  - Test successful bulk creation with various batch sizes (1, 50, 100 portfolios)
  - Test validation error responses for invalid requests (empty, oversized, invalid data)
  - Test error responses for database failures and transaction rollbacks
  - Test proper HTTP status codes and response formats
  - Test concurrent bulk requests to verify transaction isolation
  - _Requirements: 1.1, 2.3, 4.1, 4.2, 5.1, 5.2, 5.3_

- [ ] 10. Add comprehensive error handling tests
  - Test various database error scenarios (connection failures, timeouts, constraint violations)
  - Test retry behavior in integration environment with actual database
  - Test transaction timeout scenarios
  - Verify proper error logging and monitoring integration
  - _Requirements: 3.1, 3.2, 3.3, 4.3_