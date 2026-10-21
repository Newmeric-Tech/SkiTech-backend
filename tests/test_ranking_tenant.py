"""
Ranking routes use the caller's tenant (from the authenticated user record)
for every query and write. Another tenant's property or employee behaves as
missing: reads come back empty or 404, writes are refused and nothing is
stored. The caller's own tenant keeps working on every route.

Route functions are called directly against an in-memory SQLite database;
nothing touches the .env database.
"""
from datetime import datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, func, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session

from app.api.v1.endpoints import ranking
from app.models.models import Employee, Property
from app.models.ranking_models import (
    EmployeeRanking, EmployeeRankingScore, RankingAuditLog, RankingCriteriaConfig, RankingInsight,
)

MINE, OTHER = uuid4(), uuid4()
START, END = datetime(2026, 10, 1), datetime(2026, 10, 7)


@compiles(JSONB, "sqlite")
def _jsonb_as_json_on_sqlite(type_, compiler, **kw):
    return "JSON"


class AsyncSQLite:
    """Async-shaped wrapper over a sync SQLite session."""

    def __init__(self, session):
        self.s = session

    async def execute(self, stmt):
        return self.s.execute(stmt)

    async def get(self, model, key):
        return self.s.get(model, key)

    def add(self, obj):
        self.s.add(obj)

    async def flush(self):
        self.s.flush()

    async def commit(self):
        self.s.commit()

    async def rollback(self):
        self.s.rollback()


@pytest.fixture
def env():
    engine = create_engine("sqlite://")
    for model in (Property, Employee, RankingCriteriaConfig, EmployeeRankingScore,
                  EmployeeRanking, RankingInsight, RankingAuditLog):
        model.__table__.create(engine)
    s = Session(engine)
    ids = {}
    for tenant, tag in ((MINE, "mine"), (OTHER, "other")):
        prop = Property(id=uuid4(), tenant_id=tenant, name=f"P-{tag}")
        emp = Employee(id=uuid4(), tenant_id=tenant, property_id=prop.id, role_id=uuid4(),
                       first_name=tag, last_name="E", is_active=True)
        s.add_all([prop, emp])
        s.add(RankingCriteriaConfig(id=uuid4(), tenant_id=tenant, property_id=prop.id,
                                    criterion_name="Task Completion", weightage=25.0, max_points=100.0))
        s.add(EmployeeRankingScore(id=uuid4(), tenant_id=tenant, property_id=prop.id, employee_id=emp.id,
                                   criterion_name="Task Completion", weightage=25.0, raw_points=80.0,
                                   final_points=80.0, max_points=100.0, period_start=START, period_end=END))
        s.add(EmployeeRanking(id=uuid4(), tenant_id=tenant, property_id=prop.id, employee_id=emp.id,
                              period_start=START, period_end=END, ranking_type="weekly", overall_score=80.0,
                              rank=1, total_active_employees=1, scores_breakdown={"Task Completion": 80.0},
                              performance_status="consistent"))
        s.add(RankingInsight(id=uuid4(), tenant_id=tenant, property_id=prop.id, employee_id=emp.id,
                             period_start=START, period_end=END, insight_type="top", title="t",
                             description="d"))
        ids[tag] = SimpleNamespace(property=prop.id, employee=emp.id)
    s.commit()
    yield AsyncSQLite(s), s, ids
    s.close()
    engine.dispose()


USER = SimpleNamespace(id=uuid4(), tenant_id=MINE)


def _count(s, model, **where):
    q = select(func.count()).select_from(model)
    for k, v in where.items():
        q = q.where(getattr(model, k) == v)
    return s.execute(q).scalar()


# ── reads ────────────────────────────────────────────────────────────────────

async def test_property_rankings_of_other_tenant_are_empty_own_are_listed(env):
    db, _, ids = env
    other = await ranking.get_property_rankings(property_id=ids["other"].property, tenant_id=MINE,
                                                ranking_type="weekly", skip=0, limit=50,
                                                current_user=USER, session=db)
    mine = await ranking.get_property_rankings(property_id=ids["mine"].property, tenant_id=MINE,
                                               ranking_type="weekly", skip=0, limit=50,
                                               current_user=USER, session=db)
    assert (other.total, other.items) == (0, [])
    assert mine.total == 1 and mine.items[0].employee_id == ids["mine"].employee


async def test_criteria_of_other_tenant_are_empty_own_are_listed(env):
    db, _, ids = env
    other = await ranking.list_ranking_criteria(tenant_id=MINE, property_id=ids["other"].property,
                                                current_user=USER, session=db)
    mine = await ranking.list_ranking_criteria(tenant_id=MINE, property_id=ids["mine"].property,
                                               current_user=USER, session=db)
    assert other == [] and [c.criterion_name for c in mine] == ["Task Completion"]


async def test_scores_of_other_tenant_are_empty_own_are_listed(env):
    db, _, ids = env
    kwargs = dict(tenant_id=MINE, property_id=ids["mine"].property, period_start=None, period_end=None,
                  current_user=USER, session=db)
    other = await ranking.get_employee_scores(employee_id=ids["other"].employee, **kwargs)
    mine = await ranking.get_employee_scores(employee_id=ids["mine"].employee, **kwargs)
    assert other == [] and len(mine) == 1


async def test_employee_ranking_of_other_tenant_is_404_own_works(env):
    db, _, ids = env
    with pytest.raises(HTTPException) as info:
        await ranking.get_employee_ranking(employee_id=ids["other"].employee, tenant_id=MINE,
                                           ranking_type="weekly", current_user=USER, session=db)
    assert info.value.status_code == 404
    mine = await ranking.get_employee_ranking(employee_id=ids["mine"].employee, tenant_id=MINE,
                                              ranking_type="weekly", current_user=USER, session=db)
    assert mine.employee_id == ids["mine"].employee


