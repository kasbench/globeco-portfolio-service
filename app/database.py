from motor.motor_asyncio import AsyncIOMotorClient
from app.config import settings
import logging

logger = logging.getLogger(__name__)

async def create_indexes():
    """Create MongoDB indexes for optimal search performance"""
    try:
        client = AsyncIOMotorClient(settings.mongodb_uri)
        db = client[settings.mongodb_db]
        portfolio_collection = db.portfolio
        
        # Create text index on name field for efficient searching
        await portfolio_collection.create_index([("name", "text")])
        logger.info("Created text index on portfolio name field")
        
        # Create compound index for name field (case-insensitive) and dateCreated for sorting
        await portfolio_collection.create_index([("name", 1), ("dateCreated", -1)])
        logger.info("Created compound index on name and dateCreated fields")
        
        client.close()
        
    except Exception as e:
        logger.error(f"Error creating indexes: {e}")
        raise 