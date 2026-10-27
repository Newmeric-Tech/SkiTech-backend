"""
Shared in-memory SQLite harness for the attendance service tests: the real
AttendanceRecord / PropertyGeofence tables behind an async-shaped wrapper.
Never touches the .env database.
"""
from uuid import uuid4

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.models.attendance import AttendanceRecord, PropertyGeofence
from app.schemas.attendance import GeolocationData, PunchInRequest, PunchOutRequest

# Geofence centre used by the tests; 0.001 deg of latitude is ~111 m.
CENTER_LAT, CENTER_LNG = 28.5244, 77.1855
RADIUS = 200


class AsyncSQLite:
    def __init__(self, session: Session):
        self.session = session

    async def execute(self, statement, params=None):
        return self.session.execute(statement, params) if params is not None else self.session.execute(statement)

    def add(self, obj):
        self.session.add(obj)

    async def flush(self):
        self.session.flush()

    async def commit(self):
        self.session.commit()

    async def rollback(self):
        self.session.rollback()

    async def refresh(self, obj):
        self.session.refresh(obj)


def make_db():
    engine = create_engine("sqlite://")
    AttendanceRecord.__table__.create(engine)
    PropertyGeofence.__table__.create(engine)
    return engine, AsyncSQLite(Session(engine))


def add_geofence(db: AsyncSQLite, tenant_id, property_id, radius=RADIUS):
    db.add(PropertyGeofence(id=uuid4(), tenant_id=tenant_id, property_id=property_id,
                            center_lat=CENTER_LAT, center_lng=CENTER_LNG, radius_meters=radius))
    db.session.commit()


def at(meters_north: float, accuracy=10.0) -> GeolocationData:
    return GeolocationData(latitude=CENTER_LAT + meters_north / 111_195, longitude=CENTER_LNG, accuracy=accuracy)


def punch_in(meters_north=0.0, accuracy=10.0):
    return PunchInRequest(geolocation=at(meters_north, accuracy))


def punch_out(meters_north=0.0, accuracy=10.0):
    return PunchOutRequest(geolocation=at(meters_north, accuracy))


def all_records(db: AsyncSQLite):
    db.session.expire_all()
    return db.session.execute(select(AttendanceRecord).order_by(AttendanceRecord.punch_in_time)).scalars().all()