async def test_performance_portal_of_other_tenant_is_404_own_works(env):
    db, _, ids = env
    with pytest.raises(HTTPException) as info:
        await ranking.get_performance_portal(employee_id=ids["other"].employee, tenant_id=MINE,
                                             current_user=USER, session=db)
    assert info.value.status_code == 404
    mine = await ranking.get_performance_portal(employee_id=ids["mine"].employee, tenant_id=MINE,
                                                current_user=USER, session=db)
    assert mine["employee_id"] == ids["mine"].employee and mine["badges_earned"]


async def test_dashboard_of_other_tenant_is_404_own_works(env):
    db, _, ids = env
    with pytest.raises(HTTPException) as info:
        await ranking.get_dashboard_stats(property_id=ids["other"].property, tenant_id=MINE,
                                          current_user=USER, session=db)
    assert info.value.status_code == 404
    mine = await ranking.get_dashboard_stats(property_id=ids["mine"].property, tenant_id=MINE,
                                             current_user=USER, session=db)
    assert mine["active_staff"] == 1 and len(mine["top_5_employees"]) == 1


async def test_my_ranking_still_works(env):
    db, s, ids = env
    s.get(Employee, ids["mine"].employee).user_id = USER.id
    s.commit()
    mine = await ranking.get_my_ranking(ranking_type="weekly", current_user=USER, session=db)
    assert mine.employee_id == ids["mine"].employee


# ── writes ───────────────────────────────────────────────────────────────────

def _score_request():
    return SimpleNamespace(criterion_name="Task Completion", raw_points=50.0, deductions=0.0,
                           period_start=START, period_end=END, deduction_details=None, notes=None,
                           evidence=None)


@pytest.mark.parametrize("which_property", ["mine", "other"])
async def test_other_tenants_employee_cannot_be_scored(env, which_property):
    db, s, ids = env
    request = _score_request()
    # A period with no seeded score, so only the tenant check can stop the insert.
    request.period_start, request.period_end = datetime(2026, 10, 8), datetime(2026, 10, 14)
    with pytest.raises(HTTPException) as info:
        await ranking.record_employee_score(employee_id=ids["other"].employee, tenant_id=MINE,
                                            property_id=ids[which_property].property,
                                            request=request, current_user=USER, session=db)
    # Same status as a missing employee on this route (NotFound -> 400 today).
    assert info.value.status_code == 400
    assert _count(s, EmployeeRankingScore, employee_id=ids["other"].employee) == 1  # only the seed row


async def test_own_employee_can_be_scored(env):
    db, s, ids = env
    request = _score_request()
    request.period_start, request.period_end = datetime(2026, 10, 8), datetime(2026, 10, 14)  # not the seeded period
    await ranking.record_employee_score(employee_id=ids["mine"].employee, tenant_id=MINE,
                                        property_id=ids["mine"].property, request=request,
                                        current_user=USER, session=db)
    assert _count(s, EmployeeRankingScore, employee_id=ids["mine"].employee) == 2


def _criterion_request(name="Punctuality"):
    return SimpleNamespace(criterion_name=name, weightage=10.0, max_points=100.0, deduction_rules=None,
                           description=None, details=None)


async def test_criterion_cannot_be_created_on_other_tenants_property_own_works(env):
    db, s, ids = env
    with pytest.raises(HTTPException):
        await ranking.create_ranking_criterion(tenant_id=MINE, property_id=ids["other"].property,
                                               request=_criterion_request(), current_user=USER, session=db)
    assert _count(s, RankingCriteriaConfig, property_id=ids["other"].property) == 1
    await ranking.create_ranking_criterion(tenant_id=MINE, property_id=ids["mine"].property,
                                           request=_criterion_request(), current_user=USER, session=db)
    assert _count(s, RankingCriteriaConfig, property_id=ids["mine"].property) == 2


async def test_initialize_refuses_other_tenants_property_own_works(env):
    db, s, ids = env
    with pytest.raises(HTTPException):
        await ranking.initialize_ranking_criteria(tenant_id=MINE, property_id=ids["other"].property,
                                                  current_user=USER, session=db)
    assert _count(s, RankingCriteriaConfig, property_id=ids["other"].property) == 1
    result = await ranking.initialize_ranking_criteria(tenant_id=MINE, property_id=ids["mine"].property,
                                                       current_user=USER, session=db)
    assert result["success"] and result["criteria_count"] > 0


async def test_recalculate_refuses_other_tenants_property_own_works(env, monkeypatch):
    db, s, ids = env
    request = SimpleNamespace(period_start=START, period_end=END, ranking_type="weekly")
    # calculate_employee_ranking inserts rank=0, which the check_rank constraint
    # (rank >= 1) rejects for every tenant (pre-existing, out of scope), so record
    # which employees the recalculation picks instead of running it.
    picked = []

    async def record(self, tenant_id, employee_id, **kwargs):
        picked.append((tenant_id, employee_id))
        raise RuntimeError("not calculated in this test")

    monkeypatch.setattr(ranking.RankingService, "calculate_employee_ranking", record)
    with pytest.raises(HTTPException) as info:
        await ranking.recalculate_rankings(property_id=ids["other"].property, tenant_id=MINE,
                                           request=request, current_user=USER, session=db)
    assert info.value.status_code == 404
    assert _count(s, EmployeeRanking, property_id=ids["other"].property) == 1
    assert picked == []
    await ranking.recalculate_rankings(property_id=ids["mine"].property, tenant_id=MINE,
                                       request=request, current_user=USER, session=db)
    assert picked == [(MINE, ids["mine"].employee)]
