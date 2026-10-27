"""
GET /properties/{property_id}/channel-activity: newest-first feed of sync
runs with safe, short messages.

Fake session only; nothing touches a real database.
"""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import httpx
from fastapi import FastAPI

from app.api.v1.endpoints import properties

TENANT_ID = uuid4()
PROPERTY_ID = uuid4()
INTEGRATION_ID = uuid4()
STARTED = datetime(2026, 10, 21, 9, 0, tzinfo=timezone.utc)
FINISHED = datetime(2026, 10, 21, 9, 1, tzinfo=timezone.utc)

RAW_DB_ERROR = (
    '(sqlalchemy.dialects.postgresql.asyncpg.IntegrityError) duplicate key value\n'
    'DETAIL:  Failing row contains (Jane Guest, jane@example.com, +15550100).\n'
    '[SQL: INSERT INTO reservations ...]\n[parameters: (\'Jane Guest\', \'jane@example.com\')]'
)


def _run(status="success", **kw):
    run = {"id": uuid4(), "integration_id": INTEGRATION_ID, "provider_name": "mews",
           "connection_status": "active", "started_at": STARTED, "finished_at": FINISHED,
           "status": status, "records_synced": 0, "error_message": None, "rooms_summary": None}
    run.update(kw)
    return run


class FakeDB:
    def __init__(self, property_found=True, connected=True, runs=()):
        self.property_found = property_found
        self.connected = connected
        self.runs = list(runs)
        self.params = {}
        self.sql = {}

    async def execute(self, stmt, params=None):
        sql = str(stmt)
        if "FROM sync_logs" in sql:
            self.params["runs"], self.sql["runs"] = params, sql
            return SimpleNamespace(mappings=lambda: SimpleNamespace(all=lambda: self.runs[: params["limit"]]))
        if "FROM integrations" in sql:
            self.params["integrations"] = params
            return SimpleNamespace(first=lambda: (1,) if self.connected else None)
        prop = SimpleNamespace(id=PROPERTY_ID) if self.property_found else None
        return SimpleNamespace(scalar_one_or_none=lambda: prop)


async def _get(db, **params):
    app = FastAPI()
    app.include_router(properties.router)
    app.dependency_overrides[properties.get_db] = lambda: db
    app.dependency_overrides[properties.get_current_user] = lambda: {"tenant_id": str(TENANT_ID), "role": "Manager"}
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as client:
        return await client.get(f"/properties/{PROPERTY_ID}/channel-activity", params=params)


async def test_success_run_with_room_counts():
    run = _run(records_synced=12, rooms_summary={
        "insert": 3, "adopt": 1, "update": 2, "conflict": 1,
        "conflicts": [{"room_number": "101", "reason": "matches a deleted room"}]})
    db = FakeDB(runs=[run])

    resp = await _get(db)

    assert resp.status_code == 200
    body = resp.json()
    assert body["connected"] is True
    assert body["items"] == [{
        "id": str(run["id"]), "timestamp": "2026-10-21T09:01:00+00:00",
        "started_at": "2026-10-21T09:00:00+00:00", "finished_at": "2026-10-21T09:01:00+00:00",
        "integration_id": str(INTEGRATION_ID), "provider_name": "mews", "connection_status": "active",
        "status": "success", "records_synced": 12, "conflicts_count": 1,
        "message": "Synced 12 reservations; rooms: 3 imported, 1 linked, 2 updated, 1 conflict",
        "error": None,
    }]
    # Tenant-scoped, newest first, default limit 30
    assert db.params["runs"] == {"property_id": PROPERTY_ID, "tenant_id": TENANT_ID, "limit": 30}
    assert db.params["integrations"] == {"property_id": PROPERTY_ID, "tenant_id": TENANT_ID}
    assert "ORDER BY s.started_at DESC" in db.sql["runs"]
    assert "i.tenant_id = :tenant_id" in db.sql["runs"]


async def test_rooms_summary_stored_as_json_text_is_read():
    resp = await _get(FakeDB(runs=[_run(records_synced=1, rooms_summary='{"insert": 0, "conflict": 2}')]))

    item = resp.json()["items"][0]
    assert item["conflicts_count"] == 2
    assert item["message"] == "Synced 1 reservation; rooms: 0 imported, 0 linked, 0 updated, 2 conflicts"


async def test_room_import_skipped_or_failed():
    resp = await _get(FakeDB(runs=[
        _run(rooms_summary={"insert": 0, "conflict": 0, "skipped": "rooms are owned by another active integration"}),
        _run(rooms_summary={"error": "Exception: Mews resources/getAll failed: 401 Unauthorized"}),
    ]))

    messages = [i["message"] for i in resp.json()["items"]]
    assert messages == ["Synced 0 reservations; room import skipped", "Synced 0 reservations; room import failed"]


async def test_safe_error_summary_is_shown():
    resp = await _get(FakeDB(runs=[_run("error", error_message="Exception: Mews reservations/getAll failed: 401 Unauthorized")]))

    item = resp.json()["items"][0]
    assert item["status"] == "error"
    assert item["error"] == "Exception: Mews reservations/getAll failed: 401 Unauthorized"
    assert item["message"] == "Sync failed: Exception: Mews reservations/getAll failed: 401 Unauthorized"


async def test_raw_database_error_text_is_never_returned():
    resp = await _get(FakeDB(runs=[_run("error", error_message=RAW_DB_ERROR)]))

    item = resp.json()["items"][0]
    assert item["error"] is None
    assert item["message"] == "Sync failed"
    assert "Jane" not in resp.text and "jane@example.com" not in resp.text and "[SQL" not in resp.text


async def test_no_raw_or_secret_fields_in_items():
    resp = await _get(FakeDB(runs=[_run("error", error_message="Database error: UniqueViolationError sqlstate=23505")]))

    item = resp.json()["items"][0]
    assert "error_message" not in item and "rooms_summary" not in item and "credentials_json" not in item


async def test_stale_syncing_run_is_interrupted_and_recent_one_in_progress():
    now = datetime.now(timezone.utc)
    resp = await _get(FakeDB(runs=[
        _run("syncing", started_at=now - timedelta(minutes=2), finished_at=None),
        _run("syncing", started_at=now - timedelta(minutes=20), finished_at=None),
    ]))

    items = resp.json()["items"]
    assert [(i["status"], i["message"]) for i in items] == [
        ("syncing", "Sync in progress"),
        ("interrupted", "Sync interrupted: no result after 15 minutes"),
    ]
    assert items[0]["timestamp"] == items[0]["started_at"]


async def test_not_connected_keeps_history_of_disconnected_integration():
    resp = await _get(FakeDB(connected=False, runs=[_run(connection_status="disconnected")]))

    body = resp.json()
    assert body["connected"] is False
    assert body["items"][0]["connection_status"] == "disconnected"


async def test_no_runs():
    resp = await _get(FakeDB(connected=False))

    assert resp.json() == {"connected": False, "items": []}


async def test_limit_is_passed_and_bounded():
    db = FakeDB(runs=[_run() for _ in range(10)])

    assert len((await _get(db, limit=8)).json()["items"]) == 8
    assert db.params["runs"]["limit"] == 8
    assert (await _get(db, limit=0)).status_code == 422
    assert (await _get(db, limit=101)).status_code == 422


async def test_property_of_another_tenant_is_404():
    resp = await _get(FakeDB(property_found=False, runs=[_run()]))

    assert resp.status_code == 404
    assert resp.json()["detail"] == "Property not found"
