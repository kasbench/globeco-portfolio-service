from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
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

# New DTOs for v2 API with pagination
class PaginationDTO(BaseModel):
    totalElements: int = Field(...)
    totalPages: int = Field(...)
    currentPage: int = Field(...)
    pageSize: int = Field(...)
    hasNext: bool = Field(...)
    hasPrevious: bool = Field(...)

class PortfolioSearchResponseDTO(BaseModel):
    portfolios: List[PortfolioResponseDTO] = Field(...)
    pagination: PaginationDTO = Field(...)

# Bulk validation error schema for detailed error reporting
class BulkValidationError(BaseModel):
    message: str = Field(..., description="Overall error message for the bulk operation")
    errors: List[Dict[str, Any]] = Field(..., description="Per-portfolio validation errors with details") 