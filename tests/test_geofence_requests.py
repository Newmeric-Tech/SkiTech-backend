"""
Geofence change requests: a Manager proposes, an admin approves (which
applies it to the live geofence in the same transaction) or rejects.

In-memory SQLite only; never touches the .env database.
"""
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.api.v1.endpoints import attendance as attendance_routes
from app.api.v1.endpoints import geofence_requests as request_routes
from app.models.attendance import AttendanceRecord, GeofenceChangeRequest, PropertyGeofence
from tests.geofence_sqlite import (
    DELETED_PROP, FOREIGN_PROP, OTHER_TENANT, PROP_A, PROP_B, TENANT, add_user, client_for, make_env, user,
)

ROUTERS = [attendance_routes.router, request_routes.router]
MANAGER_ID, OTHER_MANAGER_ID, ADMIN_ID = uuid4(), uuid4(), uuid4()
MANAGER = user("Manager", PROP_A, user_id=MANAGER_ID)
ADMIN = user("Tenant Admin", user_id=ADMIN_ID)


@pytest.fixture
def db():
    engine, db = make_env()
    add_user(db, MANAGER_ID, "Mina", "Rao")
    add_user(db, ADMIN_ID, "Omar", role="Tenant Admin")
    yield db
    db.session.close()
    engine.dispose()


def proposal(prop=PROP_A, lat=12.9716, lng=77.5946, radius=120, **kw):
    return {"property_id": str(prop), "center_lat": lat, "center_lng": lng, "radius_meters": radius, **kw}


async def _call(db, who, method, path, json=None):
    async with client_for(db, ROUTERS, who) as c:
        return await c.request(method, path, json=json)


async def _request(db, who=MANAGER, **kw):
    return await _call(db, who, "POST", "/attendance/geofence-requests", proposal(**kw))


def _geofence(db, prop=PROP_A):
    db.session.expire_all()
    return db.session.execute(
        select(PropertyGeofence).where(PropertyGeofence.property_id == prop)).scalar_one_or_none()


def _requests(db):
    db.session.expire_all()
    return db.session.execute(select(GeofenceChangeRequest)).scalars().all()


async def _set_live(db, radius=300):
    resp = await _call(db, ADMIN, "POST", "/attendance/geofence",
                       {"property_id": str(PROP_A), "center_lat": 1.0, "center_lng": 2.0, "radius_meters": radius})
    assert resp.status_code == 201


# ── create / list ──────────────────────────────────────────────────────────

async def test_manager_request_is_pending_and_leaves_live_geofence_alone(db):
    await _set_live(db, radius=300)

    resp = await _request(db, radius=120, address="Gate 2", note="Moved entrance")

    assert resp.status_code == 201
    out = resp.json()
    assert out["status"] == "pending" and out["requested_by"] == str(MANAGER_ID)
    assert out["requested_by_name"] == "Mina Rao" and out["property_name"]
    g = _geofence(db)
    assert (g.center_lat, g.center_lng, g.radius_meters) == (1.0, 2.0, 300)


async def test_first_time_setup_request_with_no_geofence(db):
    assert (await _request(db)).status_code == 201
    assert _geofence(db) is None


@pytest.mark.parametrize("prop", [PROP_B, FOREIGN_PROP, DELETED_PROP])
async def test_manager_only_requests_for_their_own_live_property(db, prop):
    assert (await _request(db, prop=prop)).status_code == 404
    assert _requests(db) == []


async def test_staff_cannot_request(db):
    assert (await _request(db, who=user("Staff", PROP_A))).status_code == 403


async def test_invalid_proposal_is_422(db):
    assert (await _request(db, radius=5)).status_code == 422
    assert (await _request(db, lat=100)).status_code == 422


async def test_new_request_replaces_the_pending_one(db):
    first = (await _request(db, radius=100)).json()
    second = (await _request(db, radius=150)).json()

    by_id = {str(r.id): r for r in _requests(db)}
    assert by_id[first["id"]].status == "cancelled"
    assert by_id[first["id"]].review_note == "Replaced by a newer request"
    assert by_id[second["id"]].status == "pending"


