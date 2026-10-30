"""
Default ranking criteria, and migration 031 run twice on a throwaway local
PostgreSQL (skipped without LOCAL_PG_URL). Never touches the .env database.
"""
from uuid import uuid4

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

import app.models  # noqa: F401 - registers every table
from app.models.base import Base
from app.models.models import Property, Tenant
from app.models.ranking_models import RankingCriteriaConfig
from app.services.ranking_service import DEFAULT_CRITERIA, RankingService
from tests.kra_tasks_harness import property_row, sqlite_db
from tests.kra_tasks_pg import throwaway_database
from tests.test_kra_tasks_migration import alembic

TENANT = uuid4()
REVISION = "031_kra_completion_criterion"
REVIEW = text("""
    SELECT property_id, SUM(weightage) AS total_weightage
    FROM ranking_criteria_config
    WHERE is_active
    GROUP BY property_id
    HAVING ABS(SUM(weightage) - 100) > 0.001
""")
SEVEN = {"Attendance & Functionality": 20, "Task Completion": 25, "Task Quality & Cleanliness": 20,
         "Standby / Emergency Support": 10, "Overtime Contribution": 10, "Manager Review & Behaviour": 10,
         "Customer Feedback / Complaints": 5}


class CriteriaDB:
    def __init__(self, db):
        self.db = db

    async def execute(self, statement):
        return await self.db.execute(statement)

    async def get(self, model, key):
        return self.db.session.get(model, key)

    def add(self, obj):
        self.db.session.add(obj)

    async def flush(self):
        self.db.session.flush()


def test_defaults_total_100_with_the_new_weights():
    weights = {c["criterion_name"]: c["weightage"] for c in DEFAULT_CRITERIA}
    assert sum(weights.values()) == 100
    assert weights["KRA Completion"] == 10 and weights["Task Completion"] == 15
    assert len(DEFAULT_CRITERIA) == 8
    kra = next(c for c in DEFAULT_CRITERIA if c["criterion_name"] == "KRA Completion")
    assert kra["name"] == "kra_completion" and kra["max_points"] == 100


def test_other_defaults_are_unchanged():
    weights = {c["criterion_name"]: c["weightage"] for c in DEFAULT_CRITERIA}
    assert {k: v for k, v in weights.items() if k not in ("KRA Completion", "Task Completion")} == {
        k: v for k, v in SEVEN.items() if k != "Task Completion"}


async def test_initialize_criteria_is_idempotent_and_totals_100():
    db = sqlite_db()
    RankingCriteriaConfig.__table__.create(db.session.get_bind())
    prop = property_row(TENANT)
    db.session.add(prop)
    db.session.commit()
    service = RankingService(CriteriaDB(db))

    assert len(await service.initialize_criteria(TENANT, prop.id)) == 8
    assert await service.initialize_criteria(TENANT, prop.id) == []
    rows = db.session.execute(select(RankingCriteriaConfig)).scalars().all()
    assert len(rows) == 8 and sum(r.weightage for r in rows) == 100


async def test_migration_run_twice_only_touches_what_it_should():
    async with throwaway_database() as url:
        engine = create_async_engine(url, poolclass=NullPool, connect_args={
            "server_settings": {"session_replication_role": "replica"}})
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        sessions = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
        standard, customised, has_kra, no_criteria = uuid4(), uuid4(), uuid4(), uuid4()

        def row(prop, name, weight):
            return RankingCriteriaConfig(id=uuid4(), tenant_id=TENANT, property_id=prop, criterion_name=name,
                                         weightage=weight, max_points=100.0)
        async with sessions() as session:
            # Alembic's own connection enforces foreign keys, so the tenant must exist.
            session.add(Tenant(id=TENANT, business_name="T", business_type="hotel"))
            await session.flush()
            session.add_all([Property(id=p, tenant_id=TENANT, name=str(p))
                             for p in (standard, customised, has_kra, no_criteria)])
            await session.flush()
            session.add_all([row(standard, name, weight) for name, weight in SEVEN.items()])
            session.add_all([row(customised, name, 30 if name == "Task Completion" else weight)
                             for name, weight in SEVEN.items()])
            session.add_all([row(has_kra, "Task Completion", 25), row(has_kra, "KRA Completion", 7)])
            await session.commit()
        alembic(url, "stamp", "030_kra_tasks")

        async def state():
            async with sessions() as session:
                rows = (await session.execute(select(RankingCriteriaConfig))).scalars().all()
                return sorted((str(r.property_id), r.criterion_name, r.weightage, r.max_points) for r in rows)

        try:
            alembic(url, "upgrade", "head")
            first = await state()

            def weight(prop, name):
                found = [w for p, n, w, _ in first if p == str(prop) and n == name]
                return found[0] if found else None
            assert (weight(standard, "KRA Completion"), weight(standard, "Task Completion")) == (10, 15)
            assert (weight(customised, "KRA Completion"), weight(customised, "Task Completion")) == (10, 30)
            assert (weight(has_kra, "KRA Completion"), weight(has_kra, "Task Completion")) == (7, 15)
            assert weight(no_criteria, "KRA Completion") is None
            assert weight(standard, "Attendance & Functionality") == 20

            alembic(url, "stamp", "030_kra_tasks")
            alembic(url, "upgrade", "head")
            assert await state() == first

            async with engine.connect() as conn:
                assert (await conn.execute(text("SELECT version_num FROM alembic_version"))).scalar() == REVISION
                review = {row.property_id for row in await conn.execute(REVIEW)}
            assert standard not in review and customised in review and has_kra in review
        finally:
            await engine.dispose()


def test_revision_id_fits_alembic_version_column():
    assert len(REVISION) <= 32
