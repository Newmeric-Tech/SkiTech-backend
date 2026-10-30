"""
KRA Completion score: credit rules, which periods count, and the stored score.
Real service on in-memory SQLite. Never touches the .env database.
"""
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from app.models.models import Employee
from app.models.kra_tasks import KraOccurrence
from app.models.ranking_models import (
    EmployeeRanking, EmployeeRankingScore, RankingAuditLog, RankingCriteriaConfig, RankingInsight,
)
from app.services.ranking_service import (
    DEFAULT_CRITERIA, KRA_CRITERION, RankingService, kra_credit, score_kra_occurrences,
)
from tests.kra_tasks_harness import (
    SQLiteDB, assignment_row, definition_row, property_row, role_rows, sqlite_db, user_row,
)

TENANT, FOREIGN = uuid4(), uuid4()
START, END = datetime(2026, 10, 19), datetime(2026, 10, 25, 23, 59, 59)
DAY = date(2026, 10, 20)
TODAY = datetime.utcnow().date()


def at(day, hour=12):
    return datetime(day.year, day.month, day.day, hour)


# ── credit rules ────────────────────────────────────────────────────────────

@pytest.mark.parametrize("status,delayed,completed,expected", [
    ("completed", False, at(DAY), (1.0, "on_time")),
    ("completed", False, at(DAY - timedelta(days=3)), (1.0, "on_time")),
    ("completed", True, at(DAY), (0.5, "completed_after_delay")),
    ("completed", True, at(DAY + timedelta(days=9)), (0.5, "completed_after_delay")),
    ("completed", False, at(DAY + timedelta(days=2)), (0.5, "late_without_mark")),
    ("pending", False, None, (0.0, "not_completed")),
    ("delayed", True, None, (0.0, "not_completed")),
])
def test_credit_cases(status, delayed, completed, expected):
    assert kra_credit(status, delayed, completed, DAY) == expected


def test_one_day_allowance_boundary():
    last_ok = datetime(2026, 10, 21, 23, 59, 59)
    first_late = datetime(2026, 10, 22, 0, 0, 0)
    assert kra_credit("completed", False, last_ok, DAY)[0] == 1.0
    assert kra_credit("completed", False, first_late, DAY)[0] == 0.5


def row(status="completed", delayed=False, completed=None, definition=None, assignee=None, start=DAY, end=DAY,
        frequency="daily"):
    return SimpleNamespace(definition_id=definition or uuid4(), assignee_id=assignee or uuid4(), period_start=start,
                           period_end=end, status=status, was_delayed=delayed,
                           completed_at=completed if completed or status != "completed" else at(end),
                           frequency=frequency)


def test_score_is_share_of_credit_with_counts():
    result = score_kra_occurrences([
        row(), row(delayed=True), row(completed=at(DAY + timedelta(days=5))),
        row("pending", frequency="weekly"),
    ])
    assert result["raw_points"] == 50.0
    assert result["evidence"] == {
        "counted": 4, "on_time": 1, "completed_after_delay": 1, "late_without_mark": 1, "not_completed": 1,
        "by_frequency": {"daily": 3, "weekly": 1},
    }


def test_nothing_counted_gives_no_score():
    assert score_kra_occurrences([]) is None


@pytest.mark.parametrize("order", [1, -1])
def test_reassigned_task_counts_once_with_the_best_credit(order):
    definition, assignee = uuid4(), uuid4()
    rows = [row("pending", definition=definition, assignee=assignee),
            row(definition=definition, assignee=assignee)][::order]
    result = score_kra_occurrences(rows)
    assert result["raw_points"] == 100.0 and result["evidence"]["counted"] == 1
    assert result["evidence"]["on_time"] == 1


# ── stored score ────────────────────────────────────────────────────────────

class RankingDB(SQLiteDB):
    async def get(self, model, key):
        return self.session.get(model, key)

    async def delete(self, obj):
        self.session.delete(obj)

    @asynccontextmanager
    async def begin_nested(self):
        with self.session.begin_nested():
            yield


