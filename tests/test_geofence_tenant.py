"""
Geofence update/delete are scoped to the caller's tenant: another tenant's
geofence behaves as not found.

Service tests run the real query on in-memory SQLite (UUID objects, since
SQLite's UUID type can't bind strings); route tests replace the service.
Nothing touches the .env database.
"""
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.api.v1.endpoints import attendance
from app.models.attendance import PropertyGeofence
from app.schemas.attendance import PropertyGeofenceCreate
from app.services.attendance_service import GeofenceService

MINE, OTHER = uuid4(), uuid4()


class SQLiteDB:
    def __init__(self, session):
        self.session = session

    async def execute(self, stmt):
        return self.session.execute(stmt)

    async def commit(self):
        self.session.commit()

    async def refresh(self, obj):
        self.session.refresh(obj)

    async def delete(self, obj):
        self.session.delete(obj)


@pytest.fixture
def env():
    engine = create_engine("sqlite://")
    PropertyGeofence.__table__.create(engine)
    session = Session(engine)
    geofences = {}
    for tenant in (MINE, OTHER):
        g = PropertyGeofence(id=uuid4(), tenant_id=tenant, property_id=uuid4(),
                             center_lat=1.0, center_lng=1.0, radius_meters=100)
        session.add(g)
        geofences[tenant] = g.id
    session.commit()
    yield SQLiteDB(session), session, geofences
    session.close()
    engine.dispose()


def _radius(session, geofence_id):
    session.expire_all()
    row = session.execute(select(PropertyGeofence).where(PropertyGeofence.id == geofence_id)).scalar_one_or_none()
    return row.radius_meters if row else None


def _update_data():
    return PropertyGeofenceCreate(property_id=str(uuid4()), center_lat=1.0, center_lng=1.0, radius_meters=999)


async def test_update_other_tenants_geofence_is_not_found(env):
    db, session, g = env

    with pytest.raises(ValueError, match="not found"):
        await GeofenceService.update_geofence(db=db, geofence_id=g[OTHER], tenant_id=MINE,
                                              geofence_data=_update_data())

    assert _radius(session, g[OTHER]) == 100


async def test_delete_other_tenants_geofence_is_not_found(env):
    db, session, g = env

    with pytest.raises(ValueError, match="not found"):
        await GeofenceService.delete_geofence(db=db, geofence_id=g[OTHER], tenant_id=MINE)

    assert _radius(session, g[OTHER]) == 100


async def test_own_geofence_can_be_updated_and_deleted(env):
    db, session, g = env

    await GeofenceService.update_geofence(db=db, geofence_id=g[MINE], tenant_id=MINE,
                                          geofence_data=_update_data())
    assert _radius(session, g[MINE]) == 999

    await GeofenceService.delete_geofence(db=db, geofence_id=g[MINE], tenant_id=MINE)
    assert _radius(session, g[MINE]) is None


@pytest.fixture
def route_calls(monkeypatch):
    calls = []

    # Another tenant's geofence id: the tenant-filtered lookup finds nothing
    async def not_found(db, geofence_id, tenant_id):
        calls.append({"geofence_id": geofence_id, "tenant_id": tenant_id})
        return None

    async def must_not_run(**kwargs):
        raise AssertionError("update/delete must not run for a geofence outside the tenant")

    monkeypatch.setattr(GeofenceService, "get_geofence_by_id", staticmethod(not_found))
    monkeypatch.setattr(GeofenceService, "update_geofence", staticmethod(must_not_run))
    monkeypatch.setattr(GeofenceService, "delete_geofence", staticmethod(must_not_run))
    app = FastAPI()
    app.include_router(attendance.router)
    app.dependency_overrides[attendance.get_db] = lambda: None
    app.dependency_overrides[attendance.get_current_user] = lambda: {"tenant_id": str(MINE), "role": "Tenant Admin"}
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t"), calls


@pytest.mark.parametrize("method", ["PUT", "DELETE"])
async def test_routes_pass_caller_tenant_and_return_404(route_calls, method):
    client, calls = route_calls
    geofence_id = str(uuid4())
    body = {"property_id": str(uuid4()), "center_lat": 1.0, "center_lng": 1.0, "radius_meters": 100}

    async with client:
        resp = await client.request(method, f"/attendance/geofence/{geofence_id}",
                                    json=body if method == "PUT" else None)

    assert resp.status_code == 404
    assert calls[0]["tenant_id"] == MINE
    assert str(calls[0]["geofence_id"]) == geofence_id
