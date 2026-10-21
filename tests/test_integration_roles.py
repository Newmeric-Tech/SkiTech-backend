"""
Role checks on connecting a channel manager and triggering a manual sync.

Fake session only. The background sync is replaced with a recorder, so
nothing opens a real database session.
"""
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI

from app.api.dependencies import get_current_user
from app.api.v1.endpoints import integrations

TENANT_ID = uuid4()
INTEGRATION_ID = uuid4()
ROLE_DENIED = "Access forbidden: insufficient role"


class FakeDB:
    async def execute(self, stmt, params=None):
        sql = str(stmt)
        if "FROM properties" in sql:
            row = None  # property lookup fails -> the endpoint's own 403
        elif "FROM integrations" in sql:
            row = SimpleNamespace(id=INTEGRATION_ID, provider_name="mews")
        else:
            row = None
        return SimpleNamespace(fetchone=lambda: row)


@pytest.fixture
def client_for(monkeypatch):
    started = []

    async def record(integration):
        started.append(integration)

    monkeypatch.setattr(integrations, "sync_single_integration", record)

    def make(role):
        app = FastAPI()
        app.include_router(integrations.router)
        app.dependency_overrides[integrations.get_db] = lambda: FakeDB()
        app.dependency_overrides[integrations.get_current_user_obj] = lambda: SimpleNamespace(tenant_id=TENANT_ID)
        app.dependency_overrides[get_current_user] = lambda: {
            "tenant_id": str(TENANT_ID), "role": role}
        return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t")

    return make, started


CONNECT_BODY = {"provider_name": "mews", "property_id": str(uuid4()), "credentials": {}}


@pytest.mark.parametrize("role", ["Staff", "Manager"])
async def test_connect_refused_for_non_owner_roles(client_for, role):
    make, _ = client_for
    async with make(role) as client:
        resp = await client.post("/integrations", json=CONNECT_BODY)

    assert resp.status_code == 403
    assert resp.json()["detail"] == ROLE_DENIED


@pytest.mark.parametrize("role", ["Tenant Admin", "Co Admin", "Super Admin"])
async def test_connect_allowed_roles_pass_the_role_check(client_for, role):
    make, _ = client_for
    async with make(role) as client:
        resp = await client.post("/integrations", json=CONNECT_BODY)

    # Past the role check: the fake DB has no such property.
    assert resp.status_code == 403
    assert resp.json()["detail"] == "Property not found or does not belong to this tenant."


async def test_sync_refused_for_staff(client_for):
    make, started = client_for
    async with make("Staff") as client:
        resp = await client.post(f"/integrations/{INTEGRATION_ID}/sync")

    assert resp.status_code == 403
    assert resp.json()["detail"] == ROLE_DENIED
    assert started == []


@pytest.mark.parametrize("role", ["Manager", "Tenant Admin", "Co Admin", "Super Admin"])
async def test_sync_allowed_roles_start_the_sync(client_for, role):
    make, started = client_for
    async with make(role) as client:
        resp = await client.post(f"/integrations/{INTEGRATION_ID}/sync")

    assert resp.status_code == 200
    assert len(started) == 1
