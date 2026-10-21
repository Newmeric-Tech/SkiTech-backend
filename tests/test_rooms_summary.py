"""
Room-sync result stored on sync_logs.rooms_summary.

Fake sessions only; nothing touches a real database. The fake mimics
Postgres savepoints: a failed statement aborts the transaction until the
savepoint (begin_nested) or the whole transaction is rolled back.
"""
import json
import logging
from contextlib import asynccontextmanager
from datetime import datetime
from types import SimpleNamespace

import app.services.sync_service as sync_service

GUEST_NAME = "Zelda Quinlan-Harrow"
INTEGRATION = SimpleNamespace(
    id="i1", provider_name="mews", credentials_json="x", tenant_id="t1", property_id="p1",
)
EXISTING = [
    # Two rows share "101", so a fetched "101" is a conflict.
    {"id": "a", "room_number": "101", "deleted_at": None, "integration_id": None,
     "external_id": None, "owner_active": False},
    {"id": "b", "room_number": " 101", "deleted_at": None, "integration_id": None,
     "external_id": None, "owner_active": False},
]
FETCHED = [
    {"external_id": "e1", "room_number": "101", "room_type": "Double"},
    {"external_id": "e2", "room_number": "102", "room_type": "Double"},
]


class FakeSession:
    def __init__(self, missing_column=False):
        self.missing_column = missing_column
        self.aborted = False
        self.statements = []   # (sql, params) of every statement that succeeded
        self.committed = []    # statements committed so far
        self.pending = []

    async def execute(self, stmt, params=None):
        sql = " ".join(str(stmt).split())
        if self.aborted:
            raise RuntimeError("current transaction is aborted")
        if self.missing_column and "rooms_summary" in sql:
            self.aborted = True
            raise RuntimeError('column "rooms_summary" of relation "sync_logs" does not exist')
        self.statements.append((sql, params))
        self.pending.append((sql, params))
        if sql.startswith("SELECT r.id"):
            return SimpleNamespace(mappings=lambda: SimpleNamespace(all=lambda: EXISTING))
        return SimpleNamespace(scalar=lambda: "log-1")

    @asynccontextmanager
    async def begin_nested(self):
        mark = len(self.pending)
        try:
            yield
        except BaseException:
            self.aborted = False
            del self.pending[mark:]
            raise

    async def commit(self):
        if self.aborted:
            raise RuntimeError("current transaction is aborted")
        self.committed += self.pending
        self.pending = []

    async def rollback(self):
        self.aborted = False
        self.pending = []


class RoomSyncAdapter:
    supports_room_sync = True

    async def fetch_rooms(self, credentials):
        return FETCHED

    async def fetch_reservations(self, *args):
        return [{
            "external_id": "r1", "status": "confirmed", "guest_name": GUEST_NAME,
            "check_in_date": datetime(2026, 1, 1), "check_out_date": datetime(2026, 1, 2),
            "num_nights": 1, "total_amount": 1.0, "currency": "EUR",
        }]

    async def fetch_availability(self, *args):
        return []


EXPECTED_SUMMARY = {
    "insert": 1, "adopt": 0, "update": 0, "conflict": 1,
    "conflicts": [{"room_number": "101", "reason": "2 existing rooms match this number"}],
}


def _patch(monkeypatch):
    monkeypatch.setattr(sync_service, "get_adapter", lambda name: RoomSyncAdapter())
    monkeypatch.setattr(sync_service, "decrypt", lambda s: "{}")


def _summary_writes(statements):
    return [p for sql, p in statements if sql.startswith("UPDATE sync_logs SET rooms_summary")]


async def test_sync_rooms_returns_counts_and_conflicts_with_room_numbers():
    summary = await sync_service.sync_rooms(FakeSession(), INTEGRATION, FETCHED)

    assert summary == EXPECTED_SUMMARY


async def test_sync_run_stores_rooms_summary_on_its_log(monkeypatch):
    _patch(monkeypatch)
    db = FakeSession()

    await sync_service._run_single_integration_sync(db, INTEGRATION)

    writes = _summary_writes(db.committed)
    assert len(writes) == 1
    assert writes[0]["id"] == "log-1"
    assert json.loads(writes[0]["summary"]) == EXPECTED_SUMMARY
    assert GUEST_NAME not in writes[0]["summary"]


async def test_failed_room_fetch_stores_safe_error(monkeypatch):
    _patch(monkeypatch)

    async def boom(credentials):
        raise ValueError(f"bad payload for {GUEST_NAME}")

    monkeypatch.setattr(RoomSyncAdapter, "fetch_rooms", lambda self, c: boom(c))
    db = FakeSession()

    await sync_service._run_single_integration_sync(db, INTEGRATION)

    writes = _summary_writes(db.committed)
    assert [json.loads(w["summary"]) for w in writes] == [{"error": "ValueError"}]


async def test_missing_column_does_not_break_the_sync(monkeypatch, caplog):
    _patch(monkeypatch)
    db = FakeSession(missing_column=True)

    with caplog.at_level(logging.WARNING, logger="app.services.sync_service"):
        await sync_service._run_single_integration_sync(db, INTEGRATION)

    finished = [p for sql, p in db.committed if sql.startswith("UPDATE sync_logs SET finished_at")]
    assert finished and finished[-1]["status"] == "success"
    assert any(sql.startswith("INSERT INTO reservations") for sql, _ in db.committed)
    assert "could not store rooms_summary" in caplog.text
