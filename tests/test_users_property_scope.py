"""
GET /users and GET /users/{id} for a Manager: only users of the Manager's own
property. Asking for another property's list gives an empty list (as for an
unknown property); another property's user is a 404 (as for a missing one); a
Manager without a property gets 403. Tenant Admin and Co Admin are unchanged.

Runs the endpoints against an in-memory SQLite database; never touches the
.env database.
"""
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.api.dependencies import get_current_user
from app.api.v1.endpoints import users
from app.models.models import Role, User
from tests.test_user_role_change import SQLiteDB  # also registers JSONB on SQLite

TENANT = uuid4()
PROP_A, PROP_B = uuid4(), uuid4()


@pytest.fixture
def env():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Role.__table__.create(engine)
    User.__table__.create(engine)
    session = Session(engine)
    roles = {n: Role(id=uuid4(), name=n, role_level=i)
             for i, n in enumerate(["Super Admin", "Tenant Admin", "Co Admin", "Manager", "Staff"])}
    session.add_all(roles.values())
    people = {}
    for tag, role, prop in (("owner", "Tenant Admin", None), ("manager_a", "Manager", PROP_A),
                            ("staff_a", "Staff", PROP_A), ("manager_b", "Manager", PROP_B),
                            ("staff_b", "Staff", PROP_B), ("staff_none", "Staff", None)):
        people[tag] = User(id=uuid4(), tenant_id=TENANT, property_id=prop, email=f"{tag}@example.com",
                           password_hash="x", role_id=roles[role].id, is_active=True, is_verified=True)
    session.add_all(people.values())
    session.commit()
    yield session, people
    session.close()
    engine.dispose()


async def _get(env, caller, path, params=None):
    session, people = env
    app = FastAPI()
    app.include_router(users.router)
    app.dependency_overrides[users.get_db] = lambda: SQLiteDB(session)
    app.dependency_overrides[get_current_user] = lambda: caller
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as client:
        return await client.get(path, params=params or {})


def manager(prop):
    return {"user_id": str(uuid4()), "tenant_id": str(TENANT), "role": "Manager",
            "property_id": str(prop) if prop else None}


def _emails(resp):
    assert resp.status_code == 200, resp.text
    return {u["email"].split("@")[0] for u in resp.json()}


async def test_manager_lists_only_their_own_property(env):
    assert _emails(await _get(env, manager(PROP_A), "/users/")) == {"manager_a", "staff_a"}
    assert _emails(await _get(env, manager(PROP_A), "/users/", {"property_id": str(PROP_A)})) == {
        "manager_a", "staff_a"}
    assert _emails(await _get(env, manager(PROP_A), "/users/", {"role": "Staff"})) == {"staff_a"}


async def test_manager_asking_for_another_property_gets_an_empty_list(env):
    for prop in (PROP_B, uuid4()):   # another property, or an unknown one: same answer
        assert _emails(await _get(env, manager(PROP_A), "/users/", {"property_id": str(prop)})) == set()


async def test_manager_without_a_property_gets_403(env):
    assert (await _get(env, manager(None), "/users/")).status_code == 403
    _, people = env
    assert (await _get(env, manager(None), f"/users/{people['staff_a'].id}")).status_code == 403


async def test_manager_gets_404_for_a_user_of_another_property(env):
    _, people = env
    for tag in ("staff_b", "manager_b", "owner", "staff_none"):
        resp = await _get(env, manager(PROP_A), f"/users/{people[tag].id}")
        assert resp.status_code == 404 and resp.json() == {"detail": "User not found"}
    assert (await _get(env, manager(PROP_A), f"/users/{uuid4()}")).json() == {"detail": "User not found"}
    ok = await _get(env, manager(PROP_A), f"/users/{people['staff_a'].id}")
    assert ok.status_code == 200 and ok.json()["email"] == "staff_a@example.com"


async def test_tenant_admin_is_unchanged(env):
    admin = {"user_id": str(uuid4()), "tenant_id": str(TENANT), "role": "Tenant Admin", "property_id": None}
    assert _emails(await _get(env, admin, "/users/")) == {
        "owner", "manager_a", "staff_a", "manager_b", "staff_b", "staff_none"}
    assert _emails(await _get(env, admin, "/users/", {"property_id": str(PROP_B)})) == {"manager_b", "staff_b"}
    _, people = env
    assert (await _get(env, admin, f"/users/{people['staff_b'].id}")).status_code == 200


async def test_co_admin_scoping_is_unchanged(env):
    co_admin = {"user_id": str(uuid4()), "tenant_id": str(TENANT), "role": "Co Admin", "property_id": str(PROP_B)}
    assert _emails(await _get(env, co_admin, "/users/", {"property_id": str(PROP_A)})) == {"manager_b", "staff_b"}


async def test_staff_still_cannot_list_users(env):
    staff = {"user_id": str(uuid4()), "tenant_id": str(TENANT), "role": "Staff", "property_id": str(PROP_A)}
    assert (await _get(env, staff, "/users/")).status_code == 403
