"""
A failed reservation upsert must not leak guest data.

str() of a SQLAlchemy error includes the bound parameters and Postgres'
"Failing row contains (...)" DETAIL, so writing it to
integrations.error_message / sync_logs.error_message or stdout exposed guest
names, emails and phones. These tests force that failure with recognisable
guest data and check neither stored message (nor the printed output) has it.
"""
import os
from datetime import datetime
from types import SimpleNamespace

import asyncpg
import httpx
import pytest
from sqlalchemy.exc import IntegrityError

import app.services.sync_service as sync_service
from app.utils.safe_errors import safe_error_summary

GUEST_NAME = "Zelda Quux"
GUEST_EMAIL = "zelda.quux@leak.test"
GUEST_PHONE = "+99 555 0100"
GUEST_DATA = (GUEST_NAME, "Zelda", "Quux", GUEST_EMAIL, GUEST_PHONE)

RESERVATION = {
    "external_id": "r1", "status": "confirmed",
    "guest_name": GUEST_NAME, "guest_email": GUEST_EMAIL, "guest_phone": GUEST_PHONE,
    "check_in_date": datetime(2026, 1, 1), "check_out_date": datetime(2026, 1, 2),
    "num_nights": 1, "total_amount": 1.0,
    "currency": None,  # violates NOT NULL
}


class GuestDataAdapter:
    async def fetch_reservations(self, *args):
        return [dict(RESERVATION)]

    async def fetch_availability(self, *args):
        return []


def _realistic_integrity_error(params) -> IntegrityError:
    """Same layering as the asyncpg dialect: SQLAlchemy IntegrityError ->
    dialect error whose __cause__ is the asyncpg exception."""
    pg = asyncpg.exceptions.NotNullViolationError.new({
        "M": 'null value in column "currency" of relation "reservations" violates not-null constraint',
        "C": "23502", "t": "reservations", "c": "currency",
        "D": f"Failing row contains ({GUEST_NAME}, {GUEST_EMAIL}, {GUEST_PHONE}, null).",
    })

    class AdaptedIntegrityError(Exception):
        pass

    orig = AdaptedIntegrityError(f"<class '{type(pg).__module__}.{type(pg).__name__}'>: {pg.args[0]}\nDETAIL:  {pg.detail}")
    orig.__cause__ = pg
    orig.sqlstate = pg.sqlstate
    return IntegrityError("INSERT INTO reservations (...) VALUES (...)", params, orig)


class RecordingSession:
    """Raises a realistic IntegrityError on the reservations upsert and
    records the error_message parameters of every later statement."""

    def __init__(self):
        self.stored_messages = []

    async def execute(self, stmt, params=None):
        sql = str(stmt)
        params = params or {}
        if "INSERT INTO reservations" in sql:
            raise _realistic_integrity_error(params)
        if "error_message" in params:
            self.stored_messages.append(params["error_message"])
        return SimpleNamespace(scalar=lambda: "log-1")

    async def commit(self):
        pass

    async def rollback(self):
        pass


def _assert_no_guest_data(text: str):
    for value in GUEST_DATA:
        assert value not in text, f"guest data {value!r} leaked: {text!r}"


async def test_failed_upsert_stores_and_prints_no_guest_data(monkeypatch, capsys):
    monkeypatch.setattr(sync_service, "get_adapter", lambda name: GuestDataAdapter())
    monkeypatch.setattr(sync_service, "decrypt", lambda s: "{}")
    integration = SimpleNamespace(id="i1", provider_name="mews", credentials_json="x",
                                  tenant_id="t1", property_id="p1")

    # Precondition: the raw error really does carry the guest data.
    raw = str(_realistic_integrity_error(RESERVATION))
    assert GUEST_NAME in raw and GUEST_EMAIL in raw

    db = RecordingSession()
    await sync_service._run_single_integration_sync(db, integration)

    # integrations.error_message and sync_logs.error_message
    assert len(db.stored_messages) == 2
    for message in db.stored_messages:
        _assert_no_guest_data(message)
        assert message == (
            "Database error: NotNullViolationError sqlstate=23502 "
            "table=reservations column=currency"
        )
    _assert_no_guest_data(capsys.readouterr().out)


def test_summary_keeps_our_provider_messages_and_drops_other_text():
    assert safe_error_summary(Exception("Mews /x failed: 401 Unauthorized")) == \
        "Exception: Mews /x failed: 401 Unauthorized"
    assert safe_error_summary(httpx.ConnectError("connection refused")) == \
        "ConnectError: connection refused"
    # Built-in errors can echo provider values, so only the class survives.
    assert safe_error_summary(ValueError(f"invalid literal: '{GUEST_NAME}'")) == "ValueError"
    assert safe_error_summary(KeyError(GUEST_EMAIL)) == "KeyError"


@pytest.mark.skipif(not os.environ.get("LOCAL_PG_URL"), reason="needs a local Postgres (LOCAL_PG_URL)")
async def test_real_postgres_failures_carry_no_guest_data():
    """The same check against real asyncpg errors. Uses TEMP tables only."""
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
    from sqlalchemy.pool import StaticPool

    engine = create_async_engine(os.environ["LOCAL_PG_URL"], poolclass=StaticPool)
    base = {"k": "a", "name": GUEST_NAME, "email": GUEST_EMAIL, "phone": GUEST_PHONE,
            "room": "1", "n": 1, "d": datetime(2026, 1, 1), "cur": "EUR"}
    cases = [
        {**base, "cur": None},                 # not-null violation
        {**base, "k": "dup"},                  # unique violation
        {**base, "room": GUEST_NAME},          # value too long
        {**base, "d": GUEST_NAME},             # bad argument type
    ]
    try:
        async with AsyncSession(engine) as db:
            await db.execute(text(
                "CREATE TEMP TABLE r (k text UNIQUE, name text, email text, phone text, "
                "room varchar(5), n int, d timestamp, cur text NOT NULL)"))
            await db.execute(text("INSERT INTO r VALUES ('dup','x','x','x','1',1,NULL,'EUR')"))
            await db.commit()
            for params in cases:
                with pytest.raises(Exception) as info:
                    await db.execute(text(
                        "INSERT INTO r VALUES (:k,:name,:email,:phone,:room,:n,:d,:cur)"), params)
                await db.rollback()
                assert GUEST_NAME in str(info.value) or GUEST_EMAIL in str(info.value)
                summary = safe_error_summary(info.value)
                assert summary.startswith("Database error: ")
                _assert_no_guest_data(summary)
    finally:
        await engine.dispose()
