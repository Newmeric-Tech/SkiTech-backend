"""
GET /rooms/{property_id} must return rooms in a stable, natural order
(999 before 1004), not whatever order the database happens to scan.

Runs the endpoint's real query against an in-memory SQLite database; never
touches the .env database.
"""

from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.api.v1.endpoints import rooms
from app.models.models import Room

TENANT_ID = uuid4()
PROPERTY_ID = uuid4()


class SQLiteDB:
    """Async-shaped wrapper that executes queries on a sync in-memory session."""

    def __init__(self, session: Session):
        self.session = session

    async def execute(self, statement):
        return self.session.execute(statement)


@pytest.fixture
def client():
    engine = create_engine("sqlite://")
    Room.__table__.create(engine)
    session = Session(engine)

    # Inserted out of order so SQLite's natural (rowid) order is unsorted.
    for number in ["1004", "1049", "999", "1029", "101"]:
        session.add(Room(tenant_id=TENANT_ID, property_id=PROPERTY_ID, room_number=number, status="available"))
    session.add(Room(tenant_id=uuid4(), property_id=PROPERTY_ID, room_number="1", status="available"))
    session.commit()

    app = FastAPI()
    app.include_router(rooms.router)
    app.dependency_overrides[rooms.get_db] = lambda: SQLiteDB(session)
    app.dependency_overrides[rooms.get_current_user] = lambda: {"tenant_id": str(TENANT_ID)}
    yield httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t")
    session.close()
    engine.dispose()


async def test_list_rooms_sorted_naturally_by_room_number(client):
    resp = await client.get(f"/rooms/{PROPERTY_ID}")

    assert resp.status_code == 200
    assert [r["room_number"] for r in resp.json()] == ["101", "999", "1004", "1029", "1049"]
