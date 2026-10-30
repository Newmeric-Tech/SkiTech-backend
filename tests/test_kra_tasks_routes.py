"""
/kra-tasks routes: permissions, scoping and the delay/complete flow, real router
and service on in-memory SQLite. The last test runs the main flow on a throwaway
local Postgres (skipped without LOCAL_PG_URL), which is the only place a lazy
load after commit would fail. Never touches the .env database.
"""
import asyncio
from datetime import datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

import app.models  # noqa: F401 - registers every table
from app.api.dependencies import get_current_user
from app.api.v1.endpoints import kra_tasks
from app.core.database import get_db
from app.models.base import Base
from app.models.kra_tasks import KraAssignment, KraOccurrence
from app.services.kra_task_service import assign_users, ensure_occurrences
from tests.kra_tasks_harness import (
    assignment_row, definition_row, property_row, role_rows, sqlite_db, user_row,
)
from tests.kra_tasks_pg import throwaway_database

TENANT, FOREIGN = uuid4(), uuid4()
TODAY = datetime.utcnow().date()


def token(user, role, tenant=TENANT):
    return {"user_id": str(user.id), "tenant_id": str(tenant), "role": role,
            "property_id": str(user.property_id) if user.property_id else None}


def build_world(add):
    roles = role_rows()
    w = SimpleNamespace(roles=roles)
    w.prop, w.other_prop = property_row(TENANT), property_row(TENANT)
    w.foreign_prop = property_row(FOREIGN)
    w.owner = user_row(roles["Tenant Admin"], TENANT)
    w.superadmin = user_row(roles["Super Admin"], TENANT)
    w.co_admin = user_row(roles["Co Admin"], TENANT, w.prop.id)
    w.tenant_co_admin = user_row(roles["Co Admin"], TENANT)
    w.manager = user_row(roles["Manager"], TENANT, w.prop.id, first_name="Mia", last_name="Manager")
    w.other_manager = user_row(roles["Manager"], TENANT, w.other_prop.id)
    w.peer_manager = user_row(roles["Manager"], TENANT, w.prop.id)
    w.no_property_manager = user_row(roles["Manager"], TENANT)
    w.staff = user_row(roles["Staff"], TENANT, w.prop.id, first_name="Sam", last_name="Staff")
    w.colleague = user_row(roles["Staff"], TENANT, w.prop.id)
    w.other_staff = user_row(roles["Staff"], TENANT, w.other_prop.id)
    w.inactive_staff = user_row(roles["Staff"], TENANT, w.prop.id, is_active=False)
    w.foreign_owner = user_row(roles["Tenant Admin"], FOREIGN)
    w.foreign_staff = user_row(roles["Staff"], FOREIGN, w.foreign_prop.id)
    add(list(roles.values()))
    add([w.prop, w.other_prop, w.foreign_prop])
    add([v for v in vars(w).values() if hasattr(v, "password_hash")])
    return w


@pytest.fixture
def world():
    db = sqlite_db()

    def add(rows):
        db.session.add_all(rows)
        db.session.commit()
    w = build_world(add)
    w.db = db
    return w


def client(w, who):
    app = FastAPI()
    app.include_router(kra_tasks.router)
    app.dependency_overrides[get_db] = lambda: w.db
    app.dependency_overrides[get_current_user] = lambda: who
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t")


def as_owner(w):
    return client(w, token(w.owner, "Tenant Admin"))


def as_manager(w):
    return client(w, token(w.manager, "Manager"))


def as_staff(w):
    return client(w, token(w.staff, "Staff"))


def new_definition(w, frequency="daily", prop=None, tenant=TENANT, **kw):
    definition = definition_row(tenant, (prop or w.prop).id, frequency, **kw)
    w.db.session.add(definition)
    w.db.session.commit()
    return definition


def assigned(w, user=None, frequency="daily", start=None, **kw):
    definition = new_definition(w, frequency, **kw)
    assignment = assignment_row(definition, (user or w.staff).id, start or TODAY)
    w.db.session.add(assignment)
    w.db.session.commit()
    return definition, assignment


async def my_task(w, http=None, **kw):
    assigned(w, **kw)
    async with (http or as_staff(w)) as c:
        res = await c.get("/kra-tasks/my", params={"today": str(TODAY)})
    assert res.status_code == 200
    return res.json()[0]


def payload(w, **kw):
    return {"property_id": str(w.prop.id), "title": "Deposit cash", "frequency": "daily", **kw}


