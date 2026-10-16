"""
complaints.py broad `except Exception` handlers must answer 500 with a
generic detail and log only the sanitized summary. The service dependency is
replaced by one whose every call raises a DB error carrying guest data, so
nothing touches a database.
"""
import logging
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI

from app.api.v1.endpoints import complaints
from tests.test_sync_error_redaction import GUEST_DATA, GUEST_EMAIL, _realistic_integrity_error

CID = uuid4()
GET_ROUTES = [
    "/complaints/",
    f"/complaints/{CID}",
    "/complaints/me/my-complaints",
    "/complaints/me/assigned-to-me",
    f"/complaints/{CID}/comments",
    "/complaints/dashboard/staff",
    "/complaints/statistics/summary",
]


class FailingService:
    user_role = "owner"

    def __getattr__(self, name):
        async def fail(*args, **kwargs):
            raise _realistic_integrity_error({"guest_email": GUEST_EMAIL})
        return fail


@pytest.fixture
def app():
    app = FastAPI()
    app.include_router(complaints.router)
    app.dependency_overrides[complaints.get_complaint_service] = lambda: FailingService()
    return app


@pytest.mark.parametrize("path", GET_ROUTES)
async def test_get_routes_return_generic_500(app, path, caplog):
    with caplog.at_level(logging.ERROR, logger="skitech"):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as client:
            res = await client.get(path)

    assert res.status_code == 500
    assert res.json() == {"detail": "An unexpected error occurred."}
    logs = "\n".join(r.getMessage() for r in caplog.records)
    assert "[COMPLAINTS] " in logs and "Database error: NotNullViolationError" in logs
    for value in GUEST_DATA:
        assert value not in logs
        assert value not in res.text
