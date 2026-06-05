"""
Database Configuration - app/core/database.py

Async SQLAlchemy engine, session management, and dependency injection.
"""

import logging
from typing import AsyncGenerator
from urllib.parse import urlparse, urlunparse, parse_qs, urlencode

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings

logger = logging.getLogger("skitech")


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

    # Step 1: Create PostgreSQL ENUM types used by chat tables.
    # DO blocks are idempotent — they silently skip types that already exist.
    # Each runs in its own transaction so a failure doesn't cascade.
    chat_enum_sqls = [
        "DO $$ BEGIN CREATE TYPE conversationtype AS ENUM ('direct', 'group'); EXCEPTION WHEN duplicate_object THEN null; END $$;",
        "DO $$ BEGIN CREATE TYPE messagestatus AS ENUM ('sent', 'delivered', 'read'); EXCEPTION WHEN duplicate_object THEN null; END $$;",
        "DO $$ BEGIN CREATE TYPE participantrole AS ENUM ('admin', 'moderator', 'member'); EXCEPTION WHEN duplicate_object THEN null; END $$;",
        "DO $$ BEGIN CREATE TYPE mediatype AS ENUM ('image', 'file', 'video', 'audio'); EXCEPTION WHEN duplicate_object THEN null; END $$;",
    ]
    for sql in chat_enum_sqls:
        try:
            async with engine.begin() as conn:
                await conn.execute(text(sql))
        except Exception as e:
            logger.warning(f"ENUM type init skipped: {e}")

    # Step 2: Create tables one at a time, each in its own transaction.
    # This prevents a failure on one table (e.g. an already-existing ENUM type)
    # from aborting the entire run and blocking subsequent tables.
    for table in Base.metadata.sorted_tables:
        try:
            async with engine.begin() as conn:
                await conn.run_sync(lambda c, t=table: t.create(c, checkfirst=True))
            logger.debug(f"Table ready: {table.name}")
        except Exception as e:
            logger.error(f"Failed to create table '{table.name}': {e}")

    # Step 3: Idempotent column additions for existing tables.
    migrations = [
        "ALTER TABLE attendance_records ADD COLUMN IF NOT EXISTS current_status VARCHAR(50);",
        "ALTER TABLE properties ADD COLUMN IF NOT EXISTS image_urls JSONB DEFAULT '[]'::jsonb;",
        # Chat table column fixes — added after initial deployment
        "ALTER TABLE conversations ADD COLUMN IF NOT EXISTS description TEXT;",
        "ALTER TABLE conversations ADD COLUMN IF NOT EXISTS avatar_url VARCHAR(512);",
        "ALTER TABLE conversations ADD COLUMN IF NOT EXISTS last_message_at TIMESTAMP;",
        "ALTER TABLE conversations ADD COLUMN IF NOT EXISTS participant_count INTEGER NOT NULL DEFAULT 1;",
        "ALTER TABLE conversations ADD COLUMN IF NOT EXISTS unread_count INTEGER NOT NULL DEFAULT 0;",
        "ALTER TABLE conversations ADD COLUMN IF NOT EXISTS is_archived BOOLEAN NOT NULL DEFAULT false;",
        "ALTER TABLE conversations ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMP;",
        "ALTER TABLE conversation_participants ADD COLUMN IF NOT EXISTS left_at TIMESTAMP;",
        "ALTER TABLE conversation_participants ADD COLUMN IF NOT EXISTS is_muted BOOLEAN NOT NULL DEFAULT false;",
        "ALTER TABLE conversation_participants ADD COLUMN IF NOT EXISTS last_read_at TIMESTAMP;",
        "ALTER TABLE conversation_participants ADD COLUMN IF NOT EXISTS last_read_message_id UUID;",
        "ALTER TABLE messages ADD COLUMN IF NOT EXISTS tenant_id UUID REFERENCES tenants(id) ON DELETE CASCADE;",
        "ALTER TABLE messages ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMP;",
        "ALTER TABLE messages ADD COLUMN IF NOT EXISTS edited_at TIMESTAMP;",
        "ALTER TABLE messages ADD COLUMN IF NOT EXISTS edited_count INTEGER NOT NULL DEFAULT 0;",
        "ALTER TABLE messages ADD COLUMN IF NOT EXISTS mentions JSONB;",
        "ALTER TABLE messages ADD COLUMN IF NOT EXISTS reply_to_id UUID;",
        # message_media columns added after initial deployment
        "ALTER TABLE message_media ADD COLUMN IF NOT EXISTS thumbnail_key VARCHAR(512);",
        "ALTER TABLE message_media ADD COLUMN IF NOT EXISTS original_filename VARCHAR(255) NOT NULL DEFAULT '';",
        "ALTER TABLE message_media ADD COLUMN IF NOT EXISTS file_size_bytes INTEGER NOT NULL DEFAULT 0;",
        "ALTER TABLE message_media ADD COLUMN IF NOT EXISTS mime_type VARCHAR(100) NOT NULL DEFAULT '';",
        "ALTER TABLE message_media ADD COLUMN IF NOT EXISTS width INTEGER;",
        "ALTER TABLE message_media ADD COLUMN IF NOT EXISTS height INTEGER;",
        "ALTER TABLE message_media ADD COLUMN IF NOT EXISTS duration_seconds FLOAT;",
        "ALTER TABLE message_media ADD COLUMN IF NOT EXISTS is_scanned BOOLEAN NOT NULL DEFAULT false;",
        "ALTER TABLE message_media ADD COLUMN IF NOT EXISTS is_safe BOOLEAN NOT NULL DEFAULT true;",
        # ENUM column type fixes — columns were created as VARCHAR before ENUM types existed.
        # Each USING clause casts existing VARCHAR values to the ENUM type.
        # These are no-ops if the column is already the correct ENUM type (caught by except).
        "ALTER TABLE conversations ALTER COLUMN type TYPE conversationtype USING type::conversationtype;",
        "ALTER TABLE conversation_participants ALTER COLUMN role TYPE participantrole USING role::participantrole;",
        "ALTER TABLE message_delivery_status ALTER COLUMN status TYPE messagestatus USING status::messagestatus;",
        "ALTER TABLE message_media ALTER COLUMN media_type TYPE mediatype USING media_type::mediatype;",
        # OTP persistence — replaces in-memory store
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS otp_code VARCHAR(6);",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS otp_expires_at TIMESTAMP;",
        # Stripe payment integration
        "ALTER TABLE tenants ADD COLUMN IF NOT EXISTS stripe_customer_id VARCHAR(100);",
        "ALTER TABLE tenant_subscriptions ADD COLUMN IF NOT EXISTS stripe_subscription_id VARCHAR(100);",
        "ALTER TABLE subscription_plans ADD COLUMN IF NOT EXISTS stripe_price_id VARCHAR(100);",
    ]
    for sql in migrations:
        try:
            async with engine.begin() as conn:
                await conn.execute(text(sql))
        except Exception as e:
            logger.warning(f"Column migration skipped: {e}")


async def close_db() -> None:
    """Dispose connection pool on shutdown."""
    await engine.dispose()