# ── definitions ─────────────────────────────────────────────────────────────

async def test_manager_creates_definition_for_own_property(world):
    async with as_manager(world) as c:
        res = await c.post("/kra-tasks/definitions", json=payload(world, value_label="Cash deposited (₹)"))
    assert res.status_code == 201
    body = res.json()
    assert body["property_id"] == str(world.prop.id) and body["created_by"] == str(world.manager.id)
    assert body["value_label"] == "Cash deposited (₹)" and body["is_active"] is True
    assert isinstance(body["id"], str)


@pytest.mark.parametrize("who,role,code", [
    ("manager", "Manager", 404),            # another property
    ("no_property_manager", "Manager", 404),
    ("co_admin", "Co Admin", 404),          # scoped to prop
    ("owner", "Tenant Admin", 201),
    ("tenant_co_admin", "Co Admin", 201),
    ("superadmin", "Super Admin", 201),
])
async def test_creating_for_the_other_property(world, who, role, code):
    async with client(world, token(getattr(world, who), role)) as c:
        res = await c.post("/kra-tasks/definitions", json={**payload(world), "property_id": str(world.other_prop.id)})
    assert res.status_code == code


async def test_other_tenant_property_is_404_even_for_admins(world):
    async with as_owner(world) as c:
        res = await c.post("/kra-tasks/definitions", json={**payload(world), "property_id": str(world.foreign_prop.id)})
    assert res.status_code == 404


@pytest.mark.parametrize("bad", [
    {"title": ""}, {"title": "x" * 201}, {"frequency": "yearly"}, {"value_label": "x" * 101}, {"tenant_id": str(uuid4())},
])
async def test_invalid_definition_is_422(world, bad):
    async with as_owner(world) as c:
        res = await c.post("/kra-tasks/definitions", json={**payload(world), **bad})
    assert res.status_code == 422


async def test_staff_cannot_use_any_management_route(world):
    definition, assignment = assigned(world)
    calls = [
        ("POST", "/kra-tasks/definitions", payload(world)),
        ("GET", "/kra-tasks/definitions", None),
        ("PUT", f"/kra-tasks/definitions/{definition.id}", {"title": "x"}),
        ("POST", f"/kra-tasks/definitions/{definition.id}/assignments",
         {"user_ids": [str(world.staff.id)], "today": str(TODAY)}),
        ("DELETE", f"/kra-tasks/assignments/{assignment.id}", None),
        ("GET", "/kra-tasks/assignments", None),
        ("GET", "/kra-tasks/occurrences", None),
        ("GET", "/kra-tasks/summary", None),
    ]
    async with as_staff(world) as c:
        for method, path, body in calls:
            res = await c.request(method, path, json=body)
            assert res.status_code == 403, path


async def test_demoted_manager_with_old_token_is_refused(world):
    world.manager.role_id = world.roles["Staff"].id
    world.db.session.commit()
    async with as_manager(world) as c:
        res = await c.post("/kra-tasks/definitions", json=payload(world))
    assert res.status_code == 403


async def test_list_definitions_is_scoped(world):
    mine = new_definition(world)
    other = new_definition(world, prop=world.other_prop)
    new_definition(world, prop=world.foreign_prop, tenant=FOREIGN)
    async with as_manager(world) as c:
        assert [d["id"] for d in (await c.get("/kra-tasks/definitions")).json()] == [str(mine.id)]
        assert (await c.get("/kra-tasks/definitions", params={"property_id": str(world.other_prop.id)})).status_code == 404
    async with as_owner(world) as c:
        ids = {d["id"] for d in (await c.get("/kra-tasks/definitions")).json()}
        assert ids == {str(mine.id), str(other.id)}
        filtered = await c.get("/kra-tasks/definitions", params={"property_id": str(world.other_prop.id)})
        assert [d["id"] for d in filtered.json()] == [str(other.id)]


async def test_manager_without_property_cannot_list(world):
    async with client(world, token(world.no_property_manager, "Manager")) as c:
        assert (await c.get("/kra-tasks/definitions")).status_code == 403


async def test_edit_definition_fields(world):
    definition = new_definition(world)
    async with as_manager(world) as c:
        res = await c.put(f"/kra-tasks/definitions/{definition.id}",
                          json={"title": "New", "description": "D", "value_label": "Amount"})
    assert res.status_code == 200
    assert (res.json()["title"], res.json()["description"], res.json()["value_label"]) == ("New", "D", "Amount")


