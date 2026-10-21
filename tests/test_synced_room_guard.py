"""
Rooms managed by a channel manager integration: room_number / room_type
edits, delete and regenerate are refused with 409; status and price stay
editable. Rooms of a disconnected integration are manual again.

Runs the endpoints against an in-memory SQLite database; never touches the
.env database.
"""
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import create_engine, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session

from app.api.v1.endpoints import rooms
from app.models.channel_manager import Integration
from app.models.models import Booking, Property, Room

TENANT_ID = uuid4()
PROPERTY_ID = uuid4()


@compiles(JSONB, "sqlite")
def _jsonb_as_json_on_sqlite(type_, compiler, **kw):
    return "JSON"


class SQLiteDB:
    """Async-shaped wrapper over a sync in-memory session."""

    def __init__(self, session: Session):
        self.session = session

    async def execute(self, statement):
        return self.session.execute(statement)

    async def commit(self):
        self.session.commit()

    async def flush(self):
        self.session.flush()

    async def refresh(self, obj):
        self.session.refresh(obj)

    def add(self, obj):
        self.session.add(obj)


def _create(engine, *tables):
    # SQLite only evaluates server defaults such as gen_random_uuid() on
    # insert; every row here supplies its id, so the DDL is accepted as is.
    for table in tables:
        table.create(engine)


@pytest.fixture
def env():
    engine = create_engine("sqlite://")
    _create(engine, Room.__table__, Integration.__table__, Property.__table__, Booking.__table__)
    session = Session(engine)

    def integration(provider, status):
        i = Integration(id=uuid4(), tenant_id=TENANT_ID, property_id=PROPERTY_ID,
                        provider_name=provider, credentials_json="x", connection_status=status)
        session.add(i)
        return i

    def room(number, integ=None, room_type="Deluxe"):
        r = Room(id=uuid4(), tenant_id=TENANT_ID, property_id=PROPERTY_ID, room_number=number,
                 room_type=room_type, price_per_night=100, status="available",
                 integration_id=integ.id if integ else None, external_id="e-" + number if integ else None)
        session.add(r)
        return r

    active, gone = integration("mews", "active"), integration("cloudbeds", "disconnected")
    rooms_by_name = {"synced": room("101", active), "manual": room("102"), "orphaned": room("103", gone)}
    session.commit()

    app = FastAPI()
    app.include_router(rooms.router)
    app.dependency_overrides[rooms.get_db] = lambda: SQLiteDB(session)
    app.dependency_overrides[rooms.get_current_user] = lambda: {
        "tenant_id": str(TENANT_ID), "user_id": str(uuid4()), "role": "Tenant Admin"}
    client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t")
    yield client, session, rooms_by_name
    session.close()
    engine.dispose()


def _reload(session, room):
    session.expire_all()
    return session.execute(select(Room).where(Room.id == room.id)).scalar_one()


@pytest.mark.parametrize("payload", [{"room_number": "999"}, {"room_type": "Suite"}])
async def test_synced_room_number_and_type_cannot_be_changed(env, payload):
    client, session, r = env

    resp = await client.put(f"/rooms/{r['synced'].id}", json=payload)

    assert resp.status_code == 409
    assert "managed by the channel manager (mews)" in resp.json()["detail"]
    row = _reload(session, r["synced"])
    assert (row.room_number, row.room_type) == ("101", "Deluxe")


async def test_synced_room_status_and_price_stay_editable(env):
    client, session, r = env

    # The edit form resends unchanged number/type alongside the edited fields.
    resp = await client.put(f"/rooms/{r['synced'].id}", json={
        "room_number": "101", "room_type": "Deluxe", "price_per_night": 150, "status": "maintenance"})

    assert resp.status_code == 200
    assert resp.json()["integration_id"] == str(r["synced"].integration_id)
    row = _reload(session, r["synced"])
    assert (row.status, float(row.price_per_night)) == ("maintenance", 150.0)


async def test_synced_room_cannot_be_deleted(env):
    client, session, r = env

    resp = await client.delete(f"/rooms/{r['synced'].id}")

    assert resp.status_code == 409
    assert "managed by the channel manager (mews)" in resp.json()["detail"]
    assert _reload(session, r["synced"]).deleted_at is None


async def test_property_with_synced_rooms_cannot_be_regenerated(env):
    client, session, r = env
    session.add(Property(id=PROPERTY_ID, tenant_id=TENANT_ID, name="P", num_rooms=3, room_number_start=101))
    session.commit()

    resp = await client.post(f"/rooms/{PROPERTY_ID}/regenerate")

    assert resp.status_code == 409
    assert "managed by the channel manager (mews)" in resp.json()["detail"]
    assert _reload(session, r["synced"]).deleted_at is None


@pytest.mark.parametrize("which", ["manual", "orphaned"])
async def test_manual_and_disconnected_rooms_stay_fully_editable(env, which):
    client, session, r = env

    renamed = await client.put(f"/rooms/{r[which].id}", json={"room_number": "201", "room_type": "Suite"})
    deleted = await client.delete(f"/rooms/{r[which].id}")

    assert renamed.status_code == 200 and renamed.json()["room_number"] == "201"
    assert deleted.status_code == 200
    assert _reload(session, r[which]).deleted_at is not None
