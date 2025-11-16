"""
Streamlined Portfolio Service main application with integrated optimized components.

This module wires together all optimized components including:
- Environment-based configuration management
- Unified OpenTelemetry-only monitoring (Prometheus completely removed)
- Conditional middleware loading
- Optimized database operations
- Circuit breaker pattern
- Validation caching
- Graceful startup and shutdown procedures
"""

import asyncio
import logging
import os
import signal
import sys
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI
from beanie import init_beanie
from motor.motor_asyncio import AsyncIOMotorClient

# Import optimized components
from app.config import settings
from app.logging_config import setup_logging, get_logger
from app.environment_config import initialize_config_manager, initialize_feature_flags
from app.unified_monitoring import initialize_unified_monitoring, get_unified_monitoring
from app.middleware_factory import create_middleware_stack
from app.circuit_breaker import get_circuit_breaker_registry, CircuitBreakerConfig
from app.validation_cache import get_validation_cache
from app.database import create_optimized_client, create_indexes
from app.models import Portfolio

# Import API routers
from app import api_v1, api_v2, api_fast
from app.health_endpoints import router as health_router

# Global state for graceful shutdown
_shutdown_event: Optional[asyncio.Event] = None
_unified_monitoring = None
_database_client: Optional[AsyncIOMotorClient] = None

# Setup structured logging first
logger = setup_logging(log_level=settings.log_level)

async def initialize_database() -> AsyncIOMotorClient:
    """
    Initialize optimized database connection with proper error handling.
    
    Returns:
        AsyncIOMotorClient instance
        
    Raises:
        RuntimeError: If database initialization fails
    """
    global _database_client
    
    try:
        logger.info("Initializing optimized database connection")
        
        # Create optimized MongoDB client
        _database_client = create_optimized_client()
        
        # Initialize Beanie ODM
        await init_beanie(
            database=_database_client[settings.mongodb_db],
            document_models=[Portfolio],
        )
        
        # Create database indexes using the same client
        await create_indexes(_database_client)
        
        logger.info(
            "Database initialization completed successfully",
            database=settings.mongodb_db,
            connection_optimized=True,
            indexes_created=True
        )
        
        return _database_client
        
    except Exception as e:
        logger.error(
            f"Database initialization failed: {e}",
            error_type=type(e).__name__,
            exc_info=True
        )
        raise RuntimeError(f"Database initialization failed: {e}") from e


async def initialize_circuit_breakers() -> None:
    """Initialize circuit breakers for external dependencies."""
    try:
        logger.info("Initializing circuit breakers")
        
        registry = get_circuit_breaker_registry()
        
        # Database circuit breaker
        db_config = CircuitBreakerConfig(
            name="database",
            failure_threshold=5,
            recovery_timeout=30,
            success_threshold=3,
            timeout=10
        )
        registry.register("database", db_config)
        
        # OTLP export circuit breaker
        otlp_config = CircuitBreakerConfig(
            name="otlp_export",
            failure_threshold=3,
            recovery_timeout=60,
            success_threshold=2,
            timeout=30
        )
        registry.register("otlp_export", otlp_config)
        
        logger.info(
            "Circuit breakers initialized successfully",
            total_breakers=len(registry.list_breakers()),
            breaker_names=list(registry.list_breakers().keys())
        )
        
    except Exception as e:
        logger.error(
            f"Circuit breaker initialization failed: {e}",
            error_type=type(e).__name__,
            exc_info=True
        )
        # Don't raise - circuit breakers are for resilience, not critical for startup


async def initialize_validation_cache() -> None:
    """Initialize validation cache for performance optimization."""
    try:
        logger.info("Initializing validation cache")
        
        # Initialize validation cache with environment-appropriate size
        config_manager = get_or_create_config_manager()
        cache_size = 2000 if config_manager.is_production() else 1000
        
        cache = get_validation_cache(max_size=cache_size)
        
        logger.info(
            f"Validation cache initialized successfully",
            max_size=cache_size,
            environment=config_manager.current_environment
        )
        
    except Exception as e:
        logger.error(
            f"Validation cache initialization failed: {e}",
            error_type=type(e).__name__,
            exc_info=True
        )
        # Don't raise - cache is for performance, not critical for startup


