"""
/health is public: a failed DB connect must report only the safe summary,
not str(e) (which can name the DB host). The engine is replaced, so nothing
connects to a database.
"""
import app.core.database as database
from app import health_check

SECRET_HOST = "ep-secret-host.example-db.internal"


class BrokenEngine:
    def connect(self):
        raise ConnectionRefusedError(f"could not connect to {SECRET_HOST}:5432")


async def test_health_reports_safe_summary(monkeypatch):
    monkeypatch.setattr(database, "engine", BrokenEngine())
    body = await health_check()
    assert body["status"] == "degraded" and body["db"] == "error"
    assert body["db_error"] == "ConnectionRefusedError"
    assert SECRET_HOST not in str(body)
