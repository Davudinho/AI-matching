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

try:
    from backend.app.core.config import settings
except ImportError:
    from app.core.config import settings


# ---- SQLAlchemy Async Engine ----
# asyncpg uses ssl=True in connect_args, NOT ?sslmode=require (that's psycopg2 syntax).
# Strip any sslmode/ssl params from the URL to avoid conflicts.
import re as _re
_db_url = settings.DATABASE_URL
_db_url = _db_url.replace("postgresql://", "postgresql+asyncpg://").replace("postgres://", "postgresql+asyncpg://")
_db_url = _re.sub(r"[?&]sslmode=[^&]*", "", _db_url)  # strip psycopg2-style ssl param
_db_url = _re.sub(r"[?&]ssl=[^&]*", "", _db_url)      # strip any other ssl param

# Enable SSL for production (Supabase requires it)
# statement_cache_size=0 is required for Supabase connection pooler (Session/Transaction mode)
_is_production = settings.ENVIRONMENT == "production"
_connect_args = {"ssl": True, "statement_cache_size": 0} if _is_production else {}

async_engine = create_async_engine(
    _db_url,
    echo=(settings.ENVIRONMENT == "development"),  # Print SQL in dev mode
    pool_size=5,         # Render free tier: keep pool small
    max_overflow=10,
    pool_pre_ping=True,  # Test connections before using them
    connect_args=_connect_args,
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
