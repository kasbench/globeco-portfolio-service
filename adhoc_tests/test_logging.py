#!/usr/bin/env python3
"""
Test script to demonstrate structured JSON logging functionality
"""

import asyncio
import json
from app.logging_config import setup_logging, get_logger

async def test_structured_logging():
    """Test the structured logging functionality"""
    
    # Setup logging
    setup_logging(log_level="INFO")
    logger = get_logger("test_logging")
    
    print("=== Testing Structured JSON Logging ===\n")
    
    # Test basic logging
    logger.info("Application started", component="test_app", version="1.0.0")
    
    # Test logging with various fields
    logger.info("Processing user request", 
               user_id="12345",
               action="create_portfolio",
               ip_address="192.168.1.100",
               user_agent="Mozilla/5.0")
    
    # Test warning with additional context
    logger.warning("Rate limit approaching", 
                  user_id="12345",
                  current_requests=95,
                  limit=100,
                  window="1m")
    
    # Test error logging
    try:
        raise ValueError("Sample error for testing")
    except Exception as e:
        logger.error("Error processing request", 
                    error=str(e),
                    user_id="12345",
                    operation="test_operation")
    
    # Test database operation logging
    logger.info("Database operation completed",
               operation="find_all",
               collection="portfolio",
               duration=45.2,
               count=150)
    
    # Test API request logging
    logger.info("API request completed",
               method="GET",
               path="/api/v1/portfolios",
               status=200,
               duration=123.45,
               bytes=2048,
               request_id="req-123-456",
               correlation_id="corr-789-012")
    
    print("\n=== Structured logging test completed ===")
    print("All log entries above should be in JSON format with the following fields:")
    print("- timestamp (ISO 8601)")
    print("- level (info, warning, error, etc.)")
    print("- msg (log message)")
    print("- application (globeco-portfolio-service)")
    print("- server (hostname)")
    print("- location (module:function:line)")
    print("- Plus any additional custom fields")

if __name__ == "__main__":
    asyncio.run(test_structured_logging())