async def test_edit_rejects_other_fields(world):
    definition = new_definition(world)
    async with as_manager(world) as c:
        res = await c.put(f"/kra-tasks/definitions/{definition.id}", json={"property_id": str(world.other_prop.id)})
    assert res.status_code == 422


async def test_frequency_changes_only_before_any_assignment(world):
    definition = new_definition(world)
    async with as_manager(world) as c:
        assert (await c.put(f"/kra-tasks/definitions/{definition.id}", json={"frequency": "weekly"})).status_code == 200
        world.db.session.add(assignment_row(definition, world.staff.id, TODAY))
        world.db.session.commit()
        res = await c.put(f"/kra-tasks/definitions/{definition.id}", json={"frequency": "monthly"})
        assert res.status_code == 409
        same = await c.put(f"/kra-tasks/definitions/{definition.id}", json={"frequency": "weekly", "title": "T"})
        assert same.status_code == 200


async def test_edit_out_of_scope_definition_is_404(world):
    other = new_definition(world, prop=world.other_prop)
    foreign = new_definition(world, prop=world.foreign_prop, tenant=FOREIGN)
    async with as_manager(world) as c:
        assert (await c.put(f"/kra-tasks/definitions/{other.id}", json={"title": "x"})).status_code == 404
    async with as_owner(world) as c:
        assert (await c.put(f"/kra-tasks/definitions/{foreign.id}", json={"title": "x"})).status_code == 404


async def test_deactivating_keeps_periods_up_to_now_and_stops_generation(world):
    definition, assignment = assigned(world, start=TODAY - timedelta(days=2))
    async with as_manager(world) as c:
        assert (await c.put(f"/kra-tasks/definitions/{definition.id}", json={"is_active": False})).status_code == 200
    rows = world.db.session.execute(select(func.count()).select_from(KraOccurrence)).scalar()
    assert rows == 3
    assert (await ensure_occurrences(world.db, TENANT, up_to_date=TODAY + timedelta(days=5))).created == 0


async def test_reactivating_does_not_invent_missed_work_for_the_gap(world):
    definition, assignment = assigned(world, start=TODAY - timedelta(days=9), is_active=False)
    async with as_manager(world) as c:
        assert (await c.put(f"/kra-tasks/definitions/{definition.id}", json={"is_active": True})).status_code == 200
    world.db.session.refresh(assignment)
    assert assignment.start_date == TODAY
    assert (await ensure_occurrences(world.db, TENANT, up_to_date=TODAY)).created == 1


# ── assignments ─────────────────────────────────────────────────────────────

async def assign(c, definition, *users, today=None):
    return await c.post(f"/kra-tasks/definitions/{definition.id}/assignments",
                        json={"user_ids": [str(u.id) for u in users], "today": str(today or TODAY)})


async def test_manager_assigns_staff_of_own_property(world):
    definition = new_definition(world)
    async with as_manager(world) as c:
        res = await assign(c, definition, world.staff, world.colleague)
    assert res.status_code == 201
    created = res.json()["created"]
    assert {a["assignee_id"] for a in created} == {str(world.staff.id), str(world.colleague.id)}
    assert created[0]["start_date"] == str(TODAY) and created[0]["assigned_by"] == str(world.manager.id)
    assert res.json()["skipped_user_ids"] == []


@pytest.mark.parametrize("target,code", [
    ("other_staff", 404), ("other_manager", 404), ("foreign_staff", 404), ("inactive_staff", 404),
    ("peer_manager", 403), ("owner", 403),
])
async def test_manager_cannot_assign(world, target, code):
    definition = new_definition(world)
    async with as_manager(world) as c:
        res = await assign(c, definition, world.staff, getattr(world, target))
    assert res.status_code == code
    assert world.db.session.execute(select(func.count()).select_from(KraAssignment)).scalar() == 0  # all or nothing


@pytest.mark.parametrize("who,role", [("owner", "Tenant Admin"), ("co_admin", "Co Admin"), ("superadmin", "Super Admin")])
async def test_admins_can_assign_managers(world, who, role):
    definition = new_definition(world)
    async with client(world, token(getattr(world, who), role)) as c:
        res = await assign(c, definition, world.manager, world.no_property_manager, world.staff)
    assert res.status_code == 201 and len(res.json()["created"]) == 3


