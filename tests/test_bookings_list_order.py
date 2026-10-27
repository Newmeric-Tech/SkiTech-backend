"""
GET /rooms/{property_id}/bookings must return bookings newest check-in
first (ties by id) so offset/limit pages are stable.

Runs the endpoint's real query against an in-memory SQLite database; never
touches the .env database.
"""
from datetime import datetime
from uuid import UUID, uuid4

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.api.v1.endpoints import rooms
from app.models.models import Booking

TENANT_ID = uuid4()
PROPERTY_ID = uuid4()
# Two bookings share a check-in so the id tie-break is exercised.
TIED_IDS = sorted([uuid4(), uuid4()])
CHECK_INS = [
    (uuid4(), datetime(2026, 3, 1)),
    (TIED_IDS[1], datetime(2026, 5, 1)),
    (uuid4(), datetime(2026, 1, 1)),
    (TIED_IDS[0], datetime(2026, 5, 1)),
    (uuid4(), datetime(2026, 4, 1)),
]


class SQLiteDB:
    def __init__(self, session: Session):
        self.session = session

    async def execute(self, statement):
        return self.session.execute(statement)


@pytest.fixture
def client():
    engine = create_engine("sqlite://")
    Booking.__table__.create(engine)
    # Only the columns list_bookings' property check reads (the real table
    # has a JSONB column SQLite can't create).
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE properties (id CHAR(32), tenant_id CHAR(32), deleted_at DATETIME)"))
        conn.execute(text("INSERT INTO properties VALUES (:id, :tenant_id, NULL)"),
                     {"id": PROPERTY_ID.hex, "tenant_id": TENANT_ID.hex})
    session = Session(engine)
    # Inserted out of order so SQLite's natural (rowid) order is unsorted.
    for booking_id, check_in in CHECK_INS:
        session.add(Booking(id=booking_id, tenant_id=TENANT_ID, property_id=PROPERTY_ID, room_id=uuid4(),
                            created_by=uuid4(), customer_name="x", check_in=check_in,
                            check_out=check_in.replace(day=2), status="booked"))
    session.commit()

    app = FastAPI()
    app.include_router(rooms.router)
    app.dependency_overrides[rooms.get_db] = lambda: SQLiteDB(session)
    app.dependency_overrides[rooms.get_current_user] = lambda: {"tenant_id": str(TENANT_ID)}
    yield httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t")
    session.close()
    engine.dispose()


async def _ids(client, **params):
    resp = await client.get(f"/rooms/{PROPERTY_ID}/bookings", params=params)
    assert resp.status_code == 200
    return [UUID(b["id"]) for b in resp.json()]


async def test_bookings_sorted_by_check_in_desc_then_id(client):
    expected = [b for b, _ in sorted(CHECK_INS, key=lambda c: (-c[1].timestamp(), c[0]))]

    assert await _ids(client) == expected
    assert expected[:2] == TIED_IDS


async def test_pages_neither_repeat_nor_skip(client):
    pages = [await _ids(client, skip=s, limit=2) for s in (0, 2, 4)]

    assert sum(pages, []) == await _ids(client)
