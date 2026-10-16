"""
auth.py error paths must not log or return the exception text: str() of a DB
error carries the bound parameters (email, names, password hash) and the
Postgres DETAIL line. The handlers are called directly with fake sessions,
so nothing logs in against a real database.
"""
import logging
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError

import app.api.v1.endpoints.auth as auth
from app.schemas.schemas import GoogleAuthRequest, LoginRequest, RegisterRequest
from tests.test_sync_error_redaction import GUEST_EMAIL, _realistic_integrity_error

# EmailStr rejects special-use domains such as .test, so requests use a
# normal-looking address; the DB errors also carry the shared guest email.
USER_EMAIL = "zelda.quux@leakcheck.dev"
PASSWORD = "S3cret-Pass-Leak"
SECRETS = (USER_EMAIL, GUEST_EMAIL, PASSWORD, "zelda.quux")


def _assert_clean(text):
    for value in SECRETS:
        assert value not in text, f"{value!r} leaked: {text}"


def _logs(caplog):
    return "\n".join(r.getMessage() + (str(r.exc_info) if r.exc_info else "") for r in caplog.records)


class Result:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


class RegisterSession:
    """No existing user, role found, commit fails with `commit_error`."""

    def __init__(self, commit_error=None, execute_error=None):
        self.commit_error, self.execute_error = commit_error, execute_error
        self.calls = 0

    async def execute(self, stmt, params=None):
        if self.execute_error:
            raise self.execute_error
        self.calls += 1
        return Result(None if self.calls == 1 else SimpleNamespace(id=uuid4()))

    def add(self, obj):
        pass

    async def commit(self):
        if self.commit_error:
            raise self.commit_error

    async def rollback(self):
        pass


def _register_data():
    return RegisterRequest(email=USER_EMAIL, password=PASSWORD, role="Staff", tenant_id=uuid4())


async def test_register_integrity_error_is_generic(caplog):
    db = RegisterSession(commit_error=_realistic_integrity_error({"email": USER_EMAIL, "password_hash": "x"}))
    with caplog.at_level(logging.ERROR, logger="skitech"):
        with pytest.raises(HTTPException) as info:
            await auth.register(_register_data(), db=db)
    assert (info.value.status_code, info.value.detail) == (400, "Registration failed.")
    logs = _logs(caplog)
    assert "[REGISTER ERROR] commit failed: Database error: NotNullViolationError" in logs
    _assert_clean(logs)
    _assert_clean(info.value.detail)


async def test_register_duplicate_still_reported():
    orig = Exception('duplicate key value violates unique constraint "users_email_key"\n'
                     f"DETAIL:  Key (email)=({USER_EMAIL}) already exists.")
    db = RegisterSession(commit_error=IntegrityError("INSERT INTO users ...", {"email": USER_EMAIL}, orig))
    with pytest.raises(HTTPException) as info:
        await auth.register(_register_data(), db=db)
    assert (info.value.status_code, info.value.detail) == (400, "Email already registered")


async def test_register_unexpected_error_is_generic(caplog):
    db = RegisterSession(execute_error=_realistic_integrity_error({"email_1": USER_EMAIL}))
    with caplog.at_level(logging.ERROR, logger="skitech"):
        with pytest.raises(HTTPException) as info:
            await auth.register(_register_data(), db=db)
    assert (info.value.status_code, info.value.detail) == (500, "Registration failed.")
    logs = _logs(caplog)
    assert "[REGISTER ERROR]: Database error:" in logs
    _assert_clean(logs)


class FailingLoginSession:
    async def execute(self, stmt, params=None):
        raise _realistic_integrity_error({"email_1": USER_EMAIL})


async def test_login_server_error_is_generic(caplog):
    with caplog.at_level(logging.ERROR, logger="skitech"):
        with pytest.raises(HTTPException) as info:
            await auth.login(LoginRequest(email=USER_EMAIL, password=PASSWORD), request=None,
                             db=FailingLoginSession())
    assert (info.value.status_code, info.value.detail) == (500, "Login failed due to a server error.")
    logs = _logs(caplog)
    assert "[LOGIN ERROR]: Database error: NotNullViolationError" in logs
    _assert_clean(logs)


async def test_google_verification_error_logs_no_token_data(caplog, monkeypatch):
    class Response:
        status_code = 200

        def json(self):
            raise ValueError(f"Expecting value: {USER_EMAIL}")

    class Client:
        def __init__(self, *a, **kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def get(self, *a, **kw):
            return Response()

    monkeypatch.setattr(auth.httpx, "AsyncClient", Client)
    with caplog.at_level(logging.ERROR, logger="skitech"):
        with pytest.raises(HTTPException) as info:
            await auth.google_login(GoogleAuthRequest(credential="id-token"), db=None)
    assert (info.value.status_code, info.value.detail) == (401, "Google token verification failed")
    logs = _logs(caplog)
    assert "[GOOGLE LOGIN] Token verification error: ValueError" in logs
    _assert_clean(logs)
