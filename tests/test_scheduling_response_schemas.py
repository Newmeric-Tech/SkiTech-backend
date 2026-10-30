"""
The scheduling response schemas typed UUID columns as str, so every route
returning a real row failed response validation. Real routes and service on
in-memory SQLite (real tables behind the async-shaped wrapper). Never touches
the .env database.
"""
from datetime import datetime, timedelta
from types import SimpleNamespace
from uuid import UUID, uuid4

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.api.v1.endpoints import scheduling
from app.models.models import (
    Employee, EmployeeAvailability, ReplacementRequest, ShiftAssignment, WeeklySchedule,
)
from tests.attendance_sqlite import AsyncSQLite

TENANT, PROPERTY, USER = uuid4(), uuid4(), uuid4()
EMP, OTHER_EMP = uuid4(), uuid4()
SCHEDULE, SHIFT, REQUEST, AVAILABILITY = uuid4(), uuid4(), uuid4(), uuid4()
NOW = datetime(2026, 10, 28, 9, 0)
DAY = "2026-11-20T00:00:00"
WEEK = {"week_start": "2026-10-26T00:00:00", "week_end": "2026-11-01T00:00:00"}


class SchedulingDB(AsyncSQLite):
    def add_all(self, objs):
        self.session.add_all(objs)


def seed_rows():
    return [
        Employee(id=EMP, role_id=uuid4(), tenant_id=TENANT, property_id=PROPERTY, user_id=USER,
                 first_name="A", last_name="B", is_active=True),
        Employee(id=OTHER_EMP, role_id=uuid4(), tenant_id=TENANT, property_id=PROPERTY,
                 first_name="C", last_name="D", is_active=True),
        EmployeeAvailability(id=AVAILABILITY, tenant_id=TENANT, property_id=PROPERTY, employee_id=EMP,
                             availability_date=NOW, status="available"),
        WeeklySchedule(id=SCHEDULE, tenant_id=TENANT, property_id=PROPERTY, employee_id=EMP,
                       week_start_date=NOW, week_end_date=NOW, status="draft"),
        ShiftAssignment(id=SHIFT, tenant_id=TENANT, property_id=PROPERTY, schedule_id=SCHEDULE, employee_id=EMP,
                        shift_date=NOW, shift_start_time="09:00", shift_end_time="17:00", status="scheduled"),
        ReplacementRequest(id=REQUEST, tenant_id=TENANT, property_id=PROPERTY, shift_assignment_id=SHIFT,
                           original_employee_id=EMP, request_date=NOW, shift_date=NOW,
                           shift_start_time="09:00", shift_end_time="17:00", priority="normal",
                           request_type="send_request", status="pending", created_by=USER),
    ]


def make_app(get_db):
    app = FastAPI()
    app.include_router(scheduling.router)
    app.dependency_overrides[scheduling.get_db] = get_db
    app.dependency_overrides[scheduling.get_current_user_obj] = (
        lambda: SimpleNamespace(id=USER, tenant_id=TENANT, property_id=PROPERTY))
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
                             base_url="http://t")


@pytest.fixture
def env():
    engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    for model in (Employee, EmployeeAvailability, WeeklySchedule, ShiftAssignment, ReplacementRequest):
        model.__table__.create(engine)
    db = SchedulingDB(Session(engine))
    db.session.add_all(seed_rows())
    db.session.commit()
    return db, make_app(lambda: db)


def count(db, model):
    db.session.rollback()
    return db.session.execute(select(func.count()).select_from(model)).scalar()


def assert_schedule(body):
    assert body["id"] == str(SCHEDULE) and isinstance(body["id"], str)
    assert body["employee_id"] == str(EMP)
    assert body["property_id"] == str(PROPERTY)
    assert body["department_id"] is None and body["assigned_by"] is None


def assert_request(body):
    assert body["id"] == str(REQUEST) and isinstance(body["id"], str)
    assert body["shift_assignment_id"] == str(SHIFT)
    assert body["original_employee_id"] == str(EMP)
    assert body["created_by"] == str(USER)


async def test_list_schedules_returns_row_with_string_ids(env):
    db, client = env
    async with client:
        res = await client.get("/scheduling/schedules", params=WEEK)
    assert res.status_code == 200
    assert_schedule(res.json()[0])
    shift = res.json()[0]["shift_assignments"][0]
    assert shift["id"] == str(SHIFT) and shift["schedule_id"] == str(SCHEDULE)


async def test_get_schedule_returns_row_with_string_ids(env):
    db, client = env
    async with client:
        res = await client.get(f"/scheduling/schedules/{SCHEDULE}")
    assert res.status_code == 200
    assert_schedule(res.json())


async def test_schedule_with_set_optional_ids_serializes(env):
    db, client = env
    department = uuid4()
    row = db.session.get(WeeklySchedule, SCHEDULE)
    row.department_id, row.assigned_by = department, USER
    db.session.commit()
    async with client:
        res = await client.get(f"/scheduling/schedules/{SCHEDULE}")
    assert res.status_code == 200
    assert res.json()["department_id"] == str(department)
    assert res.json()["assigned_by"] == str(USER)


