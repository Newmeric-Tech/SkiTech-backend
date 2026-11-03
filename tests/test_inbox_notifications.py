"""
Personal notifications in the inbox: KRA assigned / delayed, shift assigned or
handed over, task assigned, and the outcome of a punch location request or a
punch-out correction. Each producer writes exactly one item for the right
recipient, none for anyone else; a failed notification write never fails the
action; /inbox shows each item only to its recipients; PUT /inbox/read-all.

Real routers and services on in-memory SQLite; never touches the .env database.
"""
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import select

import app.models  # noqa: F401 - registers every table
from app.api.dependencies import get_current_user
from app.api.v1.endpoints import attendance as attendance_routes
from app.api.v1.endpoints import attendance_corrections as correction_routes
from app.api.v1.endpoints import geofence_requests as request_routes
from app.api.v1.endpoints import inbox as inbox_routes
from app.api.v1.endpoints import kra_tasks
from app.api.v1.endpoints import sop as sop_routes
from app.core.database import get_db
from app.models.attendance import AttendanceRecord
from app.models.inbox import InboxItem
from app.models.kra_tasks import KraAssignment
from app.models.models import (
    Employee, ReplacementRequest, SOPExecution, SOPItem, ShiftAssignment, WeeklySchedule,
)
from app.schemas.schemas import SOPCreate
from app.schemas.scheduling import ShiftAssignmentCreate
from app.services import inbox_service
from app.services.scheduling_service import SchedulingService
from tests import geofence_sqlite
from tests.kra_tasks_harness import definition_row, sqlite_db
from tests.test_kra_tasks_routes import FOREIGN, TENANT, TODAY, build_world, token


# ── shared ──────────────────────────────────────────────────────────────────

def items(db):
    db.session.expire_all()
    return db.session.execute(select(InboxItem).order_by(InboxItem.created_at)).scalars().all()


def broken_create_inbox_item(monkeypatch):
    """Every notification write fails in the database (NOT NULL title)."""
    async def create(db, **fields):
        db.add(InboxItem(**{**fields, "title": None, "status": "unread"}))
    monkeypatch.setattr(inbox_service, "create_inbox_item", create)


@pytest.fixture
def world():
    db = sqlite_db()

    def add(rows):
        db.session.add_all(rows)
        db.session.commit()
    w = build_world(add)
    w.db = db
    w.definition = definition_row(TENANT, w.prop.id, frequency="weekly", title="Deposit cash")
    add([w.definition])
    return w


def client(w, who):
    app = FastAPI()
    app.include_router(kra_tasks.router)
    app.include_router(inbox_routes.router)
    app.dependency_overrides[get_db] = lambda: w.db
    app.dependency_overrides[get_current_user] = lambda: who
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t")


async def call(w, who, method, path, json=None, params=None):
    async with client(w, who) as c:
        return await c.request(method, path, json=json, params=params)


async def assign(w, who, *users):
    return await call(w, who, "POST", f"/kra-tasks/definitions/{w.definition.id}/assignments",
                      {"user_ids": [str(u.id) for u in users], "today": TODAY.isoformat()})


async def inbox_titles(w, who):
    resp = await call(w, who, "GET", "/inbox")
    assert resp.status_code == 200, resp.text
    return [i["title"] for i in resp.json()["items"]]


def as_(w, name, role):
    return token(getattr(w, name), role)


# ── a) KRA assigned ─────────────────────────────────────────────────────────

