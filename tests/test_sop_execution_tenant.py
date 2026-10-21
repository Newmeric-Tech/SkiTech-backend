"""
SOP approve/reject: an execution from another tenant is 404 for every role;
the Manager property check still applies within the tenant.

Fake session only; nothing touches a real database.
"""
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI

from app.api.dependencies import get_current_user
from app.api.v1.endpoints import sop
from app.models.models import SOPExecution, SOPItem

MY_TENANT, OTHER_TENANT = uuid4(), uuid4()
MY_PROPERTY = uuid4()


class FakeDB:
    def __init__(self, execution):
        self.execution = execution
        self.sop_item = SimpleNamespace(status="in_progress")
        self.commits = 0

    async def get(self, model, key):
        if model is SOPExecution:
            return self.execution if key == self.execution.id else None
        if model is SOPItem:
            return self.sop_item
        return None

    async def commit(self):
        self.commits += 1


def _execution(tenant_id, property_id=MY_PROPERTY):
    return SimpleNamespace(id=uuid4(), tenant_id=tenant_id, property_id=property_id, sop_id=uuid4(),
                           status="proof_submitted", completed_at=None, rejection_reason=None,
                           proof_image="x", proof_submitted_at="x")


def _client(db, role):
    app = FastAPI()
    app.include_router(sop.router)
    app.dependency_overrides[sop.get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: {
        "tenant_id": str(MY_TENANT), "role": role, "property_id": str(MY_PROPERTY), "user_id": str(uuid4())}
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t")


async def _call(db, role, action):
    body = {"reason": "blurry photo"} if action == "reject" else None
    async with _client(db, role) as client:
        return await client.post(f"/sop/executions/{db.execution.id}/{action}", json=body)


@pytest.mark.parametrize("action", ["approve", "reject"])
@pytest.mark.parametrize("role", ["Tenant Admin", "Co Admin", "Manager", "Super Admin"])
async def test_other_tenants_execution_is_404_for_every_role(role, action):
    db = FakeDB(_execution(OTHER_TENANT))

    resp = await _call(db, role, action)

    assert resp.status_code == 404
    assert resp.json()["detail"] == "Execution not found"
    assert db.execution.status == "proof_submitted" and db.commits == 0


@pytest.mark.parametrize("action,status", [("approve", "approved"), ("reject", "rejected")])
async def test_own_tenant_execution_still_works(action, status):
    db = FakeDB(_execution(MY_TENANT))

    resp = await _call(db, "Tenant Admin", action)

    assert resp.status_code == 200
    assert db.execution.status == status


@pytest.mark.parametrize("action", ["approve", "reject"])
async def test_manager_property_check_is_kept(action):
    db = FakeDB(_execution(MY_TENANT, property_id=uuid4()))

    resp = await _call(db, "Manager", action)

    assert resp.status_code == 403
    assert db.execution.status == "proof_submitted"
