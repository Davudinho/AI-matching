"""
backend/app/core/database.py — Database Connection

Sets up the async PostgreSQL connection pool using SQLAlchemy + asyncpg.

Key concepts:
- async_engine: The connection pool. Think of it as a receptionist that
  manages multiple concurrent connections to the database.
- AsyncSession: A single database "conversation". We open one per HTTP
  request and close it when the request finishes.
- get_db(): A FastAPI dependency — injected automatically into route
  functions to provide a fresh session.
"""

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase

from app.core.config import settings


# ---- SQLAlchemy Async Engine ----
# We convert the standard postgres:// URL to postgresql+asyncpg://
# because asyncpg is the async driver we want to use.
_db_url = settings.DATABASE_URL.replace(
    "postgresql://", "postgresql+asyncpg://"
).replace(
    "postgres://", "postgresql+asyncpg://"
)

async_engine = create_async_engine(
    _db_url,
    echo=(settings.ENVIRONMENT == "development"),  # Print SQL in dev mode
    pool_size=10,        # Keep 10 connections ready in the pool
    max_overflow=20,     # Allow up to 20 additional connections under heavy load
    pool_pre_ping=True,  # Test connections before using them (avoids stale conn errors)
)

# Session factory — creates new AsyncSession objects
AsyncSessionLocal = async_sessionmaker(
    bind=async_engine,
    class_=AsyncSession,
    expire_on_commit=False,  # Don't expire objects after commit (avoids lazy load issues)
    autoflush=False,
    autocommit=False,
)


# ---- SQLAlchemy Base ----
# All our ORM models will inherit from this Base class.
class Base(DeclarativeBase):
    pass


# ---- FastAPI Dependency ----
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Dependency injected into FastAPI route functions.
    
    Usage in a route:
        @router.get("/jds")
        async def list_jds(db: AsyncSession = Depends(get_db)):
            ...
    
    The 'async with' guarantees the session is ALWAYS closed after
    the request, even if an exception is raised. This prevents connection leaks.
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


@asynccontextmanager
async def get_db_context():
    """
    Context manager version for use outside of FastAPI (e.g. in scripts).
    
    Usage:
        async with get_db_context() as db:
            result = await db.execute(...)
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
