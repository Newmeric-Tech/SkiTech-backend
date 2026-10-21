"""
GET /properties/{property_id}/room-sync-status.

Fake session only; nothing touches a real database.
"""
from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI

from app.api.v1.endpoints import properties

TENANT_ID = uuid4()
PROPERTY_ID = uuid4()
STARTED = datetime(2026, 10, 21, 9, 0, tzinfo=timezone.utc)
FINISHED = datetime(2026, 10, 21, 9, 1, tzinfo=timezone.utc)
SUMMARY = {"insert": 2, "adopt": 1, "update": 0, "conflict": 1,
           "conflicts": [{"room_number": "101", "reason": "matches a deleted room"}]}


def _integration(provider, **kw):
    return {"id": kw.get("id", uuid4()), "provider_name": provider,
            "connection_status": "active", "last_sync_at": FINISHED}


class FakeDB:
    def __init__(self, property_found=True, integrations=(), latest=None):
        self.property_found = property_found
        self.integrations = list(integrations)
        self.latest = latest
        self.params = {}

    async def execute(self, stmt, params=None):
        sql = str(stmt)
        if "FROM integrations" in sql:
            self.params["integrations"] = params
            return SimpleNamespace(mappings=lambda: SimpleNamespace(all=lambda: self.integrations))
        if "FROM sync_logs" in sql:
            self.params["sync_logs"] = params
            return SimpleNamespace(mappings=lambda: SimpleNamespace(first=lambda: self.latest))
        # _get_property_or_404's ORM select
        prop = SimpleNamespace(id=PROPERTY_ID) if self.property_found else None
        return SimpleNamespace(scalar_one_or_none=lambda: prop)


def _client(db, role="Staff"):
    app = FastAPI()
    app.include_router(properties.router)
    app.dependency_overrides[properties.get_db] = lambda: db
    app.dependency_overrides[properties.get_current_user] = lambda: {"tenant_id": str(TENANT_ID), "role": role}
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t")


async def _get(db):
    async with _client(db) as client:
        return await client.get(f"/properties/{PROPERTY_ID}/room-sync-status")


async def test_not_connected():
    resp = await _get(FakeDB())

    assert resp.status_code == 200
    assert resp.json() == {"connected": False}


async def test_connected_room_sync_provider_returns_latest_run():
    integ = _integration("mews")
    log_id = uuid4()
    db = FakeDB(integrations=[integ], latest={
        "id": log_id, "started_at": STARTED, "finished_at": FINISHED, "status": "success",
        "error_message": None, "rooms_summary": SUMMARY,
    })

    resp = await _get(db)

    assert resp.status_code == 200
    body = resp.json()
    assert body["connected"] is True
    assert body["integration"] == {
        "id": str(integ["id"]), "provider_name": "mews", "connection_status": "active",
        "supports_room_sync": True, "last_sync_at": "2026-10-21T09:01:00+00:00",
    }
    assert body["latest_sync"] == {
        "id": str(log_id), "started_at": "2026-10-21T09:00:00+00:00", "finished_at": "2026-10-21T09:01:00+00:00",
        "status": "success", "error_message": None, "rooms_summary": SUMMARY,
    }
    # Tenant-scoped lookups
    assert db.params["integrations"] == {"property_id": PROPERTY_ID, "tenant_id": TENANT_ID}
    assert db.params["sync_logs"] == {"integration_id": integ["id"]}


async def test_provider_without_room_sync_and_no_runs_yet():
    resp = await _get(FakeDB(integrations=[_integration("channex")]))

    body = resp.json()
    assert body["integration"]["supports_room_sync"] is False
    assert body["latest_sync"] is None


async def test_prefers_the_integration_that_syncs_rooms():
    cloudbeds = _integration("cloudbeds")
    resp = await _get(FakeDB(integrations=[_integration("siteminder"), cloudbeds]))

    assert resp.json()["integration"]["id"] == str(cloudbeds["id"])


async def test_property_of_another_tenant_is_404():
    resp = await _get(FakeDB(property_found=False, integrations=[_integration("mews")]))

    assert resp.status_code == 404
    assert resp.json()["detail"] == "Property not found"
