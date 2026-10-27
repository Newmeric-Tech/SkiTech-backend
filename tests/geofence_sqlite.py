"""
Shared harness for geofence permission/request tests: the attendance router
against in-memory SQLite (real PropertyGeofence table plus a minimal
properties table). Never touches the .env database.
"""
from uuid import UUID, uuid4

import httpx
from fastapi import FastAPI
from sqlalchemy import text

from app.api.v1.endpoints import attendance as attendance_routes
from app.models.attendance import GeofenceChangeRequest
from app.models.inbox import InboxItem
from tests.attendance_sqlite import make_db

TENANT, OTHER_TENANT = uuid4(), uuid4()
PROP_A, PROP_B, FOREIGN_PROP, DELETED_PROP = uuid4(), uuid4(), uuid4(), uuid4()


def make_env():
    engine, db = make_db()
    GeofenceChangeRequest.__table__.create(engine)
    InboxItem.__table__.create(engine)
    with engine.begin() as conn:
        # Only the columns the code reads (the real tables have JSONB etc.)
        conn.execute(text("CREATE TABLE properties (id CHAR(32), tenant_id CHAR(32), name TEXT, deleted_at DATETIME)"))
        conn.execute(text("CREATE TABLE roles (id CHAR(32), name TEXT)"))
        conn.execute(text("CREATE TABLE users (id CHAR(32), first_name TEXT, last_name TEXT, role_id CHAR(32), "
                          "is_active BOOLEAN DEFAULT 1, deleted_at DATETIME)"))
        for pid, tid, deleted in ((PROP_A, TENANT, None), (PROP_B, TENANT, None),
                                  (FOREIGN_PROP, OTHER_TENANT, None), (DELETED_PROP, TENANT, "2026-01-01")):
            conn.execute(text("INSERT INTO properties VALUES (:id, :t, :n, :d)"),
                         {"id": pid.hex, "t": tid.hex, "n": f"Property {pid.hex[:4]}", "d": deleted})
    return engine, db


def _role_id(conn, role):
    found = conn.execute(text("SELECT id FROM roles WHERE name = :n"), {"n": role}).scalar()
    if found:
        return found
    rid = uuid4().hex
    conn.execute(text("INSERT INTO roles VALUES (:id, :n)"), {"id": rid, "n": role})
    return rid


def add_user(db, user_id, first, last=None, role="Manager"):
    with db.session.bind.begin() as conn:
        conn.execute(text("INSERT INTO users (id, first_name, last_name, role_id) VALUES (:id, :f, :l, :r)"),
                     {"id": user_id.hex, "f": first, "l": last, "r": _role_id(conn, role)})


def set_db_role(db, user_id, role=None, is_active=True):
    """Change what the database says about a user, leaving their token alone."""
    with db.session.bind.begin() as conn:
        if role:
            conn.execute(text("UPDATE users SET role_id = :r WHERE id = :id"),
                         {"r": _role_id(conn, role), "id": user_id.hex})
        conn.execute(text("UPDATE users SET is_active = :a WHERE id = :id"), {"a": is_active, "id": user_id.hex})


def ensure_user(db, who):
    """Record a test caller in users with the role their token carries, if not there yet."""
    uid = UUID(who["user_id"])
    with db.session.bind.begin() as conn:
        exists = conn.execute(text("SELECT 1 FROM users WHERE id = :id"), {"id": uid.hex}).scalar()
    if not exists:
        add_user(db, uid, who["role"], role=who["role"])


def user(role, property_id=None, tenant=TENANT, user_id=None):
    return {"user_id": str(user_id or uuid4()), "tenant_id": str(tenant), "role": role,
            "property_id": str(property_id) if property_id else None}


def client_for(db, routers, who):
    ensure_user(db, who)
    app = FastAPI()
    for r in routers:
        app.include_router(r)
    app.dependency_overrides[attendance_routes.get_db] = lambda: db
    app.dependency_overrides[attendance_routes.get_current_user] = lambda: who
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t")


def body(property_id, lat=28.5, lng=77.2, radius=150, **kw):
    return {"property_id": str(property_id), "center_lat": lat, "center_lng": lng, "radius_meters": radius, **kw}
