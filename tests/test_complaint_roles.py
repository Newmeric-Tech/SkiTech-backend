"""
Complaint permission tier comes from the role name, not role_level.

Seeded levels (seed_roles.py): Super Admin 0, Tenant Admin 1, Co Admin 1,
Manager 2, Staff 3. The old level mapping (<=2 owner, 3 manager) made Staff
a "manager" and Manager an "owner".

Fake objects only; nothing touches a real database.
"""
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI

from app.api.v1.endpoints import complaints

SEEDED_LEVELS = {"Super Admin": 0, "Tenant Admin": 1, "Co Admin": 1, "Manager": 2, "Staff": 3}


def _user(role_name, level=None):
    role = SimpleNamespace(name=role_name, role_level=SEEDED_LEVELS.get(role_name, 99) if level is None else level)
    return SimpleNamespace(id=uuid4(), tenant_id=uuid4(), property_id=uuid4(), role_obj=role)


@pytest.mark.parametrize("role_name,expected", [
    ("Super Admin", "owner"),
    ("Tenant Admin", "owner"),
    ("Co Admin", "owner"),
    ("Manager", "manager"),
    ("Staff", "staff"),
    ("Custom Role", "staff"),
])
async def test_tier_follows_role_name_with_seeded_levels(role_name, expected):
    service = await complaints.get_complaint_service(db=None, current_user=_user(role_name))

    assert service.user_role == expected


async def test_level_does_not_override_name():
    service = await complaints.get_complaint_service(db=None, current_user=_user("Staff", level=0))

    assert service.user_role == "staff"


async def test_user_without_role_is_staff():
    user = _user("Staff")
    user.role_obj = None

    service = await complaints.get_complaint_service(db=None, current_user=user)

    assert service.user_role == "staff"


def _client(role_name):
    app = FastAPI()
    app.include_router(complaints.router)
    app.dependency_overrides[complaints.get_db] = lambda: None
    app.dependency_overrides[complaints.get_current_user_obj] = lambda: _user(role_name)
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t")


@pytest.mark.parametrize("method,path,body", [
    ("POST", f"/complaints/{uuid4()}/resolve", {"status": "resolved", "resolution_notes": "fixed the issue"}),
    ("GET", "/complaints/dashboard/manager", None),
    ("POST", "/complaints/export", {}),
])
async def test_staff_is_refused_manager_actions(method, path, body):
    async with _client("Staff") as client:
        resp = await client.request(method, path, json=body)

    assert resp.status_code == 403


async def test_manager_is_refused_the_owner_dashboard():
    async with _client("Manager") as client:
        resp = await client.get("/complaints/dashboard/owner")

    assert resp.status_code == 403
