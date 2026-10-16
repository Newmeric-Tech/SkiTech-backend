"""
sop.create_sop: a DB failure keeps its 400 and rollback but answers a generic
detail and logs only the sanitized summary. Called directly with a fake
session; nothing touches a database.
"""
import logging
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.api.v1.endpoints import sop
from tests.test_sync_error_redaction import GUEST_DATA, GUEST_EMAIL, _realistic_integrity_error


class FlushFailsSession:
    def __init__(self):
        self.rollbacks = 0

    def add(self, obj):
        pass

    async def flush(self):
        raise _realistic_integrity_error({"e": GUEST_EMAIL})

    async def rollback(self):
        self.rollbacks += 1


async def test_create_sop_db_error_is_generic_400(caplog):
    data = SimpleNamespace(category_id=uuid4(), title="t", description=None, assigned_employee_id=None,
                           assigned_user_id=None, department_id=None, priority="high", status="pending",
                           due_date=None)
    db = FlushFailsSession()
    with caplog.at_level(logging.ERROR, logger="skitech"):
        with pytest.raises(HTTPException) as info:
            await sop.create_sop(property_id=uuid4(), data=data, db=db, user={"tenant_id": str(uuid4())})

    assert (info.value.status_code, info.value.detail) == (400, "Could not create the SOP.")
    assert db.rollbacks == 1
    logs = "\n".join(r.getMessage() for r in caplog.records)
    assert "[SOP] create_sop failed: Database error: NotNullViolationError" in logs
    for value in GUEST_DATA:
        assert value not in logs
