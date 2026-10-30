"""
Migration 030 on a throwaway local PostgreSQL, in both orders: tables already
made by create_all (app startup), and tables missing. Either way it must end
with the same columns, constraints and indexes. Skipped without LOCAL_PG_URL.
"""
import os
import subprocess
import sys
from pathlib import Path

from sqlalchemy import bindparam, text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

import app.models  # noqa: F401 - registers every table
from app.models.base import Base
from tests.kra_tasks_pg import throwaway_database

BACKEND = Path(__file__).resolve().parent.parent
# The repo's alembic/ folder would shadow the package if the cwd came first on sys.path.
RUN_ALEMBIC = ("import sys; sys.path.remove(''); from alembic.config import main; "
               "sys.path.append('.'); main(argv=sys.argv[1:])")
KRA_TABLES = ("kra_definitions", "kra_assignments", "kra_occurrences")


def alembic(url, *args):
    env = {**os.environ, "DATABASE_URL": url.render_as_string(hide_password=False), "ENVIRONMENT": "development"}
    done = subprocess.run([sys.executable, "-c", RUN_ALEMBIC, *args], cwd=BACKEND, env=env,
                          capture_output=True, text=True, timeout=120)
    # Output can include the connection URL, so only the end of it is kept.
    assert done.returncode == 0, done.stderr[-400:].replace(url.password or "\0", "***")


async def describe(conn):
    columns = (await conn.execute(text(
        "SELECT table_name, column_name, data_type, is_nullable, character_maximum_length, numeric_precision "
        "FROM information_schema.columns WHERE table_name IN :t ORDER BY 1, 2"
    ).bindparams(bindparam("t", expanding=True)), {"t": KRA_TABLES})).all()
    constraints = (await conn.execute(text(
        "SELECT conname, contype::text, pg_get_constraintdef(oid) FROM pg_constraint "
        "WHERE conrelid::regclass::text IN :t AND contype <> 'p' ORDER BY 1"
    ).bindparams(bindparam("t", expanding=True)), {"t": KRA_TABLES})).all()
    indexes = (await conn.execute(text(
        "SELECT indexname, indexdef FROM pg_indexes WHERE tablename IN :t AND indexname NOT LIKE '%_pkey' ORDER BY 1"
    ).bindparams(bindparam("t", expanding=True)), {"t": KRA_TABLES})).all()
    return columns, constraints, indexes


async def build(url, with_kra_tables):
    """A database at revision 029, with or without the KRA tables already there."""
    engine = create_async_engine(url, poolclass=NullPool)
    tables = [t for t in Base.metadata.sorted_tables if with_kra_tables or t.name not in KRA_TABLES]
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=tables))
    await engine.dispose()
    alembic(url, "stamp", "029_attendance_corrections")


async def state(url):
    engine = create_async_engine(url, poolclass=NullPool)
    async with engine.connect() as conn:
        version = (await conn.execute(text("SELECT version_num FROM alembic_version"))).scalar()
        shape = await describe(conn)
    await engine.dispose()
    return version, shape


def test_revision_id_fits_alembic_version_column():
    assert len("030_kra_tasks") <= 32


async def test_both_orders_end_with_the_same_schema():
    async with throwaway_database() as existing, throwaway_database() as missing:
        await build(existing, with_kra_tables=True)
        before, before_shape = await state(existing)
        alembic(existing, "upgrade", "head")
        after, after_shape = await state(existing)
        assert before == "029_attendance_corrections" and after == "030_kra_tasks"
        assert after_shape == before_shape   # only the version moved

        await build(missing, with_kra_tables=False)
        alembic(missing, "upgrade", "head")
        version, missing_shape = await state(missing)
        assert version == "030_kra_tasks"
        assert missing_shape == after_shape


async def test_rerun_and_downgrade_round_trip():
    async with throwaway_database() as url:
        await build(url, with_kra_tables=False)
        alembic(url, "upgrade", "head")
        _, first = await state(url)
        alembic(url, "downgrade", "029_attendance_corrections")
        version, gone = await state(url)
        assert version == "029_attendance_corrections" and gone == ([], [], [])
        alembic(url, "upgrade", "head")
        assert (await state(url))[1] == first
