"""
An employee counts for a property's rankings only if their employee record is
at that property and, when linked to a login, that user is active, not deleted
and at the same property. Unlinked employees count as before. Excluded
employees are not calculated, listed or counted, and their stored rows stay in
the database but are not returned.

Runs the service against an in-memory SQLite database; nothing touches the .env
database.
"""
from datetime import datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from app.models.models import Employee, Property, User
from app.models.ranking_models import (
    EmployeeRanking, EmployeeRankingScore, RankingAuditLog, RankingCriteriaConfig, RankingInsight,
)
from app.services.ranking_service import RankingService
from tests.test_ranking_tenant import AsyncSQLite  # also registers JSONB on SQLite

TENANT = uuid4()
START, END = datetime(2026, 10, 1), datetime(2026, 10, 7)


@pytest.fixture
def w():
    engine = create_engine("sqlite://")
    for model in (Property, User, Employee, RankingCriteriaConfig, EmployeeRankingScore,
                  EmployeeRanking, RankingInsight, RankingAuditLog):
        model.__table__.create(engine)
    s = Session(engine)
    a, b = (Property(id=uuid4(), tenant_id=TENANT, name=n) for n in ("A", "B"))
    s.add_all([a, b])

    def user(prop, **fields):
        fields = {"is_active": True, **fields}
        u = User(id=uuid4(), tenant_id=TENANT, property_id=prop.id, email=f"{uuid4().hex}@example.com",
                 password_hash="x", role_id=uuid4(), is_verified=True, **fields)
        s.add(u)
        return u

    users = {
        "member": user(a),                                  # a normal member of A
        "manager_b": user(b),                               # B's manager, with a stray employee record at A
        "inactive": user(a, is_active=False),
        "deleted": user(a, deleted_at=datetime(2026, 9, 1)),
    }
    employees = {}
    for tag, points in (("member", 90.0), ("unlinked", 70.0), ("manager_b", 95.0),
                        ("inactive", 60.0), ("deleted", 50.0)):
        emp = Employee(id=uuid4(), tenant_id=TENANT, property_id=a.id, role_id=uuid4(), first_name=tag,
                       last_name="E", is_active=True, user_id=users[tag].id if tag in users else None)
        s.add(emp)
        s.add(EmployeeRankingScore(id=uuid4(), tenant_id=TENANT, property_id=a.id, employee_id=emp.id,
                                   criterion_name="Task Completion", weightage=100.0, raw_points=points,
                                   final_points=points, max_points=100.0, period_start=START, period_end=END))
        employees[tag] = emp.id
    s.add(RankingCriteriaConfig(id=uuid4(), tenant_id=TENANT, property_id=a.id,
                                criterion_name="Task Completion", weightage=100.0, max_points=100.0))
    s.commit()
    yield SimpleNamespace(db=AsyncSQLite(s), s=s, a=a.id, b=b.id, emp=employees)
    s.close()
    engine.dispose()


COUNTED = {"member", "unlinked"}


def _old_row(w, tag, rank=1, score=99.0):
    """A ranking stored before the rule, e.g. by an earlier recalculation."""
    w.s.add(EmployeeRanking(id=uuid4(), tenant_id=TENANT, property_id=w.a, employee_id=w.emp[tag],
                            period_start=START, period_end=END, ranking_type="weekly", overall_score=score,
                            rank=rank, total_active_employees=5, scores_breakdown={"Task Completion": score},
                            performance_status="promotion_ready"))
    w.s.commit()


async def _recalculate(w):
    return await RankingService(w.db).recalculate_property_rankings(
        tenant_id=TENANT, property_id=w.a, period_start=START, period_end=END, ranking_type="weekly")


async def test_only_counted_employees_are_calculated(w):
    result = await _recalculate(w)

    assert (result["total_calculated"], result["failed"]) == (2, 0)
    w.s.expire_all()
    rows = w.s.execute(select(EmployeeRanking)).scalars().all()
    assert {r.employee_id for r in rows} == {w.emp[t] for t in COUNTED}
    assert {r.rank for r in rows} == {1, 2}
    assert {r.total_active_employees for r in rows} == {2}


async def test_list_shows_counted_employees_and_hides_stored_rows_of_others(w):
    _old_row(w, "manager_b")
    await _recalculate(w)

    items, total = await RankingService(w.db).get_rankings_for_property(TENANT, w.a, "weekly")

    assert total == 2
    assert {i.employee_id for i in items} == {w.emp[t] for t in COUNTED}
    # Hidden, not deleted
    assert w.s.execute(select(func.count()).select_from(EmployeeRanking).where(
        EmployeeRanking.employee_id == w.emp["manager_b"])).scalar() == 1


@pytest.mark.parametrize("excluded", ["manager_b", "inactive", "deleted"])
async def test_stored_row_of_an_excluded_employee_is_not_returned(w, excluded):
    _old_row(w, excluded)
    _old_row(w, "member", rank=2, score=90.0)

    items, total = await RankingService(w.db).get_rankings_for_property(TENANT, w.a, "weekly")

    assert total == 1 and [i.employee_id for i in items] == [w.emp["member"]]


async def test_dashboard_counts_only_counted_employees(w):
    _old_row(w, "manager_b")
    await _recalculate(w)

    stats = await RankingService(w.db).get_dashboard_stats(TENANT, w.a)

    assert stats["active_staff"] == 2
    assert {e.employee_id for e in stats["top_5_employees"]} == {w.emp[t] for t in COUNTED}
    assert sum(stats["performance_distribution"].values()) == 2


async def test_unlinked_employee_still_counts_by_record_property(w):
    await _recalculate(w)
    items, _ = await RankingService(w.db).get_rankings_for_property(TENANT, w.a, "weekly")
    assert w.emp["unlinked"] in {i.employee_id for i in items}


async def test_member_who_moved_to_another_property_stops_counting(w):
    w.s.get(User, w.s.get(Employee, w.emp["member"]).user_id).property_id = w.b
    w.s.commit()

    result = await _recalculate(w)

    assert result["total_calculated"] == 1
    items, _ = await RankingService(w.db).get_rankings_for_property(TENANT, w.a, "weekly")
    assert [i.employee_id for i in items] == [w.emp["unlinked"]]