@pytest.mark.parametrize("target,code", [("other_manager", 404), ("other_staff", 404), ("foreign_staff", 404), ("co_admin", 403)])
async def test_admin_assignment_limits(world, target, code):
    definition = new_definition(world)
    async with as_owner(world) as c:
        assert (await assign(c, definition, getattr(world, target))).status_code == code


async def test_already_assigned_user_is_skipped_not_duplicated(world):
    definition = new_definition(world)
    async with as_manager(world) as c:
        await assign(c, definition, world.staff)
        res = await assign(c, definition, world.staff, world.colleague)
    assert [a["assignee_id"] for a in res.json()["created"]] == [str(world.colleague.id)]
    assert res.json()["skipped_user_ids"] == [str(world.staff.id)]
    assert world.db.session.execute(select(func.count()).select_from(KraAssignment)).scalar() == 2


async def test_repeated_user_id_in_one_request_is_one_assignment(world):
    definition = new_definition(world)
    async with as_manager(world) as c:
        res = await assign(c, definition, world.staff, world.staff)
    assert len(res.json()["created"]) == 1


async def test_ended_user_can_be_assigned_again(world):
    definition = new_definition(world)
    async with as_manager(world) as c:
        first = (await assign(c, definition, world.staff)).json()["created"][0]
        await c.delete(f"/kra-tasks/assignments/{first['id']}")
        res = await assign(c, definition, world.staff)
    assert len(res.json()["created"]) == 1 and res.json()["created"][0]["id"] != first["id"]


@pytest.mark.parametrize("delta", [-2, 2])
async def test_assign_today_out_of_range_is_422(world, delta):
    definition = new_definition(world)
    async with as_manager(world) as c:
        assert (await assign(c, definition, world.staff, today=TODAY + timedelta(days=delta))).status_code == 422


async def test_inactive_definition_cannot_be_assigned(world):
    definition = new_definition(world, is_active=False)
    async with as_manager(world) as c:
        assert (await assign(c, definition, world.staff)).status_code == 409


async def test_ending_assignment_keeps_occurrences_and_stops_generation(world):
    _, assignment = assigned(world, start=TODAY - timedelta(days=1))
    async with as_manager(world) as c:
        res = await c.delete(f"/kra-tasks/assignments/{assignment.id}")
        assert res.status_code == 200
        assert res.json()["is_active"] is False and res.json()["ended_at"]
        assert (await c.delete(f"/kra-tasks/assignments/{assignment.id}")).status_code == 409
    assert world.db.session.execute(select(func.count()).select_from(KraOccurrence)).scalar() == 2
    assert (await ensure_occurrences(world.db, TENANT, up_to_date=TODAY + timedelta(days=5))).created == 0


async def test_end_and_list_assignments_are_scoped(world):
    definition, assignment = assigned(world)
    assigned(world, world.other_staff, prop=world.other_prop)
    async with client(world, token(world.other_manager, "Manager")) as c:
        assert (await c.delete(f"/kra-tasks/assignments/{assignment.id}")).status_code == 404
        assert (await c.get("/kra-tasks/assignments", params={"definition_id": str(definition.id)})).status_code == 404
    async with client(world, token(world.foreign_owner, "Tenant Admin", FOREIGN)) as c:
        assert (await c.delete(f"/kra-tasks/assignments/{assignment.id}")).status_code == 404
    async with as_manager(world) as c:
        all_mine = (await c.get("/kra-tasks/assignments")).json()
        assert [a["id"] for a in all_mine] == [str(assignment.id)]
        assert all_mine[0]["assignee_name"] == "Sam Staff"


# ── doing the work ──────────────────────────────────────────────────────────

async def test_my_lists_unfinished_and_this_periods_completed(world):
    def_a, _ = assigned(world, start=TODAY - timedelta(days=2), title="A", value_label="Amount", description="Desc")
    async with as_staff(world) as c:
        items = (await c.get("/kra-tasks/my", params={"today": str(TODAY)})).json()
        assert len(items) == 3
        assert (items[0]["title"], items[0]["description"], items[0]["frequency"], items[0]["value_label"]) == (
            "A", "Desc", "daily", "Amount")
        assert items[0]["display_status"] == "pending" and items[0]["assignee_name"] == "Sam Staff"
        by_day = {i["period_start"]: i["id"] for i in items}
        await c.post(f"/kra-tasks/occurrences/{by_day[str(TODAY)]}/complete", json={})
        await c.post(f"/kra-tasks/occurrences/{by_day[str(TODAY - timedelta(days=1))]}/complete", json={})
        items = (await c.get("/kra-tasks/my", params={"today": str(TODAY)})).json()
    # Completed today stays; completed yesterday drops off; the older unfinished one stays.
    assert {i["period_start"] for i in items} == {str(TODAY), str(TODAY - timedelta(days=2))}


