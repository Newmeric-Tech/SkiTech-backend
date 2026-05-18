"""
Alembic environment - alembic/env.py
"""

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import async_engine_from_config

# Import Base so all models are registered
from app.models.base import Base
import app.models  # noqa: F401 - registers all ORM models

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def get_url():
    """Read DATABASE_URL from .env / environment."""
    import os
    from dotenv import load_dotenv
    load_dotenv()
    url = os.getenv("DATABASE_URL", "")
    # Alembic needs the sync driver for migrations
    return url.replace("postgresql+asyncpg://", "postgresql://")


def run_migrations_offline() -> None:
    url = get_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection):
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    url = get_url()
    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = url

    connectable = async_engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
        # Use sync driver for Alembic
    )
    # Actually just use sync engine for migrations
    from sqlalchemy import create_engine
    sync_engine = create_engine(url)
    with sync_engine.connect() as connection:
        do_run_migrations(connection)
    sync_engine.dispose()


def run_migrations_online() -> None:
    from sqlalchemy import create_engine
    url = get_url()
    sync_engine = create_engine(url)
    with sync_engine.connect() as connection:
        do_run_migrations(connection)
    sync_engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
