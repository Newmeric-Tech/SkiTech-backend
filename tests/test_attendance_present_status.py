"""
auto_closed records (punched in, never punched out) are not "present",
don't hide a completed shift in the property's today list, and absurd
(>24 h) completed shifts stay out of the daily total.

In-memory SQLite / fake session only; never touches the .env database.
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
from tests.attendance_sqlite import make_db

TENANT, PROPERTY = uuid4(), uuid4()
TODAY = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)


def _rec(db, user, hour, status, hours=None):
    rid = uuid4()
    db.add(AttendanceRecord(id=rid, tenant_id=TENANT, user_id=user, property_id=PROPERTY,
                            punch_in_time=TODAY + timedelta(hours=hour), punch_in_lat=0, punch_in_lon=0,
                            is_within_fence=True, status=status, hours_worked=hours))
    db.session.commit()
    return rid


@pytest.fixture
def db():
    engine, db = make_db()
    yield db
    db.session.close()
    engine.dispose()


async def test_today_prefers_active_then_completed_over_auto_closed(db):
    worked, review_only, running = uuid4(), uuid4(), uuid4()
    completed = _rec(db, worked, 0.1, "completed", hours=0.05)
    _rec(db, worked, 0.2, AUTO_CLOSED)                  # later, but auto_closed
    lone_auto = _rec(db, review_only, 0.1, AUTO_CLOSED)
    _rec(db, running, 0.1, "completed", hours=0.05)
    active = _rec(db, running, 0.15, "active")

    rows = {r.user_id: r.id for r in await AttendanceService.get_property_attendance_today(db, PROPERTY, TENANT)}

    assert rows == {worked: completed, review_only: lone_auto, running: active}


async def test_daily_summary_skips_implausible_hours(db):
    user = uuid4()
    _rec(db, user, 0.1, "completed", hours=0.05)
    _rec(db, user, 0.2, "completed", hours=3721.0)
    _rec(db, user, 0.3, AUTO_CLOSED)

    summary = await AttendanceService.get_daily_summary(db, user, TENANT, datetime.now(timezone.utc))

    assert summary["total_hours_worked"] == 0.05
    assert summary["total_records"] == 2  # completed only, as before


class FakeDB:
    """Answers the endpoint's user-name lookup and active-staff count."""
    async def execute(self, stmt):
        if "count" in str(stmt).lower():
            return SimpleNamespace(scalar=lambda: 3)
        return []


async def test_today_endpoint_does_not_count_auto_closed_as_present(monkeypatch):
    recs = [SimpleNamespace(user_id=uuid4(), status=s, punch_in_time=TODAY, punch_out_time=None,
                            hours_worked=None, current_status=None, is_within_fence=True)
            for s in ("active", "completed", AUTO_CLOSED)]

    async def fake_today(**_):
        return recs
    monkeypatch.setattr(AttendanceService, "get_property_attendance_today", staticmethod(fake_today))
    app = FastAPI()
    app.include_router(attendance_routes.router)
    app.dependency_overrides[attendance_routes.get_db] = lambda: FakeDB()
    # require_permission returns a new closure per route; override that route's own one
    route = next(r for r in app.routes if getattr(r, "path", "") == "/attendance/property/{property_id}/today")
    perm_dep = route.dependant.dependencies[-1].call
    app.dependency_overrides[perm_dep] = lambda: {"tenant_id": str(TENANT), "role": "Manager"}

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as client:
        body = (await client.get(f"/attendance/property/{PROPERTY}/today")).json()

    assert body["present"] == 2
    assert body["absent"] == 1
    assert [r["status"] for r in body["records"]] == ["active", "completed", AUTO_CLOSED]
