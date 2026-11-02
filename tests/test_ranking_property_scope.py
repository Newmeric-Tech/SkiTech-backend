"""
Property scope on the ranking routes. Tenant Admin and Super Admin reach every
property of their tenant; a Co Admin with a property and a Manager only that
one (a Manager without one gets 403); Staff only their own employee record and
their own property's ranking list. Out-of-scope properties and employees answer
404, like missing ones.

Route functions are called directly against an in-memory SQLite database;
nothing touches the .env database.
"""
from datetime import datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.api.v1.endpoints import ranking
from app.models.models import Employee, Property
from app.models.ranking_models import (
    EmployeeRanking, EmployeeRankingScore, RankingAuditLog, RankingCriteriaConfig, RankingInsight,
)
from tests.test_ranking_tenant import AsyncSQLite  # also registers JSONB on SQLite

TENANT, OTHER_TENANT = uuid4(), uuid4()
START, END = datetime(2026, 10, 1), datetime(2026, 10, 7)


def caller(role, property_id=None, tenant_id=TENANT, user_id=None):
    return SimpleNamespace(id=user_id or uuid4(), tenant_id=tenant_id, property_id=property_id,
                           role_obj=SimpleNamespace(name=role))


@pytest.fixture
def w():
    engine = create_engine("sqlite://")
    for model in (Property, Employee, RankingCriteriaConfig, EmployeeRankingScore,
                  EmployeeRanking, RankingInsight, RankingAuditLog):
        model.__table__.create(engine)
    s = Session(engine)
    staff_user = uuid4()
    world = SimpleNamespace(db=AsyncSQLite(s), s=s, staff_user=staff_user)
    for tag, tenant in (("a", TENANT), ("b", TENANT), ("x", OTHER_TENANT)):
        prop = Property(id=uuid4(), tenant_id=tenant, name=f"P-{tag}")
        emp = Employee(id=uuid4(), tenant_id=tenant, property_id=prop.id, role_id=uuid4(),
                       first_name=tag, last_name="E", is_active=True,
                       user_id=staff_user if tag == "a" else None)
        s.add_all([prop, emp])
        s.add(RankingCriteriaConfig(id=uuid4(), tenant_id=tenant, property_id=prop.id,
                                    criterion_name="Task Completion", weightage=100.0, max_points=100.0))
        s.add(EmployeeRankingScore(id=uuid4(), tenant_id=tenant, property_id=prop.id, employee_id=emp.id,
                                   criterion_name="Task Completion", weightage=100.0, raw_points=80.0,
                                   final_points=80.0, max_points=100.0, period_start=START, period_end=END))
        s.add(EmployeeRanking(id=uuid4(), tenant_id=tenant, property_id=prop.id, employee_id=emp.id,
                              period_start=START, period_end=END, ranking_type="weekly", overall_score=80.0,
                              rank=1, total_active_employees=1, scores_breakdown={"Task Completion": 80.0},
                              performance_status="consistent"))
        setattr(world, tag, SimpleNamespace(prop=prop.id, emp=emp.id))
    s.commit()
    yield world
    s.close()
    engine.dispose()


# ── every route, by property or employee ────────────────────────────────────

def _calls(w, target):
    """(name, coroutine factory) for each ranking route aimed at `target`."""
    db = w.db
    t = target
    criterion = SimpleNamespace(criterion_name="Punctuality", weightage=10.0, max_points=100.0,
                                deduction_rules=None, description=None, details=None)
    score = SimpleNamespace(criterion_name="Task Completion", raw_points=50.0, deductions=0.0,
                            period_start=datetime(2026, 10, 8), period_end=datetime(2026, 10, 14),
                            deduction_details=None, notes=None, evidence=None)
    recalc = SimpleNamespace(period_start=START, period_end=END, ranking_type="weekly")
    return {
        "rankings": lambda u: ranking.get_property_rankings(
            property_id=t.prop, tenant_id=u.tenant_id, ranking_type="weekly", skip=0, limit=50,
            current_user=u, session=db),
        "dashboard": lambda u: ranking.get_dashboard_stats(
            property_id=t.prop, tenant_id=u.tenant_id, current_user=u, session=db),
        "recalculate": lambda u: ranking.recalculate_rankings(
            property_id=t.prop, tenant_id=u.tenant_id, request=recalc, current_user=u, session=db),
        "criteria": lambda u: ranking.list_ranking_criteria(
            tenant_id=u.tenant_id, property_id=t.prop, current_user=u, session=db),
        "create_criterion": lambda u: ranking.create_ranking_criterion(
            tenant_id=u.tenant_id, property_id=t.prop, request=criterion, current_user=u, session=db),
        "initialize": lambda u: ranking.initialize_ranking_criteria(
            tenant_id=u.tenant_id, property_id=t.prop, current_user=u, session=db),
        "scores": lambda u: ranking.get_employee_scores(
            employee_id=t.emp, tenant_id=u.tenant_id, property_id=t.prop, period_start=None,
            period_end=None, current_user=u, session=db),
        "record_score": lambda u: ranking.record_employee_score(
            employee_id=t.emp, tenant_id=u.tenant_id, property_id=t.prop, request=score,
            current_user=u, session=db),
        "employee_ranking": lambda u: ranking.get_employee_ranking(
            employee_id=t.emp, tenant_id=u.tenant_id, ranking_type="weekly", current_user=u, session=db),
        "portal": lambda u: ranking.get_performance_portal(
            employee_id=t.emp, tenant_id=u.tenant_id, current_user=u, session=db),
    }


