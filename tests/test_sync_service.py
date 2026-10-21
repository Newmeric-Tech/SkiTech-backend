"""
_run_single_integration_sync error path.

A failed upsert aborts the Postgres transaction, so the error bookkeeping
must roll back first or its UPDATE fails with InFailedSQLTransactionError.
The fake session below mimics that: after a failed execute it rejects every
statement until rollback() is called.
"""
from datetime import datetime
from types import SimpleNamespace

import app.services.sync_service as sync_service


class AbortingSession:
    def __init__(self):
        self.aborted = False
        self.calls = []

    async def execute(self, stmt, params=None):
        sql = str(stmt)
        if self.aborted:
            raise RuntimeError("current transaction is aborted")
        self.calls.append(sql.split()[0])
        if "INSERT INTO reservations" in sql:
            self.aborted = True
            raise RuntimeError("null value in column currency")
        return SimpleNamespace(scalar=lambda: "log-1")

    async def commit(self):
        if self.aborted:
            raise RuntimeError("current transaction is aborted")

    async def rollback(self):
        self.aborted = False
        self.calls.append("ROLLBACK")


class FailingUpsertAdapter:
    async def fetch_reservations(self, *args):
        return [{
            "external_id": "r1", "status": "confirmed", "guest_name": "g",
            "check_in_date": datetime(2026, 1, 1), "check_out_date": datetime(2026, 1, 2),
            "num_nights": 1, "total_amount": 1.0, "currency": None,
        }]

    async def fetch_availability(self, *args):
        return []


async def test_failed_upsert_rolls_back_before_marking_error(monkeypatch):
    monkeypatch.setattr(sync_service, "get_adapter", lambda name: FailingUpsertAdapter())
    monkeypatch.setattr(sync_service, "decrypt", lambda s: "{}")
    integration = SimpleNamespace(
        id="i1", provider_name="mews", credentials_json="x", tenant_id="t1", property_id="p1",
    )
    db = AbortingSession()

    await sync_service._run_single_integration_sync(db, integration)

    # create_sync_log's stale-run UPDATE and INSERT, failed reservation
    # INSERT, rollback, then the error UPDATE on integrations and the
    # sync_logs UPDATE.
    assert db.calls == ["UPDATE", "INSERT", "INSERT", "ROLLBACK", "UPDATE", "UPDATE"]