async def test_kra_assignment_notifies_each_new_assignee_once(world):
    w = world
    manager = as_(w, "manager", "Manager")
    assert (await assign(w, manager, w.staff, w.colleague)).status_code == 201

    got = items(w.db)
    assert len(got) == 2
    assert {i.recipient_user_id for i in got} == {w.staff.id, w.colleague.id}
    for i in got:
        assert (i.source_module, i.item_type, i.recipient_role) == ("kra", "kra_assigned", None)
        assert i.title == "New KRA assigned: Deposit cash (weekly)"
        assert i.property_id == w.prop.id and i.tenant_id == TENANT and i.status == "unread"
        assert "Mia Manager" in i.body
    assignment_ids = set(w.db.session.execute(select(KraAssignment.id)).scalars().all())
    assert {i.source_record_id for i in got} == assignment_ids

    # Assigning the same people again creates nothing: skipped, no new items
    again = await assign(w, manager, w.staff, w.colleague)
    assert again.status_code == 201 and len(again.json()["skipped_user_ids"]) == 2
    assert len(items(w.db)) == 2


async def test_kra_assignment_item_is_seen_only_by_its_assignee(world):
    w = world
    await assign(w, as_(w, "manager", "Manager"), w.staff)
    title = "New KRA assigned: Deposit cash (weekly)"

    assert await inbox_titles(w, as_(w, "staff", "Staff")) == [title]
    for name, role in (("colleague", "Staff"), ("other_staff", "Staff"), ("manager", "Manager"),
                       ("peer_manager", "Manager"), ("owner", "Tenant Admin"), ("co_admin", "Co Admin")):
        assert await inbox_titles(w, as_(w, name, role)) == [], name
    assert await inbox_titles(w, token(w.foreign_owner, "Tenant Admin", FOREIGN)) == []
    assert await inbox_titles(w, token(w.foreign_staff, "Staff", FOREIGN)) == []


async def test_owner_assigning_a_manager_notifies_that_manager_at_their_property(world):
    w = world
    assert (await assign(w, as_(w, "owner", "Tenant Admin"), w.manager)).status_code == 201

    assert await inbox_titles(w, as_(w, "manager", "Manager")) == ["New KRA assigned: Deposit cash (weekly)"]
    assert await inbox_titles(w, as_(w, "peer_manager", "Manager")) == []


async def test_failed_notification_does_not_fail_the_assignment(world, monkeypatch):
    w = world
    broken_create_inbox_item(monkeypatch)

    resp = await assign(w, as_(w, "manager", "Manager"), w.staff, w.colleague)

    assert resp.status_code == 201 and len(resp.json()["created"]) == 2
    w.db.session.expire_all()
    assert len(w.db.session.execute(select(KraAssignment)).scalars().all()) == 2
    assert items(w.db) == []


# ── b) KRA delayed ──────────────────────────────────────────────────────────

async def _my_occurrence(w):
    resp = await call(w, as_(w, "staff", "Staff"), "GET", "/kra-tasks/my", params={"today": TODAY.isoformat()})
    assert resp.status_code == 200, resp.text
    return resp.json()[0]["id"]


async def _delay(w, occurrence_id):
    return await call(w, as_(w, "staff", "Staff"), "POST", f"/kra-tasks/occurrences/{occurrence_id}/delay",
                      {"reason": "Bank closed for a family emergency"})


async def test_delay_notifies_the_propertys_managers_once(world):
    w = world
    await assign(w, as_(w, "manager", "Manager"), w.staff)
    occurrence_id = await _my_occurrence(w)
    before = len(items(w.db))

    assert (await _delay(w, occurrence_id)).status_code == 200
    assert (await _delay(w, occurrence_id)).status_code == 409   # already delayed

    [item] = items(w.db)[before:]
    assert (item.source_module, item.item_type, item.recipient_role, item.recipient_user_id) == (
        "kra", "kra_delayed", "manager", None)
    assert item.property_id == w.prop.id and str(item.source_record_id) == occurrence_id
    assert item.title == "Sam Staff marked 'Deposit cash' as delayed"
    assert "Bank" not in item.body and "emergency" not in item.body   # the reason stays on the task

    title = item.title
    for name, role in (("manager", "Manager"), ("peer_manager", "Manager"), ("owner", "Tenant Admin"),
                       ("co_admin", "Co Admin")):
        assert title in await inbox_titles(w, as_(w, name, role)), name
    for name, role in (("other_manager", "Manager"), ("staff", "Staff"), ("colleague", "Staff")):
        assert title not in await inbox_titles(w, as_(w, name, role)), name
    assert await inbox_titles(w, token(w.foreign_owner, "Tenant Admin", FOREIGN)) == []