async def test_my_only_has_the_callers_tasks(world):
    assigned(world, world.colleague)
    async with as_staff(world) as c:
        assert (await c.get("/kra-tasks/my", params={"today": str(TODAY)})).json() == []


@pytest.mark.parametrize("today,code", [
    (str(TODAY + timedelta(days=2)), 422), (str(TODAY - timedelta(days=2)), 422), ("not-a-date", 422),
    (str(TODAY + timedelta(days=1)), 200), (str(TODAY - timedelta(days=1)), 200),
])
async def test_my_today_validation(world, today, code):
    async with as_staff(world) as c:
        assert (await c.get("/kra-tasks/my", params={"today": today})).status_code == code


async def test_my_requires_today(world):
    async with as_staff(world) as c:
        assert (await c.get("/kra-tasks/my")).status_code == 422


async def test_delayed_then_completed_is_completed_delayed(world):
    task = await my_task(world)
    async with as_staff(world) as c:
        delayed = await c.post(f"/kra-tasks/occurrences/{task['id']}/delay", json={"reason": "Bank closed"})
        assert delayed.status_code == 200
        assert delayed.json()["status"] == "delayed" and delayed.json()["display_status"] == "delayed"
        assert delayed.json()["was_delayed"] is True and delayed.json()["delayed_at"]
        assert delayed.json()["delay_reason"] == "Bank closed"
        done = await c.post(f"/kra-tasks/occurrences/{task['id']}/complete", json={"note": "Done"})
    assert done.status_code == 200
    assert done.json()["status"] == "completed" and done.json()["display_status"] == "completed_delayed"
    assert done.json()["was_delayed"] is True and done.json()["completed_at"]
    assert done.json()["completion_note"] == "Done"


async def test_completed_without_delay_stays_plain_completed(world):
    task = await my_task(world)
    async with as_staff(world) as c:
        done = await c.post(f"/kra-tasks/occurrences/{task['id']}/complete", json={})
    assert done.json()["display_status"] == "completed" and done.json()["was_delayed"] is False


async def test_invalid_transitions_are_409(world):
    task = await my_task(world)
    url = f"/kra-tasks/occurrences/{task['id']}"
    async with as_staff(world) as c:
        await c.post(f"{url}/delay", json={})
        assert (await c.post(f"{url}/delay", json={})).status_code == 409
        await c.post(f"{url}/complete", json={})
        assert (await c.post(f"{url}/complete", json={})).status_code == 409
        assert (await c.post(f"{url}/delay", json={})).status_code == 409


@pytest.mark.parametrize("action", ["delay", "complete"])
@pytest.mark.parametrize("who,role,code", [
    ("manager", "Manager", 403), ("owner", "Tenant Admin", 403), ("colleague", "Staff", 403),
    ("superadmin", "Super Admin", 403),
    ("other_staff", "Staff", 404), ("other_manager", "Manager", 404),
])
async def test_only_the_assignee_can_act(world, action, who, role, code):
    task = await my_task(world)
    async with client(world, token(getattr(world, who), role)) as c:
        res = await c.post(f"/kra-tasks/occurrences/{task['id']}/{action}", json={})
    assert res.status_code == code
    row = world.db.session.execute(select(KraOccurrence)).scalar_one()
    assert row.status == "pending"


@pytest.mark.parametrize("action", ["delay", "complete"])
async def test_other_tenant_occurrence_is_404(world, action):
    task = await my_task(world)
    async with client(world, token(world.foreign_staff, "Staff", FOREIGN)) as c:
        res = await c.post(f"/kra-tasks/occurrences/{task['id']}/{action}", json={})
    assert res.status_code == 404


async def test_unknown_occurrence_is_404(world):
    async with as_staff(world) as c:
        assert (await c.post(f"/kra-tasks/occurrences/{uuid4()}/complete", json={})).status_code == 404


