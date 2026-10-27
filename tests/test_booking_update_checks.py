"""
PUT /rooms/bookings/{id} checks the stay as it will be after the update
(existing + changed values): check_out after check_in (422 instead of the
database constraint), and the same overlap rule as create (400), ignoring
the booking itself and cancelled/completed bookings.

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


def d(day, hour=12):
    return datetime(2026, 11, day, hour)


@pytest.fixture
def env():
    engine = create_engine("sqlite://")
    Room.__table__.create(engine)
    Booking.__table__.create(engine)
    session = Session(engine)
    room = Room(id=uuid4(), tenant_id=TENANT_ID, property_id=PROPERTY_ID, room_number="101", status="occupied")
    other_room = Room(id=uuid4(), tenant_id=TENANT_ID, property_id=PROPERTY_ID, room_number="102", status="occupied")
    session.add_all([room, other_room])
    session.commit()
    app = FastAPI()
    app.include_router(rooms.router)
    app.dependency_overrides[rooms.get_db] = lambda: SQLiteDB(session)
    app.dependency_overrides[rooms.get_current_user] = lambda: {
        "tenant_id": str(TENANT_ID), "user_id": str(USER_ID), "role": "Manager"}
    client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t")
    yield client, session, room, other_room
    session.close()
    engine.dispose()


def _booking(session, room, check_in, check_out, status="booked"):
    b = Booking(id=uuid4(), tenant_id=TENANT_ID, property_id=PROPERTY_ID, room_id=room.id, created_by=USER_ID,
                customer_name="Guest", check_in=check_in, check_out=check_out, status=status)
    session.add(b)
    session.commit()
    return b.id


def _dates(session, booking_id):
    session.expire_all()
    b = session.get(Booking, booking_id)
    return b.check_in, b.check_out


async def _put(client, booking_id, **body):
    return await client.put(f"/rooms/bookings/{booking_id}", json=body)


async def test_reversed_dates_are_422_and_nothing_changes(env):
    client, session, room, _ = env
    bid = _booking(session, room, d(10), d(12))

    resp = await _put(client, bid, check_in=d(14).isoformat(), check_out=d(13).isoformat())

    assert resp.status_code == 422 and resp.json()["detail"] == "check_out must be after check_in"
    assert _dates(session, bid) == (d(10), d(12))


async def test_partial_update_is_checked_against_the_existing_check_in(env):
    client, session, room, _ = env
    bid = _booking(session, room, d(10), d(12))

    before = await _put(client, bid, check_out=d(9).isoformat())     # before the existing check_in
    equal = await _put(client, bid, check_out=d(10).isoformat())     # not after it
    ok = await _put(client, bid, check_out=d(15).isoformat())

    assert before.status_code == 422 and equal.status_code == 422
    assert ok.status_code == 200 and _dates(session, bid) == (d(10), d(15))


async def test_explicit_null_date_is_422(env):
    client, session, room, _ = env
    bid = _booking(session, room, d(10), d(12))

    resp = await client.put(f"/rooms/bookings/{bid}", json={"check_in": None})

    assert resp.status_code == 422
    assert _dates(session, bid) == (d(10), d(12))


async def test_overlap_with_another_active_booking_is_400(env):
    client, session, room, _ = env
    bid = _booking(session, room, d(10), d(12))
    _booking(session, room, d(13), d(16), status="checked_in")

    resp = await _put(client, bid, check_out=d(14).isoformat())   # 10-14 overlaps 13-16

    assert resp.status_code == 400
    assert resp.json()["detail"] == "Room already has an active booking for the selected dates"
    assert _dates(session, bid) == (d(10), d(12))


async def test_touching_stays_and_other_rooms_do_not_overlap(env):
    client, session, room, other_room = env
    bid = _booking(session, room, d(10), d(12))
    _booking(session, room, d(13), d(16))
    _booking(session, other_room, d(10), d(20))

    resp = await _put(client, bid, check_out=d(13).isoformat())   # ends exactly when the next starts

    assert resp.status_code == 200 and _dates(session, bid) == (d(10), d(13))


@pytest.mark.parametrize("status", ["cancelled", "completed"])
async def test_cancelled_and_completed_bookings_do_not_block(env, status):
    client, session, room, _ = env
    bid = _booking(session, room, d(10), d(12))
    _booking(session, room, d(13), d(16), status=status)

    assert (await _put(client, bid, check_out=d(15).isoformat())).status_code == 200


async def test_a_booking_does_not_overlap_itself(env):
    client, session, room, _ = env
    bid = _booking(session, room, d(10), d(14))

    resp = await _put(client, bid, check_in=d(11).isoformat(), check_out=d(13).isoformat())

    assert resp.status_code == 200 and _dates(session, bid) == (d(11), d(13))


async def test_status_only_update_skips_the_date_checks(env):
    client, session, room, _ = env
    bid = _booking(session, room, d(10), d(12))
    # An existing overlap (e.g. created before these checks) doesn't block an unrelated change
    _booking(session, room, d(11), d(13))

    resp = await _put(client, bid, status="checked_in", customer_name="New name")

    assert resp.status_code == 200
    session.expire_all()
    b = session.get(Booking, bid)
    assert b.status == "checked_in" and b.customer_name == "New name"


async def test_create_still_uses_the_same_overlap_rule(env):
    client, session, room, _ = env
    session.get(Room, room.id).status = "available"
    session.commit()
    _booking(session, room, d(10), d(12))

    overlap = await client.post(f"/rooms/{PROPERTY_ID}/bookings", json={
        "room_id": str(room.id), "check_in": d(11).isoformat(), "check_out": d(13).isoformat()})

    assert overlap.status_code == 400
    assert overlap.json()["detail"] == "Room already has an active booking for the selected dates"


async def test_two_existing_overlaps_are_a_400_not_a_500(env):
    client, session, room, _ = env
    session.get(Room, room.id).status = "available"
    session.commit()
    _booking(session, room, d(10), d(12))
    _booking(session, room, d(12), d(14))

    resp = await client.post(f"/rooms/{PROPERTY_ID}/bookings", json={
        "room_id": str(room.id), "check_in": d(11).isoformat(), "check_out": d(13).isoformat()})

    assert resp.status_code == 400
