"""
Rankings through the real routes on a throwaway local PostgreSQL, which is where
timezone-aware dates, aborted transactions and lazy loads actually fail. Skipped
without LOCAL_PG_URL. Never touches the .env database.
"""
from datetime import date, datetime
from types import SimpleNamespace
from uuid import uuid4

import httpx
from fastapi import FastAPI
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

import app.models  # noqa: F401 - registers every table
from app.api.v1.endpoints import ranking as ranking_routes
from app.models.base import Base
from app.models.kra_tasks import KraOccurrence
from app.models.models import Department, Employee
from app.models.ranking_models import EmployeeRanking, EmployeeRankingScore, RankingCriteriaConfig
from app.repositories.ranking_repository import EmployeeRankingRepository
from app.services.ranking_service import DEFAULT_CRITERIA, KRA_CRITERION
from tests.kra_tasks_harness import (
    assignment_row, definition_row, property_row, role_rows, user_row,
)
from tests.kra_tasks_pg import throwaway_database

TENANT = uuid4()
# What lib/api/ranking.ts getPeriodDates sends: toISOString(), with the Z suffix.
START_Z, END_Z = "2026-10-19T00:00:00.000Z", "2026-10-25T23:59:59.999Z"
DAY = date(2026, 10, 20)


class PgWorld:
    def __init__(self, url):
        # replica role: no foreign key triggers, so the tenant parent needn't be seeded.
        self.engine = create_async_engine(url, poolclass=NullPool, connect_args={
            "server_settings": {"session_replication_role": "replica"}})
        self.sessions = async_sessionmaker(self.engine, expire_on_commit=False, autoflush=False)

    async def __aenter__(self):
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        roles = role_rows()
        self.prop = property_row(TENANT)
        self.department = Department(id=uuid4(), tenant_id=TENANT, property_id=self.prop.id, name="Front Desk")
        self.user = user_row(roles["Staff"], TENANT, self.prop.id)
        self.emp_with_tasks = Employee(id=uuid4(), tenant_id=TENANT, property_id=self.prop.id, user_id=self.user.id,
                                       role_id=uuid4(), first_name="Sam", last_name="Staff", is_active=True)
        self.emp_no_tasks = Employee(id=uuid4(), tenant_id=TENANT, property_id=self.prop.id, role_id=uuid4(),
                                     first_name="Nia", last_name="NoTasks", is_active=True)
        definition = definition_row(TENANT, self.prop.id)
        assignment = assignment_row(definition, self.user.id, date(2026, 10, 19), is_active=False)
        occurrence = KraOccurrence(
            id=uuid4(), tenant_id=TENANT, property_id=self.prop.id, assignment_id=assignment.id,
            definition_id=definition.id, assignee_id=self.user.id, period_start=DAY, period_end=DAY,
            status="completed", completed_at=datetime(2026, 10, 20, 12))
        for rows in (list(roles.values()), [self.prop], [self.department, self.user],
                     [self.emp_with_tasks, self.emp_no_tasks, definition], [assignment], [occurrence],
                     [RankingCriteriaConfig(id=uuid4(), tenant_id=TENANT, property_id=self.prop.id,
                                            criterion_name=c["criterion_name"], weightage=c["weightage"],
                                            max_points=c["max_points"]) for c in DEFAULT_CRITERIA]):
            await self.add(rows)

        fastapi_app = FastAPI()
        fastapi_app.include_router(ranking_routes.router)

        async def real_session():
            async with self.sessions() as session:
                yield session
        fastapi_app.dependency_overrides[ranking_routes.get_async_session] = real_session
        fastapi_app.dependency_overrides[ranking_routes.get_current_user] = (
            lambda: SimpleNamespace(id=self.user.id, tenant_id=TENANT))
        self.client = httpx.AsyncClient(transport=httpx.ASGITransport(app=fastapi_app), base_url="http://t")
        return self

    async def __aexit__(self, *exc):
        await self.client.aclose()
        await self.engine.dispose()

    async def add(self, rows):
        async with self.sessions() as session:
            session.add_all(rows)
            await session.commit()

    async def recalculate(self):
        res = await self.client.post(
            f"/rankings/properties/{self.prop.id}/recalculate", params={"tenant_id": str(TENANT)},
            json={"ranking_type": "weekly", "period_start": START_Z, "period_end": END_Z})
        assert res.status_code == 200, res.text
        return res.json()

    async def rankings(self):
        async with self.sessions() as session:
            rows = (await session.execute(select(EmployeeRanking))).scalars().all()
            return {r.employee_id: r for r in rows}

    async def kra_scores(self):
        async with self.sessions() as session:
            return (await session.execute(select(EmployeeRankingScore).where(
                EmployeeRankingScore.criterion_name == KRA_CRITERION))).scalars().all()


async def test_recalculating_with_the_frontends_dates_ranks_everyone():
    async with throwaway_database() as url, PgWorld(url) as w:
        result = await w.recalculate()
        assert result["employees_processed"] == 2

        rows = await w.rankings()
        assert {r.rank for r in rows.values()} == {1, 2}
        assert rows[w.emp_with_tasks.id].scores_breakdown[KRA_CRITERION] == 100.0
        assert KRA_CRITERION not in rows[w.emp_no_tasks.id].scores_breakdown

        scores = await w.kra_scores()
        assert len(scores) == 1 and scores[0].employee_id == w.emp_with_tasks.id
        assert scores[0].period_start == datetime(2026, 10, 19)   # stored as naive UTC
        assert scores[0].evidence["on_time"] == 1


async def test_recalculating_twice_replaces_rows_and_picks_up_changes():
    async with throwaway_database() as url, PgWorld(url) as w:
        await w.recalculate()
        before = await w.rankings()

        async with w.sessions() as session:
            occurrence = (await session.execute(select(KraOccurrence))).scalar_one()
            occurrence.was_delayed = True
            await session.commit()
        result = await w.recalculate()
        assert result["employees_processed"] == 2

        after = await w.rankings()
        assert len(after) == 2
        assert after[w.emp_with_tasks.id].id == before[w.emp_with_tasks.id].id
        assert after[w.emp_with_tasks.id].scores_breakdown[KRA_CRITERION] == 50.0
        assert len(await w.kra_scores()) == 1
        async with w.sessions() as session:
            assert (await session.execute(select(func.count()).select_from(EmployeeRanking))).scalar() == 2


async def test_one_employees_database_error_leaves_the_others_ranked(monkeypatch, caplog):
    async with throwaway_database() as url, PgWorld(url) as w:
        real = EmployeeRankingRepository.create_ranking

        async def fail_for_one(self, **kwargs):
            if kwargs["employee_id"] == w.emp_no_tasks.id:
                await self.session.execute(text("SELECT 1/0"))   # aborts the current transaction level
            return await real(self, **kwargs)
        monkeypatch.setattr(EmployeeRankingRepository, "create_ranking", fail_for_one)

        result = await w.recalculate()

        assert result["employees_processed"] == 1
        rows = await w.rankings()
        assert list(rows) == [w.emp_with_tasks.id] and rows[w.emp_with_tasks.id].rank == 1
        assert len(await w.kra_scores()) == 1
        assert f"calculation failed for employee {w.emp_no_tasks.id}" in caplog.text