@pytest.fixture
def w():
    base = sqlite_db()
    db = RankingDB(base.session)
    for model in (Employee, RankingCriteriaConfig, EmployeeRankingScore, EmployeeRanking, RankingInsight,
                  RankingAuditLog):
        model.__table__.create(db.session.get_bind())
    roles = role_rows()
    prop = property_row(TENANT)
    other_prop = property_row(TENANT)
    user = user_row(roles["Staff"], TENANT, prop.id)
    db.session.add_all([*roles.values(), prop, other_prop, user])
    db.session.commit()
    employee = Employee(id=uuid4(), tenant_id=TENANT, property_id=prop.id, user_id=user.id, role_id=uuid4(),
                        first_name="Sam", last_name="Staff", is_active=True)
    db.session.add(employee)
    db.session.add_all([
        RankingCriteriaConfig(id=uuid4(), tenant_id=TENANT, property_id=prop.id, criterion_name=c["criterion_name"],
                              weightage=c["weightage"], max_points=c["max_points"])
        for c in DEFAULT_CRITERIA
    ])
    db.session.commit()
    return SimpleNamespace(db=db, prop=prop, other_prop=other_prop, user=user, employee=employee, roles=roles,
                           service=RankingService(db))


def kra_criterion(w):
    return w.db.session.execute(select(RankingCriteriaConfig).where(
        RankingCriteriaConfig.criterion_name == KRA_CRITERION)).scalar_one()


def give(w, *occurrences, frequency="daily", tenant=TENANT, prop=None, user=None):
    """An ended assignment (so nothing else is generated) with these occurrences:
    (period_start, period_end, status, was_delayed, completed_at)."""
    definition = definition_row(tenant, (prop or w.prop).id, frequency)
    assignment = assignment_row(definition, (user or w.user).id, START.date(), is_active=False)
    w.db.session.add_all([definition, assignment])
    for start, end, status, delayed, completed in occurrences:
        w.db.session.add(KraOccurrence(
            id=uuid4(), tenant_id=tenant, property_id=definition.property_id, assignment_id=assignment.id,
            definition_id=definition.id, assignee_id=(user or w.user).id, period_start=start, period_end=end,
            status=status, was_delayed=delayed, completed_at=completed))
    w.db.session.commit()
    return definition, assignment


def done(day):
    return (day, day, "completed", False, at(day))


def missed(day):
    return (day, day, "pending", False, None)


async def store(w, start=START, end=END):
    applicable = await w.service.store_kra_score(TENANT, w.employee, kra_criterion(w), start, end)
    w.db.session.commit()
    return applicable


def stored(w):
    return w.db.session.execute(select(EmployeeRankingScore).where(
        EmployeeRankingScore.criterion_name == KRA_CRITERION)).scalars().all()


async def test_score_row_is_written_for_the_exact_period(w):
    give(w, done(DAY), missed(DAY + timedelta(days=1)))
    assert await store(w) is True
    row_ = stored(w)[0]
    assert (row_.raw_points, row_.final_points, row_.deductions, row_.max_points) == (50.0, 50.0, 0.0, 100.0)
    assert (row_.period_start, row_.period_end) == (START, END)
    assert row_.weightage == 10.0 and row_.employee_id == w.employee.id and row_.tenant_id == TENANT
    assert row_.evidence["counted"] == 2 and row_.notes is None


async def test_evidence_holds_no_personal_text(w):
    definition, assignment = give(w)
    w.db.session.add(KraOccurrence(
        id=uuid4(), tenant_id=TENANT, property_id=w.prop.id, assignment_id=assignment.id,
        definition_id=definition.id, assignee_id=w.user.id, period_start=DAY, period_end=DAY, status="completed",
        was_delayed=True, delay_reason="SECRET-REASON", completed_at=at(DAY), completion_note="SECRET-NOTE"))
    w.db.session.commit()
    await store(w)
    assert "SECRET" not in str(stored(w)[0].evidence) and stored(w)[0].notes is None


async def test_period_ending_on_window_edges_counts_and_outside_does_not(w):
    give(w, done(START.date()), done(END.date()), missed(START.date() - timedelta(days=1)),
         missed(END.date() + timedelta(days=1)))
    await store(w)
    assert stored(w)[0].evidence["counted"] == 2 and stored(w)[0].raw_points == 100.0


async def test_weekly_period_counts_by_its_end_date(w):
    give(w, (date(2026, 10, 12), date(2026, 10, 18), "pending", False, None),   # ends before the window
         (date(2026, 10, 19), date(2026, 10, 25), "completed", False, at(date(2026, 10, 25))),
         (date(2026, 10, 26), date(2026, 11, 1), "pending", False, None),       # ends after the window
         frequency="weekly")
    await store(w)
    assert stored(w)[0].evidence["counted"] == 1 and stored(w)[0].evidence["by_frequency"] == {"weekly": 1}


