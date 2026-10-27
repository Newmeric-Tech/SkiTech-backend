"""
Missed punch-out corrections: the owner of an auto_closed shift claims a
punch-out time; a Manager of the property (staff requests) or an admin
approves it, completing the shift with hours from the approved time.

In-memory SQLite only; never touches the .env database.
"""
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select

from app.api.v1.endpoints import attendance_corrections as correction_routes
from app.models.attendance import AttendanceCorrectionRequest, AttendanceRecord
from app.models.inbox import InboxItem
from tests.geofence_sqlite import (
    OTHER_TENANT, PROP_A, PROP_B, TENANT, client_for, make_env, set_db_role, user,
)

ROUTERS = [correction_routes.router]
STAFF_ID, MANAGER_ID, OTHER_MANAGER_ID, ADMIN_ID = uuid4(), uuid4(), uuid4(), uuid4()
STAFF = user("Staff", PROP_A, user_id=STAFF_ID)
MANAGER = user("Manager", PROP_A, user_id=MANAGER_ID)
MANAGER_B = user("Manager", PROP_B, user_id=OTHER_MANAGER_ID)
ADMIN = user("Tenant Admin", user_id=ADMIN_ID)
PUNCH_IN = datetime.now(timezone.utc).replace(microsecond=0) - timedelta(days=2)


@pytest.fixture
def db():
    engine, db = make_env()
    yield db
    db.session.close()
    engine.dispose()


def _shift(db, owner=STAFF_ID, status="auto_closed", tenant=TENANT, prop=PROP_A):
    rec = AttendanceRecord(id=uuid4(), tenant_id=tenant, user_id=owner, property_id=prop, punch_in_time=PUNCH_IN,
                           punch_in_lat=0, punch_in_lon=0, is_within_fence=True, status=status)
    db.session.add(rec)
    db.session.commit()
    return rec.id


async def _call(db, who, method, path, json=None):
    async with client_for(db, ROUTERS, who) as c:
        return await c.request(method, path, json=json)


async def _claim(db, record_id, who=STAFF, hours=8.5, reason="Phone battery died"):
    claimed = (PUNCH_IN + timedelta(hours=hours)).isoformat()
    return await _call(db, who, "POST", "/attendance/correction-requests",
                       {"attendance_id": str(record_id), "claimed_punch_out_time": claimed, "reason": reason})


def _record(db, record_id):
    db.session.expire_all()
    return db.session.get(AttendanceRecord, record_id)


# ── submit ─────────────────────────────────────────────────────────────────

async def test_owner_submits_a_correction_for_an_auto_closed_shift(db):
    rid = _shift(db)

    resp = await _claim(db, rid, hours=8.5)

    assert resp.status_code == 201
    out = resp.json()
    assert out["status"] == "pending" and out["requester_role"] == "Staff"
    assert out["claimed_hours"] == 8.5 and out["attendance_id"] == str(rid)
    assert _record(db, rid).status == "auto_closed"   # untouched until approved
    db.session.expire_all()
    [item] = db.session.execute(select(InboxItem)).scalars().all()
    assert (item.item_type, item.recipient_role) == ("attendance_correction_request", "manager")


async def test_cannot_correct_someone_elses_or_another_tenants_shift(db):
    assert (await _claim(db, _shift(db, owner=uuid4()))).status_code == 404
    assert (await _claim(db, _shift(db, tenant=OTHER_TENANT))).status_code == 404


async def test_only_auto_closed_shifts_can_be_corrected(db):
    assert (await _claim(db, _shift(db, status="completed"))).status_code == 409
    assert (await _claim(db, _shift(db, status="active"))).status_code == 409


@pytest.mark.parametrize("hours", [0, -1, 16.5, 24 * 3])
async def test_claimed_time_must_be_after_punch_in_and_within_16_hours(db, hours):
    resp = await _claim(db, _shift(db), hours=hours)

    assert resp.status_code == 400


async def test_claimed_time_cannot_be_in_the_future(db):
    rec = AttendanceRecord(id=uuid4(), tenant_id=TENANT, user_id=STAFF_ID, property_id=PROP_A,
                           punch_in_time=datetime.now(timezone.utc) - timedelta(hours=2), punch_in_lat=0,
                           punch_in_lon=0, is_within_fence=True, status="auto_closed")
    db.session.add(rec)
    db.session.commit()
    future = (datetime.now(timezone.utc) + timedelta(hours=3)).isoformat()

    resp = await _call(db, STAFF, "POST", "/attendance/correction-requests",
                       {"attendance_id": str(rec.id), "claimed_punch_out_time": future, "reason": "left late"})

    assert resp.status_code == 400


async def test_a_reason_is_required(db):
    assert (await _claim(db, _shift(db), reason="")).status_code == 422


async def test_new_request_replaces_the_pending_one(db):
    rid = _shift(db)
    first = (await _claim(db, rid, hours=8)).json()
    second = (await _claim(db, rid, hours=9)).json()

    db.session.expire_all()
    rows = {str(r.id): r.status for r in db.session.execute(select(AttendanceCorrectionRequest)).scalars()}
    assert rows == {first["id"]: "cancelled", second["id"]: "pending"}


# ── review ─────────────────────────────────────────────────────────────────

async def test_manager_of_the_property_approves_a_staff_request(db):
    rid = _shift(db)
    req = (await _claim(db, rid, hours=8.5)).json()

    resp = await _call(db, MANAGER, "POST", f"/attendance/correction-requests/{req['id']}/approve",
                       {"review_note": "Confirmed with the night guard"})

    assert resp.status_code == 200 and resp.json()["status"] == "approved"
    rec = _record(db, rid)
    assert rec.status == "completed" and rec.hours_worked == 8.5
    assert rec.punch_out_time.replace(tzinfo=timezone.utc) == PUNCH_IN + timedelta(hours=8.5)


