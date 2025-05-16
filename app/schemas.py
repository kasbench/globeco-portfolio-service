from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime

class PortfolioResponseDTO(BaseModel):
    portfolioId: str = Field(...)
    name: str = Field(...)
    dateCreated: Optional[datetime] = None
    version: int = Field(...)

class PortfolioPutDTO(BaseModel):
    portfolioId: str = Field(...)
    name: str = Field(...)
    dateCreated: Optional[datetime] = None
    version: int = Field(...)

class PortfolioPostDTO(BaseModel):
    name: str = Field(...)
    dateCreated: Optional[datetime] = None
    version: Optional[int] = 1 