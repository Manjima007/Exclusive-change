"""
Async Database Session Management.

This module configures SQLAlchemy 2.0 with async support using asyncpg.
It provides the async engine, session factory, and a dependency for FastAPI.

Key Design Decisions:
    - Uses async sessions for non-blocking I/O
    - Connection pooling tuned for high concurrency
    - Context manager pattern for automatic cleanup

Usage in FastAPI:
    @app.get("/items")
    async def get_items(db: AsyncSession = Depends(get_db)):
        result = await db.execute(select(Item))
        return result.scalars().all()
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from app.core.config import settings


def create_engine() -> AsyncEngine:
    """
    Create and configure the async SQLAlchemy engine.
    
    The engine is configured with connection pooling optimized for
    high-concurrency workloads. Pool settings are loaded from environment.
    
    Pool Configuration:
        - pool_size: Number of persistent connections
        - max_overflow: Additional connections allowed under load
        - pool_timeout: Seconds to wait for a connection
        - pool_pre_ping: Validate connections before use (handles DB restarts)
    
    Returns:
        AsyncEngine: Configured async SQLAlchemy engine.
    
    Note:
        For testing, use NullPool to avoid connection issues with pytest-asyncio.
    """
    # Build connection arguments for asyncpg
    connect_args: dict = {
        # Statement cache size (asyncpg specific)
        "statement_cache_size": 0,  # Disable for pgbouncer compatibility
    }
    
    # Use NullPool for development/testing to avoid event loop issues
    # NullPool doesn't support pool_size, max_overflow, pool_timeout
    if settings.APP_ENV == "development":
        engine = create_async_engine(
            str(settings.DATABASE_URL),
            echo=settings.DEBUG,  # Log SQL statements in debug mode
            pool_pre_ping=True,  # Verify connections are alive
            connect_args=connect_args,
            poolclass=NullPool,
        )
    else:
        # Production: use connection pooling
        engine = create_async_engine(
            str(settings.DATABASE_URL),
            echo=settings.DEBUG,
            pool_size=settings.DB_POOL_SIZE,
            max_overflow=settings.DB_MAX_OVERFLOW,
            pool_timeout=settings.DB_POOL_TIMEOUT,
            pool_pre_ping=True,
            connect_args=connect_args,
        )
    
    return engine


# Create the global engine instance
engine = create_engine()

# Create async session factory
# expire_on_commit=False allows accessing attributes after commit
async_session_factory = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,  # Explicit flush for better control
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency that provides an async database session.
    
    This is the primary way to get a database session in route handlers.
    The session is automatically closed when the request completes.
    
    Yields:
        AsyncSession: Database session for the current request.
    
    Example:
        @router.get("/flags")
        async def list_flags(
            db: AsyncSession = Depends(get_db),
            tenant_id: UUID = Depends(get_current_tenant_id),
        ):
            result = await db.execute(
                select(Flag).where(Flag.tenant_id == tenant_id)
            )
            return result.scalars().all()
    
    Note:
        Always use `async with` or this dependency to ensure proper cleanup.
    """
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


@asynccontextmanager
async def get_db_context() -> AsyncGenerator[AsyncSession, None]:
    """
    Context manager for database sessions outside of request handlers.
    
    Use this for background tasks, CLI commands, or anywhere FastAPI's
    dependency injection is not available.
    
    Yields:
        AsyncSession: Database session.
    
    Example:
        async def background_task():
            async with get_db_context() as db:
                await db.execute(update(Flag).where(...))
                await db.commit()
    """
    async with async_session_factory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_db() -> None:
    """
    Initialize database connection and verify connectivity.
    
    Called during application startup to fail fast if the database
    is not reachable.
    
    Raises:
        Exception: If database connection fails.
    """
    from sqlalchemy import text
    
    async with engine.begin() as conn:
        # Simple connectivity check
        await conn.execute(text("SELECT 1"))


async def close_db() -> None:
    """
    Close all database connections.
    
    Called during application shutdown for graceful cleanup.
    """
    await engine.dispose()


# Type alias for dependency injection
DBSession = Annotated[AsyncSession, Depends(get_db)]