async def test_value_accepted_when_definition_has_a_label(world):
    task = await my_task(world, value_label="Cash deposited (₹)")
    async with as_staff(world) as c:
        done = await c.post(f"/kra-tasks/occurrences/{task['id']}/complete", json={"value": 1500.5})
    assert done.status_code == 200 and done.json()["completion_value"] == 1500.5


async def test_zero_value_and_no_value_are_accepted_with_a_label(world):
    task = await my_task(world, value_label="Amount")
    async with as_staff(world) as c:
        done = await c.post(f"/kra-tasks/occurrences/{task['id']}/complete", json={"value": 0})
    assert done.status_code == 200 and done.json()["completion_value"] == 0


async def test_value_rejected_without_a_label(world):
    task = await my_task(world)
    async with as_staff(world) as c:
        res = await c.post(f"/kra-tasks/occurrences/{task['id']}/complete", json={"value": 10})
        assert res.status_code == 422
        assert (await c.post(f"/kra-tasks/occurrences/{task['id']}/complete", json={})).status_code == 200


@pytest.mark.parametrize("value", [-1, "abc"])
async def test_bad_value_is_422(world, value):
    task = await my_task(world, value_label="Amount")
    async with as_staff(world) as c:
        res = await c.post(f"/kra-tasks/occurrences/{task['id']}/complete", json={"value": value})
    assert res.status_code == 422
    assert world.db.session.execute(select(KraOccurrence)).scalar_one().status == "pending"


async def test_ended_assignments_existing_task_can_still_be_finished(world):
    _, assignment = assigned(world)
    async with as_staff(world) as c:
        task = (await c.get("/kra-tasks/my", params={"today": str(TODAY)})).json()[0]
        assignment.is_active = False
        world.db.session.commit()
        assert (await c.post(f"/kra-tasks/occurrences/{task['id']}/complete", json={})).status_code == 200


# ── monitoring ──────────────────────────────────────────────────────────────

async def test_monitor_generates_without_the_assignee_ever_opening_the_app(world):
    assigned(world, start=TODAY - timedelta(days=2))
    async with as_manager(world) as c:
        res = await c.get("/kra-tasks/occurrences")
    assert res.status_code == 200
    assert res.json()["total"] == 3 and len(res.json()["items"]) == 3
    assert res.json()["items"][0]["assignee_id"] == str(world.staff.id)


async def test_monitor_is_scoped_by_property_and_tenant(world):
    assigned(world)
    assigned(world, world.other_staff, prop=world.other_prop)
    async with as_manager(world) as c:
        assert (await c.get("/kra-tasks/occurrences")).json()["total"] == 1
        assert (await c.get("/kra-tasks/occurrences", params={"property_id": str(world.other_prop.id)})).status_code == 404
        assert (await c.get("/kra-tasks/occurrences", params={"user_id": str(world.other_staff.id)})).status_code == 404
        assert (await c.get("/kra-tasks/summary", params={"property_id": str(world.other_prop.id)})).status_code == 404
    async with as_owner(world) as c:
        assert (await c.get("/kra-tasks/occurrences")).json()["total"] == 2
        assert (await c.get("/kra-tasks/occurrences", params={"property_id": str(world.foreign_prop.id)})).status_code == 404
        assert (await c.get("/kra-tasks/occurrences", params={"user_id": str(world.foreign_staff.id)})).status_code == 404
    async with client(world, token(world.foreign_owner, "Tenant Admin", FOREIGN)) as c:
        assert (await c.get("/kra-tasks/occurrences")).json()["total"] == 0


async def test_monitor_filters_and_pagination(world):
    assigned(world, frequency="weekly", title="W")
    assigned(world, world.colleague, start=TODAY - timedelta(days=3), title="D")
    async with as_owner(world) as c:
        params = {"property_id": str(world.prop.id)}
        assert (await c.get("/kra-tasks/occurrences", params=params)).json()["total"] == 5
        weekly = await c.get("/kra-tasks/occurrences", params={**params, "frequency": "weekly"})
        assert [i["title"] for i in weekly.json()["items"]] == ["W"]
        one = await c.get("/kra-tasks/occurrences", params={**params, "user_id": str(world.colleague.id)})
        assert one.json()["total"] == 4
        page = await c.get("/kra-tasks/occurrences", params={**params, "skip": 1, "limit": 2})
        assert (page.json()["skip"], page.json()["limit"], len(page.json()["items"]), page.json()["total"]) == (1, 2, 2, 5)
        narrow = await c.get("/kra-tasks/occurrences", params={
            **params, "frequency": "daily", "period_from": str(TODAY - timedelta(days=1)), "period_to": str(TODAY)})
        assert narrow.json()["total"] == 2
        for bad in ({"status": "overdue"}, {"frequency": "yearly"}, {"limit": 0}, {"limit": 201}, {"skip": -1},
                    {"period_from": str(TODAY), "period_to": str(TODAY - timedelta(days=1))}):
            assert (await c.get("/kra-tasks/occurrences", params=bad)).status_code == 422, bad


