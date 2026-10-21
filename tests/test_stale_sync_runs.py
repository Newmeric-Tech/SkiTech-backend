"""
create_sync_log closes out the integration's runs stuck in 'syncing' for
more than STALE_SYNC_MINUTES before starting a new one.

The first test uses a recording fake session. The second runs the real SQL
against TEMP tables on a local Postgres (LOCAL_PG_URL) and is skipped
without one; it never touches the .env database.
"""
import os
from types import SimpleNamespace
from uuid import uuid4

import pytest

import app.services.sync_service as sync_service


class RecordingSession:
    def __init__(self):
        self.statements = []
        self.commits = 0

    async def execute(self, stmt, params=None):
        self.statements.append((" ".join(str(stmt).split()), params))
        return SimpleNamespace(scalar=lambda: "new-log")

    async def commit(self):
        self.commits += 1


async def test_create_sync_log_marks_stale_runs_before_inserting():
    db = RecordingSession()

    log_id = await sync_service.create_sync_log(db, "integ-1")

    assert log_id == "new-log"
    (stale_sql, stale_params), (insert_sql, _) = db.statements
    assert stale_sql.startswith("UPDATE sync_logs SET status = 'error'")
    assert "status = 'syncing'" in stale_sql and "finished_at IS NULL" in stale_sql
    assert "INTERVAL '15 minutes'" in stale_sql
    assert stale_params == {"integration_id": "integ-1",
                            "message": "Sync interrupted: no result after 15 minutes"}
    assert insert_sql.startswith("INSERT INTO sync_logs")
    assert db.commits == 1


@pytest.mark.skipif(not os.environ.get("LOCAL_PG_URL"), reason="needs a local Postgres (LOCAL_PG_URL)")
async def test_only_this_integrations_stale_unfinished_runs_are_closed():
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
    from sqlalchemy.pool import StaticPool

    engine = create_async_engine(os.environ["LOCAL_PG_URL"], poolclass=StaticPool)
    mine, other = uuid4(), uuid4()
    rows = {
        "stale": (mine, "20 minutes", "syncing", False),
        "recent": (mine, "5 minutes", "syncing", False),
        "other_integration": (other, "20 minutes", "syncing", False),
        "finished": (mine, "20 minutes", "success", True),
    }
    try:
        async with AsyncSession(engine) as db:
            await db.execute(text(
                "CREATE TEMP TABLE sync_logs (id UUID PRIMARY KEY DEFAULT gen_random_uuid(), "
                "integration_id UUID, started_at TIMESTAMPTZ, finished_at TIMESTAMPTZ, "
                "status VARCHAR(20), records_synced INT, error_message TEXT, name TEXT)"))
            for name, (integ, age, status, finished) in rows.items():
                await db.execute(text(
                    f"INSERT INTO sync_logs (integration_id, started_at, finished_at, status, name) "
                    f"VALUES (:i, NOW() - INTERVAL '{age}', {'NOW()' if finished else 'NULL'}, :s, :n)"),
                    {"i": integ, "s": status, "n": name})
            await db.commit()

            new_id = await sync_service.create_sync_log(db, str(mine))

            result = {r.name: (r.status, r.error_message, r.finished_at is not None)
                      for r in (await db.execute(text("SELECT * FROM sync_logs"))).fetchall()}
            assert result["stale"] == ("error", "Sync interrupted: no result after 15 minutes", True)
            assert result["recent"] == ("syncing", None, False)
            assert result["other_integration"] == ("syncing", None, False)
            assert result["finished"] == ("success", None, True)
            assert result[None] == ("syncing", None, False)  # the new run
            assert new_id
    finally:
        await engine.dispose()
