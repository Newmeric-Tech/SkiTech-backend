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


# ── ranking calculation ─────────────────────────────────────────────────────

def manual_score(w, name, points=100.0, employee=None):
    w.db.session.add(EmployeeRankingScore(
        id=uuid4(), tenant_id=TENANT, property_id=w.prop.id, employee_id=(employee or w.employee).id,
        criterion_name=name, weightage=1.0, raw_points=points, final_points=points, max_points=100.0,
        period_start=START, period_end=END))
    w.db.session.commit()


OTHERS = [c["criterion_name"] for c in DEFAULT_CRITERIA if c["criterion_name"] != KRA_CRITERION]


async def calculate(w, employee=None):
    ranking = await w.service.calculate_employee_ranking(TENANT, (employee or w.employee).id, w.prop.id, START, END)
    w.db.session.commit()
    return ranking


async def test_no_tasks_scales_the_other_weights_to_100(w):
    for name in OTHERS:
        manual_score(w, name)
    ranking = await calculate(w)
    assert ranking.overall_score == pytest.approx(100)
    assert KRA_CRITERION not in ranking.scores_breakdown
    assert stored(w) == []


async def test_employee_without_user_scales_too(w):
    for name in OTHERS:
        manual_score(w, name)
    w.employee.user_id = None
    w.db.session.commit()
    ranking = await calculate(w)
    assert ranking.overall_score == pytest.approx(100) and KRA_CRITERION not in ranking.scores_breakdown


async def test_kra_score_feeds_the_overall_at_its_weight(w):
    for name in OTHERS:
        manual_score(w, name)
    give(w, done(DAY), missed(DAY + timedelta(days=1)))
    ranking = await calculate(w)
    assert ranking.scores_breakdown[KRA_CRITERION] == 50.0
    assert ranking.overall_score == pytest.approx(95)   # 90 + 50% of 10


async def test_missing_manual_score_still_counts_as_zero(w):
    manual_score(w, "Task Completion")
    give(w, done(DAY))
    ranking = await calculate(w)
    assert ranking.scores_breakdown["Attendance & Functionality"] == 0.0
    assert ranking.overall_score == pytest.approx(25)   # Task Completion 15 + KRA 10


async def test_missing_manual_score_counts_as_zero_when_kra_does_not_apply(w):
    manual_score(w, "Task Completion")
    ranking = await calculate(w)
    assert ranking.scores_breakdown["Attendance & Functionality"] == 0.0
    assert ranking.overall_score == pytest.approx(15 / 90 * 100)


async def test_other_criteria_keep_their_manual_scores(w):
    manual_score(w, "Attendance & Functionality", 80.0)
    give(w, done(DAY))
    ranking = await calculate(w)
    assert ranking.scores_breakdown["Attendance & Functionality"] == 80.0
    rows = w.db.session.execute(select(EmployeeRankingScore).where(
        EmployeeRankingScore.criterion_name == "Attendance & Functionality")).scalars().all()
    assert len(rows) == 1 and rows[0].raw_points == 80.0


async def test_property_without_the_kra_criterion_is_unaffected(w):
    w.db.session.delete(kra_criterion(w))
    w.db.session.commit()
    for name in OTHERS:
        manual_score(w, name)
    give(w, missed(DAY))
    ranking = await calculate(w)
    assert ranking.overall_score == pytest.approx(100) and stored(w) == []


async def test_overall_is_clamped_to_100(w):
    for criterion in w.db.session.execute(select(RankingCriteriaConfig)).scalars():
        criterion.max_points = 50.0
    w.db.session.commit()
    for name in OTHERS:
        manual_score(w, name)
    ranking = await calculate(w)
    assert ranking.overall_score == 100


async def test_rerunning_a_period_updates_one_ranking_and_one_score(w):
    for name in OTHERS:
        manual_score(w, name)
    give(w, missed(DAY))
    first = await calculate(w)
    assert first.scores_breakdown[KRA_CRITERION] == 0.0 and first.overall_score == pytest.approx(90)

    occurrence = w.db.session.execute(select(KraOccurrence)).scalar_one()
    occurrence.status, occurrence.completed_at = "completed", at(DAY)
    w.db.session.commit()
    second = await calculate(w)

    assert second.id == first.id and second.overall_score == pytest.approx(100)
    assert second.scores_breakdown[KRA_CRITERION] == 100.0
    assert second.recalculated_at is not None
    assert second.previous_overall_score is None and second.score_change is None   # not compared with itself
    assert len(stored(w)) == 1
    assert w.db.session.execute(select(func.count()).select_from(EmployeeRanking)).scalar() == 1


async def test_detail_and_portal_leave_out_kra_when_not_applicable(w):
    for name in OTHERS:
        manual_score(w, name)
    await calculate(w)
    detail = await w.service.get_employee_ranking_detail(TENANT, w.employee.id)
    assert KRA_CRITERION not in [s.criterion_name for s in detail.scores_breakdown]
    assert len(detail.scores_breakdown) == len(OTHERS)
    portal = await w.service.get_performance_portal(TENANT, w.employee.id)
    assert KRA_CRITERION not in portal.score_breakdown
    assert portal.current_overall_score == pytest.approx(100)
    items, _ = await w.service.get_rankings_for_property(TENANT, w.prop.id)
    assert items[0].overall_score == pytest.approx(100)


async def test_detail_and_portal_show_kra_when_applicable(w):
    give(w, done(DAY))
    await calculate(w)
    detail = await w.service.get_employee_ranking_detail(TENANT, w.employee.id)
    row_ = next(s for s in detail.scores_breakdown if s.criterion_name == KRA_CRITERION)
    assert (row_.score, row_.weightage, row_.weighted_score) == (100.0, 10.0, 10.0)
    portal = await w.service.get_performance_portal(TENANT, w.employee.id)
    assert portal.score_breakdown[KRA_CRITERION] == 100.0


async def test_recalculation_logs_a_failure_and_continues(w, monkeypatch, caplog):
    other = Employee(id=uuid4(), tenant_id=TENANT, property_id=w.prop.id, role_id=uuid4(),
                     first_name="O", last_name="K", is_active=True)
    w.db.session.add(other)
    w.db.session.commit()
    real = w.service.calculate_employee_ranking
    secret = "Failing row contains (guest@leak.test)"

    async def sometimes(tenant_id, employee_id, **kwargs):
        if employee_id == w.employee.id:
            raise RuntimeError(secret)
        return await real(tenant_id, employee_id, **kwargs)
    monkeypatch.setattr(w.service, "calculate_employee_ranking",
                        lambda tenant_id, employee_id, **kw: sometimes(tenant_id, employee_id, **kw))

    result = await w.service.recalculate_property_rankings(TENANT, w.prop.id, START, END, "weekly")

    assert set(result) == {"success", "total_calculated", "period"}
    assert result["success"] is True and result["total_calculated"] == 1
    assert f"[RANKING] calculation failed for employee {w.employee.id}" in caplog.text
    assert secret not in caplog.text
    rows = w.db.session.execute(select(EmployeeRanking)).scalars().all()
    assert [r.employee_id for r in rows] == [other.id] and rows[0].rank == 1
