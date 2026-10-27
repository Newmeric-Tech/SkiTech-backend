"""
Role changes while a request is in flight: the token's role can be up to
one access-token lifetime old, so reviewers and direct editors are checked
against the role stored now.

In-memory SQLite only; never touches the .env database.
"""
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select

from app.api.v1.endpoints import attendance as attendance_routes
from app.api.v1.endpoints import geofence_requests as request_routes
from app.models.attendance import GeofenceChangeRequest, PropertyGeofence
from tests.geofence_sqlite import PROP_A, PROP_B, client_for, make_env, set_db_role, user

ROUTERS = [attendance_routes.router, request_routes.router]
MANAGER_ID, ADMIN_ID = uuid4(), uuid4()
MANAGER = user("Manager", PROP_A, user_id=MANAGER_ID)
ADMIN = user("Tenant Admin", user_id=ADMIN_ID)


@pytest.fixture
def db():
    engine, db = make_env()
    yield db
    db.session.close()
    engine.dispose()


async def _call(db, who, method, path, json=None):
    async with client_for(db, ROUTERS, who) as c:
        return await c.request(method, path, json=json)


async def _request(db, who=MANAGER):
    resp = await _call(db, who, "POST", "/attendance/geofence-requests",
                       {"property_id": str(PROP_A), "center_lat": 12.9, "center_lng": 77.6, "radius_meters": 120})
    assert resp.status_code == 201
    return resp.json()


def _status(db, request_id):
    db.session.expire_all()
    return db.session.execute(
        select(GeofenceChangeRequest.status).where(GeofenceChangeRequest.id == UUID(request_id))).scalar_one()


def _geofences(db):
    db.session.expire_all()
    return db.session.execute(select(PropertyGeofence)).scalars().all()


@pytest.mark.parametrize("action", ["approve", "reject"])
async def test_demoted_admin_with_an_old_token_cannot_review(db, action):
    req = await _request(db)
    await _call(db, ADMIN, "GET", "/attendance/geofence-requests")  # records the admin
    set_db_role(db, ADMIN_ID, role="Manager")                         # demoted; token still says Tenant Admin

    resp = await _call(db, ADMIN, "POST", f"/attendance/geofence-requests/{req['id']}/{action}")

    assert resp.status_code == 403 and "Sign in again" in resp.json()["detail"]
    assert _status(db, req["id"]) == "pending"
    assert _geofences(db) == []


async def test_deactivated_admin_cannot_review(db):
    req = await _request(db)
    await _call(db, ADMIN, "GET", "/attendance/geofence-requests")
    set_db_role(db, ADMIN_ID, is_active=False)

    resp = await _call(db, ADMIN, "POST", f"/attendance/geofence-requests/{req['id']}/approve")

    assert resp.status_code == 403
    assert _status(db, req["id"]) == "pending"


async def test_demoted_admin_cannot_change_the_location_directly(db):
    await _call(db, ADMIN, "GET", "/attendance/geofence-requests")
    set_db_role(db, ADMIN_ID, role="Manager")

    resp = await _call(db, ADMIN, "POST", "/attendance/geofence",
                       {"property_id": str(PROP_A), "center_lat": 1.0, "center_lng": 2.0, "radius_meters": 100})

    assert resp.status_code == 403
    assert _geofences(db) == []


async def test_requester_promoted_to_admin_still_cannot_approve_their_own(db):
    req = await _request(db)
    set_db_role(db, MANAGER_ID, role="Tenant Admin")
    promoted = user("Tenant Admin", user_id=MANAGER_ID)

    resp = await _call(db, promoted, "POST", f"/attendance/geofence-requests/{req['id']}/approve")

    assert resp.status_code == 403
    assert _status(db, req["id"]) == "pending"


async def test_manager_moved_to_another_property_can_still_cancel_their_request(db):
    req = await _request(db)
    moved = user("Manager", PROP_B, user_id=MANAGER_ID)

    resp = await _call(db, moved, "POST", f"/attendance/geofence-requests/{req['id']}/cancel")

    assert resp.status_code == 200 and resp.json()["status"] == "cancelled"


async def test_promoted_manager_with_an_old_token_cannot_review_yet(db):
    # DB says admin, token still says Manager: require_roles uses the token, so
    # the new rights apply after the next sign-in or token refresh.
    other_manager = user("Manager", PROP_A)
    req = await _request(db, who=other_manager)
    set_db_role(db, MANAGER_ID, role="Tenant Admin")

    resp = await _call(db, MANAGER, "POST", f"/attendance/geofence-requests/{req['id']}/approve")

    assert resp.status_code == 403
