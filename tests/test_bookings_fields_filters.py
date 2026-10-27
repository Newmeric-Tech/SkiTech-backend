"""
Bookings expose the stored channel/payment columns, and
GET /rooms/{property_id}/bookings supports active_only and stays
tenant-scoped (404 for another tenant's property).

In-memory SQLite only; never touches the .env database.
"""
from datetime import datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.api.v1.endpoints import rooms
from app.models.models import Booking

TENANT_ID = uuid4()
OTHER_TENANT_ID = uuid4()
PROPERTY_ID = uuid4()
OTHER_PROPERTY_ID = uuid4()
NOW = datetime.utcnow()

EXPOSED = {
    "booking_source": "Booking.com",
    "special_requests": "Late arrival, extra pillows",
    "external_reservation_id": "BDC-123",
    "currency": "EUR",
    "room_rate": 120.5,
    "payment_status": "pending",
}


class SQLiteDB:
    def __init__(self, session: Session):
        self.session = session

    async def execute(self, statement):
        return self.session.execute(statement)


def _booking(key, check_in, check_out, status, tenant_id=TENANT_ID, property_id=PROPERTY_ID, **extra):
    return Booking(id=key, tenant_id=tenant_id, property_id=property_id, room_id=uuid4(),
                   created_by=uuid4(), customer_name="Guest", check_in=check_in,
                   check_out=check_out, status=status, **extra)


IDS = {name: uuid4() for name in (
    "in_house", "arriving_now", "future", "past", "cancelled_now", "completed_now", "other_tenant")}


@pytest.fixture
def session():
    engine = create_engine("sqlite://")
    Booking.__table__.create(engine)
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE properties (id CHAR(32), tenant_id CHAR(32), deleted_at DATETIME)"))
        for pid, tid in ((PROPERTY_ID, TENANT_ID), (OTHER_PROPERTY_ID, OTHER_TENANT_ID)):
            conn.execute(text("INSERT INTO properties VALUES (:id, :tenant_id, NULL)"),
                         {"id": pid.hex, "tenant_id": tid.hex})
    s = Session(engine)
    day = timedelta(days=1)
    s.add_all([
        _booking(IDS["in_house"], NOW - day, NOW + day, "checked_in",
                 **{**EXPOSED, "room_rate": Decimal("120.50")}),
        _booking(IDS["arriving_now"], NOW - timedelta(minutes=5), NOW + 2 * day, "booked"),
        _booking(IDS["future"], NOW + day, NOW + 2 * day, "booked"),
        _booking(IDS["past"], NOW - 3 * day, NOW - day, "checked_in"),
        _booking(IDS["cancelled_now"], NOW - day, NOW + day, "cancelled"),
        _booking(IDS["completed_now"], NOW - day, NOW + day, "completed"),
        _booking(IDS["other_tenant"], NOW - day, NOW + day, "checked_in",
                 tenant_id=OTHER_TENANT_ID, property_id=OTHER_PROPERTY_ID),
    ])
    s.commit()
    yield s
    s.close()
    engine.dispose()


@pytest.fixture
def client(session):
    app = FastAPI()
    app.include_router(rooms.router)
    app.dependency_overrides[rooms.get_db] = lambda: SQLiteDB(session)
    app.dependency_overrides[rooms.get_current_user] = lambda: {"tenant_id": str(TENANT_ID), "role": "Staff"}
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t")


async def _list(client, property_id=PROPERTY_ID, **params):
    return await client.get(f"/rooms/{property_id}/bookings", params=params)


async def test_list_and_detail_return_the_stored_columns(client):
    listed = {b["id"]: b for b in (await _list(client)).json()}
    detail = (await client.get(f"/rooms/bookings/detail/{IDS['in_house']}")).json()

    for body in (listed[str(IDS["in_house"])], detail):
        assert {k: body[k] for k in EXPOSED} == EXPOSED


async def test_unset_columns_are_null(client):
    detail = (await client.get(f"/rooms/bookings/detail/{IDS['future']}")).json()

    # payment_status and currency have ORM defaults ("paid", "USD"); the rest are null.
    assert detail["booking_source"] is None
    assert detail["special_requests"] is None
    assert detail["external_reservation_id"] is None
    assert detail["room_rate"] is None


async def test_active_only_keeps_stays_under_way(client):
    resp = await _list(client, active_only="true")

    assert resp.status_code == 200
    assert {UUID(b["id"]) for b in resp.json()} == {IDS["in_house"], IDS["arriving_now"]}


async def test_active_only_combines_with_status_and_keeps_order(client):
    only_checked_in = await _list(client, active_only="true", status="checked_in")
    active = await _list(client, active_only="true")

    assert [UUID(b["id"]) for b in only_checked_in.json()] == [IDS["in_house"]]
    # Existing order: newest check-in first
    assert [UUID(b["id"]) for b in active.json()] == [IDS["arriving_now"], IDS["in_house"]]


async def test_without_filters_all_tenant_bookings_are_listed(client):
    ids = {UUID(b["id"]) for b in (await _list(client)).json()}

    assert ids == set(IDS.values()) - {IDS["other_tenant"]}


async def test_other_tenant_property_is_404(client):
    resp = await _list(client, property_id=OTHER_PROPERTY_ID)

    assert resp.status_code == 404
    assert resp.json()["detail"] == "Property not found"


async def test_unknown_property_is_404(client):
    assert (await _list(client, property_id=uuid4())).status_code == 404


async def test_other_tenant_booking_detail_is_404(client):
    assert (await client.get(f"/rooms/bookings/detail/{IDS['other_tenant']}")).status_code == 404
