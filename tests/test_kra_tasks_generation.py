"""
Period boundaries, today validation, and occurrence generation by the reusable
ensure_occurrences(): pure logic and in-memory SQLite, plus the unique key and
concurrent calls on a throwaway local Postgres (skipped without LOCAL_PG_URL).
"""
import asyncio
from datetime import date, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

import app.models  # noqa: F401 - registers every table
from app.models.base import Base
from app.models.kra_tasks import KraOccurrence
from app.services import kra_task_service as service
from app.services.kra_task_service import (
    MAX_PERIODS_PER_CALL, ensure_occurrences, period_for, periods_newest_first, validate_client_today,
)
from tests.kra_tasks_harness import (
    assignment_row, definition_row, property_row, role_rows, sqlite_db, user_row,
)
from tests.kra_tasks_pg import throwaway_database

TENANT = uuid4()


# ── periods ─────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("frequency,day,expected", [
    ("daily", date(2026, 3, 1), (date(2026, 3, 1), date(2026, 3, 1))),
    ("weekly", date(2026, 10, 30), (date(2026, 10, 26), date(2026, 11, 1))),    # crosses a month end
    ("weekly", date(2026, 12, 31), (date(2026, 12, 28), date(2027, 1, 3))),     # crosses a year end
    ("weekly", date(2026, 10, 26), (date(2026, 10, 26), date(2026, 11, 1))),    # Monday
    ("weekly", date(2026, 11, 1), (date(2026, 10, 26), date(2026, 11, 1))),     # Sunday
    ("monthly", date(2028, 2, 29), (date(2028, 2, 1), date(2028, 2, 29))),      # leap day
    ("monthly", date(2027, 2, 15), (date(2027, 2, 1), date(2027, 2, 28))),
    ("monthly", date(2026, 12, 31), (date(2026, 12, 1), date(2026, 12, 31))),
    ("quarterly", date(2026, 3, 31), (date(2026, 1, 1), date(2026, 3, 31))),
    ("quarterly", date(2026, 4, 1), (date(2026, 4, 1), date(2026, 6, 30))),
    ("quarterly", date(2026, 9, 30), (date(2026, 7, 1), date(2026, 9, 30))),
    ("quarterly", date(2026, 10, 1), (date(2026, 10, 1), date(2026, 12, 31))),
    ("quarterly", date(2028, 2, 29), (date(2028, 1, 1), date(2028, 3, 31))),    # leap day
])
def test_period_boundaries(frequency, day, expected):
    assert period_for(frequency, day) == expected


def test_unknown_frequency_is_rejected():
    with pytest.raises(ValueError):
        period_for("yearly", date(2026, 1, 1))


def test_periods_cover_start_through_up_to_newest_first():
    weeks = list(periods_newest_first("weekly", date(2026, 10, 14), date(2026, 10, 27)))
    assert [w[0] for w in weeks] == [date(2026, 10, 26), date(2026, 10, 19), date(2026, 10, 12)]


def test_no_periods_when_start_is_after_up_to():
    assert list(periods_newest_first("daily", date(2026, 10, 2), date(2026, 10, 1))) == []


@pytest.mark.parametrize("delta,valid", [(-2, False), (-1, True), (0, True), (1, True), (2, False)])
def test_today_must_be_within_one_day_of_utc(delta, valid):
    today = datetime.utcnow().date() + timedelta(days=delta)
    if valid:
        assert validate_client_today(today) == today
    else:
        with pytest.raises(ValueError):
            validate_client_today(today)


# ── generation on SQLite ────────────────────────────────────────────────────

@pytest.fixture
def world():
    db = sqlite_db()
    roles = role_rows()
    prop = property_row(TENANT)
    staff = user_row(roles["Staff"], TENANT, prop.id)
    db.session.add_all([*roles.values(), prop, staff])
    db.session.commit()
    return db, prop, staff, roles


def give(db, prop, user, frequency="daily", start=date(2026, 10, 1), **kw):
    definition = definition_row(TENANT, prop.id, frequency, **kw)
    assignment = assignment_row(definition, user.id, start)
    db.session.add_all([definition, assignment])
    db.session.commit()
    return definition, assignment