async def test_failed_notification_does_not_fail_the_delay(world, monkeypatch):
    w = world
    await assign(w, as_(w, "manager", "Manager"), w.staff)
    occurrence_id = await _my_occurrence(w)
    before = len(items(w.db))
    broken_create_inbox_item(monkeypatch)

    resp = await _delay(w, occurrence_id)

    assert resp.status_code == 200 and resp.json()["status"] == "delayed"
    assert len(items(w.db)) == before


# ── c) shifts ───────────────────────────────────────────────────────────────

@pytest.fixture
def shifts(world):
    w = world
    for model in (Employee, WeeklySchedule, ShiftAssignment, ReplacementRequest):
        model.__table__.create(w.db.session.get_bind())
    staff_role = w.roles["Staff"].id

    def employee(user=None, prop=w.prop.id, tenant=TENANT):
        e = Employee(id=uuid4(), tenant_id=tenant, property_id=prop, user_id=user.id if user else None,
                     role_id=staff_role, first_name="E", last_name="Mployee", is_active=True)
        w.db.session.add(e)
        return e
    w.emp_staff, w.emp_colleague, w.emp_no_login = employee(w.staff), employee(w.colleague), employee()
    w.emp_foreign = employee(w.foreign_staff, prop=w.foreign_prop.id, tenant=FOREIGN)
    w.schedule = WeeklySchedule(id=uuid4(), tenant_id=TENANT, property_id=w.prop.id, employee_id=w.emp_staff.id,
                                week_start_date=datetime(2026, 11, 2), week_end_date=datetime(2026, 11, 8),
                                status="draft")
    w.db.session.add(w.schedule)
    w.db.session.commit()
    w.service = SchedulingService(w.db, TENANT, w.prop.id, w.manager.id)
    return w


SHIFT = ShiftAssignmentCreate(shift_date=datetime(2026, 11, 3), shift_start_time="09:00", shift_end_time="17:00")


async def test_new_shift_notifies_the_employees_login(shifts):
    w = shifts
    shift = await w.service.create_shift_assignment(w.schedule.id, w.emp_staff.id, SHIFT)
    w.db.session.commit()

    [item] = items(w.db)
    assert (item.source_module, item.item_type, item.recipient_user_id) == ("scheduling", "shift_assigned", w.staff.id)
    assert item.source_record_id == shift.id and item.property_id == w.prop.id
    assert item.title == "New shift: Tue 03 Nov, 09:00-17:00"
    assert await inbox_titles(w, as_(w, "staff", "Staff")) == [item.title]
    assert await inbox_titles(w, as_(w, "colleague", "Staff")) == []


async def test_shift_for_an_employee_without_a_login_or_from_another_tenant_notifies_nobody(shifts):
    w = shifts
    await w.service.create_shift_assignment(w.schedule.id, w.emp_no_login.id, SHIFT)
    await w.service.create_shift_assignment(w.schedule.id, w.emp_foreign.id, SHIFT)
    w.db.session.commit()

    assert items(w.db) == []


async def test_replacement_assignment_notifies_the_new_employee_once(shifts):
    w = shifts
    shift = await w.service.create_shift_assignment(w.schedule.id, w.emp_staff.id, SHIFT)
    request = ReplacementRequest(
        id=uuid4(), tenant_id=TENANT, property_id=w.prop.id, shift_assignment_id=shift.id,
        original_employee_id=w.emp_staff.id, request_date=datetime(2026, 11, 1), shift_date=datetime(2026, 11, 3),
        shift_start_time="09:00", shift_end_time="17:00", request_type="sick", status="pending")
    w.db.session.add(request)
    w.db.session.commit()

    await w.service.direct_assign_replacement(request.id, w.emp_colleague.id)
    await w.service.direct_assign_replacement(request.id, w.emp_colleague.id)   # double submit
    w.db.session.commit()

    handed = [i for i in items(w.db) if i.item_type == "shift_reassigned"]
    assert len(handed) == 1
    assert handed[0].recipient_user_id == w.colleague.id and handed[0].source_record_id == request.id
    assert handed[0].title == "Shift assigned to you: Tue 03 Nov, 09:00-17:00"


