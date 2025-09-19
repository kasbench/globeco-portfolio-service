"""
Database initialization helper for ensuring Beanie ODM is properly initialized.

This module provides utilities to initialize the database connection and Beanie ODM
even when the FastAPI lifespan events don't run (e.g., during testing).
"""

import asyncio
import logging
from typing import Optional
from motor.motor_asyncio import AsyncIOMotorClient
from beanie import init_beanie

from app.config import settings
from app.models import Portfolio
from app.database import create_optimized_client, create_indexes

logger = logging.getLogger(__name__)

# Global state to track initialization
_database_initialized = False
_database_client: Optional[AsyncIOMotorClient] = None
_initialization_lock = asyncio.Lock()


async def ensure_database_initialized() -> bool:
    """
    Ensure that the database and Beanie ODM are properly initialized.
    
    This function can be called multiple times safely and will only initialize once.
    It's designed to work both in normal application startup and during testing.
    
    Returns:
        True if initialization was successful, False otherwise
    """
    global _database_initialized, _database_client
    
    if _database_initialized:
        return True
    
    async with _initialization_lock:
        # Double-check after acquiring lock
        if _database_initialized:
            return True
        
        try:
            logger.info("Initializing database connection and Beanie ODM")
            
            # Create optimized MongoDB client
            _database_client = create_optimized_client()
            
            # Initialize Beanie ODM
            await init_beanie(
                database=_database_client[settings.mongodb_db],
                document_models=[Portfolio],
            )
            
            # Create database indexes for optimal performance
            await create_indexes()
            
            _database_initialized = True
            
            logger.info(
                f"Database initialization completed successfully: database={settings.mongodb_db}, "
                f"connection_optimized=True, indexes_created=True"
            )
            
            return True
            
        except Exception as e:
            logger.error(
                f"Database initialization failed: {e} (type: {type(e).__name__})",
                exc_info=True
            )
            
            # Clean up on failure
            if _database_client:
                _database_client.close()
                _database_client = None
            
            return False


async def close_database_connection() -> None:
    """Close the database connection and reset initialization state."""
    global _database_initialized, _database_client
    
    async with _initialization_lock:
        if _database_client:
            _database_client.close()
            _database_client = None
        
        _database_initialized = False
        
        logger.info("Database connection closed and state reset")


def is_database_initialized() -> bool:
    """Check if the database is initialized."""
    return _database_initialized


def get_database_client() -> Optional[AsyncIOMotorClient]:
    """Get the current database client if initialized."""
    return _database_client