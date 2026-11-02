"""
Forgot/reset password match the email ignoring case (deleted users and
emails that match two accounts get nothing), answer forgot-password the same
way whether or not the account exists, and refuse a wrong or expired code.
POST /users/me/change-password answers 400, not 500, when the stored hash
is empty or unrecognised.

Runs the endpoints against an in-memory SQLite database with send_otp
replaced; never touches the .env database and sends no email.
"""
from datetime import datetime, timedelta
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import create_engine
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.api.dependencies import get_current_user
from app.api.v1.endpoints import auth, users
from app.core.security import hash_password, verify_password
from app.models.models import Role, User

TENANT_ID = uuid4()
NEW_PASSWORD = "NewSecret123"


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


@pytest.fixture
def env(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Role.__table__.create(engine)
    User.__table__.create(engine)
    session = Session(engine)
    role = Role(id=uuid4(), name="Staff", role_level=4)
    session.add(role)
    session.commit()

    sent = []
    monkeypatch.setattr(auth, "send_otp", lambda email, otp, purpose: sent.append((email, otp, purpose)) or True)

    def add_user(email, password_hash=None, **fields):
        user = User(id=uuid4(), tenant_id=TENANT_ID, email=email, role_id=role.id, is_active=True,
                    is_verified=True, password_hash=hash_password("OldSecret123") if password_hash is None
                    else password_hash, **fields)
        session.add(user)
        session.commit()
        return user

    app = FastAPI()
    app.include_router(auth.router)
    app.include_router(users.router)
    app.dependency_overrides[auth.get_db] = lambda: SQLiteDB(session)
    app.dependency_overrides[users.get_db] = lambda: SQLiteDB(session)
    client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t")
    yield client, app, session, add_user, sent
    session.close()
    engine.dispose()


async def _post(client, path, body):
    async with client:
        return await client.post(path, json=body)


async def test_mixed_case_stored_email_gets_a_code_and_can_reset(env):
    client, _, session, add_user, sent = env
    user = add_user("Ana.Ruiz@Example.COM")

    async with client:
        forgot = await client.post("/auth/forgot-password", json={"email": "ana.ruiz@example.com"})
        assert forgot.status_code == 200
        assert len(sent) == 1
        email, otp, purpose = sent[0]
        assert (email, purpose) == ("Ana.Ruiz@Example.COM", "password_reset")

        reset = await client.post("/auth/reset-password",
                                  json={"email": "ANA.RUIZ@example.com", "otp": otp, "new_password": NEW_PASSWORD})

    assert reset.status_code == 200
    session.refresh(user)
    assert verify_password(NEW_PASSWORD, user.password_hash)
    assert user.otp_code is None and user.otp_expires_at is None


async def test_deleted_user_gets_no_code_and_cannot_reset(env):
    client, _, session, add_user, sent = env
    user = add_user("gone@example.com", deleted_at=datetime.utcnow(), otp_code="123456",
                    otp_expires_at=datetime.utcnow() + timedelta(minutes=5))

    async with client:
        forgot = await client.post("/auth/forgot-password", json={"email": "GONE@example.com"})
        reset = await client.post("/auth/reset-password",
                                  json={"email": "gone@example.com", "otp": "123456", "new_password": NEW_PASSWORD})

    assert forgot.status_code == 200 and sent == []
    assert reset.status_code == 404
    session.refresh(user)
    assert not verify_password(NEW_PASSWORD, user.password_hash)


async def test_forgot_password_answers_the_same_whether_or_not_the_user_exists(env):
    client, _, _, add_user, sent = env
    add_user("real@example.com")

    async with client:
        known = await client.post("/auth/forgot-password", json={"email": "real@example.com"})
        unknown = await client.post("/auth/forgot-password", json={"email": "nobody@example.com"})

    assert known.status_code == unknown.status_code == 200
    assert known.json() == unknown.json()
    assert known.content == unknown.content
    assert [e for e, _, _ in sent] == ["real@example.com"]


async def test_email_matching_two_accounts_by_case_gets_nothing(env):
    client, _, session, add_user, sent = env
    first = add_user("dup@example.com", otp_code="123456", otp_expires_at=datetime.utcnow() + timedelta(minutes=5))
    add_user("DUP@example.com")

    async with client:
        forgot = await client.post("/auth/forgot-password", json={"email": "dup@example.com"})
        unknown = await client.post("/auth/forgot-password", json={"email": "nobody@example.com"})
        reset = await client.post("/auth/reset-password",
                                  json={"email": "dup@example.com", "otp": "123456", "new_password": NEW_PASSWORD})

    assert forgot.content == unknown.content and sent == []
    assert reset.status_code == 404
    session.refresh(first)
    assert not verify_password(NEW_PASSWORD, first.password_hash)


@pytest.mark.parametrize("otp, expires_in", [("000000", timedelta(minutes=5)), ("123456", timedelta(seconds=-1))])
async def test_wrong_or_expired_code_answers_400(env, otp, expires_in):
    client, _, session, add_user, _ = env
    user = add_user("u@example.com", otp_code="123456", otp_expires_at=datetime.utcnow() + expires_in)

    resp = await _post(client, "/auth/reset-password",
                       {"email": "u@example.com", "otp": otp, "new_password": NEW_PASSWORD})

    assert resp.status_code == 400
    assert resp.json()["detail"] == "Invalid or expired OTP"
    session.refresh(user)
    assert not verify_password(NEW_PASSWORD, user.password_hash)


async def _change_password(env, stored_hash, current_password="OldSecret123"):
    client, app, session, add_user, _ = env
    user = add_user("me@example.com", password_hash=stored_hash)
    app.dependency_overrides[get_current_user] = lambda: {
        "user_id": str(user.id), "tenant_id": str(TENANT_ID), "role": "Staff"}
    resp = await _post(client, "/users/me/change-password",
                       {"current_password": current_password, "new_password": NEW_PASSWORD})
    session.refresh(user)
    return resp, user


@pytest.mark.parametrize("stored_hash", ["", "not-a-bcrypt-hash"])
async def test_change_password_without_a_usable_stored_hash_answers_400(env, stored_hash):
    resp, user = await _change_password(env, stored_hash)

    assert resp.status_code == 400
    assert resp.json()["detail"] == "This account has no password set. Use Forgot password to set one."
    assert user.password_hash == stored_hash


async def test_change_password_still_checks_the_current_password(env):
    wrong, _ = await _change_password(env, hash_password("OldSecret123"), current_password="Wrong12345")

    assert wrong.status_code == 400
    assert wrong.json()["detail"] == "Current password is incorrect"


async def test_change_password_with_the_right_current_password_succeeds(env):
    resp, user = await _change_password(env, hash_password("OldSecret123"))

    assert resp.status_code == 200
    assert verify_password(NEW_PASSWORD, user.password_hash)
