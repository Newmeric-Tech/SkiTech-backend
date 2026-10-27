"""
A geofence change request notifies the owner through the existing inbox:
one unread owner-tier item per pending request, actioned once the request
is approved, rejected, cancelled or replaced. Managers don't see it.

In-memory SQLite only; never touches the .env database.
"""
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.api.v1.endpoints import attendance as attendance_routes
from app.api.v1.endpoints import geofence_requests as request_routes
from app.api.v1.endpoints import inbox as inbox_routes
from app.models.inbox import InboxItem
from tests.geofence_sqlite import PROP_A, PROP_B, client_for, make_env, user

ROUTERS = [attendance_routes.router, request_routes.router, inbox_routes.router]
MANAGER = user("Manager", PROP_A)
ADMIN = user("Tenant Admin")


@pytest.fixture
def db():
    engine, db = make_env()
    yield db
    db.session.close()
    engine.dispose()


async def _call(db, who, method, path, json=None):
    async with client_for(db, ROUTERS, who) as c:
        return await c.request(method, path, json=json)


async def _request(db, radius=120):
    resp = await _call(db, MANAGER, "POST", "/attendance/geofence-requests",
                       {"property_id": str(PROP_A), "center_lat": 12.9, "center_lng": 77.6, "radius_meters": radius})
    assert resp.status_code == 201
    return resp.json()


def _items(db):
    db.session.expire_all()
    return {str(i.source_record_id): i for i in db.session.execute(select(InboxItem)).scalars().all()}


async def test_request_creates_one_unread_owner_item(db):
    req = await _request(db)

    item = _items(db)[req["id"]]
    assert (item.source_module, item.item_type, item.recipient_role) == (
        "attendance", "geofence_change_request", "owner")
    assert item.status == "unread" and str(item.property_id) == str(PROP_A)
    assert "approve" in item.body


@pytest.mark.parametrize("action, who", [("approve", ADMIN), ("reject", ADMIN), ("cancel", MANAGER)])
async def test_item_is_actioned_when_the_request_is_closed(db, action, who):
    req = await _request(db)

    await _call(db, who, "POST", f"/attendance/geofence-requests/{req['id']}/{action}")

    assert _items(db)[req["id"]].status == "actioned"


async def test_replaced_request_item_is_actioned_and_new_one_unread(db):
    first = await _request(db, radius=100)
    second = await _request(db, radius=150)

    items = _items(db)
    assert items[first["id"]].status == "actioned"
    assert items[second["id"]].status == "unread"


async def test_owners_see_it_in_the_inbox_and_managers_do_not(db):
    await _request(db)

    owner_view = (await _call(db, ADMIN, "GET", "/inbox")).json()
    owner_count = (await _call(db, ADMIN, "GET", "/inbox/unread-count")).json()
    scoped_co_admin = (await _call(db, user("Co Admin", PROP_A), "GET", "/inbox")).json()
    other_co_admin = (await _call(db, user("Co Admin", PROP_B), "GET", "/inbox")).json()
    manager_view = (await _call(db, MANAGER, "GET", "/inbox")).json()

    assert [i["item_type"] for i in owner_view["items"]] == ["geofence_change_request"]
    assert owner_count == {"unread_count": 1}
    assert scoped_co_admin["total"] == 1
    assert other_co_admin["total"] == 0
    assert manager_view["total"] == 0
