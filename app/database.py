from motor.motor_asyncio import AsyncIOMotorClient
from app.config import settings
from app.tracing import trace_database_call
import logging
from typing import Optional
from pymongo.errors import ServerSelectionTimeoutError, ConnectionFailure
import asyncio

logger = logging.getLogger(__name__)


def create_optimized_client(mongodb_uri: Optional[str] = None) -> AsyncIOMotorClient:
    """
    Create optimized MongoDB client with tuned connection settings for performance.
    
    Implements connection pool configuration with:
    - maxPoolSize=20, minPoolSize=5 for optimal resource usage
    - Connection timeout and retry configuration
    - Environment-based optimization settings
    
    Args:
        mongodb_uri: MongoDB connection URI (optional, uses settings default)
        
    Returns:
        Configured AsyncIOMotorClient with optimized settings
    """
    try:
        from app.environment_config import get_config_manager
        config_manager = get_config_manager()
        db_config = config_manager.get_database_config()
        
        # Use environment-specific connection pool settings
        max_pool_size = db_config.max_pool_size
        min_pool_size = db_config.min_pool_size
        connection_timeout = db_config.connection_timeout
        
        logger.info(
            f"Creating optimized MongoDB client: max_pool_size={max_pool_size}, "
            f"min_pool_size={min_pool_size}, connection_timeout={connection_timeout}ms"
        )
        
    except Exception as e:
        # Fallback to default optimized settings if config manager fails
        logger.warning(f"Failed to load database config, using defaults: {e}")
        max_pool_size = 20
        min_pool_size = 5
        connection_timeout = 30000
    
    uri = mongodb_uri or settings.mongodb_uri
    
    # Optimized connection parameters
    client = AsyncIOMotorClient(
        uri,
        # Connection pool settings
        maxPoolSize=max_pool_size,           # Maximum connections in pool
        minPoolSize=min_pool_size,           # Minimum connections to maintain
        maxIdleTimeMS=300000,                # 5 minutes max idle time
        
        # Connection timeout settings
        connectTimeoutMS=connection_timeout,  # Connection establishment timeout
        serverSelectionTimeoutMS=5000,       # Server selection timeout (5s)
        socketTimeoutMS=60000,               # Socket timeout (60s)
        
        # Retry and reliability settings
        retryWrites=True,                    # Enable retry writes
        retryReads=True,                     # Enable retry reads
        maxConnecting=10,                    # Max concurrent connection attempts
        
        # Performance optimizations
        compressors="zstd,zlib,snappy",      # Enable compression
        zlibCompressionLevel=6,              # Balanced compression level
        
        # Monitoring and health
        heartbeatFrequencyMS=10000,          # Heartbeat every 10s
        serverMonitoringMode="stream",       # Use streaming monitoring
        
        # Write concern for performance (can be overridden per operation)
        w=1,                                 # Acknowledge from primary only
        journal=False,                       # Don't wait for journal sync (faster)
        
        # Read preferences for performance
        readPreference="primary",            # Read from primary for consistency
        readConcernLevel="local",            # Local read concern for performance
    )
    
    logger.info(
        f"MongoDB client created successfully: uri={uri[:50]}..., "
        f"pool_config=max:{max_pool_size}/min:{min_pool_size}"
    )
    
    return client


async def test_connection_health(client: AsyncIOMotorClient, timeout: float = 5.0) -> bool:
    """
    Test MongoDB connection health with timeout.
    
    Args:
        client: MongoDB client to test
        timeout: Timeout in seconds for the health check
        
    Returns:
        True if connection is healthy, False otherwise
    """
    try:
        # Use admin command with timeout
        await asyncio.wait_for(
            client.admin.command("ping"),
            timeout=timeout
        )
        return True
    except (ServerSelectionTimeoutError, ConnectionFailure, asyncio.TimeoutError) as e:
        logger.warning(f"MongoDB connection health check failed: {e}")
        return False
    except Exception as e:
        logger.error(f"Unexpected error during MongoDB health check: {e}")
        return False


async def get_connection_pool_stats(client: AsyncIOMotorClient) -> dict:
    """
    Get connection pool statistics for monitoring.
    
    Args:
        client: MongoDB client to inspect
        
    Returns:
        Dictionary with connection pool statistics
    """
    try:
        # Get server info and connection stats
        server_info = await client.server_info()
        
        # Note: Motor/PyMongo doesn't expose detailed pool stats directly
        # This provides basic connection information
        stats = {
            "server_version": server_info.get("version", "unknown"),
            "connection_configured": True,
            "max_pool_size": getattr(client, "max_pool_size", "unknown"),
            "min_pool_size": getattr(client, "min_pool_size", "unknown"),
        }
        
        return stats
        
    except Exception as e:
        logger.error(f"Failed to get connection pool stats: {e}")
        return {
            "error": str(e),
            "connection_configured": False
        }

async def create_indexes():
    """Create MongoDB indexes for optimal search performance using optimized client"""
    client = None
    try:
        # Use optimized client for index creation
        client = create_optimized_client()
        
        # Test connection health before proceeding
        if not await test_connection_health(client):
            raise ConnectionFailure("MongoDB connection health check failed")
        
        db = client[settings.mongodb_db]
        portfolio_collection = db.portfolio
        
        # Create text index on name field for efficient searching
        await trace_database_call(
            "create_text_index",
            "portfolio",
            lambda: portfolio_collection.create_index([("name", "text")])
        )
        logger.info("Created text index on portfolio name field")
        
        # Create compound index for name field (case-insensitive) and dateCreated for sorting
        await trace_database_call(
            "create_compound_index", 
            "portfolio",
            lambda: portfolio_collection.create_index([("name", 1), ("dateCreated", -1)])
        )
        logger.info("Created compound index on name and dateCreated fields")
        
        # Log connection pool stats for monitoring
        pool_stats = await get_connection_pool_stats(client)
        logger.info(f"Index creation completed with connection stats: {pool_stats}")
        
    except Exception as e:
        logger.error(f"Error creating indexes: {e}")
        raise
    finally:
        if client:
            client.close()
            logger.debug("MongoDB client closed after index creation") 