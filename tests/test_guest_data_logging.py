"""
Guest data must not reach the logs through the generic error paths:
the middleware's unhandled-exception logging, the audit middleware, the
Little Hotelier webhook upsert, and SQLAlchemy's own error text
(hide_parameters). Each test raises an error that carries recognisable guest
data, the way a failed DB statement does, and checks the captured logs.
No test touches the .env database.
"""
import logging
import os
from datetime import datetime
from types import SimpleNamespace

import httpx
import pytest
from fastapi import FastAPI, HTTPException

from app.utils.safe_errors import log_safe_exception
from tests.test_sync_error_redaction import (
    GUEST_DATA, GUEST_EMAIL, GUEST_NAME, GUEST_PHONE, _realistic_integrity_error,
)

GUEST_PARAMS = {"guest_name": GUEST_NAME, "guest_email": GUEST_EMAIL, "guest_phone": GUEST_PHONE}


def _assert_clean(text):
    for value in GUEST_DATA:
        assert value not in text, f"guest data {value!r} leaked: {text}"


def _logs(caplog):
    return "\n".join(r.getMessage() + (str(r.exc_info) if r.exc_info else "") for r in caplog.records)


# --- helper -----------------------------------------------------------------

def test_log_safe_exception_keeps_frames_drops_message(caplog):
    def failing_statement():
        raise _realistic_integrity_error(GUEST_PARAMS)

    logger = logging.getLogger("test.safe")
    try:
        failing_statement()
    except Exception as err:
        with caplog.at_level(logging.ERROR, logger="test.safe"):
            log_safe_exception(logger, "Unhandled exception", err)

    record = caplog.records[-1]
    assert record.exc_info is None
    message = record.getMessage()
    assert message.startswith("Unhandled exception: Database error: NotNullViolationError sqlstate=23502")
    assert "in failing_statement" in message          # stack frames are kept
    _assert_clean(message)


# --- middleware ---------------------------------------------------------------

def _app_raising(err):
    from app.middleware.middleware import ErrorHandlerMiddleware, LoggingMiddleware

    app = FastAPI()

    @app.get("/boom")
    async def boom():
        raise err

    # Same order as app/__init__.py: LoggingMiddleware outermost.
    app.add_middleware(ErrorHandlerMiddleware)
    app.add_middleware(LoggingMiddleware)
    return app


async def test_error_handler_logs_no_guest_data(caplog):
    app = _app_raising(_realistic_integrity_error(GUEST_PARAMS))
    with caplog.at_level(logging.INFO, logger="skitech"):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as client:
            res = await client.get("/boom")

    assert res.status_code == 500
    assert res.json() == {"error": "INTERNAL_SERVER_ERROR", "detail": "An unexpected error occurred"}
    logs = _logs(caplog)
    assert "Unhandled exception: Database error: NotNullViolationError" in logs
    _assert_clean(logs)
    _assert_clean(res.text)


async def test_logging_middleware_reraise_path_logs_no_guest_data(caplog):
    from app.middleware.middleware import LoggingMiddleware

    app = FastAPI()

    @app.get("/boom")
    async def boom():
        raise _realistic_integrity_error(GUEST_PARAMS)

    app.add_middleware(LoggingMiddleware)  # no ErrorHandler: exercises middleware.py "Unhandled:" path
    with caplog.at_level(logging.INFO, logger="skitech"):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
                                     base_url="http://t") as client:
            await client.get("/boom")

    logs = _logs(caplog)
    assert "Unhandled: Database error: NotNullViolationError" in logs
    _assert_clean(logs)


async def test_audit_failure_logs_no_user_data(caplog, monkeypatch):
    import app.core.database as database
    from app.middleware.middleware import AuditMiddleware

    class FailingSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        def add(self, obj):
            pass

        async def commit(self):
            raise _realistic_integrity_error({"user_email": GUEST_EMAIL})

    # Never reach the real (.env) database from the audit middleware.
    monkeypatch.setattr(database, "AsyncSessionLocal", FailingSession)

    app = FastAPI()

    @app.post("/api/v1/vendors")
    async def create_vendor():
        return {"ok": True}

    app.add_middleware(AuditMiddleware)
    with caplog.at_level(logging.WARNING, logger="skitech"):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as client:
            res = await client.post("/api/v1/vendors")

    assert res.status_code == 200
    logs = _logs(caplog)
    assert "[AUDIT ERROR] Database error:" in logs
    _assert_clean(logs)