async def test_failed_notification_does_not_fail_the_shift(shifts, monkeypatch):
    w = shifts
    broken_create_inbox_item(monkeypatch)

    shift = await w.service.create_shift_assignment(w.schedule.id, w.emp_staff.id, SHIFT)
    w.db.session.commit()

    w.db.session.expire_all()
    assert w.db.session.get(ShiftAssignment, shift.id) is not None
    assert items(w.db) == []


# ── d) tasks (SOP items) ────────────────────────────────────────────────────

@pytest.fixture
def tasks(world):
    w = world
    for model in (SOPItem, SOPExecution):
        model.__table__.create(w.db.session.get_bind())
    return w


async def _create_task(w, assignee_id, title="Restock minibar"):
    who = {**as_(w, "manager", "Manager")}
    data = SOPCreate(category_id=uuid4(), title=title, assigned_user_id=assignee_id, priority="high",
                     due_date=datetime(2026, 11, 5))
    return await sop_routes.create_sop(property_id=w.prop.id, data=data, db=w.db, user=who)


async def test_task_assignment_notifies_the_assignee(tasks):
    w = tasks
    sop = await _create_task(w, w.staff.id)

    [item] = items(w.db)
    execution = w.db.session.execute(select(SOPExecution)).scalar_one()
    assert (item.source_module, item.item_type, item.recipient_user_id) == ("sop", "task_assigned", w.staff.id)
    assert item.source_record_id == execution.id and execution.sop_id == sop.id
    assert item.title == "New task assigned: Restock minibar"
    assert "high" in item.body and "05 Nov 2026" in item.body
    assert await inbox_titles(w, as_(w, "staff", "Staff")) == [item.title]
    assert await inbox_titles(w, as_(w, "colleague", "Staff")) == []


async def test_task_for_a_user_of_another_tenant_or_no_assignee_notifies_nobody(tasks):
    w = tasks
    await _create_task(w, w.foreign_staff.id)
    await _create_task(w, None)

    assert items(w.db) == []


async def test_failed_notification_does_not_fail_the_task(tasks, monkeypatch):
    w = tasks
    broken_create_inbox_item(monkeypatch)

    await _create_task(w, w.staff.id)

    w.db.session.expire_all()
    assert len(w.db.session.execute(select(SOPExecution)).scalars().all()) == 1
    assert items(w.db) == []


# ── e) punch location requests and corrections: the requester hears back ──

GEO_ROUTERS = [attendance_routes.router, request_routes.router, inbox_routes.router, correction_routes.router]
MANAGER_ID, STAFF_ID = uuid4(), uuid4()
G_MANAGER = geofence_sqlite.user("Manager", geofence_sqlite.PROP_A, user_id=MANAGER_ID)
G_MANAGER_B = geofence_sqlite.user("Manager", geofence_sqlite.PROP_B)
G_STAFF = geofence_sqlite.user("Staff", geofence_sqlite.PROP_A, user_id=STAFF_ID)
G_ADMIN = geofence_sqlite.user("Tenant Admin")
G_FOREIGN = geofence_sqlite.user("Tenant Admin", tenant=geofence_sqlite.OTHER_TENANT)


@pytest.fixture
def geo():
    engine, db = geofence_sqlite.make_env()
    yield db
    db.session.close()
    engine.dispose()


async def gcall(db, who, method, path, json=None):
    async with geofence_sqlite.client_for(db, GEO_ROUTERS, who) as c:
        return await c.request(method, path, json=json)


