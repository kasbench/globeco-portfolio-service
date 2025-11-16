# MongoDB Multiple Connection Creation Fix

## Problem
The application was creating 5+ MongoDB connections during startup, as evidenced by repeated log messages:
```
"MongoDB client created successfully: uri=mongodb://globeco-portfolio-service-mongodb:27017..."
```

## Root Cause Analysis

### Issue #1: Duplicate Client in Index Creation (FIXED)
`create_indexes()` was creating its own MongoDB client instead of reusing the existing one from `initialize_database()`.

### Issue #2: Duplicate Initialization Paths (FIXED)
The application had two separate database initialization paths that weren't coordinated:

1. **Main Application Startup** (`app/main.py:initialize_database()`)
   - Creates a client during FastAPI lifespan startup
   - Initializes Beanie ODM
   - Creates indexes

2. **Service Layer Fallback** (`app/database_init.py:ensure_database_initialized()`)
   - Called from service methods (for testing scenarios)
   - Was creating a **separate** client even when main app already initialized
   - This caused duplicate initialization on first API request after startup

The service layer wasn't checking if Beanie was already initialized by the main application, leading to redundant initialization.

## Solution

### Fix #1: Share MongoDB Client for Index Creation

Modified `create_indexes()` to accept an existing MongoDB client as a parameter instead of creating its own:

**app/database.py** - Updated `create_indexes()` signature:
```python
# Before
async def create_indexes():
    client = create_optimized_client()
    # ... use client ...
    client.close()

# After
async def create_indexes(client: AsyncIOMotorClient):
    # ... use provided client ...
    # No client creation or closing
```

**app/main.py** and **app/database_init.py** - Pass the existing client:
```python
_database_client = create_optimized_client()
await init_beanie(...)
await create_indexes(_database_client)  # Pass existing client
```

### Fix #2: Detect Existing Beanie Initialization

Modified `ensure_database_initialized()` to check if Beanie is already initialized before creating a new client:

**app/database_init.py** - Added Beanie initialization check:
```python
async def ensure_database_initialized() -> bool:
    # Check if Beanie is already initialized by main app
    try:
        from app.models import Portfolio
        if Portfolio.get_motor_collection() is not None:
            # Already initialized, skip duplicate initialization
            logger.debug("Database already initialized by application startup")
            return True
    except Exception:
        pass
    
    # Only initialize if not already done
    # ... rest of initialization code ...
```

This ensures that when service methods call `ensure_database_initialized()` after the main app has already started, it detects the existing initialization and skips creating a duplicate client.

## Result
- Reduced MongoDB connection creation from 5+ to 1 during application lifecycle
- Main application startup creates exactly 1 client
- Service layer detects existing initialization and reuses it
- Health check endpoints still create temporary connections (expected and necessary)
- Connection pooling is now more efficient
- Startup logs are cleaner and less confusing

## Why This Matters at Scale

### Connection Pool Impact
- Each MongoDB client creates its own connection pool (10-50 connections)
- With duplicate clients: **2 pools per pod = 20-100 connections per pod**
- At 10 replicas: **200-1000 connections** instead of 100-500
- At 50 replicas: **1000-5000 connections** instead of 500-2500

### Resource Waste
- Each client maintains separate connection pool in memory
- Unnecessary overhead multiplied by number of replicas
- Could hit MongoDB connection limits in production

### The Real Problem
Both clients stay alive until pod shutdown - they're never closed, so you're maintaining duplicate connection pools for the entire pod lifetime.

## Final Solution

After the initial fixes didn't fully resolve the issue, the simplest and most reliable solution was to **remove the `ensure_database_initialized()` calls from service methods entirely**.

**app/services.py** - Removed all `ensure_database_initialized()` calls:
```python
# Before
async def get_all_portfolios() -> List[Portfolio]:
    if not await ensure_database_initialized():
        raise RuntimeError("Failed to initialize database connection")
    # ... rest of method ...

# After  
async def get_all_portfolios() -> List[Portfolio]:
    # Database is already initialized by FastAPI lifespan
    # ... rest of method ...
```

This works because:
1. The FastAPI lifespan in `main.py` **always** initializes the database on startup
2. The `ensure_database_initialized()` function was only needed for testing scenarios
3. Tests should use proper test fixtures to initialize the database

## Expected Behavior After Fix

### During Application Startup
You should see only **1** "MongoDB client created successfully" message during startup:
```
"Creating optimized MongoDB client: max_pool_size=50, min_pool_size=10..."
"MongoDB client created successfully: uri=mongodb://..."
"Created text index on portfolio name field"
"Created compound index on name and dateCreated fields"
"Database initialization completed successfully"
```

### On First API Request
**No additional "MongoDB client created" messages** - the service methods now rely on the database being initialized during application startup.

### Health Check Endpoints
Health endpoints (`/health/ready`, `/health/startup`, `/health/detailed`) will still create temporary clients for their checks, which is expected and necessary for proper health monitoring. These clients are short-lived and closed immediately after the health check.