async def test_monitor_status_filter_and_summary_counts(world):
    assigned(world, frequency="daily", start=TODAY - timedelta(days=2))
    assigned(world, frequency="monthly")
    async with as_staff(world) as c:
        items = (await c.get("/kra-tasks/my", params={"today": str(TODAY)})).json()
        daily = [i for i in items if i["frequency"] == "daily"]
        await c.post(f"/kra-tasks/occurrences/{daily[0]['id']}/complete", json={})
        await c.post(f"/kra-tasks/occurrences/{daily[1]['id']}/delay", json={})
        await c.post(f"/kra-tasks/occurrences/{daily[1]['id']}/complete", json={})
        monthly = [i for i in items if i["frequency"] == "monthly"][0]
        await c.post(f"/kra-tasks/occurrences/{monthly['id']}/delay", json={})
    async with as_manager(world) as c:
        async def total(status):
            return (await c.get("/kra-tasks/occurrences", params={"status": status})).json()["total"]
        assert [await total(s) for s in ("pending", "delayed", "completed", "completed_delayed")] == [1, 1, 2, 1]
        summary = (await c.get("/kra-tasks/summary")).json()
    by = {row["frequency"]: row for row in summary["by_frequency"]}
    assert by["daily"] == {"frequency": "daily", "pending": 1, "delayed": 0, "completed": 2,
                           "completed_with_delay": 1, "total": 3}
    assert by["monthly"]["delayed"] == 1 and by["weekly"]["total"] == 0 and by["quarterly"]["total"] == 0
    assert summary["totals"] == {"pending": 1, "delayed": 1, "completed": 2, "completed_with_delay": 1, "total": 4}
    assert summary["property_id"] == str(world.prop.id)


async def test_period_to_is_not_generated_far_into_the_future(world):
    assigned(world)
    async with as_manager(world) as c:
        res = await c.get("/kra-tasks/occurrences", params={"period_to": str(TODAY + timedelta(days=30))})
    assert res.json()["total"] == 2   # today and, at most, one day ahead


# ── old KRA routes ──────────────────────────────────────────────────────────

def test_old_kra_routes_are_still_registered_and_separate():
    from app.api.v1.router import router
    paths = {route.path for route in router.routes}
    assert "/v1/kra/daily" in paths and "/v1/kra/compliance" in paths
    assert "/v1/kra-tasks/my" in paths and "/v1/kra-tasks/summary" in paths


# ── whole flow on a real async driver ───────────────────────────────────────

