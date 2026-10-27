"""
GET /rooms/{property_id}/live-summary: each room's current booking with a
server-side stay progress, and active-booking counts per booking_source.

In-memory SQLite only; never touches the .env database.
"""
from datetime import datetime, timedelta
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.api.v1.endpoints import rooms
from app.models.models import Booking, Room

TENANT_ID = uuid4()
OTHER_TENANT_ID = uuid4()
PROPERTY_ID = uuid4()
EMPTY_PROPERTY_ID = uuid4()
OTHER_PROPERTY_ID = uuid4()
DAY = timedelta(days=1)


class SQLiteDB:
    def __init__(self, session: Session):
        self.session = session
        self.statements = 0

    async def execute(self, statement):
        self.statements += 1
        return self.session.execute(statement)


@pytest.fixture
def setup():
    engine = create_engine("sqlite://")
    Room.__table__.create(engine)
    Booking.__table__.create(engine)
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE properties (id CHAR(32), tenant_id CHAR(32), deleted_at DATETIME)"))
        for pid, tid in ((PROPERTY_ID, TENANT_ID), (EMPTY_PROPERTY_ID, TENANT_ID),
                         (OTHER_PROPERTY_ID, OTHER_TENANT_ID)):
            conn.execute(text("INSERT INTO properties VALUES (:id, :tenant_id, NULL)"),
                         {"id": pid.hex, "tenant_id": tid.hex})
    session = Session(engine)
    now = datetime.utcnow()
    r = {n: Room(id=uuid4(), tenant_id=TENANT_ID, property_id=PROPERTY_ID, room_number=n, status="available")
         for n in ("101", "102", "103", "104", "105")}
    deleted = Room(id=uuid4(), tenant_id=TENANT_ID, property_id=PROPERTY_ID, room_number="199",
                   status="available", deleted_at=now)
    foreign_room = Room(id=uuid4(), tenant_id=OTHER_TENANT_ID, property_id=OTHER_PROPERTY_ID,
                        room_number="101", status="occupied")
    session.add_all([*r.values(), deleted, foreign_room])

    def booking(room, status, check_in, check_out, **kw):
        b = Booking(id=uuid4(), tenant_id=room.tenant_id, property_id=room.property_id, room_id=room.id,
                    created_by=uuid4(), customer_name=kw.pop("name", "Guest"), status=status,
                    check_in=check_in, check_out=check_out, **kw)
        session.add(b)
        return b

    b = {
        # 101: one quarter through a four-day stay
        "101": booking(r["101"], "checked_in", now - DAY, now + 3 * DAY, name="Ana",
                       booking_source="Booking.com", special_requests="Quiet room", total_amount=400,
                       currency="EUR"),
        # 102: booked and arrival time passed, not yet checked in -> still current
        "102": booking(r["102"], "booked", now - timedelta(hours=1), now + DAY, booking_source="Airbnb"),
        # 103: only finished or future bookings -> no current booking
        "103_past": booking(r["103"], "completed", now - 3 * DAY, now - DAY, booking_source="Airbnb"),
        "103_future": booking(r["103"], "booked", now + DAY, now + 2 * DAY, booking_source="Airbnb"),
        "103_cancelled": booking(r["103"], "cancelled", now - DAY, now + DAY, booking_source="Airbnb"),
        # 104: two overlapping active bookings -> the checked-in one wins
        "104_booked": booking(r["104"], "booked", now - timedelta(hours=2), now + DAY),
        "104_in": booking(r["104"], "checked_in", now - DAY, now + DAY, booking_source="  "),
        # bookings of a deleted room still count toward sources, but the room isn't listed
        "deleted_room": booking(deleted, "checked_in", now - DAY, now + DAY, booking_source="Booking.com"),
        "foreign": booking(foreign_room, "checked_in", now - DAY, now + DAY, booking_source="Expedia"),
    }
    session.commit()

    db = SQLiteDB(session)
    app = FastAPI()
    app.include_router(rooms.router)
    app.dependency_overrides[rooms.get_db] = lambda: db
    app.dependency_overrides[rooms.get_current_user] = lambda: {"tenant_id": str(TENANT_ID), "role": "Staff"}
    client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t")
    yield client, db, r, b
    session.close()
    engine.dispose()


async def _summary(client, property_id=PROPERTY_ID):
    return await client.get(f"/rooms/{property_id}/live-summary")


async def test_current_booking_per_room(setup):
    client, _, r, b = setup
    body = (await _summary(client)).json()
    by_room = {row["room_id"]: row["current_booking"] for row in body["rooms"]}

    assert list(by_room) == [str(r[n].id) for n in ("101", "102", "103", "104", "105")]
    ana = by_room[str(r["101"].id)]
    assert ana["booking_id"] == str(b["101"].id)
    assert ana["guest_name"] == "Ana"
    assert ana["booking_source"] == "Booking.com"
    assert ana["special_requests"] == "Quiet room"
    assert ana["status"] == "checked_in"
    assert ana["total_amount"] == 400
    assert ana["currency"] == "EUR"
    assert 24.9 <= ana["stay_progress_pct"] <= 25.1
    assert by_room[str(r["102"].id)]["booking_id"] == str(b["102"].id)
    assert by_room[str(r["103"].id)] is None
    assert by_room[str(r["104"].id)]["booking_id"] == str(b["104_in"].id)
    assert by_room[str(r["105"].id)] is None


async def test_source_counts_cover_active_bookings_only(setup):
    client, *_ = setup
    body = (await _summary(client)).json()

    # 101 + deleted room = 2 Booking.com, 102 = Airbnb; 104's two have no source.
    assert body["active_bookings"] == 5
    assert body["source_counts"] == [
        {"source": "Booking.com", "count": 2},
        {"source": None, "count": 2},
        {"source": "Airbnb", "count": 1},
    ]


async def test_one_query_for_bookings_regardless_of_room_count(setup):
    client, db, *_ = setup
    await _summary(client)

    assert db.statements == 3  # property check, rooms, bookings


async def test_empty_property(setup):
    client, *_ = setup
    resp = await _summary(client, EMPTY_PROPERTY_ID)

    assert resp.status_code == 200
    body = resp.json()
    assert body["rooms"] == [] and body["source_counts"] == [] and body["active_bookings"] == 0


async def test_other_tenant_property_is_404(setup):
    client, *_ = setup
    resp = await _summary(client, OTHER_PROPERTY_ID)

    assert resp.status_code == 404
    assert resp.json()["detail"] == "Property not found"


def test_stay_progress_bounds():
    start = datetime(2026, 1, 1)
    end = datetime(2026, 1, 3)
    assert rooms._stay_progress(start, end, datetime(2026, 1, 2)) == 50.0
    assert rooms._stay_progress(start, end, datetime(2025, 12, 31)) == 0.0
    assert rooms._stay_progress(start, end, datetime(2026, 1, 5)) == 100.0
    assert rooms._stay_progress(start, start, start) == 100.0