ROUTES = ["rankings", "dashboard", "recalculate", "criteria", "create_criterion", "initialize",
          "scores", "record_score", "employee_ranking", "portal"]
STAFF_OWN = {"rankings", "scores", "employee_ranking", "portal"}


async def _status(call, user):
    try:
        await call(user)
        return 200
    except HTTPException as e:
        return e.status_code


@pytest.mark.parametrize("route", ROUTES)
async def test_manager_of_a_gets_404_for_b_and_works_on_a(w, route):
    manager = caller("Manager", property_id=w.a.prop)
    assert await _status(_calls(w, w.b)[route], manager) == 404
    assert await _status(_calls(w, w.a)[route], manager) == 200


@pytest.mark.parametrize("route", ROUTES)
@pytest.mark.parametrize("role", ["Tenant Admin", "Super Admin"])
async def test_admin_works_on_both_properties(w, route, role):
    admin = caller(role)
    assert await _status(_calls(w, w.a)[route], admin) == 200
    assert await _status(_calls(w, w.b)[route], admin) == 200


@pytest.mark.parametrize("route", ROUTES)
async def test_co_admin_with_a_property_is_limited_to_it(w, route):
    co_admin = caller("Co Admin", property_id=w.a.prop)
    assert await _status(_calls(w, w.b)[route], co_admin) == 404
    assert await _status(_calls(w, w.a)[route], co_admin) == 200


@pytest.mark.parametrize("route", ["rankings", "dashboard", "employee_ranking"])
async def test_co_admin_without_a_property_is_tenant_wide(w, route):
    co_admin = caller("Co Admin")
    assert await _status(_calls(w, w.a)[route], co_admin) == 200
    assert await _status(_calls(w, w.b)[route], co_admin) == 200


@pytest.mark.parametrize("route", ROUTES)
async def test_manager_without_a_property_gets_403(w, route):
    assert await _status(_calls(w, w.a)[route], caller("Manager")) == 403


@pytest.mark.parametrize("route", ROUTES)
async def test_another_tenants_property_or_employee_is_404(w, route):
    assert await _status(_calls(w, w.x)[route], caller("Tenant Admin")) == 404
    assert await _status(_calls(w, w.x)[route], caller("Manager", property_id=w.a.prop)) == 404


@pytest.mark.parametrize("route", sorted(set(ROUTES) - STAFF_OWN))
async def test_staff_cannot_reach_property_wide_routes(w, route):
    staff = caller("Staff", property_id=w.a.prop, user_id=w.staff_user)
    assert await _status(_calls(w, w.a)[route], staff) == 403


@pytest.mark.parametrize("route", ["scores", "employee_ranking", "portal"])
async def test_staff_reach_their_own_record_only(w, route):
    staff = caller("Staff", property_id=w.a.prop, user_id=w.staff_user)
    assert await _status(_calls(w, w.a)[route], staff) == 200       # w.a.emp is linked to this user
    assert await _status(_calls(w, w.b)[route], staff) == 403
    other_staff = caller("Staff", property_id=w.a.prop)
    assert await _status(_calls(w, w.a)[route], other_staff) == 403


async def test_staff_read_their_own_propertys_ranking_list_only(w):
    staff = caller("Staff", property_id=w.a.prop, user_id=w.staff_user)
    assert await _status(_calls(w, w.a)["rankings"], staff) == 200
    assert await _status(_calls(w, w.b)["rankings"], staff) == 404


async def test_unknown_or_missing_role_gets_403(w):
    assert await _status(_calls(w, w.a)["rankings"], caller("Guest")) == 403
    no_role = SimpleNamespace(id=uuid4(), tenant_id=TENANT, property_id=None, role_obj=None)
    assert await _status(_calls(w, w.a)["dashboard"], no_role) == 403


async def test_manager_of_a_does_not_write_to_b(w):
    manager = caller("Manager", property_id=w.a.prop)
    before = w.s.query(RankingCriteriaConfig).filter_by(property_id=w.b.prop).count()
    assert await _status(_calls(w, w.b)["create_criterion"], manager) == 404
    assert await _status(_calls(w, w.b)["record_score"], manager) == 404
    assert w.s.query(RankingCriteriaConfig).filter_by(property_id=w.b.prop).count() == before
    assert w.s.query(EmployeeRankingScore).filter_by(employee_id=w.b.emp).count() == 1
