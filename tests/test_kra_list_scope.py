"""
KRA list routes and /kra/compliance: Staff (any role outside
KRA_MANAGER_ROLES) only ever see their own KRAs, whatever user_id they pass;
Manager/Tenant Admin/Co Admin/Super Admin may filter by a user (UUID) or see
the whole tenant.

Daily list and compliance run the real queries on in-memory SQLite; the
weekly/monthly/quarterly routes are checked with a recording fake service.
Nothing touches the .env database.
"""
from datetime import date
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.api.v1.endpoints import kra
from app.models.kra import DailyKRA

TENANT = uuid4()
ME, COLLEAGUE = uuid4(), uuid4()
DAY = date(2026, 10, 20)


class AsyncSQLite:
    def __init__(self, session):
        self.s = session

    async def execute(self, stmt):
        return self.s.execute(stmt)


@pytest.fixture
def db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    DailyKRA.__table__.create(engine)
    s = Session(engine)
    for user in (ME, COLLEAGUE):
        s.add(DailyKRA(id=uuid4(), tenant_id=TENANT, user_id=user, date=DAY, is_submitted=True))
    s.commit()
    yield AsyncSQLite(s)
    s.close()
    engine.dispose()


def _ctx(role, user_id=ME):
    return {"tenant_id": TENANT, "user_id": user_id, "role": role}


async def _daily(db, role, user_id=None):
    page = await kra.list_daily_kras(skip=0, limit=20, page=None, page_size=None, user_id=user_id,
                                     db=db, user_context=_ctx(role))
    return sorted(str(item.user_id) for item in page.items)


# ── daily list, real query ──────────────────────────────────────────────────

async def test_staff_without_user_id_sees_only_own(db):
    assert await _daily(db, "Staff") == [str(ME)]


async def test_staff_passing_someone_elses_id_still_sees_only_own(db):
    assert await _daily(db, "Staff", user_id=COLLEAGUE) == [str(ME)]


@pytest.mark.parametrize("role", ["Manager", "Tenant Admin", "Co Admin", "Super Admin"])
async def test_manager_sees_all_or_a_filtered_user(db, role):
    assert await _daily(db, role) == sorted([str(ME), str(COLLEAGUE)])
    assert await _daily(db, role, user_id=COLLEAGUE) == [str(COLLEAGUE)]


async def test_user_id_query_parameter_is_a_uuid(db):
    app = FastAPI()
    app.include_router(kra.router)
    app.dependency_overrides[kra.get_db_session] = lambda: db
    app.dependency_overrides[kra.get_current_user_context] = lambda: _ctx("Manager")
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as client:
        resp = await client.get("/kra/daily", params={"user_id": str(COLLEAGUE)})

    assert resp.status_code == 200
    assert [item["user_id"] for item in resp.json()["items"]] == [str(COLLEAGUE)]


# ── weekly / monthly / quarterly lists ──────────────────────────────────────

@pytest.fixture
def seen(monkeypatch):
    calls = []

    def service(period):
        class Service:
            def __init__(self, db):
                pass

        async def list_kras(self, tenant_id, user_id=None, skip=0, limit=20):
            calls.append((period, user_id))
            return [], 0

        setattr(Service, f"list_{period}_kras", list_kras)
        return Service

    for period in ("weekly", "monthly", "quarterly"):
        monkeypatch.setattr(kra, f"{period.capitalize()}KRAService", service(period))
    return calls


@pytest.mark.parametrize("period", ["weekly", "monthly", "quarterly"])
@pytest.mark.parametrize("role,passed,expected", [
    ("Staff", None, ME),
    ("Staff", COLLEAGUE, ME),
    ("Manager", None, None),
    ("Manager", COLLEAGUE, COLLEAGUE),
])
async def test_other_lists_scope_user_the_same_way(seen, period, role, passed, expected):
    route = getattr(kra, f"list_{period}_kras")
    await route(skip=0, limit=20, page=None, page_size=None, user_id=passed, db=None, user_context=_ctx(role))

    assert seen == [(period, expected)]


# ── compliance, real query ──────────────────────────────────────────────────

async def _compliance(db, role, employee_id=None):
    return await kra.get_kra_compliance(start_date=DAY, end_date=DAY, employee_id=employee_id,
                                        property_id=None, db=db, user_context=_ctx(role))


@pytest.mark.parametrize("passed", [None, COLLEAGUE])
async def test_staff_compliance_covers_only_themselves(db, passed):
    result = await _compliance(db, "Staff", passed)

    assert result.employee_id == ME
    assert (result.expected_submissions, result.actual_submissions) == (1, 1)


async def test_manager_compliance_covers_tenant_or_filtered_user(db):
    everyone = await _compliance(db, "Manager")
    one = await _compliance(db, "Manager", COLLEAGUE)

    assert (everyone.employee_id, everyone.expected_submissions) == (None, 2)
    assert (one.employee_id, one.expected_submissions) == (COLLEAGUE, 1)
