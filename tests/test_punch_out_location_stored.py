"""
Punch-out stores its own location check (accuracy, within-fence, distance),
and PunchOutResponse.is_within_fence reports it instead of
`punch_out_lat is not None`.

In-memory SQLite / monkeypatched service only; never touches the .env database.
"""
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI

from app.api.v1.endpoints import attendance as attendance_routes
from app.models.attendance import AttendanceRecord
from app.services.attendance_service import AttendanceService
from tests.attendance_sqlite import add_geofence, make_db, punch_out

TENANT, USER, PROPERTY = uuid4(), uuid4(), uuid4()


@pytest.fixture
def db():
    engine, db = make_db()
    add_geofence(db, TENANT, PROPERTY, radius=200)
    db.add(AttendanceRecord(id=uuid4(), tenant_id=TENANT, user_id=USER, property_id=PROPERTY,
                            punch_in_time=datetime.now(timezone.utc) - timedelta(hours=3),
                            punch_in_lat=0, punch_in_lon=0, is_within_fence=True, distance_meters=5.0,
                            status="active"))
    db.session.commit()
    yield db
    db.session.close()
    engine.dispose()


async def test_punch_out_inside_stores_its_location(db):
    record, _, _ = await AttendanceService.create_punch_out(db, USER, PROPERTY, TENANT, punch_out(30, accuracy=12))

    assert record.punch_out_acc == 12
    assert record.punch_out_within_fence is True
    assert 25 < record.punch_out_distance_meters < 35
    assert record.distance_meters == 5.0  # punch-in distance unchanged


async def test_borderline_punch_out_is_stored_as_outside(db):
    # 280 m with 90 m accuracy is accepted (280 - 90 <= 200) but is beyond
    # radius + the 50 m boundary buffer, so it is recorded as outside.
    record, _, _ = await AttendanceService.create_punch_out(db, USER, PROPERTY, TENANT, punch_out(280, accuracy=90))

    assert record.status == "completed"
    assert record.punch_out_within_fence is False
    assert 275 < record.punch_out_distance_meters < 285


@pytest.mark.parametrize("within", [True, False])
async def test_response_reports_the_punch_out_result(monkeypatch, within):
    record = AttendanceRecord(id=uuid4(), hours_worked=2.5, punch_out_lat=28.6,
                              punch_out_within_fence=within, punch_out_distance_meters=120.0,
                              distance_meters=3.0)

    async def fake_punch_out(**_):
        return record, False, None
    monkeypatch.setattr(AttendanceService, "create_punch_out", staticmethod(fake_punch_out))

    app = FastAPI()
    app.include_router(attendance_routes.router)
    app.dependency_overrides[attendance_routes.get_db] = lambda: None
    app.dependency_overrides[attendance_routes.get_current_user] = lambda: {
        "user_id": str(USER), "tenant_id": str(TENANT), "role": "Manager"}
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as client:
        resp = await client.post("/attendance/punch-out", params={"property_id": str(PROPERTY)},
                                 json={"geolocation": {"latitude": 28.6, "longitude": 77.2, "accuracy": 10}})

    body = resp.json()
    assert body["is_within_fence"] is within  # was always True once punch_out_lat was set
    assert body["distance_meters"] == 120.0    # punch-out distance, not punch-in
