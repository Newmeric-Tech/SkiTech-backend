"""
ranking.py broad `except Exception` handlers: unexpected errors keep their
400 but answer a generic detail and log only the sanitized summary, while
NotFound (including a request tenant_id that isn't the caller's) is a 404
with its own message. Handlers are called directly with fakes; nothing
touches a database.
"""
import logging
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.api.v1.endpoints import ranking
from app.utils.exceptions import NotFound
from tests.test_sync_error_redaction import GUEST_DATA, GUEST_EMAIL, _realistic_integrity_error

GENERIC = "Could not complete the ranking request."
TENANT = uuid4()


class Session:
    def __init__(self):
        self.rollbacks = 0

    async def rollback(self):
        self.rollbacks += 1

    async def commit(self):
        pass


def _service_raising(err):
    class Service:
        def __init__(self, session):
            pass

        async def get_rankings_for_property(self, **kwargs):
            raise err
    return Service


async def _rankings(user_tenant=TENANT):
    return await ranking.get_property_rankings(
        property_id=uuid4(), tenant_id=TENANT, ranking_type="weekly", skip=0, limit=50,
        current_user=SimpleNamespace(tenant_id=user_tenant), session=Session())


async def test_db_error_is_generic_400(monkeypatch, caplog):
    monkeypatch.setattr(ranking, "RankingService", _service_raising(_realistic_integrity_error({"e": GUEST_EMAIL})))
    with caplog.at_level(logging.ERROR, logger="skitech"):
        with pytest.raises(HTTPException) as info:
            await _rankings()
    assert (info.value.status_code, info.value.detail) == (400, GENERIC)
    logs = "\n".join(r.getMessage() for r in caplog.records)
    assert "[RANKING] get_property_rankings failed: Database error: NotNullViolationError" in logs
    for value in GUEST_DATA:
        assert value not in logs


async def test_tenant_mismatch_is_404():
    with pytest.raises(HTTPException) as info:
        await _rankings(user_tenant=uuid4())
    assert (info.value.status_code, info.value.detail) == (404, "Tenant not found")


async def test_service_not_found_is_404_with_its_message(monkeypatch):
    monkeypatch.setattr(ranking, "RankingService", _service_raising(NotFound("Property x")))
    with pytest.raises(HTTPException) as info:
        await _rankings()
    assert (info.value.status_code, info.value.detail) == (404, "Property x not found")


async def test_rollbacks_kept_on_both_paths(monkeypatch):
    class Repo:
        def __init__(self, session):
            pass

        async def create_criteria(self, **kwargs):
            raise _realistic_integrity_error({"e": GUEST_EMAIL})

    class TenantOk:
        def __init__(self, session):
            pass

        async def require_property(self, tenant_id, property_id):
            pass

    monkeypatch.setattr(ranking, "RankingCriteriaRepository", Repo)
    # Let the tenant check pass so the failing create_criteria is what's exercised.
    monkeypatch.setattr(ranking, "RankingService", TenantOk)
    request = SimpleNamespace(criterion_name="c", weightage=1, max_points=1, deduction_rules=None,
                              description=None, details=None)

    denied = Session()
    with pytest.raises(HTTPException) as info:
        await ranking.create_ranking_criterion(tenant_id=TENANT, property_id=uuid4(), request=request,
                                               current_user=SimpleNamespace(tenant_id=uuid4()), session=denied)
    assert (info.value.status_code, info.value.detail, denied.rollbacks) == (404, "Tenant not found", 1)

    failed = Session()
    with pytest.raises(HTTPException) as info:
        await ranking.create_ranking_criterion(tenant_id=TENANT, property_id=uuid4(), request=request,
                                               current_user=SimpleNamespace(tenant_id=TENANT), session=failed)
    assert (info.value.status_code, info.value.detail, failed.rollbacks) == (400, GENERIC, 1)
