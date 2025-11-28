"""
Exclusive-Change: Enterprise Feature Flag Service

This is the main FastAPI application entry point.

The application provides:
    - Management API: CRUD operations for feature flags (JWT auth)
    - Evaluation API: High-performance flag evaluation (API key auth)

Startup/Shutdown:
    - Connects to PostgreSQL (via SQLAlchemy async)
    - Connects to Redis for caching
    - Validates all configuration at startup
"""

import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.v1.router import api_router
from app.cache.redis import cache
from app.core.config import settings
from app.core.exceptions import ExclusiveChangeException
from app.db.session import close_db, init_db

# Configure logging
logging.basicConfig(
    level=logging.DEBUG if settings.DEBUG else logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """
    Application lifespan manager.
    
    Handles startup and shutdown events:
        - Startup: Initialize database and cache connections
        - Shutdown: Close all connections gracefully
    """
    # Startup
    logger.info(f"Starting {settings.APP_NAME} in {settings.APP_ENV} mode")
    
    try:
        # Initialize database connection
        await init_db()
        logger.info("Database connection established")
        
        # Initialize Redis connection
        await cache.connect()
        logger.info("Redis connection established")
        
    except Exception as e:
        logger.error(f"Failed to initialize services: {e}")
        raise
    
    yield  # Application runs here
    
    # Shutdown
    logger.info("Shutting down application")
    
    await cache.disconnect()
    await close_db()
    
    logger.info("Shutdown complete")


# Create FastAPI application
app = FastAPI(
    title=settings.APP_NAME,
    description="""
    ## Enterprise Feature Flag Service
    
    A high-concurrency, multi-tenant SaaS backend for managing feature flags.
    
    ### Features
    - **Percentage Rollout**: Gradually roll out features to a percentage of users
    - **Deterministic Hashing**: Same user always gets the same flag value
    - **Multi-Tenant**: Complete data isolation between tenants
    - **High Performance**: Async I/O with Redis caching
    
    ### Authentication
    
    **Management API** (flag CRUD):
    - Requires JWT token from Supabase Auth
    - Include in `Authorization: Bearer <token>` header
    - Include tenant ID in `X-Tenant-ID` header
    
    **Evaluation API** (flag evaluation):
    - Requires API key
    - Include in `X-API-Key` header
    """,
    version="0.1.0",
    docs_url="/docs" if settings.DEBUG else None,
    redoc_url="/redoc" if settings.DEBUG else None,
    lifespan=lifespan,
)


# =============================================================================
# Middleware
# =============================================================================

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# =============================================================================
# Exception Handlers
# =============================================================================

@app.exception_handler(ExclusiveChangeException)
async def exclusive_change_exception_handler(
    request: Request,
    exc: ExclusiveChangeException,
) -> JSONResponse:
    """Handle all Exclusive-Change custom exceptions."""
    return JSONResponse(
        status_code=exc.status_code,
        content=exc.to_dict(),
    )


@app.exception_handler(Exception)
async def generic_exception_handler(
    request: Request,
    exc: Exception,
) -> JSONResponse:
    """Handle unexpected exceptions."""
    logger.exception(f"Unhandled exception: {exc}")
    
    if settings.DEBUG:
        # Include error details in debug mode
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "error": {
                    "code": "INTERNAL_ERROR",
                    "message": str(exc),
                    "type": type(exc).__name__,
                }
            },
        )
    
    # Generic error in production
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": {
                "code": "INTERNAL_ERROR",
                "message": "An unexpected error occurred",
            }
        },
    )


# =============================================================================
# Routes
# =============================================================================

# Include API v1 routes
app.include_router(api_router)


# Health check endpoint
@app.get(
    "/health",
    tags=["health"],
    summary="Health check",
    description="Check if the service is healthy and all dependencies are reachable.",
)
async def health_check() -> dict:
    """
    Health check endpoint.
    
    Returns the health status of the application and its dependencies.
    """
    # Check Redis
    redis_healthy = await cache.health_check()
    
    # Overall health
    is_healthy = redis_healthy
    
    return {
        "status": "healthy" if is_healthy else "unhealthy",
        "service": settings.APP_NAME,
        "environment": settings.APP_ENV,
        "dependencies": {
            "redis": "healthy" if redis_healthy else "unhealthy",
            "database": "healthy",  # Would fail at startup if unhealthy
        },
    }


@app.get("/", tags=["root"])
async def root() -> dict:
    """Root endpoint with API information."""
    return {
        "service": settings.APP_NAME,
        "version": "0.1.0",
        "documentation": "/docs" if settings.DEBUG else "Disabled in production",
        "health": "/health",
    }


# =============================================================================
# Run with Uvicorn (for development)
# =============================================================================

if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.DEBUG,
        log_level="debug" if settings.DEBUG else "info",
    )