async def test_one_pending_per_property_is_enforced_by_the_database(db):
    for _ in range(2):
        db.session.add(GeofenceChangeRequest(id=uuid4(), tenant_id=TENANT, property_id=PROP_A,
                                             center_lat=1, center_lng=1, radius_meters=100, status="pending"))
    with pytest.raises(IntegrityError):
        db.session.commit()
    db.session.rollback()


async def test_listing_scopes(db):
    await _request(db)
    other_mgr = user("Manager", PROP_A, user_id=OTHER_MANAGER_ID)
    await _request(db, who=other_mgr, radius=200)   # replaces the first

    mine = (await _call(db, MANAGER, "GET", "/attendance/geofence-requests")).json()
    everyone = (await _call(db, ADMIN, "GET", "/attendance/geofence-requests")).json()
    pending = (await _call(db, ADMIN, "GET", "/attendance/geofence-requests?status=pending")).json()
    foreign = (await _call(db, user("Tenant Admin", tenant=OTHER_TENANT), "GET",
                           "/attendance/geofence-requests")).json()

    assert [r["requested_by"] for r in mine] == [str(MANAGER_ID)]
    assert len(everyone) == 2
    assert [r["requested_by"] for r in pending] == [str(OTHER_MANAGER_ID)]
    assert foreign == []


# ── review ─────────────────────────────────────────────────────────────────

async def test_approve_creates_the_live_geofence(db):
    req = (await _request(db, lat=12.97, lng=77.59, radius=120, address="Gate 2")).json()

    resp = await _call(db, ADMIN, "POST", f"/attendance/geofence-requests/{req['id']}/approve",
                       {"review_note": "Checked on site"})

    assert resp.status_code == 200
    out = resp.json()
    assert out["status"] == "approved" and out["reviewed_by"] == str(ADMIN_ID)
    assert out["review_note"] == "Checked on site" and out["reviewed_at"]
    g = _geofence(db)
    assert (g.center_lat, g.center_lng, g.radius_meters, g.address) == (12.97, 77.59, 120, "Gate 2")


async def test_approve_updates_an_existing_geofence(db):
    await _set_live(db, radius=300)
    req = (await _request(db, radius=90)).json()

    await _call(db, ADMIN, "POST", f"/attendance/geofence-requests/{req['id']}/approve")

    assert _geofence(db).radius_meters == 90
    assert len(db.session.execute(select(PropertyGeofence)).scalars().all()) == 1


async def test_reject_leaves_the_geofence_unchanged(db):
    await _set_live(db, radius=300)
    req = (await _request(db, radius=90)).json()

    resp = await _call(db, ADMIN, "POST", f"/attendance/geofence-requests/{req['id']}/reject",
                       {"review_note": "Wrong building"})

    assert resp.json()["status"] == "rejected" and resp.json()["review_note"] == "Wrong building"
    assert _geofence(db).radius_meters == 300


async def test_manager_cannot_approve_any_request(db):
    req = (await _request(db)).json()

    resp = await _call(db, MANAGER, "POST", f"/attendance/geofence-requests/{req['id']}/approve")

    assert resp.status_code == 403
    assert _geofence(db) is None


async def test_self_approval_is_blocked(db):
    # An admin may file a request too, but only another admin can approve it
    req = (await _request(db, who=ADMIN)).json()

    resp = await _call(db, ADMIN, "POST", f"/attendance/geofence-requests/{req['id']}/approve")

    assert resp.status_code == 403
    assert _geofence(db) is None
    other_admin = user("Co Admin")
    resp = await _call(db, other_admin, "POST", f"/attendance/geofence-requests/{req['id']}/approve")
    assert resp.status_code == 200