def starts(db, assignment=None):
    query = select(KraOccurrence.period_start).order_by(KraOccurrence.period_start)
    if assignment is not None:
        query = query.where(KraOccurrence.assignment_id == assignment.id)
    return list(db.session.execute(query).scalars())


async def test_past_range_is_generated_without_the_assignee_doing_anything(world):
    db, prop, staff, _ = world
    _, assignment = give(db, prop, staff, start=date(2026, 10, 1))
    result = await ensure_occurrences(db, TENANT, up_to_date=date(2026, 10, 5))
    await db.commit()
    assert result.created == 5
    assert starts(db, assignment) == [date(2026, 10, d) for d in range(1, 6)]
    row = db.session.execute(select(KraOccurrence).limit(1)).scalar_one()
    assert (row.status, row.was_delayed, row.assignee_id, row.tenant_id) == ("pending", False, staff.id, TENANT)


async def test_generation_is_idempotent(world):
    db, prop, staff, _ = world
    give(db, prop, staff)
    first = await ensure_occurrences(db, TENANT, up_to_date=date(2026, 10, 3))
    second = await ensure_occurrences(db, TENANT, up_to_date=date(2026, 10, 3))
    assert (first.created, second.created) == (3, 0)
    assert len(starts(db)) == 3


async def test_existing_rows_are_left_as_they_are(world):
    db, prop, staff, _ = world
    give(db, prop, staff)
    await ensure_occurrences(db, TENANT, up_to_date=date(2026, 10, 1))
    row = db.session.execute(select(KraOccurrence)).scalar_one()
    row.status = "completed"
    await db.commit()
    await ensure_occurrences(db, TENANT, up_to_date=date(2026, 10, 2))
    db.session.refresh(row)
    assert row.status == "completed"


async def test_first_period_contains_the_start_date(world):
    db, prop, staff, _ = world
    _, assignment = give(db, prop, staff, "monthly", start=date(2026, 8, 20))
    await ensure_occurrences(db, TENANT, up_to_date=date(2026, 10, 2))
    assert starts(db, assignment) == [date(2026, 8, 1), date(2026, 9, 1), date(2026, 10, 1)]


async def test_filters_by_assignee_and_property_and_tenant(world):
    db, prop, staff, roles = world
    other_prop = property_row(TENANT)
    colleague = user_row(roles["Staff"], TENANT, other_prop.id)
    foreign_tenant = uuid4()
    foreign_prop = property_row(foreign_tenant)
    foreign_user = user_row(roles["Staff"], foreign_tenant, foreign_prop.id)
    db.session.add_all([other_prop, colleague, foreign_prop, foreign_user])
    db.session.commit()
    _, mine = give(db, prop, staff)
    _, theirs = give(db, other_prop, colleague)
    foreign_def = definition_row(foreign_tenant, foreign_prop.id)
    foreign = assignment_row(foreign_def, foreign_user.id, date(2026, 10, 1))
    db.session.add_all([foreign_def, foreign])
    db.session.commit()

    day = date(2026, 10, 1)
    await ensure_occurrences(db, TENANT, assignee_id=staff.id, up_to_date=day)
    assert (len(starts(db, mine)), len(starts(db, theirs))) == (1, 0)
    await ensure_occurrences(db, TENANT, property_id=other_prop.id, up_to_date=day)
    assert len(starts(db, theirs)) == 1
    await ensure_occurrences(db, TENANT, up_to_date=day)
    assert starts(db, foreign) == []


async def test_ended_assignment_generates_no_new_occurrences(world):
    db, prop, staff, _ = world
    _, assignment = give(db, prop, staff)
    await ensure_occurrences(db, TENANT, up_to_date=date(2026, 10, 2))
    assignment.is_active = False
    await db.commit()
    result = await ensure_occurrences(db, TENANT, up_to_date=date(2026, 10, 9))
    assert result.created == 0 and len(starts(db)) == 2


