"""
superadmin delete_user / delete_tenant: a failed commit must answer 500 with
a generic detail and log only the sanitized summary. Handlers are called
directly with a fake session; nothing touches a database.
"""
import logging
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.api.v1.endpoints import superadmin
from tests.test_sync_error_redaction import GUEST_DATA, GUEST_EMAIL, _realistic_integrity_error


class CommitFailsSession:
    def __init__(self, row):
        self.row = row
        self.rolled_back = False

    async def execute(self, stmt, params=None):
        return SimpleNamespace(scalar_one_or_none=lambda: self.row)

    async def commit(self):
        raise _realistic_integrity_error({"email": GUEST_EMAIL})

    async def rollback(self):
        self.rolled_back = True


def _assert_clean(caplog, info):
    logs = "\n".join(r.getMessage() + (str(r.exc_info) if r.exc_info else "") for r in caplog.records)
    assert "Database error: NotNullViolationError" in logs
    for value in GUEST_DATA:
        assert value not in logs
        assert value not in str(info.value.detail)


async def test_delete_user_failure_is_generic(caplog):
    db = CommitFailsSession(SimpleNamespace(deleted_at=None, is_active=True))
    with caplog.at_level(logging.ERROR):
        with pytest.raises(HTTPException) as info:
            await superadmin.delete_user(str(uuid4()), db=db, user={"user_id": "someone-else"})
    assert (info.value.status_code, info.value.detail) == (500, "Failed to delete user.")
    assert db.rolled_back
    _assert_clean(caplog, info)


async def test_delete_tenant_failure_is_generic(caplog):
    db = CommitFailsSession(SimpleNamespace(business_name="Acme"))
    with caplog.at_level(logging.ERROR):
        with pytest.raises(HTTPException) as info:
            await superadmin.delete_tenant(str(uuid4()), db=db, user={"user_id": "sa"})
    assert (info.value.status_code, info.value.detail) == (500, "Delete failed.")
    assert db.rolled_back
    _assert_clean(caplog, info)
