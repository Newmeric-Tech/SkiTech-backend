"""
Role checks on the channel manager routes: connect, test connection,
disconnect and manual sync.

Fake session only. The background sync and the provider adapter are
replaced, so nothing opens a real database session or calls a provider.
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
    def __init__(self):
        self.disconnected = []

    async def commit(self):
        pass

    async def execute(self, stmt, params=None):
        sql = str(stmt)
        if "UPDATE integrations" in sql:
            hit = params["id"] == INTEGRATION_ID and params["tenant_id"] == TENANT_ID
            if hit:
                self.disconnected.append(params["id"])
            return SimpleNamespace(rowcount=1 if hit else 0)
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
    db = FakeDB()

    async def record(integration):
        started.append(integration)

    monkeypatch.setattr(integrations, "sync_single_integration", record)

    class OkAdapter:
        async def test_connection(self, credentials):
            return {"success": True, "message": "ok"}

    monkeypatch.setattr(integrations, "get_adapter", lambda name: OkAdapter())

    def make(role, tenant_id=TENANT_ID):
        app = FastAPI()
        app.include_router(integrations.router)
        app.dependency_overrides[integrations.get_db] = lambda: db
        app.dependency_overrides[integrations.get_current_user_obj] = lambda: SimpleNamespace(tenant_id=tenant_id)
        app.dependency_overrides[get_current_user] = lambda: {
            "tenant_id": str(tenant_id), "role": role}
        return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t")

    make.db = db
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


TEST_BODY = {"provider_name": "mews", "credentials": {}}


@pytest.mark.parametrize("role", ["Staff", "Manager"])
async def test_test_connection_refused_for_non_owner_roles(client_for, role):
    make, _ = client_for
    async with make(role) as client:
        resp = await client.post("/integrations/test", json=TEST_BODY)

    assert resp.status_code == 403
    assert resp.json()["detail"] == ROLE_DENIED


async def test_test_connection_allowed_for_tenant_admin(client_for):
    make, _ = client_for
    async with make("Tenant Admin") as client:
        resp = await client.post("/integrations/test", json=TEST_BODY)

    assert resp.status_code == 200
    assert resp.json() == {"success": True, "message": "ok"}


@pytest.mark.parametrize("role", ["Staff", "Manager"])
async def test_disconnect_refused_for_non_owner_roles(client_for, role):
    make, _ = client_for
    async with make(role) as client:
        resp = await client.delete(f"/integrations/{INTEGRATION_ID}")

    assert resp.status_code == 403
    assert resp.json()["detail"] == ROLE_DENIED
    assert make.db.disconnected == []


async def test_disconnect_allowed_for_tenant_admin(client_for):
    make, _ = client_for
    async with make("Tenant Admin") as client:
        resp = await client.delete(f"/integrations/{INTEGRATION_ID}")

    assert resp.status_code == 200
    assert make.db.disconnected == [INTEGRATION_ID]


async def test_disconnect_from_another_tenant_is_404(client_for):
    make, _ = client_for
    async with make("Tenant Admin", tenant_id=uuid4()) as client:
        resp = await client.delete(f"/integrations/{INTEGRATION_ID}")

    assert resp.status_code == 404
    assert make.db.disconnected == []