def _outcomes(db):
    return [i for i in items(db) if i.recipient_user_id is not None]


async def _geofence_request(db):
    resp = await gcall(db, G_MANAGER, "POST", "/attendance/geofence-requests",
                       geofence_sqlite.body(geofence_sqlite.PROP_A))
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


@pytest.mark.parametrize("action", ["approve", "reject"])
async def test_geofence_review_notifies_the_requester(geo, action):
    rid = await _geofence_request(geo)

    assert (await gcall(geo, G_ADMIN, "POST", f"/attendance/geofence-requests/{rid}/{action}", {})).status_code == 200
    assert (await gcall(geo, G_ADMIN, "POST", f"/attendance/geofence-requests/{rid}/{action}", {})).status_code == 409

    outcome = "approved" if action == "approve" else "rejected"
    [item] = _outcomes(geo)
    assert (item.source_module, item.item_type, item.recipient_user_id) == (
        "attendance", f"geofence_request_{outcome}", MANAGER_ID)
    assert str(item.source_record_id) == rid and item.property_id == geofence_sqlite.PROP_A
    assert item.title == f"Punch location request {outcome}"

    async def titles(who):
        resp = await gcall(geo, who, "GET", "/inbox")
        return [i["title"] for i in resp.json()["items"]]
    assert item.title in await titles(G_MANAGER)
    assert item.title not in await titles(G_MANAGER_B)
    assert item.title not in await titles(G_ADMIN)   # personal to the requester
    assert await titles(G_FOREIGN) == []


async def test_failed_notification_does_not_fail_the_approval(geo, monkeypatch):
    rid = await _geofence_request(geo)
    broken_create_inbox_item(monkeypatch)

    resp = await gcall(geo, G_ADMIN, "POST", f"/attendance/geofence-requests/{rid}/approve", {})

    assert resp.status_code == 200 and resp.json()["status"] == "approved"
    assert _outcomes(geo) == []


PUNCH_IN = datetime.now(timezone.utc).replace(microsecond=0) - timedelta(days=2)


async def _correction(db):
    rec = AttendanceRecord(id=uuid4(), tenant_id=geofence_sqlite.TENANT, user_id=STAFF_ID,
                           property_id=geofence_sqlite.PROP_A, punch_in_time=PUNCH_IN, punch_in_lat=0,
                           punch_in_lon=0, is_within_fence=True, status="auto_closed")
    db.session.add(rec)
    db.session.commit()
    resp = await gcall(db, G_STAFF, "POST", "/attendance/correction-requests", {
        "attendance_id": str(rec.id), "claimed_punch_out_time": (PUNCH_IN + timedelta(hours=8)).isoformat(),
        "reason": "Phone battery died"})
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


@pytest.mark.parametrize("action", ["approve", "reject"])
async def test_correction_review_notifies_the_requester(geo, action):
    rid = await _correction(geo)

    assert (await gcall(geo, G_MANAGER, "POST", f"/attendance/correction-requests/{rid}/{action}", {})
            ).status_code == 200

    outcome = "approved" if action == "approve" else "rejected"
    [item] = _outcomes(geo)
    assert (item.item_type, item.recipient_user_id, item.property_id) == (
        f"attendance_correction_{outcome}", STAFF_ID, geofence_sqlite.PROP_A)
    assert item.title == f"Punch-out correction {outcome}"
    assert ("8.0 h" in item.body) == (action == "approve")
    assert "battery" not in item.body
    staff_inbox = (await gcall(geo, G_STAFF, "GET", "/inbox")).json()["items"]
    assert [i["title"] for i in staff_inbox] == [item.title]


# ── PUT /inbox/read-all ─────────────────────────────────────────────────────

