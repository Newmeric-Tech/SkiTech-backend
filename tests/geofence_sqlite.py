"""
Shared harness for geofence permission/request tests: the attendance router
against in-memory SQLite (real PropertyGeofence table plus a minimal
properties table). Never touches the .env database.
"""
from uuid import uuid4

import httpx
from fastapi import FastAPI
from sqlalchemy import text

from app.api.v1.endpoints import attendance as attendance_routes
from tests.attendance_sqlite import make_db

TENANT, OTHER_TENANT = uuid4(), uuid4()
PROP_A, PROP_B, FOREIGN_PROP, DELETED_PROP = uuid4(), uuid4(), uuid4(), uuid4()


def make_env():
    engine, db = make_db()
    with engine.begin() as conn:
        # Only the columns geofence_scope reads (the real table has JSONB)
        conn.execute(text("CREATE TABLE properties (id CHAR(32), tenant_id CHAR(32), deleted_at DATETIME)"))
        for pid, tid, deleted in ((PROP_A, TENANT, None), (PROP_B, TENANT, None),
                                  (FOREIGN_PROP, OTHER_TENANT, None), (DELETED_PROP, TENANT, "2026-01-01")):
            conn.execute(text("INSERT INTO properties VALUES (:id, :t, :d)"),
                         {"id": pid.hex, "t": tid.hex, "d": deleted})
    return engine, db


def user(role, property_id=None, tenant=TENANT, user_id=None):
    return {"user_id": str(user_id or uuid4()), "tenant_id": str(tenant), "role": role,
            "property_id": str(property_id) if property_id else None}


def client_for(db, routers, who):
    app = FastAPI()
    for r in routers:
        app.include_router(r)
    app.dependency_overrides[attendance_routes.get_db] = lambda: db
    app.dependency_overrides[attendance_routes.get_current_user] = lambda: who
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t")


def body(property_id, lat=28.5, lng=77.2, radius=150, **kw):
    return {"property_id": str(property_id), "center_lat": lat, "center_lng": lng, "radius_meters": radius, **kw}
