"""
Direct geofence changes: only Super Admin / Tenant Admin / Co Admin, on a
property of their own tenant (Co Admin: their scoped property). Managers
get 403 pointing to the request flow. Reads return real UUIDs (the
response model used to 500 on them).

In-memory SQLite only; never touches the .env database.
"""
import pytest
from sqlalchemy import select

from app.api.v1.endpoints import attendance as attendance_routes
from app.models.attendance import PropertyGeofence
from tests.geofence_sqlite import (
    DELETED_PROP, FOREIGN_PROP, PROP_A, PROP_B, TENANT, body, client_for, make_env, user,
)

ROUTERS = [attendance_routes.router]


@pytest.fixture
def db():
    engine, db = make_env()
    yield db
    db.session.close()
    engine.dispose()


def _geofences(db):
    db.session.expire_all()
    return db.session.execute(select(PropertyGeofence)).scalars().all()


async def _post(db, who, payload):
    async with client_for(db, ROUTERS, who) as c:
        return await c.post("/attendance/geofence", json=payload)


@pytest.mark.parametrize("role", ["Super Admin", "Tenant Admin", "Co Admin"])
async def test_admins_set_the_location_directly(db, role):
    resp = await _post(db, user(role), body(PROP_A, radius=150, address="Main gate"))

    assert resp.status_code == 201
    out = resp.json()
    assert out["property_id"] == str(PROP_A) and out["tenant_id"] == str(TENANT)
    assert out["radius_meters"] == 150
    async with client_for(db, ROUTERS, user("Tenant Admin")) as c:
        got = await c.get(f"/attendance/geofence/{PROP_A}")
    assert got.status_code == 200 and got.json()["id"] == out["id"]


async def test_manager_gets_403_pointing_to_requests(db):
    resp = await _post(db, user("Manager", PROP_A), body(PROP_A))

    assert resp.status_code == 403
    assert "geofence-requests" in resp.json()["detail"] and "approve" in resp.json()["detail"]
    assert _geofences(db) == []


async def test_manager_cannot_update_or_delete(db):
    created = (await _post(db, user("Tenant Admin"), body(PROP_A, radius=150))).json()
    async with client_for(db, ROUTERS, user("Manager", PROP_A)) as c:
        put = await c.put(f"/attendance/geofence/{created['id']}", json=body(PROP_A, radius=900))
        delete = await c.delete(f"/attendance/geofence/{created['id']}")

    assert put.status_code == 403 and delete.status_code == 403
    [g] = _geofences(db)
    assert g.radius_meters == 150


async def test_staff_is_forbidden(db):
    assert (await _post(db, user("Staff", PROP_A), body(PROP_A))).status_code == 403


@pytest.mark.parametrize("prop", [FOREIGN_PROP, DELETED_PROP])
async def test_other_tenant_or_deleted_property_is_404(db, prop):
    resp = await _post(db, user("Tenant Admin"), body(prop))

    assert resp.status_code == 404
    assert _geofences(db) == []


async def test_co_admin_is_limited_to_their_property(db):
    assert (await _post(db, user("Co Admin", PROP_A), body(PROP_B))).status_code == 404
    assert (await _post(db, user("Co Admin", PROP_A), body(PROP_A))).status_code == 201


@pytest.mark.parametrize("payload", [
    body(PROP_A, radius=19), body(PROP_A, radius=2001), body(PROP_A, lat=90.5), body(PROP_A, lng=-181),
])
async def test_invalid_coordinates_or_radius_are_422(db, payload):
    assert (await _post(db, user("Tenant Admin"), payload)).status_code == 422


async def test_update_and_delete_by_admin(db):
    created = (await _post(db, user("Tenant Admin"), body(PROP_A, radius=150))).json()
    async with client_for(db, ROUTERS, user("Co Admin")) as c:
        put = await c.put(f"/attendance/geofence/{created['id']}", json=body(PROP_A, radius=400))
        assert put.status_code == 200 and put.json()["radius_meters"] == 400
        assert (await c.delete(f"/attendance/geofence/{created['id']}")).status_code == 200
    assert _geofences(db) == []


async def test_manager_reads_only_their_property(db):
    await _post(db, user("Tenant Admin"), body(PROP_A))
    await _post(db, user("Tenant Admin"), body(PROP_B))
    async with client_for(db, ROUTERS, user("Manager", PROP_A)) as c:
        own = await c.get(f"/attendance/geofence/{PROP_A}")
        other = await c.get(f"/attendance/geofence/{PROP_B}")
        listed = await c.get("/attendance/geofence")

    assert own.status_code == 200
    assert other.status_code == 404
    assert [g["property_id"] for g in listed.json()["geofences"]] == [str(PROP_A)]


async def test_other_tenant_cannot_read(db):
    await _post(db, user("Tenant Admin"), body(PROP_A))
    async with client_for(db, ROUTERS, user("Tenant Admin", tenant=FOREIGN_PROP)) as c:
        assert (await c.get(f"/attendance/geofence/{PROP_A}")).status_code == 404
        assert (await c.get("/attendance/geofence")).json()["total"] == 0
