"""
Database Configuration - app/core/database.py

Async SQLAlchemy engine, session management, and dependency injection.
"""

from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings

# Build connection args - add SSL only for cloud databases
connect_args = {}
if "neon.tech" in settings.DATABASE_URL or settings.is_production:
    connect_args = {
        "ssl": "require",
        "server_settings": {"application_name": "skitech"},
    }

engine = create_async_engine(
    url=settings.DATABASE_URL,
    echo=settings.DB_ECHO,
    pool_size=settings.DB_POOL_SIZE,
    max_overflow=settings.DB_MAX_OVERFLOW,
    pool_pre_ping=True,
    pool_recycle=1800,
    connect_args=connect_args,
)

AsyncSessionLocal = sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency: yields an async DB session."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


async def init_db() -> None:
    """Create all tables on startup (dev / first run)."""
    from app.models.base import Base  # noqa: F401 - registers all models
    import app.models  # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def close_db() -> None:
    """Dispose connection pool on shutdown."""
    await engine.dispose()
