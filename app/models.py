from beanie import Document
from pydantic import Field
from typing import Optional
from datetime import datetime
from bson import ObjectId

class Portfolio(Document):
    id: Optional[ObjectId] = Field(default_factory=ObjectId, alias="_id")
    name: str
    dateCreated: datetime = Field(default_factory=datetime.utcnow)
    version: int = 1

    class Settings:
        name = "portfolio"

    model_config = {"arbitrary_types_allowed": True} 