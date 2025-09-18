"""
Minimal FastAPI application without OpenTelemetry overhead for performance testing.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from beanie import init_beanie
from motor.motor_asyncio import AsyncIOMotorClient
from app.config import settings
from app.models import Portfolio
from app import api_v1, api_v2
from app.database import create_indexes
from app.logging_config import setup_logging, get_logger
from contextlib import asynccontextmanager
import os

# Setup minimal logging
logger = setup_logging(log_level="WARNING")  # Minimal logging

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Minimal lifespan with just database setup"""
    client = AsyncIOMotorClient(settings.mongodb_uri)
    await init_beanie(
        database=client[settings.mongodb_db],
        document_models=[Portfolio],
    )
    # Create database indexes for optimal search performance
    await create_indexes()
    logger.info("Database initialized")
    yield
    logger.info("Application shutdown")

# Create minimal FastAPI app
app = FastAPI(
    title="GlobeCo Portfolio Service (Performance Mode)",
    lifespan=lifespan
)

# Configure CORS (minimal)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API routers
app.include_router(api_v1.router)
app.include_router(api_v2.router)

@app.get("/")
async def root():
    return {"message": "GlobeCo Portfolio Service - Performance Mode"}

@app.get("/health")
async def health():
    return {"status": "healthy", "service": "globeco-portfolio-service", "mode": "performance"}

# Simple metrics endpoint (just returns empty)
@app.get("/metrics")
async def get_metrics():
    from fastapi.responses import Response
    return Response(
        content="# No metrics in performance mode\n",
        media_type="text/plain; version=0.0.4; charset=utf-8"
    )