async def test_create_schedule_saves_and_answers_200(env):
    db, client = env
    before = count(db, WeeklySchedule)
    async with client:
        res = await client.post("/scheduling/schedules", json={
            "employee_id": str(OTHER_EMP), "week_start_date": DAY, "week_end_date": DAY, "status": "draft"})
    assert res.status_code == 200
    UUID(res.json()["id"])
    assert res.json()["employee_id"] == str(OTHER_EMP)
    assert count(db, WeeklySchedule) == before + 1


async def test_create_shift_saves_and_answers_200(env):
    db, client = env
    before = count(db, ShiftAssignment)
    async with client:
        res = await client.post("/scheduling/shifts",
                                params={"schedule_id": str(SCHEDULE), "employee_id": str(EMP)},
                                json={"shift_date": DAY, "shift_start_time": "09:00", "shift_end_time": "17:00"})
    assert res.status_code == 200
    assert res.json()["schedule_id"] == str(SCHEDULE) and res.json()["employee_id"] == str(EMP)
    assert res.json()["property_id"] == str(PROPERTY)
    assert count(db, ShiftAssignment) == before + 1


async def test_create_availability_saves_and_answers_200(env):
    db, client = env
    before = count(db, EmployeeAvailability)
    async with client:
        res = await client.post("/scheduling/availability", params={"employee_id": str(OTHER_EMP)},
                                json={"employee_id": str(OTHER_EMP), "availability_date": DAY, "status": "off"})
    assert res.status_code == 200
    assert res.json()["employee_id"] == str(OTHER_EMP) and res.json()["property_id"] == str(PROPERTY)
    assert count(db, EmployeeAvailability) == before + 1


async def test_list_replacement_requests_returns_row_with_string_ids(env):
    db, client = env
    async with client:
        res = await client.get("/scheduling/replacement-requests")
    assert res.status_code == 200
    assert_request(res.json()[0])


async def test_get_replacement_request_keeps_null_optional_ids(env):
    db, client = env
    async with client:
        res = await client.get(f"/scheduling/replacement-requests/{REQUEST}")
    assert res.status_code == 200
    assert_request(res.json())
    assert res.json()["replacement_employee_id"] is None and res.json()["responded_by"] is None


async def test_create_replacement_request_saves_and_answers_200(env):
    db, client = env
    before = count(db, ReplacementRequest)
    async with client:
        res = await client.post(
            "/scheduling/replacement-requests",
            params={"shift_assignment_id": str(SHIFT), "original_employee_id": str(EMP)},
            json={"original_employee_id": str(EMP), "shift_date": DAY, "shift_start_time": "09:00",
                  "shift_end_time": "17:00", "request_type": "send_request"})
    assert res.status_code == 200
    assert res.json()["created_by"] == str(USER)
    assert count(db, ReplacementRequest) == before + 1


async def test_accept_answers_200_with_employee_ids(env):
    db, client = env
    async with client:
        res = await client.post(f"/scheduling/replacement-requests/{REQUEST}/accept",
                                params={"employee_id": str(OTHER_EMP)})
    assert res.status_code == 200
    assert res.json()["status"] == "accepted"
    assert res.json()["replacement_employee_id"] == str(OTHER_EMP)
    assert res.json()["responded_by"] == str(OTHER_EMP)


async def test_reject_answers_200_with_responder(env):
    db, client = env
    async with client:
        res = await client.post(f"/scheduling/replacement-requests/{REQUEST}/reject",
                                params={"employee_id": str(OTHER_EMP)})
    assert res.status_code == 200
    assert res.json()["status"] == "rejected" and res.json()["responded_by"] == str(OTHER_EMP)


async def test_assign_answers_200_with_replacement(env):
    db, client = env
    async with client:
        res = await client.post(f"/scheduling/replacement-requests/{REQUEST}/assign",
                                params={"replacement_employee_id": str(OTHER_EMP)})
    assert res.status_code == 200
    assert res.json()["status"] == "assigned" and res.json()["replacement_employee_id"] == str(OTHER_EMP)


async def test_staff_dashboard_returns_pending_request(env):
    db, client = env
    async with client:
        res = await client.get("/scheduling/dashboard/staff", params={"employee_id": str(EMP)})
    assert res.status_code == 200
    assert_request(res.json()["emergency_shift_requests"][0])


async def test_me_returns_pending_request(env):
    db, client = env
    async with client:
        res = await client.get("/scheduling/me")
    assert res.status_code == 200
    assert_request(res.json()["emergency_shift_requests"][0])


async def test_manager_dashboard_returns_pending_request(env):
    db, client = env
    async with client:
        res = await client.get("/scheduling/dashboard/manager", params=WEEK)
    assert res.status_code == 200
    assert_request(res.json()["pending_responses"][0])
