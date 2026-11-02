"""
Recalculation no longer hides failure: the service counts employees whose
calculation failed, and the route answers 500 with a generic message when
active employees existed but none succeeded, or 200 with the failed count
when some did. Service tests use in-memory SQLite; the route tests run on a
throwaway local PostgreSQL (skipped without LOCAL_PG_URL). Never touches the
.env database.
"""
from sqlalchemy import func, select

from app.models.ranking_models import EmployeeRanking
from app.services.ranking_service import RankingService
from tests.kra_tasks_pg import throwaway_database
from tests.test_ranking_kra_pg import PgWorld, TENANT as PG_TENANT, START_Z, END_Z
from tests.test_ranking_recalculate import END, START, TENANT, env  # noqa: F401 - env is a fixture

GENERIC = "Could not calculate rankings. Please try again or contact support."


def _fail_for(monkeypatch, employee_ids):
    real = RankingService.calculate_employee_ranking

    async def calculate(self, **kwargs):
        if kwargs["employee_id"] in employee_ids:
            raise RuntimeError("boom")
        return await real(self, **kwargs)
    monkeypatch.setattr(RankingService, "calculate_employee_ranking", calculate)


async def test_service_counts_failed_employees(env, monkeypatch):  # noqa: F811
    db, _, property_id, employees = env
    _fail_for(monkeypatch, {employees["low"]})

    result = await RankingService(db).recalculate_property_rankings(
        tenant_id=TENANT, property_id=property_id, period_start=START, period_end=END)

    assert result["success"] and result["total_calculated"] == 1 and result["failed"] == 1


async def test_service_reports_zero_failed_when_all_succeed(env):  # noqa: F811
    db, _, property_id, _ = env

    result = await RankingService(db).recalculate_property_rankings(
        tenant_id=TENANT, property_id=property_id, period_start=START, period_end=END)

    assert result["total_calculated"] == 2 and result["failed"] == 0


async def _post_recalculate(w):
    return await w.client.post(
        f"/rankings/properties/{w.prop.id}/recalculate", params={"tenant_id": str(PG_TENANT)},
        json={"ranking_type": "weekly", "period_start": START_Z, "period_end": END_Z})


async def test_route_answers_500_when_every_employee_fails(monkeypatch):
    async with throwaway_database() as url, PgWorld(url) as w:
        _fail_for(monkeypatch, {w.emp_with_tasks.id, w.emp_no_tasks.id})

        res = await _post_recalculate(w)

        assert res.status_code == 500
        assert res.json() == {"detail": GENERIC}
        async with w.sessions() as session:
            assert (await session.execute(select(func.count()).select_from(EmployeeRanking))).scalar() == 0


async def test_route_answers_200_with_the_failed_count_when_some_succeed(monkeypatch):
    async with throwaway_database() as url, PgWorld(url) as w:
        _fail_for(monkeypatch, {w.emp_no_tasks.id})

        res = await _post_recalculate(w)

        assert res.status_code == 200, res.text
        body = res.json()
        assert body["employees_processed"] == 1 and body["failed"] == 1
        assert body["message"] == "Calculated rankings for 1 employees; 1 could not be calculated"
        assert list(await w.rankings()) == [w.emp_with_tasks.id]


async def test_route_reports_zero_failed_when_all_succeed():
    async with throwaway_database() as url, PgWorld(url) as w:
        res = await _post_recalculate(w)

        assert res.status_code == 200, res.text
        assert res.json()["failed"] == 0
        assert res.json()["message"] == "Calculated rankings for 2 employees"