async def test_main_flow_on_postgres():
    async with throwaway_database() as url:
        # replica role: no foreign key triggers, so the tenant parent needn't be seeded.
        engine = create_async_engine(url, poolclass=NullPool, connect_args={
            "server_settings": {"session_replication_role": "replica"}})
        try:
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            sessions = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)

            async def add(rows):
                async with sessions() as session:
                    session.add_all(rows)
                    await session.commit()

            pending = []
            w = build_world(pending.append)
            for rows in pending:
                await add(rows)

            app = FastAPI()
            app.include_router(kra_tasks.router)

            async def real_session():
                async with sessions() as session:
                    yield session
            app.dependency_overrides[get_db] = real_session

            def http(user, role):
                app.dependency_overrides[get_current_user] = lambda: token(user, role)
                return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t")

            async with http(w.manager, "Manager") as c:
                created = await c.post("/kra-tasks/definitions", json={
                    **payload(w), "frequency": "weekly", "value_label": "Amount"})
                assert created.status_code == 201, created.text
                definition_id = created.json()["id"]
                edited = await c.put(f"/kra-tasks/definitions/{definition_id}", json={"title": "Renamed"})
                assert edited.status_code == 200, edited.text
                assign_res = await c.post(f"/kra-tasks/definitions/{definition_id}/assignments",
                                          json={"user_ids": [str(w.staff.id)], "today": str(TODAY)})
                assert assign_res.status_code == 201, assign_res.text
                assert assign_res.json()["created"][0]["assignee_name"] == "Sam Staff"
                assert (await c.post(f"/kra-tasks/definitions/{definition_id}/assignments", json={
                    "user_ids": [str(w.staff.id)], "today": str(TODAY)})).json()["skipped_user_ids"] == [str(w.staff.id)]

            async with http(w.staff, "Staff") as c:
                mine = await c.get("/kra-tasks/my", params={"today": str(TODAY)})
                assert mine.status_code == 200, mine.text
                task = mine.json()[0]
                assert task["title"] == "Renamed"
                delayed = await c.post(f"/kra-tasks/occurrences/{task['id']}/delay", json={"reason": "Later"})
                assert delayed.status_code == 200, delayed.text
                done = await c.post(f"/kra-tasks/occurrences/{task['id']}/complete", json={"value": 12.5})
                assert done.status_code == 200, done.text
                assert done.json()["display_status"] == "completed_delayed"
                assert done.json()["completion_value"] == 12.5
                assert (await c.post(f"/kra-tasks/occurrences/{task['id']}/complete", json={})).status_code == 409

            async with http(w.manager, "Manager") as c:
                page = await c.get("/kra-tasks/occurrences", params={"status": "completed_delayed"})
                assert page.status_code == 200 and page.json()["total"] == 1, page.text
                summary = await c.get("/kra-tasks/summary")
                assert summary.status_code == 200, summary.text
                assert summary.json()["totals"]["completed_with_delay"] == 1
                listed = await c.get("/kra-tasks/assignments", params={"definition_id": definition_id})
                assert listed.status_code == 200, listed.text
                ended = await c.delete(f"/kra-tasks/assignments/{listed.json()[0]['id']}")
                assert ended.status_code == 200 and ended.json()["is_active"] is False, ended.text
                off = await c.put(f"/kra-tasks/definitions/{definition_id}", json={"is_active": False})
                assert off.status_code == 200, off.text
        finally:
            await engine.dispose()


# ── errors and races ────────────────────────────────────────────────────────

async def test_unexpected_error_is_generic_and_logged_without_its_text(world, monkeypatch, caplog):
    secret = "Failing row contains (guest@leak.test)"

    async def explode(*args, **kwargs):
        raise RuntimeError(secret)
    monkeypatch.setattr(kra_tasks.tasks, "create_definition", explode)
    async with as_manager(world) as c:
        res = await c.post("/kra-tasks/definitions", json=payload(world))
    assert res.status_code == 500
    assert res.json() == {"detail": "An unexpected error occurred."}
    assert "[KRA TASKS] create_definition failed" in caplog.text
    assert secret not in caplog.text


async def test_scoped_co_admin_only_sees_own_property(world):
    mine = new_definition(world)
    other = new_definition(world, prop=world.other_prop)
    async with client(world, token(world.co_admin, "Co Admin")) as c:
        assert [d["id"] for d in (await c.get("/kra-tasks/definitions")).json()] == [str(mine.id)]
        assert (await c.put(f"/kra-tasks/definitions/{other.id}", json={"title": "x"})).status_code == 404
    async with client(world, token(world.tenant_co_admin, "Co Admin")) as c:
        assert len((await c.get("/kra-tasks/definitions")).json()) == 2


async def test_two_assigns_at_once_make_one_assignment_on_postgres():
    async with throwaway_database() as url:
        engine = create_async_engine(url, poolclass=NullPool, connect_args={
            "server_settings": {"session_replication_role": "replica"}})
        try:
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            sessions = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
            pending = []
            w = build_world(pending.append)
            definition = definition_row(TENANT, w.prop.id)
            pending.append([definition])
            for rows in pending:
                async with sessions() as session:
                    session.add_all(rows)
                    await session.commit()

            async def assign_once():
                async with sessions() as session:
                    created, skipped = await assign_users(
                        session, token(w.manager, "Manager"), definition.id, [w.staff.id], TODAY)
                    return len(created), len(skipped)

            results = await asyncio.gather(*[assign_once() for _ in range(5)])
            assert sum(created for created, _ in results) == 1
            assert sum(skipped for _, skipped in results) == 4
            async with sessions() as session:
                assert (await session.execute(select(func.count()).select_from(KraAssignment))).scalar() == 1
        finally:
            await engine.dispose()
