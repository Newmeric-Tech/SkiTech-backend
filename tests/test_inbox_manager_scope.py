"""
What a Manager sees in GET /inbox: "manager" items of their own property
and items addressed to them, never another property's, another tenant's or
owner-only items. A manager without an assigned property only sees items
addressed to them personally.

In-memory SQLite only; never touches the .env database.
"""
from uuid import uuid4

import pytest

from app.api.v1.endpoints import inbox as inbox_routes
from app.models.inbox import InboxItem
from tests.geofence_sqlite import OTHER_TENANT, PROP_A, PROP_B, TENANT, client_for, make_env, user

MANAGER_ID = uuid4()


@pytest.fixture
def db():
    engine, db = make_env()
    yield db
    db.session.close()
    engine.dispose()


def _item(db, title, tenant=TENANT, prop=PROP_A, role="manager", to_user=None, item_type="low_stock"):
    db.session.add(InboxItem(id=uuid4(), tenant_id=tenant, property_id=prop, source_module="inventory",
                             item_type=item_type, source_record_id=uuid4(), recipient_role=role,
                             recipient_user_id=to_user, title=title, body="b", status="unread"))
    db.session.commit()


async def _titles(db, who, path="/inbox"):
    async with client_for(db, [inbox_routes.router], who) as c:
        resp = await c.get(path)
    assert resp.status_code == 200
    return resp.json()


@pytest.fixture
def items(db):
    _item(db, "own property, manager queue")
    _item(db, "own property, correction", item_type="attendance_correction_request")
    _item(db, "other property, manager queue", prop=PROP_B)
    _item(db, "other tenant, manager queue", tenant=OTHER_TENANT)
    _item(db, "own property, owner only", role="owner", item_type="geofence_change_request")
    _item(db, "addressed to me", role=None, to_user=MANAGER_ID)
    return db


async def test_manager_sees_own_property_and_personal_items_only(items):
    body = await _titles(items, user("Manager", PROP_A, user_id=MANAGER_ID))

    assert {i["title"] for i in body["items"]} == {
        "own property, manager queue", "own property, correction", "addressed to me"}


async def test_unread_count_uses_the_same_scope(items):
    body = await _titles(items, user("Manager", PROP_A, user_id=MANAGER_ID), "/inbox/unread-count")

    assert body == {"unread_count": 3}


async def test_manager_without_a_property_only_sees_personal_items(items):
    body = await _titles(items, user("Manager", None, user_id=MANAGER_ID))

    assert [i["title"] for i in body["items"]] == ["addressed to me"]


async def test_manager_of_another_property(items):
    body = await _titles(items, user("Manager", PROP_B))

    assert [i["title"] for i in body["items"]] == ["other property, manager queue"]
