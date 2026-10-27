"""
Hours today / this week for the Punch page: only the requested day/week,
running shift capped, implausible (>24 h) and auto-closed records left out
and counted for review.

In-memory SQLite only; never touches the .env database.
"""
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI

from app.api.v1.endpoints import attendance as attendance_routes
from app.models.attendance import AttendanceRecord
from app.services.attendance_service import AUTO_CLOSED, AttendanceService
from tests.attendance_sqlite import make_db

TENANT, USER, PROPERTY = uuid4(), uuid4(), uuid4()
# Wednesday 15:00 UTC; local day starts 00:00, week starts Monday 00:00
NOW = datetime(2026, 10, 28, 15, 0, tzinfo=timezone.utc)
DAY_START = datetime(2026, 10, 28, tzinfo=timezone.utc)
WEEK_START = datetime(2026, 10, 26, tzinfo=timezone.utc)


def _rec(db, punch_in, status="completed", hours=None, tenant=TENANT, prop=PROPERTY):
    db.add(AttendanceRecord(id=uuid4(), tenant_id=tenant, user_id=USER, property_id=prop, punch_in_time=punch_in,
                            punch_in_lat=0, punch_in_lon=0, is_within_fence=True, status=status,
                            hours_worked=hours,
                            punch_out_time=punch_in + timedelta(hours=hours) if hours is not None else None))
    db.session.commit()


@pytest.fixture
def db():
    engine, db = make_db()
    yield db
    db.session.close()
    engine.dispose()


async def _totals(db):
    return await AttendanceService.get_user_totals(db, USER, PROPERTY, TENANT, DAY_START, WEEK_START, now=NOW)


async def test_today_and_week_only_count_their_own_records(db):
    _rec(db, datetime(2026, 10, 28, 6, tzinfo=timezone.utc), hours=3.0)     # today
    _rec(db, datetime(2026, 10, 27, 9, tzinfo=timezone.utc), hours=8.0)     # Tuesday
    _rec(db, datetime(2026, 10, 26, 9, tzinfo=timezone.utc), hours=7.5)     # Monday
    _rec(db, datetime(2026, 10, 25, 9, tzinfo=timezone.utc), hours=9.0)     # last Sunday: not this week
    _rec(db, datetime(2026, 5, 15, 9, tzinfo=timezone.utc), hours=3721.0)   # old absurd record

    t = await _totals(db)

    assert t["hours_today"] == 3.0
    assert t["hours_this_week"] == 18.5
    assert t["needs_review_this_week"] == 0


async def test_running_shift_is_added_to_today_and_week(db):
    _rec(db, datetime(2026, 10, 28, 6, tzinfo=timezone.utc), hours=3.0)
    _rec(db, datetime(2026, 10, 28, 13, tzinfo=timezone.utc), status="active")  # 2 h so far

    t = await _totals(db)

    assert t["open_shift_hours"] == 2.0
    assert t["hours_today"] == 5.0 and t["hours_this_week"] == 5.0


async def test_running_shift_is_capped_and_stale_one_ignored(db):
    _rec(db, datetime(2026, 10, 28, 1, tzinfo=timezone.utc), status="active")   # 14 h -> 12
    t = await _totals(db)
    assert t["open_shift_hours"] == 12.0 and t["hours_today"] == 12.0

    engine, db2 = make_db()
    _rec(db2, datetime(2026, 10, 27, 20, tzinfo=timezone.utc), status="active")  # 19 h: stale
    t = await AttendanceService.get_user_totals(db2, USER, PROPERTY, TENANT, DAY_START, WEEK_START, now=NOW)
    assert t["open_shift_hours"] == 0 and t["hours_this_week"] == 0
    engine.dispose()


async def test_implausible_and_auto_closed_records_are_excluded_and_flagged(db):
    _rec(db, datetime(2026, 10, 27, 9, tzinfo=timezone.utc), hours=3967.0)
    _rec(db, datetime(2026, 10, 26, 9, tzinfo=timezone.utc), status=AUTO_CLOSED)
    _rec(db, datetime(2026, 10, 26, 18, tzinfo=timezone.utc), hours=24.0)    # exactly 24 counts

    t = await _totals(db)

    assert t["hours_this_week"] == 24.0
    assert t["needs_review_this_week"] == 2


async def test_other_property_and_tenant_are_not_counted(db):
    _rec(db, datetime(2026, 10, 28, 6, tzinfo=timezone.utc), hours=3.0, prop=uuid4())
    _rec(db, datetime(2026, 10, 28, 6, tzinfo=timezone.utc), hours=3.0, tenant=uuid4())

    t = await _totals(db)

    assert t["hours_today"] == 0 and t["hours_this_week"] == 0


async def test_no_records(db):
    t = await _totals(db)

    assert (t["hours_today"], t["hours_this_week"], t["open_shift_hours"], t["needs_review_this_week"]) == (0, 0, 0, 0)


# ── Endpoint ───────────────────────────────────────────────────────────────

def _client(monkeypatch, seen):
    async def fake_totals(**kw):
        seen.update(kw)
        return {"hours_today": 1.0}
    monkeypatch.setattr(AttendanceService, "get_user_totals", staticmethod(fake_totals))
    app = FastAPI()
    app.include_router(attendance_routes.router)
    app.dependency_overrides[attendance_routes.get_db] = lambda: None
    app.dependency_overrides[attendance_routes.get_current_user] = lambda: {
        "user_id": str(USER), "tenant_id": str(TENANT), "role": "Manager"}
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t")


async def test_endpoint_passes_local_boundaries_and_caller_tenant(monkeypatch):
    seen = {}
    now = datetime.now(timezone.utc)
    local_midnight = (now - timedelta(hours=3)).replace(minute=0, second=0, microsecond=0)
    async with _client(monkeypatch, seen) as client:
        resp = await client.get("/attendance/totals", params={
            "property_id": str(PROPERTY), "day_start": local_midnight.isoformat(),
            "week_start": (local_midnight - timedelta(days=2)).isoformat()})

    assert resp.status_code == 200
    assert seen["tenant_id"] == str(TENANT) and seen["user_id"] == str(USER)
    assert seen["day_start"] == local_midnight


async def test_endpoint_defaults_to_utc_day_and_monday(monkeypatch):
    seen = {}
    async with _client(monkeypatch, seen) as client:
        await client.get("/attendance/totals", params={"property_id": str(PROPERTY)})

    assert seen["day_start"].hour == 0 and seen["day_start"].tzinfo is not None
    assert seen["week_start"].weekday() == 0 and seen["week_start"] <= seen["day_start"]


async def test_endpoint_rejects_ranges_older_than_a_week(monkeypatch):
    async with _client(monkeypatch, {}) as client:
        resp = await client.get("/attendance/totals", params={
            "property_id": str(PROPERTY), "week_start": "2026-01-01T00:00:00+00:00"})

    assert resp.status_code == 400
