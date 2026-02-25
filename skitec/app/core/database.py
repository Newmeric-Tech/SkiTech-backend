"""
Database Configuration & Session Management

Initializes SQLAlchemy 2.0 engine and session management.
Provides dependency injection for database sessions.
Supports connection pooling and event listeners for production readiness.
"""

from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    create_async_engine,
)
from sqlalchemy.orm import sessionmaker

from app.core.config import settings

# Create async engine with connection pooling
engine = create_async_engine(
    url=settings.DATABASE_URL,
    echo=settings.DB_ECHO,
    pool_size=settings.DB_POOL_SIZE,
    max_overflow=settings.DB_MAX_OVERFLOW,
    pool_pre_ping=True,  # Verify connections before using
    pool_recycle=3600,  # Recycle connections after 1 hour
)

# Create async session maker
AsyncSessionLocal = sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Dependency injection for database session

    Provides database session to route handlers.
    Automatically handles session cleanup via context manager.

    Yields:
        AsyncSession: SQLAlchemy async session instance
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


async def init_db() -> None:
    """
    Initialize database - Create all tables

    Run this during application startup.
    Uses declarative base metadata from models.
    """
    from app.models.base import Base

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def close_db() -> None:
    """
    Close database connections

    Run this during application shutdown.
    Cleans up connection pools and async resources.
    """
    await engine.dispose()