async def test_read_all_marks_only_what_the_caller_can_see(world):
    w = world
    manager = as_(w, "manager", "Manager")
    await assign(w, manager, w.staff, w.colleague)
    occurrence_id = await _my_occurrence(w)
    await _delay(w, occurrence_id)                      # a "manager" queue item
    foreign = InboxItem(tenant_id=FOREIGN, property_id=w.foreign_prop.id, source_module="kra",
                        item_type="kra_assigned", source_record_id=uuid4(), recipient_user_id=w.foreign_staff.id,
                        title="x", body="x", status="unread")
    w.db.session.add(foreign)
    w.db.session.commit()

    staff = as_(w, "staff", "Staff")
    assert (await call(w, staff, "GET", "/inbox/unread-count")).json() == {"unread_count": 1}
    resp = await call(w, staff, "PUT", "/inbox/read-all")
    assert resp.status_code == 200 and resp.json() == {"updated": 1}
    assert (await call(w, staff, "GET", "/inbox/unread-count")).json() == {"unread_count": 0}

    by_recipient = {(i.recipient_user_id, i.recipient_role): i for i in items(w.db)}
    assert by_recipient[(w.staff.id, None)].status == "read" and by_recipient[(w.staff.id, None)].read_at
    assert by_recipient[(w.colleague.id, None)].status == "unread"
    assert by_recipient[(None, "manager")].status == "unread"
    assert by_recipient[(w.foreign_staff.id, None)].status == "unread"

    assert (await call(w, manager, "PUT", "/inbox/read-all")).json() == {"updated": 1}   # the delay item
    assert (await call(w, manager, "PUT", "/inbox/read-all")).json() == {"updated": 0}
    still = {(i.recipient_user_id, i.recipient_role): i.status for i in items(w.db)}
    assert still[(w.colleague.id, None)] == "unread" and still[(None, "manager")] == "read"


async def test_a_caller_without_a_tenant_has_an_empty_inbox(world):
    w = world
    await assign(w, as_(w, "manager", "Manager"), w.staff)
    superadmin = {"user_id": str(uuid4()), "tenant_id": None, "role": "Super Admin", "property_id": None}

    assert (await call(w, superadmin, "GET", "/inbox/unread-count")).json() == {"unread_count": 0}
    assert (await call(w, superadmin, "GET", "/inbox")).json()["items"] == []
    assert (await call(w, superadmin, "PUT", "/inbox/read-all")).json() == {"updated": 0}
    assert items(w.db)[0].status == "unread"


# ── Postgres: savepoint behaviour (a failed INSERT aborts the transaction) ──

async def test_notifications_on_postgres_concurrent_assigns_and_a_failed_write(monkeypatch):
    import asyncio

    from sqlalchemy import func
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from sqlalchemy.pool import NullPool

    from app.models.base import Base
    from app.services.kra_task_service import assign_users
    from tests.kra_tasks_pg import throwaway_database

    async with throwaway_database() as url:
        engine = create_async_engine(url, poolclass=NullPool, connect_args={
            "server_settings": {"session_replication_role": "replica"}})
        try:
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            sessions = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
            pending = []
            w = build_world(pending.append)
            first = definition_row(TENANT, w.prop.id, title="Deposit cash")
            second = definition_row(TENANT, w.prop.id, title="Count float")
            pending.append([first, second])
            for rows in pending:
                async with sessions() as session:
                    session.add_all(rows)
                    await session.commit()
            manager = token(w.manager, "Manager")

            async def assign_once(definition):
                async with sessions() as session:
                    created, _ = await assign_users(session, manager, definition.id, [w.staff.id], TODAY)
                    return len(created)

            assert sum(await asyncio.gather(*[assign_once(first) for _ in range(5)])) == 1

            broken_create_inbox_item(monkeypatch)
            assert await assign_once(second) == 1

            async with sessions() as session:
                assert (await session.execute(select(func.count()).select_from(KraAssignment))).scalar() == 2
                rows = (await session.execute(select(InboxItem))).scalars().all()
            assert [(i.item_type, i.recipient_user_id, i.title) for i in rows] == [
                ("kra_assigned", w.staff.id, "New KRA assigned: Deposit cash (daily)")]
        finally:
            await engine.dispose()
