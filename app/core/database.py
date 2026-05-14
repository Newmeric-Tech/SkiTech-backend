"""
Database Configuration - app/core/database.py

Async SQLAlchemy engine, session management, and dependency injection.
"""

from typing import AsyncGenerator
from urllib.parse import urlparse, urlunparse, parse_qs, urlencode

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings


def _clean_db_url(url: str) -> str:
    """Strip SSL query params from the URL — asyncpg gets ssl via connect_args."""
    parsed = urlparse(url)
    params = parse_qs(parsed.query, keep_blank_values=True)
    for key in ("sslmode", "ssl", "channel_binding"):
        params.pop(key, None)
    clean_query = urlencode({k: v[0] for k, v in params.items()})
    return urlunparse(parsed._replace(query=clean_query))


_is_cloud = "neon.tech" in settings.DATABASE_URL or settings.is_production

connect_args: dict = {}
if _is_cloud:
    connect_args = {
        "ssl": "require",
        "server_settings": {"application_name": "skitech"},
    }

_db_url = _clean_db_url(settings.DATABASE_URL) if _is_cloud else settings.DATABASE_URL

engine = create_async_engine(
    url=_db_url,
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

        # Idempotent column additions for existing tables
        # (create_all skips tables that already exist, so new columns need ALTER TABLE)
        migrations = [
            "ALTER TABLE attendance_records ADD COLUMN IF NOT EXISTS current_status VARCHAR(50);",
            "ALTER TABLE properties ADD COLUMN IF NOT EXISTS image_urls JSONB DEFAULT '[]'::jsonb;",
        ]
        for sql in migrations:
            await conn.execute(text(sql))


async def close_db() -> None:
    """Dispose connection pool on shutdown."""
    await engine.dispose()
