"""
Rankings on a throwaway local PostgreSQL whose ranking tables are created by
migration 006 itself (performance_status and status are VARCHAR(50), no enum
types), as in production, instead of from the model. Skipped without
LOCAL_PG_URL. Never touches the .env database.
"""
import importlib.util
import sys
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

from sqlalchemy import Index, MetaData, Table, func, select, text

from app.models.base import Base
from app.models.ranking_models import EmployeeRanking, PerformanceStatus, RankingStatus
from app.repositories.ranking_repository import EmployeeRankingRepository
from tests.kra_tasks_pg import throwaway_database
from tests.test_ranking_kra_pg import TENANT, PgWorld

MIGRATION_006 = Path(__file__).resolve().parents[1] / "alembic" / "versions" / "006_add_ranking_tables.py"
RANKING_TABLES = {"ranking_criteria_config", "employee_ranking_scores", "employee_rankings",
                  "ranking_audit_logs", "ranking_insights"}


class _Op:
    """Stand-in for alembic.op with the two calls migration 006 makes. The repo's
    alembic/ package shadows the real one under pytest; the columns and indexes
    are still the migration's own, issued as the same CREATE TABLE / CREATE INDEX."""

    def __init__(self, conn):
        self.conn = conn
        self.meta = MetaData()
        self.meta.reflect(conn)   # the tables the foreign keys point at

    def create_table(self, name, *items):
        Table(name, self.meta, *items).create(self.conn)

    def create_index(self, name, table, columns):
        Index(name, *[self.meta.tables[table].c[c] for c in columns]).create(self.conn)


def _run_migration_006(sync_conn):
    spec = importlib.util.spec_from_file_location("migration_006", MIGRATION_006)
    module = importlib.util.module_from_spec(spec)
    real = sys.modules.get("alembic")
    sys.modules["alembic"] = SimpleNamespace(op=_Op(sync_conn))
    try:
        spec.loader.exec_module(module)   # its "from alembic import op" gets the stand-in
    finally:
        if real is None:
            sys.modules.pop("alembic", None)
        else:
            sys.modules["alembic"] = real
    module.upgrade()


class MigratedWorld(PgWorld):
    """PgWorld, but the ranking tables come from migration 006, not the model."""

    async def create_schema(self):
        # Table by table: metadata.create_all would create every enum type in the
        # metadata, including those of the ranking tables it skips
        def create_others(conn):
            for table in Base.metadata.sorted_tables:
                if table.name not in RANKING_TABLES:
                    table.create(conn)
        async with self.engine.begin() as conn:
            await conn.run_sync(create_others)
            await conn.run_sync(_run_migration_006)

    async def column_types(self):
        async with self.engine.connect() as conn:
            rows = await conn.execute(text(
                "SELECT column_name, data_type FROM information_schema.columns "
                "WHERE table_name = 'employee_rankings' AND column_name IN ('performance_status', 'status')"))
            return dict(rows.all())

    async def enum_types(self):
        async with self.engine.connect() as conn:
            return (await conn.execute(text("SELECT typname FROM pg_type WHERE typtype = 'e'"))).scalars().all()

    async def stored_values(self):
        async with self.engine.connect() as conn:
            return (await conn.execute(text(
                "SELECT performance_status, status FROM employee_rankings"))).all()


async def test_schema_is_shaped_like_production():
    async with throwaway_database() as url, MigratedWorld(url) as w:
        assert await w.column_types() == {"performance_status": "character varying",
                                          "status": "character varying"}
        assert await w.enum_types() == []


async def test_recalculate_saves_and_ranks_everyone():
    async with throwaway_database() as url, MigratedWorld(url) as w:
        result = await w.recalculate()

        assert result["employees_processed"] == 2
        rows = await w.rankings()
        assert {r.rank for r in rows.values()} == {1, 2}
        assert all(r.total_active_employees == 2 for r in rows.values())
        assert all(isinstance(r.performance_status, PerformanceStatus) for r in rows.values())
        assert all(r.status == RankingStatus.ACTIVE for r in rows.values())
        # Stored as the lowercase values the migration's defaults use
        values = PerformanceStatus._value2member_map_
        assert all(p in values and s == "active" for p, s in await w.stored_values())


async def test_second_run_updates_instead_of_duplicating():
    async with throwaway_database() as url, MigratedWorld(url) as w:
        await w.recalculate()
        before = await w.rankings()
        await w.recalculate()
        after = await w.rankings()

        assert {k: v.id for k, v in after.items()} == {k: v.id for k, v in before.items()}
        assert all(r.recalculated_at is not None for r in after.values())
        async with w.sessions() as session:
            assert (await session.execute(select(func.count()).select_from(EmployeeRanking))).scalar() == 2


async def test_reads_work():
    async with throwaway_database() as url, MigratedWorld(url) as w:
        await w.recalculate()
        params = {"tenant_id": str(TENANT)}
        statuses = {r.performance_status.value for r in (await w.rankings()).values()}

        listed = await w.client.get(f"/rankings/properties/{w.prop.id}/rankings", params=params)
        assert listed.status_code == 200, listed.text
        assert {i["performance_status"] for i in listed.json()["items"]} == statuses

        detail = await w.client.get(f"/rankings/employees/{w.emp_with_tasks.id}/ranking", params=params)
        assert detail.status_code == 200, detail.text
        assert detail.json()["performance_status"] in statuses

        portal = await w.client.get(f"/rankings/employees/{w.emp_with_tasks.id}/performance-portal", params=params)
        assert portal.status_code == 200, portal.text
        assert portal.json()["performance_status"] in statuses

        dashboard = await w.client.get(f"/rankings/properties/{w.prop.id}/dashboard", params=params)
        assert dashboard.status_code == 200, dashboard.text
        assert dashboard.json()["active_staff"] == 2


async def test_repository_saves_plain_strings_and_enum_members():
    async with throwaway_database() as url, MigratedWorld(url) as w:
        async with w.sessions() as session:
            repo = EmployeeRankingRepository(session)
            common = dict(tenant_id=TENANT, property_id=w.prop.id, user_id=None, ranking_type="weekly",
                          period_start=datetime(2026, 10, 19), period_end=datetime(2026, 10, 25, 23, 59, 59),
                          overall_score=50.0, rank=1, total_active_employees=2, scores_breakdown={})
            await repo.create_ranking(employee_id=w.emp_with_tasks.id, performance_status="needs_improvement",
                                      **common)
            await repo.create_ranking(employee_id=w.emp_no_tasks.id,
                                      performance_status=PerformanceStatus.HIGH_PERFORMER, **common)
            await session.commit()

        assert sorted(await w.stored_values()) == [("high_performer", "active"), ("needs_improvement", "active")]
        rows = await w.rankings()
        assert rows[w.emp_with_tasks.id].performance_status == PerformanceStatus.NEEDS_IMPROVEMENT
        assert rows[w.emp_no_tasks.id].performance_status == PerformanceStatus.HIGH_PERFORMER
