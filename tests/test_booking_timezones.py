"""
Booking create/update accept offset-aware times (converted to naive UTC,
which is what bookings.check_in/check_out hold) instead of failing with a
500; naive times are kept as UTC; unparsable ones are a 422. The overlap
check on create compares the converted values.

In-memory SQLite only; never touches the .env database.
"""
from datetime import datetime
from uuid import UUID, uuid4

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.api.v1.endpoints import rooms
from app.models.models import Booking, Room

TENANT_ID, PROPERTY_ID, USER_ID = uuid4(), uuid4(), uuid4()


class SQLiteDB:
    def __init__(self, session: Session):
        self.session = session

    async def execute(self, statement):
        return self.session.execute(statement)

    def add(self, obj):
        self.session.add(obj)

    async def commit(self):
        self.session.commit()

    async def refresh(self, obj):
        self.session.refresh(obj)


@pytest.fixture
def env():
    engine = create_engine("sqlite://")
    Room.__table__.create(engine)
    Booking.__table__.create(engine)
    session = Session(engine)
    room = Room(id=uuid4(), tenant_id=TENANT_ID, property_id=PROPERTY_ID, room_number="101", status="available")
    session.add(room)
    session.commit()
    app = FastAPI()
    app.include_router(rooms.router)
    app.dependency_overrides[rooms.get_db] = lambda: SQLiteDB(session)
    who = {"tenant_id": str(TENANT_ID), "user_id": str(USER_ID), "role": "Manager"}
    app.dependency_overrides[rooms.get_current_user] = lambda: who
    client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t")
    yield client, session, room
    session.close()
    engine.dispose()


def _stored(session, booking_id):
    session.expire_all()
    b = session.get(Booking, UUID(booking_id))
    return b.check_in, b.check_out


async def _create(client, room, check_in, check_out):
    return await client.post(f"/rooms/{PROPERTY_ID}/bookings", json={
        "room_id": str(room.id), "customer_name": "Guest", "check_in": check_in, "check_out": check_out})


@pytest.mark.parametrize("check_in, check_out", [
    ("2026-10-27T14:00:00Z", "2026-10-28T10:00:00Z"),
    ("2026-10-27T19:30:00+05:30", "2026-10-28T15:30:00+05:30"),
    ("2026-10-27T14:00:00", "2026-10-28T10:00:00"),          # naive: taken as UTC
])
async def test_create_stores_naive_utc(env, check_in, check_out):
    client, session, room = env

    resp = await _create(client, room, check_in, check_out)

    assert resp.status_code == 201
    assert _stored(session, resp.json()["id"]) == (datetime(2026, 10, 27, 14), datetime(2026, 10, 28, 10))
    assert resp.json()["check_in"] == "2026-10-27T14:00:00"


@pytest.mark.parametrize("bad", ["tomorrow", "2026-13-45T25:00:00", ""])
async def test_unparsable_time_is_422_with_a_clear_message(env, bad):
    client, _, room = env

    resp = await _create(client, room, bad, "2026-10-28T10:00:00Z")

    assert resp.status_code == 422
    msg = resp.json()["detail"][0]["msg"]
    assert "check_in must be an ISO 8601 date-time" in msg


async def test_order_check_uses_converted_values(env):
    client, _, room = env
    # Wall clock says 10:00 -> 14:00, but 14:00+05:30 is 08:30 UTC: before check-in
    resp = await _create(client, room, "2026-10-27T10:00:00Z", "2026-10-27T14:00:00+05:30")

    assert resp.status_code == 422
    assert "check_out must be after check_in" in resp.json()["detail"][0]["msg"]


def _existing(session, room, start, end):
    """A booked stay already on the room (14:00-18:00 UTC); room left available."""
    session.add(Booking(id=uuid4(), tenant_id=TENANT_ID, property_id=PROPERTY_ID, room_id=room.id,
                        created_by=USER_ID, customer_name="First", check_in=start, check_out=end, status="booked"))
    session.commit()


async def test_overlap_detected_after_conversion(env):
    client, session, room = env
    _existing(session, room, datetime(2026, 10, 27, 14), datetime(2026, 10, 27, 18))

    # 20:00+05:30 = 14:30 UTC: inside the existing 14:00-18:00 UTC stay
    resp = await _create(client, room, "2026-10-27T20:00:00+05:30", "2026-10-28T02:00:00+05:30")

    assert resp.status_code == 400
    assert "already has an active booking" in resp.json()["detail"]


async def test_no_false_overlap_from_wall_clock_times(env):
    client, session, room = env
    _existing(session, room, datetime(2026, 10, 27, 14), datetime(2026, 10, 27, 18))

    # Wall clock 12:00-19:25 would look like an overlap, but in UTC it is
    # 06:30-13:55, which ends before the existing stay starts
    resp = await _create(client, room, "2026-10-27T12:00:00+05:30", "2026-10-27T19:25:00+05:30")

    assert resp.status_code == 201
    assert _stored(session, resp.json()["id"]) == (datetime(2026, 10, 27, 6, 30), datetime(2026, 10, 27, 13, 55))


async def test_update_converts_aware_times_and_rejects_bad_ones(env):
    client, session, room = env
    created = (await _create(client, room, "2026-10-27T14:00:00Z", "2026-10-28T10:00:00Z")).json()

    ok = await client.put(f"/rooms/bookings/{created['id']}", json={
        "check_in": "2026-10-27T11:00:00-04:00", "check_out": "2026-10-28T12:00:00"})
    bad = await client.put(f"/rooms/bookings/{created['id']}", json={"check_out": "next week"})

    assert ok.status_code == 200
    assert _stored(session, created["id"]) == (datetime(2026, 10, 27, 15), datetime(2026, 10, 28, 12))
    assert bad.status_code == 422
    assert "check_out must be an ISO 8601 date-time" in bad.json()["detail"][0]["msg"]
