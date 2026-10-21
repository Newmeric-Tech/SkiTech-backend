"""
POST /auth/refresh rebuilds the token payload from the database: missing,
deleted, inactive or unverified users get 401, and a role (or tenant,
property, name) changed since login shows up in the new tokens.

Runs the endpoint against an in-memory SQLite database; never touches the
.env database. Tokens are signed/decoded with the app's own helpers.
"""
from datetime import datetime
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import create_engine
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.api.v1.endpoints import auth
from app.core.security import create_access_token, create_refresh_token, decode_token
from app.models.models import Role, User

TENANT_ID, PROPERTY_ID = uuid4(), uuid4()


@compiles(JSONB, "sqlite")
def _jsonb_as_json_on_sqlite(type_, compiler, **kw):
    return "JSON"


class SQLiteDB:
    def __init__(self, session):
        self.session = session

    async def execute(self, stmt):
        return self.session.execute(stmt)


@pytest.fixture
def env():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Role.__table__.create(engine)
    User.__table__.create(engine)
    session = Session(engine)
    roles = {n: Role(id=uuid4(), name=n, role_level=i) for i, n in enumerate(["Tenant Admin", "Manager", "Staff"])}
    session.add_all(roles.values())
    user = User(id=uuid4(), tenant_id=TENANT_ID, property_id=PROPERTY_ID, email="u@x.test", password_hash="x",
                first_name="Ana", last_name="Ruiz", role_id=roles["Staff"].id, is_active=True, is_verified=True)
    session.add(user)
    session.commit()

    app = FastAPI()
    app.include_router(auth.router)
    app.dependency_overrides[auth.get_db] = lambda: SQLiteDB(session)
    client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t")
    yield client, session, roles, user
    session.close()
    engine.dispose()


def _login_refresh_token(user, role="Staff"):
    """A refresh token as login issued it (role at login time)."""
    return create_refresh_token({
        "sub": str(user.id), "user_id": str(user.id), "tenant_id": str(TENANT_ID),
        "property_id": str(PROPERTY_ID), "email": user.email, "role": role,
        "first_name": "Ana", "last_name": "Ruiz",
    })


async def _refresh(client, token):
    async with client:
        return await client.post("/auth/refresh", json={"refresh_token": token})


async def test_role_changed_since_login_shows_in_new_tokens(env):
    client, session, roles, user = env
    token = _login_refresh_token(user, role="Staff")
    user.role_id = roles["Manager"].id
    user.first_name = "Anabel"
    session.commit()

    resp = await _refresh(client, token)

    assert resp.status_code == 200
    access, refresh = decode_token(resp.json()["access_token"]), decode_token(resp.json()["refresh_token"])
    assert access["type"] == "access" and refresh["type"] == "refresh"
    for p in (access, refresh):
        assert p["role"] == "Manager"
        assert p["first_name"] == "Anabel"
        assert (p["user_id"], p["tenant_id"], p["property_id"]) == (str(user.id), str(TENANT_ID), str(PROPERTY_ID))


@pytest.mark.parametrize("change", ["inactive", "unverified", "deleted"])
async def test_inactive_unverified_or_deleted_user_gets_401(env, change):
    client, session, _, user = env
    token = _login_refresh_token(user)
    if change == "inactive":
        user.is_active = False
    elif change == "unverified":
        user.is_verified = False
    else:
        user.deleted_at = datetime.utcnow()
    session.commit()

    resp = await _refresh(client, token)

    assert resp.status_code == 401


async def test_unknown_user_gets_401(env):
    client, _, _, user = env
    ghost = type("U", (), {"id": uuid4(), "email": "ghost@x.test"})()

    resp = await _refresh(client, _login_refresh_token(ghost))

    assert resp.status_code == 401


async def test_access_token_is_not_accepted_as_refresh_token(env):
    client, _, _, user = env

    resp = await _refresh(client, create_access_token({"user_id": str(user.id)}))

    assert resp.status_code == 401