# --- webhook ------------------------------------------------------------------

class WebhookSession:
    """Returns one Little Hotelier integration, fails the reservation upsert."""

    def __init__(self):
        self.rolled_back = False
        self.committed = False

    async def execute(self, stmt, params=None):
        sql = str(stmt)
        if "FROM integrations" in sql:
            integration = SimpleNamespace(id="i1", tenant_id="t1", property_id="p1", credentials_json="enc")
            return SimpleNamespace(fetchall=lambda: [integration])
        if "INSERT INTO reservations" in sql:
            raise _realistic_integrity_error(params)
        return SimpleNamespace()

    async def commit(self):
        self.committed = True

    async def rollback(self):
        self.rolled_back = True


class JsonRequest:
    def __init__(self, body):
        self._body = body

    async def json(self):
        return self._body


async def test_webhook_upsert_failure_logs_no_guest_data(caplog, monkeypatch):
    import app.api.v1.endpoints.webhooks as webhooks

    monkeypatch.setattr(webhooks, "decrypt", lambda s: '{"smx_token": "tok"}')
    body = {"OTA_HotelResNotifRQ": {"HotelReservations": [{
        "UniqueID": {"ID": "lh-1"},
        "ResGuests": [{"Profiles": [{"Profile": {"Customer": {
            "PersonName": {"GivenName": "Zelda", "Surname": "Quux"},
            "Email": GUEST_EMAIL, "Telephone": GUEST_PHONE}}}]}],
        "RoomStays": [{"TimeSpan": {"Start": "2026-01-01", "End": "2026-01-02"}}],
    }]}}
    db = WebhookSession()

    with caplog.at_level(logging.ERROR, logger="skitech"):
        with pytest.raises(HTTPException) as info:
            await webhooks.little_hotelier_webhook(
                request=JsonRequest(body), db=db, x_lh_smx_token="tok", x_smx_token=None, authorization=None)

    assert info.value.status_code == 500
    assert info.value.detail == "Failed to store reservation."
    assert db.rolled_back and not db.committed
    logs = _logs(caplog)
    assert "failed to store reservation for integration i1: Database error: NotNullViolationError" in logs
    _assert_clean(logs)


# --- hide_parameters ----------------------------------------------------------

def test_app_engine_hides_parameters():
    # Importing the module builds the engine; it does not connect.
    from app.core.database import engine
    assert engine.sync_engine.hide_parameters is True


@pytest.mark.skipif(not os.environ.get("LOCAL_PG_URL"), reason="needs a local Postgres (LOCAL_PG_URL)")
async def test_hide_parameters_against_real_postgres():
    """hide_parameters drops the bound-parameter block from str(err); Postgres'
    DETAIL ("Failing row contains") still carries values, which is why the
    log paths use safe_error_summary. Uses a TEMP table only."""
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
    from sqlalchemy.pool import StaticPool

    engine = create_async_engine(os.environ["LOCAL_PG_URL"], poolclass=StaticPool, hide_parameters=True)
    try:
        async with AsyncSession(engine) as db:
            await db.execute(text("CREATE TEMP TABLE g (name text, email text, cur text NOT NULL)"))
            with pytest.raises(Exception) as info:
                await db.execute(text("INSERT INTO g VALUES (:name, :email, :cur)"),
                                 {"name": GUEST_NAME, "email": GUEST_EMAIL, "cur": None})
            await db.rollback()
    finally:
        await engine.dispose()

    raw = str(info.value)
    assert "SQL parameters hidden due to hide_parameters=True" in raw
    assert "'name':" not in raw and "'email':" not in raw
    assert GUEST_EMAIL in raw   # DETAIL line: hide_parameters alone is not enough
