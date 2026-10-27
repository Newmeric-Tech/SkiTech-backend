"""
Punch in/out are rejected (nothing saved, open record untouched) when the
property has no geofence, GPS accuracy is worse than 100 m, or the user is
definitely outside: distance - accuracy > radius.

In-memory SQLite only; never touches the .env database.
"""
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from app.models.attendance import AttendanceRecord
from app.services.attendance_service import NO_GEOFENCE_MESSAGE, AttendanceService
from tests.attendance_sqlite import RADIUS, add_geofence, all_records, make_db, punch_in, punch_out

TENANT = uuid4()
OTHER_TENANT = uuid4()
USER = uuid4()
PROPERTY = uuid4()


@pytest.fixture
def db():
    engine, db = make_db()
    add_geofence(db, TENANT, PROPERTY)
    yield db
    db.session.close()
    engine.dispose()


def _in(db, request, tenant=TENANT, prop=PROPERTY):
    return AttendanceService.create_punch_in(db, USER, prop, tenant, request)


def _out(db, request, tenant=TENANT, prop=PROPERTY):
    return AttendanceService.create_punch_out(db, USER, prop, tenant, request)


def _open_record(db, hours_ago=2):
    db.add(AttendanceRecord(id=uuid4(), tenant_id=TENANT, user_id=USER, property_id=PROPERTY,
                            punch_in_time=datetime.now(timezone.utc) - timedelta(hours=hours_ago),
                            punch_in_lat=0, punch_in_lon=0, is_within_fence=True, status="active"))
    db.session.commit()


async def test_inside_is_saved(db):
    record, _, _ = await _in(db, punch_in(50))

    assert record.status == "active"
    assert record.is_within_fence is True
    assert 45 < record.distance_meters < 55
    assert len(all_records(db)) == 1


async def test_outside_is_rejected_and_nothing_saved(db):
    with pytest.raises(ValueError) as err:
        await _in(db, punch_in(1000, accuracy=10))

    assert "1000 m from the property" in str(err.value)
    assert f"within {RADIUS} m" in str(err.value)
    assert all_records(db) == []


async def test_borderline_within_accuracy_is_saved(db):
    # 250 m out, accuracy 60 m: 250 - 60 = 190 <= 200 -> could be inside
    record, _, _ = await _in(db, punch_in(250, accuracy=60))

    assert record.status == "active"


async def test_just_beyond_radius_plus_accuracy_is_rejected(db):
    # 260 m out, accuracy 50 m: 210 > 200
    with pytest.raises(ValueError):
        await _in(db, punch_in(260, accuracy=50))
    assert all_records(db) == []


async def test_poor_accuracy_is_rejected(db):
    with pytest.raises(ValueError) as err:
        await _in(db, punch_in(0, accuracy=150))

    assert "GPS accuracy too low" in str(err.value)
    assert all_records(db) == []


async def test_accuracy_of_exactly_100_m_is_accepted(db):
    record, _, _ = await _in(db, punch_in(0, accuracy=100))

    assert record.status == "active"


async def test_no_geofence_is_rejected():
    engine, db = make_db()
    with pytest.raises(ValueError) as err:
        await _in(db, punch_in(0))

    assert str(err.value) == NO_GEOFENCE_MESSAGE
    assert all_records(db) == []
    engine.dispose()


async def test_geofence_of_another_tenant_does_not_count(db):
    # Same property id, but the caller's tenant has no geofence for it
    with pytest.raises(ValueError) as err:
        await _in(db, punch_in(0), tenant=OTHER_TENANT)

    assert str(err.value) == NO_GEOFENCE_MESSAGE
    assert all_records(db) == []


async def test_punch_out_outside_leaves_open_record_untouched(db):
    _open_record(db)

    with pytest.raises(ValueError):
        await _out(db, punch_out(1000))

    [record] = all_records(db)
    assert record.status == "active"
    assert record.punch_out_time is None and record.hours_worked is None


async def test_punch_out_poor_accuracy_and_no_geofence_leave_record_open():
    engine, db = make_db()
    _open_record(db)
    with pytest.raises(ValueError):
        await _out(db, punch_out(0))           # no geofence
    add_geofence(db, TENANT, PROPERTY)
    with pytest.raises(ValueError):
        await _out(db, punch_out(0, accuracy=500))

    [record] = all_records(db)
    assert record.status == "active" and record.punch_out_time is None
    engine.dispose()


async def test_punch_out_inside_closes_the_record(db):
    _open_record(db, hours_ago=2)

    record, _, _ = await _out(db, punch_out(20))

    assert record.status == "completed"
    assert 1.9 < record.hours_worked < 2.1


# ── Endpoint: rejection reaches the client as a 400 with the message ──────

import httpx
from fastapi import FastAPI

from app.api.v1.endpoints import attendance as attendance_routes

BODY = {"geolocation": {"latitude": 28.6, "longitude": 77.2, "accuracy": 10}}


def _client():
    app = FastAPI()
    app.include_router(attendance_routes.router)
    app.dependency_overrides[attendance_routes.get_db] = lambda: None
    app.dependency_overrides[attendance_routes.get_current_user] = lambda: {
        "user_id": str(USER), "tenant_id": str(TENANT), "role": "Manager"}
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t")


@pytest.mark.parametrize("path, method", [("punch-in", "create_punch_in"), ("punch-out", "create_punch_out")])
async def test_rejection_is_a_400_with_the_message(monkeypatch, path, method):
    async def reject(**_):
        raise ValueError(NO_GEOFENCE_MESSAGE)
    monkeypatch.setattr(AttendanceService, method, staticmethod(reject))

    async with _client() as client:
        resp = await client.post(f"/attendance/{path}", params={"property_id": str(PROPERTY)}, json=BODY)

    assert resp.status_code == 400
    assert resp.json()["detail"] == NO_GEOFENCE_MESSAGE


async def test_unexpected_error_text_is_not_returned(monkeypatch):
    async def boom(**_):
        raise RuntimeError("[SQL: INSERT ...] [parameters: ('secret',)]")
    monkeypatch.setattr(AttendanceService, "create_punch_in", staticmethod(boom))

    async with _client() as client:
        resp = await client.post("/attendance/punch-in", params={"property_id": str(PROPERTY)}, json=BODY)

    assert resp.status_code == 500
    assert "secret" not in resp.text and "SQL" not in resp.text