async def test_running_periods_are_not_counted(w):
    yesterday = TODAY - timedelta(days=1)
    give(w, missed(TODAY), (yesterday, yesterday, "completed", False, at(yesterday)))
    give(w, (TODAY - timedelta(days=2), TODAY + timedelta(days=1), "pending", False, None), frequency="weekly")
    await store(w, datetime(yesterday.year, yesterday.month, yesterday.day),
                at(TODAY + timedelta(days=5)))
    assert stored(w)[0].evidence["counted"] == 1 and stored(w)[0].raw_points == 100.0


async def test_only_running_periods_means_not_applicable(w):
    give(w, missed(TODAY))
    assert await store(w, at(TODAY - timedelta(days=1)), at(TODAY + timedelta(days=1))) is False
    assert stored(w) == []


async def test_missed_tasks_count_though_the_employee_never_opened_the_app(w):
    definition = definition_row(TENANT, w.prop.id)
    w.db.session.add_all([definition, assignment_row(definition, w.user.id, START.date())])
    w.db.session.commit()
    assert w.db.session.execute(select(func.count()).select_from(KraOccurrence)).scalar() == 0

    assert await store(w) is True
    assert stored(w)[0].raw_points == 0.0 and stored(w)[0].evidence["not_completed"] == 7


async def test_generation_stops_at_today_when_the_window_is_in_the_future(w):
    definition = definition_row(TENANT, w.prop.id)
    w.db.session.add_all([definition, assignment_row(definition, w.user.id, TODAY - timedelta(days=1))])
    w.db.session.commit()
    await store(w, at(TODAY - timedelta(days=1)), at(TODAY + timedelta(days=10)))
    latest = w.db.session.execute(select(func.max(KraOccurrence.period_end))).scalar()
    assert latest == TODAY


async def test_no_tasks_is_not_applicable_and_writes_nothing(w):
    assert await store(w) is False
    assert stored(w) == []


async def test_employee_without_user_is_not_applicable(w):
    give(w, done(DAY))
    w.employee.user_id = None
    w.db.session.commit()
    assert await store(w) is False
    assert stored(w) == []


async def test_rerun_replaces_the_row(w):
    definition, assignment = give(w, missed(DAY))
    await store(w)
    first = stored(w)[0]
    assert first.raw_points == 0.0
    occurrence = w.db.session.execute(select(KraOccurrence)).scalar_one()
    occurrence.status, occurrence.completed_at = "completed", at(DAY)
    w.db.session.commit()

    await store(w)
    rows = stored(w)
    assert len(rows) == 1 and rows[0].id == first.id and rows[0].raw_points == 100.0
    assert rows[0].evidence["on_time"] == 1


async def test_earlier_row_is_removed_when_it_stops_applying(w):
    give(w, done(DAY))
    await store(w)
    assert len(stored(w)) == 1
    w.db.session.execute(KraOccurrence.__table__.delete())
    w.db.session.commit()
    assert await store(w) is False
    assert stored(w) == []


async def test_other_tenants_occurrences_are_never_counted(w):
    foreign_prop = property_row(FOREIGN)
    w.db.session.add(foreign_prop)
    w.db.session.commit()
    give(w, missed(DAY), tenant=FOREIGN, prop=foreign_prop)
    assert await store(w) is False
    assert stored(w) == []


async def test_other_propertys_occurrences_are_not_counted(w):
    give(w, missed(DAY), prop=w.other_prop)
    assert await store(w) is False


async def test_ended_and_reassigned_task_counts_once(w):
    definition, first = give(w, missed(DAY))
    second = assignment_row(definition, w.user.id, DAY, is_active=False)
    w.db.session.add(second)
    w.db.session.add(KraOccurrence(
        id=uuid4(), tenant_id=TENANT, property_id=w.prop.id, assignment_id=second.id, definition_id=definition.id,
        assignee_id=w.user.id, period_start=DAY, period_end=DAY, status="completed", completed_at=at(DAY)))
    w.db.session.commit()
    await store(w)
    assert stored(w)[0].evidence["counted"] == 1 and stored(w)[0].raw_points == 100.0
