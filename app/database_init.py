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
    
    NOTE: In production, the database is initialized during application startup
    via the FastAPI lifespan. This function is primarily for testing scenarios
    where the lifespan events don't run.
    
    Returns:
        True if initialization was successful, False otherwise
    """
    global _database_initialized, _database_client
    
    # First check if Beanie is already initialized (by main app startup)
    try:
        # Try a simple database operation to check if Beanie is working
        from app.models import Portfolio
        # If we can access the motor collection, Beanie is initialized
        if Portfolio.get_motor_collection() is not None:
            # Beanie is already initialized by the main application
            if not _database_initialized:
                logger.debug("Database already initialized by application startup, skipping duplicate initialization")
                _database_initialized = True
            return True
    except Exception:
        # Beanie not initialized yet, continue with initialization
        pass
    
    if _database_initialized:
        return True
    
    async with _initialization_lock:
        # Double-check after acquiring lock
        if _database_initialized:
            return True
        
        # Check again if Beanie was initialized while we were waiting for the lock
        try:
            from app.models import Portfolio
            if Portfolio.get_motor_collection() is not None:
                logger.debug("Database was initialized while waiting for lock, skipping duplicate initialization")
                _database_initialized = True
                return True
        except Exception:
            pass
        
        try:
            logger.info("Initializing database connection and Beanie ODM (fallback for testing)")
            
            # Create optimized MongoDB client
            _database_client = create_optimized_client()
            
            # Initialize Beanie ODM
            await init_beanie(
                database=_database_client[settings.mongodb_db],
                document_models=[Portfolio],
            )
            
            # Create database indexes using the same client
            await create_indexes(_database_client)
            
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