async def test_reject_leaves_the_shift_auto_closed(db):
    rid = _shift(db)
    req = (await _claim(db, rid)).json()

    resp = await _call(db, ADMIN, "POST", f"/attendance/correction-requests/{req['id']}/reject",
                       {"review_note": "No record of this"})

    assert resp.json()["status"] == "rejected"
    rec = _record(db, rid)
    assert rec.status == "auto_closed" and rec.hours_worked is None


async def test_manager_of_another_property_and_staff_cannot_review(db):
    req = (await _claim(db, _shift(db))).json()

    other_mgr = await _call(db, MANAGER_B, "POST", f"/attendance/correction-requests/{req['id']}/approve")
    coworker = await _call(db, user("Staff", PROP_A), "POST", f"/attendance/correction-requests/{req['id']}/approve")

    assert other_mgr.status_code == 404 and coworker.status_code == 404


async def test_managers_own_request_goes_to_admins_only(db):
    rid = _shift(db, owner=MANAGER_ID)
    req = (await _claim(db, rid, who=MANAGER)).json()
    assert req["requester_role"] == "Manager"

    self_review = await _call(db, MANAGER, "POST", f"/attendance/correction-requests/{req['id']}/approve")
    peer = await _call(db, user("Manager", PROP_A), "POST", f"/attendance/correction-requests/{req['id']}/approve")
    admin = await _call(db, ADMIN, "POST", f"/attendance/correction-requests/{req['id']}/approve")

    assert self_review.status_code == 403
    assert peer.status_code == 404
    assert admin.status_code == 200 and _record(db, rid).status == "completed"


async def test_admins_cannot_approve_their_own(db):
    rid = _shift(db, owner=ADMIN_ID)
    req = (await _claim(db, rid, who=ADMIN)).json()

    assert (await _call(db, ADMIN, "POST", f"/attendance/correction-requests/{req['id']}/approve")).status_code == 403
    assert (await _call(db, user("Co Admin"), "POST",
                        f"/attendance/correction-requests/{req['id']}/approve")).status_code == 200


@pytest.mark.parametrize("second", ["approve", "reject"])
async def test_double_review_is_409(db, second):
    req = (await _claim(db, _shift(db))).json()
    await _call(db, MANAGER, "POST", f"/attendance/correction-requests/{req['id']}/approve")

    assert (await _call(db, ADMIN, "POST", f"/attendance/correction-requests/{req['id']}/{second}")).status_code == 409


async def test_shift_changed_meanwhile_is_409(db):
    rid = _shift(db)
    req = (await _claim(db, rid)).json()
    rec = db.session.get(AttendanceRecord, rid)
    rec.status = "completed"
    db.session.commit()

    resp = await _call(db, MANAGER, "POST", f"/attendance/correction-requests/{req['id']}/approve")

    assert resp.status_code == 409


async def test_other_tenant_gets_404(db):
    req = (await _claim(db, _shift(db))).json()
    foreign = user("Tenant Admin", tenant=OTHER_TENANT)

    for action in ("approve", "reject", "cancel"):
        assert (await _call(db, foreign, "POST",
                            f"/attendance/correction-requests/{req['id']}/{action}")).status_code == 404


async def test_demoted_manager_with_an_old_token_cannot_review(db):
    req = (await _claim(db, _shift(db))).json()
    await _call(db, MANAGER, "GET", "/attendance/correction-requests")
    set_db_role(db, MANAGER_ID, role="Staff")

    resp = await _call(db, MANAGER, "POST", f"/attendance/correction-requests/{req['id']}/approve")

    assert resp.status_code == 403
    db.session.expire_all()
    assert db.session.get(AttendanceCorrectionRequest, UUID(req["id"])).status == "pending"


# ── cancel / list ──────────────────────────────────────────────────────────

async def test_requester_cancels_while_pending(db):
    req = (await _claim(db, _shift(db))).json()

    assert (await _call(db, MANAGER, "POST", f"/attendance/correction-requests/{req['id']}/cancel")).status_code == 404
    assert (await _call(db, STAFF, "POST", f"/attendance/correction-requests/{req['id']}/cancel")).json()["status"] == "cancelled"
    assert (await _call(db, STAFF, "POST", f"/attendance/correction-requests/{req['id']}/cancel")).status_code == 409


async def test_listing_scopes(db):
    staff_req = (await _claim(db, _shift(db))).json()
    mgr_req = (await _claim(db, _shift(db, owner=MANAGER_ID), who=MANAGER)).json()
    staff_b = user("Staff", PROP_B)
    b_req = (await _claim(db, _shift(db, owner=UUID(staff_b["user_id"]), prop=PROP_B), who=staff_b)).json()

    ids = lambda resp: {r["id"] for r in resp.json()}
    assert ids(await _call(db, STAFF, "GET", "/attendance/correction-requests")) == {staff_req["id"]}
    assert ids(await _call(db, MANAGER, "GET", "/attendance/correction-requests")) == {staff_req["id"], mgr_req["id"]}
    assert ids(await _call(db, MANAGER, "GET", "/attendance/correction-requests?mine=true")) == {mgr_req["id"]}
    assert ids(await _call(db, ADMIN, "GET", "/attendance/correction-requests")) == {
        staff_req["id"], mgr_req["id"], b_req["id"]}
    assert ids(await _call(db, user("Tenant Admin", tenant=OTHER_TENANT), "GET",
                           "/attendance/correction-requests")) == set()
