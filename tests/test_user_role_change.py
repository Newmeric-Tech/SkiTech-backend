"""
PUT /users/{user_id}/role rules:
- nobody may change their own role;
- Super Admin may assign any role;
- anyone else may only assign Manager or Staff, and only to a Manager or
  Staff user.

Runs the endpoint against an in-memory SQLite database; never touches the
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
from sqlalchemy.pool import StaticPool

from app.api.dependencies import get_current_user
from app.api.v1.endpoints import users
from app.models.models import Role, User

TENANT_ID = uuid4()
ROLE_NAMES = ["Super Admin", "Tenant Admin", "Co Admin", "Manager", "Staff"]


@compiles(JSONB, "sqlite")
def _jsonb_as_json_on_sqlite(type_, compiler, **kw):
    return "JSON"


class SQLiteDB:
    def __init__(self, session):
        self.session = session

    async def execute(self, stmt):
        return self.session.execute(stmt)

    async def commit(self):
        self.session.commit()

    async def refresh(self, obj):
        self.session.refresh(obj)


@pytest.fixture
def env():
    # FastAPI serializes the response in a worker thread; share one connection.
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Role.__table__.create(engine)
    User.__table__.create(engine)
    session = Session(engine)
    roles = {}
    for level, name in enumerate(ROLE_NAMES):
        roles[name] = Role(id=uuid4(), name=name, role_level=level)
        session.add(roles[name])
    people = {}
    for name in ROLE_NAMES:
        people[name] = User(id=uuid4(), tenant_id=TENANT_ID, email=f"{name.replace(' ', '').lower()}@x.test",
                            password_hash="x", role_id=roles[name].id, is_active=True, is_verified=True)
        session.add(people[name])
    session.commit()
    yield session, roles, people
    session.close()
    engine.dispose()


def _role_of(session, user):
    session.expire_all()
    return session.execute(
        select(Role.name).join(User, User.role_id == Role.id).where(User.id == user.id)
    ).scalar_one()


async def _change(env, caller_role, target_role, new_role):
    session, roles, people = env
    caller = people[caller_role]
    app = FastAPI()
    app.include_router(users.router)
    app.dependency_overrides[users.get_db] = lambda: SQLiteDB(session)
    app.dependency_overrides[get_current_user] = lambda: {
        "user_id": str(caller.id), "tenant_id": str(TENANT_ID), "role": caller_role}
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as client:
        return await client.put(f"/users/{people[target_role].id}/role", json={"role_id": str(roles[new_role].id)})


@pytest.mark.parametrize("caller", ["Super Admin", "Tenant Admin", "Co Admin"])
async def test_nobody_can_change_their_own_role(env, caller):
    new_role = "Staff" if caller != "Staff" else "Manager"

    resp = await _change(env, caller, caller, new_role)

    assert resp.status_code == 403
    assert resp.json()["detail"] == "You cannot change your own role."
    assert _role_of(env[0], env[2][caller]) == caller


@pytest.mark.parametrize("caller", ["Tenant Admin", "Co Admin"])
@pytest.mark.parametrize("target,new_role", [
    ("Staff", "Super Admin"),
    ("Staff", "Tenant Admin"),
    ("Manager", "Co Admin"),
    ("Tenant Admin", "Staff"),   # demoting an owner
    ("Super Admin", "Staff"),
])
async def test_non_superadmin_limited_to_manager_and_staff(env, caller, target, new_role):
    if caller == target:
        pytest.skip("covered by the self-change test")

    resp = await _change(env, caller, target, new_role)

    assert resp.status_code == 403
    assert "only change users between Manager and Staff" in resp.json()["detail"]
    assert _role_of(env[0], env[2][target]) == target


@pytest.mark.parametrize("caller", ["Tenant Admin", "Co Admin"])
@pytest.mark.parametrize("target,new_role", [("Staff", "Manager"), ("Manager", "Staff")])
async def test_non_superadmin_can_switch_manager_and_staff(env, caller, target, new_role):
    resp = await _change(env, caller, target, new_role)

    assert resp.status_code == 200
    assert _role_of(env[0], env[2][target]) == new_role


async def test_superadmin_may_assign_any_role(env):
    resp = await _change(env, "Super Admin", "Staff", "Tenant Admin")

    assert resp.status_code == 200
    assert _role_of(env[0], env[2]["Staff"]) == "Tenant Admin"
