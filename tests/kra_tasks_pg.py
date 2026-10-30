"""
Throwaway local PostgreSQL for the KRA task tests: one database created and
dropped per use, reached through LOCAL_PG_URL, which must point at localhost.
Skips cleanly when it is unset or nothing answers. Never touches .env's database.
"""
import os
from contextlib import asynccontextmanager
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}


def local_pg_url():
    raw = os.environ.get("LOCAL_PG_URL")
    if not raw:
        pytest.skip("needs a local Postgres (LOCAL_PG_URL)")
    url = make_url(raw)
    if url.host not in LOCAL_HOSTS:
        pytest.skip("LOCAL_PG_URL must point at localhost")
    return url


@asynccontextmanager
async def throwaway_database():
    """Yields the URL of a new empty database; drops it afterwards."""
    url = local_pg_url()
    name = f"skitech_kra_test_{uuid4().hex}"
    admin = create_async_engine(url, isolation_level="AUTOCOMMIT", poolclass=NullPool)
    try:
        async with admin.connect() as conn:
            await conn.execute(text(f'CREATE DATABASE "{name}"'))
    except (OSError, SQLAlchemyError) as exc:
        await admin.dispose()
        pytest.skip(f"local Postgres not available: {type(exc).__name__}")
    try:
        yield url.set(database=name)
    finally:
        async with admin.connect() as conn:
            await conn.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        await admin.dispose()