@pytest.mark.parametrize("second", ["approve", "reject"])
async def test_double_review_is_409(db, second):
    req = (await _request(db)).json()
    await _call(db, ADMIN, "POST", f"/attendance/geofence-requests/{req['id']}/approve")

    resp = await _call(db, user("Co Admin"), "POST", f"/attendance/geofence-requests/{req['id']}/{second}")

    assert resp.status_code == 409


async def test_other_tenant_admin_gets_404(db):
    req = (await _request(db)).json()
    foreign_admin = user("Tenant Admin", tenant=OTHER_TENANT)

    for action in ("approve", "reject", "cancel"):
        resp = await _call(db, foreign_admin, "POST", f"/attendance/geofence-requests/{req['id']}/{action}")
        assert resp.status_code == 404
    assert _requests(db)[0].status == "pending"


async def test_co_admin_scoped_to_another_property_gets_404(db):
    req = (await _request(db)).json()

    resp = await _call(db, user("Co Admin", PROP_B), "POST", f"/attendance/geofence-requests/{req['id']}/approve")

    assert resp.status_code == 404


async def test_co_admin_of_the_property_can_approve(db):
    req = (await _request(db)).json()

    resp = await _call(db, user("Co Admin", PROP_A), "POST", f"/attendance/geofence-requests/{req['id']}/approve")

    assert resp.status_code == 200 and _geofence(db) is not None


async def test_approving_for_a_deleted_property_is_409_but_reject_works(db):
    req = GeofenceChangeRequest(id=uuid4(), tenant_id=TENANT, property_id=DELETED_PROP, requested_by=MANAGER_ID,
                                center_lat=1, center_lng=1, radius_meters=100, status="pending")
    db.session.add(req)
    db.session.commit()

    approve = await _call(db, ADMIN, "POST", f"/attendance/geofence-requests/{req.id}/approve")
    reject = await _call(db, ADMIN, "POST", f"/attendance/geofence-requests/{req.id}/reject")

    assert approve.status_code == 409 and "deleted" in approve.json()["detail"]
    assert reject.status_code == 200
    assert _geofence(db, DELETED_PROP) is None


async def test_approve_while_someone_is_punched_in_keeps_their_open_shift(db):
    await _set_live(db, radius=300)
    shift = AttendanceRecord(id=uuid4(), tenant_id=TENANT, user_id=uuid4(), property_id=PROP_A,
                             punch_in_time=datetime.now(timezone.utc) - timedelta(hours=2),
                             punch_in_lat=1.0, punch_in_lon=2.0, is_within_fence=True, distance_meters=5.0,
                             status="active")
    db.session.add(shift)
    db.session.commit()
    req = (await _request(db, lat=40.0, lng=50.0, radius=100)).json()

    await _call(db, ADMIN, "POST", f"/attendance/geofence-requests/{req['id']}/approve")

    db.session.expire_all()
    still = db.session.get(AttendanceRecord, shift.id)
    assert still.status == "active" and still.punch_out_time is None
    assert still.is_within_fence is True and still.distance_meters == 5.0


# ── cancel ─────────────────────────────────────────────────────────────────

async def test_requester_can_cancel_while_pending(db):
    req = (await _request(db)).json()

    other = await _call(db, user("Manager", PROP_A), "POST", f"/attendance/geofence-requests/{req['id']}/cancel")
    own = await _call(db, MANAGER, "POST", f"/attendance/geofence-requests/{req['id']}/cancel")
    again = await _call(db, MANAGER, "POST", f"/attendance/geofence-requests/{req['id']}/cancel")

    assert other.status_code == 403
    assert own.status_code == 200 and own.json()["status"] == "cancelled"
    assert again.status_code == 409


async def test_cannot_cancel_an_approved_request(db):
    req = (await _request(db)).json()
    await _call(db, ADMIN, "POST", f"/attendance/geofence-requests/{req['id']}/approve")

    resp = await _call(db, MANAGER, "POST", f"/attendance/geofence-requests/{req['id']}/cancel")
    assert resp.status_code == 409