async def startup_sequence() -> None:
    """
    Execute complete startup sequence with proper dependency order.
    
    Startup order:
    1. Environment configuration
    2. Unified monitoring (OpenTelemetry only)
    3. Circuit breakers
    4. Validation cache
    5. Database connection
    6. Async monitoring components
    """
    global _unified_monitoring
    
    try:
        logger.info("Starting Portfolio Service startup sequence")
        
        # 1. Initialize environment-based configuration
        logger.info("Step 1: Initializing environment configuration")
        config_manager = get_or_create_config_manager()
        feature_flags = initialize_feature_flags(config_manager)
        
        logger.info(
            "Environment configuration initialized",
            environment=config_manager.current_environment,
            config_summary=config_manager.get_config_summary(),
            observability_flags=feature_flags.get_observability_summary()
        )
        
        # 2. Initialize unified OpenTelemetry monitoring (Prometheus completely removed)
        logger.info("Step 2: Initializing unified OpenTelemetry monitoring")
        _unified_monitoring = initialize_unified_monitoring(config_manager.get_monitoring_config())
        
        logger.info(
            "Unified monitoring initialized successfully",
            tracing_enabled=_unified_monitoring.is_tracing_enabled,
            metrics_enabled=_unified_monitoring.is_metrics_enabled,
            otlp_endpoint=config_manager.get_monitoring_config().otlp_endpoint
        )
        
        # Initialize OpenTelemetry metrics after meter provider is set up
        if _unified_monitoring.is_metrics_enabled:
            from app.monitoring import initialize_otel_metrics
            otel_metrics_initialized = initialize_otel_metrics()
            logger.info(
                "OpenTelemetry metrics initialization completed",
                success=otel_metrics_initialized,
                metrics_enabled=_unified_monitoring.is_metrics_enabled
            )
        
        # 3. Initialize circuit breakers
        logger.info("Step 3: Initializing circuit breakers")
        await initialize_circuit_breakers()
        
        # 4. Initialize validation cache
        logger.info("Step 4: Initializing validation cache")
        await initialize_validation_cache()
        
        # 5. Initialize database connection
        logger.info("Step 5: Initializing database connection")
        await initialize_database()
        
        # 6. Configure OpenTelemetry instrumentation (middleware already configured at module level)
        logger.info("Step 6: Configuring OpenTelemetry instrumentation")
        if _unified_monitoring and _unified_monitoring.is_tracing_enabled:
            logger.info("Instrumenting FastAPI with OpenTelemetry")
            _unified_monitoring.instrument_fastapi(app)
        
        # 7. Start async monitoring components
        logger.info("Step 7: Starting async monitoring components")
        await _unified_monitoring.start_async_components()
        
        logger.info(
            "Portfolio Service startup sequence completed successfully",
            environment=config_manager.current_environment,
            total_steps=7,
            monitoring_status=_unified_monitoring.get_monitoring_status(),
            middleware_count=len(getattr(app, 'user_middleware', [])),
            router_count=len(app.routes)
        )
        
    except Exception as e:
        logger.error(
            f"Startup sequence failed: {e}",
            error_type=type(e).__name__,
            exc_info=True
        )
        raise RuntimeError(f"Application startup failed: {e}") from e


