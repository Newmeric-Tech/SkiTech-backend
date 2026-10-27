"""
Stale open attendance records: punch-out closes every open record of the
user at that property (only the newest gets real hours), punch-in closes
records older than 16 h instead of blocking forever, and /attendance/status
never reports more than 12 h or a stale shift as running.

In-memory SQLite / monkeypatched service only; never touches the .env database.
"""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI

from app.api.v1.endpoints import attendance as attendance_routes
from app.models.attendance import AttendanceRecord
from app.services.attendance_service import AUTO_CLOSED, AttendanceService
from tests.attendance_sqlite import add_geofence, all_records, make_db, punch_in, punch_out

TENANT, OTHER_TENANT = uuid4(), uuid4()
USER = uuid4()
PROPERTY, OTHER_PROPERTY = uuid4(), uuid4()
NOW = datetime.now(timezone.utc)


@pytest.fixture
def db():
    engine, db = make_db()
    add_geofence(db, TENANT, PROPERTY)
    yield db
    db.session.close()
    engine.dispose()


def _open(db, hours_ago, tenant=TENANT, prop=PROPERTY, user=USER):
    record = AttendanceRecord(id=uuid4(), tenant_id=tenant, user_id=user, property_id=prop,
                              punch_in_time=NOW - timedelta(hours=hours_ago), punch_in_lat=0, punch_in_lon=0,
                              is_within_fence=True, status="active", current_status="lunch_break")
    db.add(record)
    db.session.commit()
    return record.id


def _by_id(db):
    return {r.id: r for r in all_records(db)}


async def _out(db, request=None):
    return await AttendanceService.create_punch_out(db, USER, PROPERTY, TENANT, request or punch_out(0))


async def _in(db, request=None):
    return await AttendanceService.create_punch_in(db, USER, PROPERTY, TENANT, request or punch_in(0))


# ── punch-out ──────────────────────────────────────────────────────────────

async def test_punch_out_with_no_open_record(db):
    with pytest.raises(ValueError, match="No active punch in"):
        await _out(db)


async def test_punch_out_closes_all_three_open_records(db):
    newest = _open(db, 2)
    may_15 = _open(db, 24 * 165)
    may_20 = _open(db, 24 * 160)

    record, has_warning, _ = await _out(db)

    rows = _by_id(db)
    assert record.id == newest and not has_warning
    assert rows[newest].status == "completed"
    assert 1.9 < rows[newest].hours_worked < 2.1
    for old in (may_15, may_20):
        assert rows[old].status == AUTO_CLOSED
        assert rows[old].hours_worked is None          # no invented hours
        assert rows[old].punch_out_time is None
        assert rows[old].current_status is None
    # Nothing left open: the next status check says punched out
    assert await AttendanceService.get_active_punch_in(db, USER, PROPERTY, TENANT) is None


async def test_punch_out_when_the_newest_is_stale_closes_it_without_hours(db):
    stale = _open(db, 24 * 165)

    record, has_warning, warning = await _out(db)

    assert record.id == stale and record.status == AUTO_CLOSED
    assert record.hours_worked is None and record.punch_out_time is None
    assert has_warning and "older than 16 hours" in warning


async def test_punch_out_leaves_other_property_and_other_tenant_alone(db):
    mine = _open(db, 1)
    other_property = _open(db, 3, prop=OTHER_PROPERTY)
    other_tenant = _open(db, 3, tenant=OTHER_TENANT)
    other_user = _open(db, 3, user=uuid4())

    await _out(db)

    rows = _by_id(db)
    assert rows[mine].status == "completed"
    for untouched in (other_property, other_tenant, other_user):
        assert rows[untouched].status == "active" and rows[untouched].punch_out_time is None


async def test_rejected_punch_out_changes_none_of_the_open_records(db):
    ids = [_open(db, 2), _open(db, 24 * 165), _open(db, 24 * 160)]

    with pytest.raises(ValueError):
        await _out(db, punch_out(5000))

    rows = _by_id(db)
    assert all(rows[i].status == "active" and rows[i].hours_worked is None for i in ids)


# ── punch-in ───────────────────────────────────────────────────────────────

async def test_punch_in_auto_closes_stale_records_and_starts_a_shift(db):
    stale = [_open(db, 17), _open(db, 24 * 165)]

    record, _, _ = await _in(db)

    rows = _by_id(db)
    assert all(rows[i].status == AUTO_CLOSED and rows[i].hours_worked is None for i in stale)
    assert rows[record.id].status == "active"
    assert (await AttendanceService.get_active_punch_in(db, USER, PROPERTY, TENANT)).id == record.id


async def test_punch_in_is_still_blocked_by_a_recent_open_record(db):
    recent = _open(db, 15)
    stale = _open(db, 24 * 165)

    with pytest.raises(ValueError, match="already have an active punch-in"):
        await _in(db)

    rows = _by_id(db)
    assert len(rows) == 2
    assert rows[recent].status == "active" and rows[stale].status == "active"


async def test_rejected_punch_in_does_not_close_stale_records(db):
    stale = _open(db, 24 * 165)

    with pytest.raises(ValueError):
        await _in(db, punch_in(5000))

    rows = _by_id(db)
    assert len(rows) == 1 and rows[stale].status == "active"


async def test_stale_record_at_another_property_does_not_block_or_get_closed(db):
    elsewhere = _open(db, 24 * 165, prop=OTHER_PROPERTY)

    await _in(db)

    assert _by_id(db)[elsewhere].status == "active"


# ── /attendance/status ─────────────────────────────────────────────────────

async def _status(monkeypatch, hours_ago):
    record = SimpleNamespace(id=uuid4(), punch_in_time=NOW - timedelta(hours=hours_ago), is_within_fence=True,
                             current_status=None, punch_in_lat=1.0, punch_in_lon=2.0)

    async def fake_active(**_):
        return record
    monkeypatch.setattr(AttendanceService, "get_active_punch_in", staticmethod(fake_active))
    app = FastAPI()
    app.include_router(attendance_routes.router)
    app.dependency_overrides[attendance_routes.get_db] = lambda: None
    app.dependency_overrides[attendance_routes.get_current_user] = lambda: {
        "user_id": str(USER), "tenant_id": str(TENANT), "role": "Manager"}
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as client:
        resp = await client.get("/attendance/status", params={"property_id": str(PROPERTY)})
    assert resp.status_code == 200
    return resp.json(), record


async def test_status_running_shift(monkeypatch):
    body, _ = await _status(monkeypatch, 2)

    assert body["punched_in"] is True
    assert 1.99 <= body["hours_so_far"] <= 2.01


async def test_status_hours_are_capped_at_12(monkeypatch):
    body, _ = await _status(monkeypatch, 14)

    assert body["punched_in"] is True and body["hours_so_far"] == 12


async def test_status_reports_a_stale_shift_not_thousands_of_hours(monkeypatch):
    body, record = await _status(monkeypatch, 24 * 165)

    assert body["punched_in"] is False
    assert "hours_so_far" not in body
    assert body["stale_shift"]["attendance_id"] == str(record.id)
