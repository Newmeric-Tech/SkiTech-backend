"""
Recalculating a property's rankings completes and assigns ranks 1..n.

calculate_employee_ranking used to insert rank=0, which the check_rank
constraint (rank >= 1) rejects, so recalculation failed for any property
with active employees. SQLite enforces the model's CHECK constraints, so an
in-memory database reproduces it; nothing touches the .env database.
"""
from contextlib import asynccontextmanager
from datetime import datetime
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session

from app.models.models import Employee, Property
from app.models.ranking_models import (
    EmployeeRanking, EmployeeRankingScore, RankingAuditLog, RankingCriteriaConfig, RankingInsight,
)
from app.services.ranking_service import RankingService

TENANT = uuid4()
START, END = datetime(2026, 10, 1), datetime(2026, 10, 7)


@compiles(JSONB, "sqlite")
def _jsonb_as_json_on_sqlite(type_, compiler, **kw):
    return "JSON"


class AsyncSQLite:
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

    @asynccontextmanager
    async def begin_nested(self):
        with self.s.begin_nested():
            yield

    async def commit(self):
        self.s.commit()


@pytest.fixture
def env():
    engine = create_engine("sqlite://")
    for model in (Property, Employee, RankingCriteriaConfig, EmployeeRankingScore,
                  EmployeeRanking, RankingInsight, RankingAuditLog):
        model.__table__.create(engine)
    s = Session(engine)
    prop = Property(id=uuid4(), tenant_id=TENANT, name="P")
    s.add(prop)
    s.add(RankingCriteriaConfig(id=uuid4(), tenant_id=TENANT, property_id=prop.id,
                                criterion_name="Task Completion", weightage=100.0, max_points=100.0))
    employees = {}
    for name, points in (("low", 50.0), ("high", 90.0)):
        emp = Employee(id=uuid4(), tenant_id=TENANT, property_id=prop.id, role_id=uuid4(),
                       first_name=name, last_name="E", is_active=True)
        s.add(emp)
        s.add(EmployeeRankingScore(id=uuid4(), tenant_id=TENANT, property_id=prop.id, employee_id=emp.id,
                                   criterion_name="Task Completion", weightage=100.0, raw_points=points,
                                   final_points=points, max_points=100.0, period_start=START, period_end=END))
        employees[name] = emp.id
    s.commit()
    yield AsyncSQLite(s), s, prop.id, employees
    s.close()
    engine.dispose()


async def test_recalculation_with_two_employees_assigns_ranks_1_and_2(env):
    db, s, property_id, employees = env

    result = await RankingService(db).recalculate_property_rankings(
        tenant_id=TENANT, property_id=property_id, period_start=START, period_end=END, ranking_type="weekly")

    assert result["success"] and result["total_calculated"] == 2
    s.expire_all()
    rows = {r.employee_id: r for r in s.execute(select(EmployeeRanking)).scalars()}
    assert rows[employees["high"]].rank == 1
    assert rows[employees["low"]].rank == 2
    assert {r.total_active_employees for r in rows.values()} == {2}
    assert rows[employees["high"]].overall_score > rows[employees["low"]].overall_score