async def shutdown_sequence() -> None:
    """
    Execute graceful shutdown sequence.
    
    Shutdown order:
    1. Stop async monitoring components
    2. Close database connections
    3. Shutdown monitoring system
    4. Clear caches
    """
    global _unified_monitoring, _database_client
    
    try:
        logger.info("Starting Portfolio Service shutdown sequence")
        
        # 1. Stop async monitoring components
        if _unified_monitoring:
            logger.info("Step 1: Stopping async monitoring components")
            await _unified_monitoring.stop_async_components()
        
        # 2. Close database connections
        if _database_client:
            logger.info("Step 2: Closing database connections")
            _database_client.close()
            _database_client = None
        
        # 3. Shutdown monitoring system
        if _unified_monitoring:
            logger.info("Step 3: Shutting down monitoring system")
            _unified_monitoring.shutdown()
            _unified_monitoring = None
        
        # 4. Clear caches
        logger.info("Step 4: Clearing caches")
        from app.validation_cache import reset_validation_cache
        from app.health_endpoints import clear_health_caches
        
        reset_validation_cache()
        clear_health_caches()
        
        logger.info("Portfolio Service shutdown sequence completed successfully")
        
    except Exception as e:
        logger.error(
            f"Shutdown sequence failed: {e}",
            error_type=type(e).__name__,
            exc_info=True
        )


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    FastAPI lifespan context manager for startup and shutdown.
    
    Args:
        app: FastAPI application instance
    """
    global _shutdown_event
    
    # Startup
    _shutdown_event = asyncio.Event()
    await startup_sequence()
    
    # Register signal handlers for graceful shutdown
    def signal_handler(signum, frame):
        logger.info(f"Received signal {signum}, initiating graceful shutdown")
        _shutdown_event.set()
    
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)
    
    try:
        yield
    finally:
        # Shutdown
        await shutdown_sequence()


# Global configuration manager to avoid repeated initialization
_config_manager = None

def get_or_create_config_manager():
    """Get or create the global configuration manager to avoid repeated initialization."""
    global _config_manager
    if _config_manager is None:
        _config_manager = initialize_config_manager()
    return _config_manager

# Initialize configuration manager once at module level
_config_manager = get_or_create_config_manager()


# Create FastAPI application with integrated lifespan management
app = FastAPI(
    title="GlobeCo Portfolio Service",
    description="Streamlined portfolio management service with optimized performance",
    version="2.0.0",
    lifespan=lifespan
)

# Configure middleware BEFORE the application starts
# This must happen at module level, not during lifespan startup
try:
    logger.info("Configuring middleware stack at application creation")
    config_manager = get_or_create_config_manager()
    create_middleware_stack(app, config_manager)
    logger.info("Middleware stack configured successfully")
except Exception as e:
    logger.error(f"Failed to configure middleware stack: {e}", exc_info=True)
    # Don't raise here - let the app start without middleware if needed

# Include API routers immediately (not in startup event)
# Note: Routers already have their prefixes defined, so we don't add them here
app.include_router(api_v1.router, tags=["v1"])
app.include_router(api_v2.router, tags=["v2"])
app.include_router(api_fast.router, tags=["fast"])

# Include optimized health endpoints
app.include_router(health_router, tags=["health"])


@app.get("/", tags=["root"])
async def root():
    """Root endpoint with service information."""
    config_manager = get_or_create_config_manager()
    
    return {
        "message": "GlobeCo Portfolio Service",
        "version": "2.0.0",
        "environment": config_manager.current_environment,
        "status": "operational",
        "features": {
            "unified_monitoring": True,
            "prometheus_removed": True,
            "optimized_performance": True,
            "environment_profiles": True,
            "circuit_breakers": True,
            "validation_caching": True
        }
    }


@app.get("/health", tags=["health"])
async def legacy_health():
    """Legacy health endpoint for backward compatibility."""
    return {
        "status": "healthy", 
        "service": "globeco-portfolio-service",
        "version": "2.0.0"
    }





if __name__ == "__main__":
    import uvicorn
    
    # Get configuration for development server
    config_manager = get_or_create_config_manager()
    
    # Development server configuration
    uvicorn_config = {
        "host": "0.0.0.0",
        "port": 8000,
        "log_level": "info" if config_manager.is_development() else "warning",
        "reload": config_manager.is_development(),
        "workers": 1,  # Single worker for development
    }
    
    logger.info(
        f"Starting Portfolio Service development server",
        environment=config_manager.current_environment,
        **uvicorn_config
    )
    
    uvicorn.run("app.main:app", **uvicorn_config) 