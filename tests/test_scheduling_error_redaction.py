"""
scheduling.py broad `except Exception` handlers must keep their 400 but answer
a generic detail and log only the sanitized summary; handlers that rolled
back still roll back. Service and DB dependencies are fakes, so nothing
touches a database.
"""
import logging
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI

from app.api.v1.endpoints import scheduling
from tests.test_sync_error_redaction import GUEST_DATA, GUEST_EMAIL, _realistic_integrity_error

GENERIC = {"detail": "Could not complete the scheduling request."}
ID = uuid4()


class FailingService:
    def __getattr__(self, name):
        async def fail(*args, **kwargs):
            raise _realistic_integrity_error({"guest_email": GUEST_EMAIL})
        return fail


class FakeDB:
    def __init__(self):
        self.rollbacks = 0

    async def rollback(self):
        self.rollbacks += 1

    async def commit(self):
        pass


@pytest.fixture
def client_db():
    db = FakeDB()
    app = FastAPI()
    app.include_router(scheduling.router)
    app.dependency_overrides[scheduling.get_scheduling_service] = lambda: FailingService()
    app.dependency_overrides[scheduling.get_db] = lambda: db
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t"), db


CASES = [
    # (method, path, rolls back)
    ("PUT", f"/scheduling/schedules/{ID}/publish", True),
    ("POST", f"/scheduling/replacement-requests/{ID}/accept?employee_id={ID}", True),
    ("POST", f"/scheduling/replacement-requests/{ID}/reject?employee_id={ID}", True),
    ("POST", f"/scheduling/replacement-requests/{ID}/assign?replacement_employee_id={ID}", True),
    ("GET", "/scheduling/dashboard/manager", False),
    ("GET", f"/scheduling/dashboard/staff?employee_id={ID}", False),
]


@pytest.mark.parametrize("method,path,rolls_back", CASES)
async def test_db_error_gives_generic_400(client_db, method, path, rolls_back, caplog):
    client, db = client_db
    with caplog.at_level(logging.ERROR, logger="skitech"):
        async with client:
            res = await client.request(method, path)

    assert res.status_code == 400
    assert res.json() == GENERIC
    assert db.rollbacks == (1 if rolls_back else 0)
    logs = "\n".join(r.getMessage() for r in caplog.records)
    assert "[SCHEDULING] " in logs and "Database error: NotNullViolationError" in logs
    for value in GUEST_DATA:
        assert value not in logs and value not in res.text


async def test_malformed_id_keeps_400_with_generic_detail(client_db):
    client, db = client_db
    async with client:
        res = await client.put("/scheduling/schedules/not-a-uuid/publish")
    assert res.status_code == 400
    assert res.json() == GENERIC   # was "badly formed hexadecimal UUID string"
    assert db.rollbacks == 1