async def test_deactivated_definition_generates_none(world):
    db, prop, staff, _ = world
    give(db, prop, staff, is_active=False)
    assert (await ensure_occurrences(db, TENANT, up_to_date=date(2026, 10, 9))).created == 0


async def test_deleted_definition_generates_none(world):
    db, prop, staff, _ = world
    definition, _ = give(db, prop, staff)
    definition.soft_delete()
    await db.commit()
    assert (await ensure_occurrences(db, TENANT, up_to_date=date(2026, 10, 9))).created == 0


async def test_deactivated_assignee_generates_none(world):
    db, prop, staff, _ = world
    give(db, prop, staff)
    staff.is_active = False
    await db.commit()
    assert (await ensure_occurrences(db, TENANT, up_to_date=date(2026, 10, 9))).created == 0


async def test_cap_keeps_the_newest_periods_and_later_calls_fill_the_rest(world, monkeypatch):
    db, prop, staff, _ = world
    monkeypatch.setattr(service, "MAX_PERIODS_PER_CALL", 3)
    _, assignment = give(db, prop, staff, start=date(2026, 10, 1))
    up_to = date(2026, 10, 5)

    first = await ensure_occurrences(db, TENANT, up_to_date=up_to)
    assert (first.created, first.capped_assignments) == (3, 1)
    assert starts(db, assignment) == [date(2026, 10, d) for d in (3, 4, 5)]

    second = await ensure_occurrences(db, TENANT, up_to_date=up_to)
    assert (second.created, second.capped_assignments) == (2, 0)
    assert starts(db, assignment) == [date(2026, 10, d) for d in range(1, 6)]


def test_cap_covers_more_than_a_year_of_daily_tasks():
    assert MAX_PERIODS_PER_CALL > 366


# ── unique key and concurrency on a real database ───────────────────────────

async def pg_world(url):
    # replica role: no foreign key triggers, so the tenant parent needn't be seeded.
    engine = create_async_engine(url, poolclass=NullPool, connect_args={
        "server_settings": {"session_replication_role": "replica"}})
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sessions = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
    roles = role_rows()
    prop = property_row(TENANT)
    staff = user_row(roles["Staff"], TENANT, prop.id)
    definition = definition_row(TENANT, prop.id)
    assignment = assignment_row(definition, staff.id, date(2026, 10, 1))
    async with sessions() as session:
        session.add_all(roles.values())
        await session.flush()
        session.add_all([prop, staff])
        await session.flush()
        session.add(definition)
        await session.flush()
        session.add(assignment)
        await session.commit()
    return engine, sessions, assignment


async def count(sessions):
    async with sessions() as session:
        return (await session.execute(select(func.count()).select_from(KraOccurrence))).scalar()


async def test_generation_called_twice_and_concurrently_on_postgres():
    async with throwaway_database() as url:
        engine, sessions, _ = await pg_world(url)
        try:
            async def call():
                async with sessions() as session:
                    result = await ensure_occurrences(session, TENANT, up_to_date=date(2026, 10, 30))
                    await session.commit()
                    return result.created

            created = await asyncio.gather(*[call() for _ in range(6)])
            assert sum(created) == 30
            assert await count(sessions) == 30
            assert await call() == 0
            assert await count(sessions) == 30
        finally:
            await engine.dispose()


async def test_unique_key_rejects_a_second_row_for_the_same_period_on_postgres():
    async with throwaway_database() as url:
        engine, sessions, assignment = await pg_world(url)
        try:
            def row():
                return KraOccurrence(tenant_id=TENANT, property_id=assignment.property_id,
                                     assignment_id=assignment.id, definition_id=assignment.definition_id,
                                     assignee_id=assignment.assignee_id, period_start=date(2026, 10, 1),
                                     period_end=date(2026, 10, 1))
            async with sessions() as session:
                session.add(row())
                await session.commit()
            async with sessions() as session:
                session.add(row())
                with pytest.raises(IntegrityError):
                    await session.commit()
        finally:
            await engine.dispose()
