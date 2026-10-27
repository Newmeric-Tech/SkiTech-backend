"""
Attendance Service

Handles business logic for punch in/out, geofence validation,
attendance record management, and geofence configuration.
"""

from datetime import datetime, timezone, timedelta
from typing import Optional, Tuple, List

from sqlalchemy import select, and_, desc, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.attendance import AttendanceRecord, PropertyGeofence
from app.schemas.attendance import GeolocationData, PunchInRequest, PunchOutRequest, PropertyGeofenceCreate
from app.utils.geolocation import is_within_geofence, validate_coordinates, get_accuracy_warning

# An open record (status "active", no punch-out) older than this is a
# forgotten punch-out, not a shift: it is closed as AUTO_CLOSED with
# hours_worked NULL (unknown, excluded from totals) and punch_out_time NULL
# rather than inventing a punch-out time and payable hours.
STALE_SHIFT_HOURS = 16
# hours_so_far for a running shift never reports more than this.
MAX_SHIFT_HOURS = 12
AUTO_CLOSED = "auto_closed"
# A completed record above this many hours is a data error (e.g. a stale
# record closed against "now" before auto-closing existed): left out of
# totals and flagged for review.
MAX_PLAUSIBLE_HOURS = 24

NO_GEOFENCE_MESSAGE = (
    "Attendance location is not set for this property. Ask your manager or owner to set it."
)


def _as_utc(dt: datetime) -> datetime:
    """punch times are timestamptz; treat a naive value as UTC."""
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


def is_stale(record: AttendanceRecord, now: datetime) -> bool:
    return now - _as_utc(record.punch_in_time) > timedelta(hours=STALE_SHIFT_HOURS)


def auto_close(record: AttendanceRecord) -> None:
    """Close a forgotten open record without inventing hours (see STALE_SHIFT_HOURS)."""
    record.status = AUTO_CLOSED
    record.current_status = None


async def _open_records(db: AsyncSession, user_id, property_id, tenant_id) -> List[AttendanceRecord]:
    """The user's open records at this property, newest first."""
    result = await db.execute(
        select(AttendanceRecord).where(
            and_(
                AttendanceRecord.user_id == user_id,
                AttendanceRecord.property_id == property_id,
                AttendanceRecord.tenant_id == tenant_id,
                AttendanceRecord.status == "active",
                AttendanceRecord.punch_out_time == None,
            )
        ).order_by(desc(AttendanceRecord.punch_in_time))
    )
    return list(result.scalars().all())


async def check_punch_location(
    db: AsyncSession, property_id: str, tenant_id: str, geolocation: GeolocationData
) -> Tuple[bool, float]:
    """
    Decide whether a punch may be recorded at this location. Returns
    (is_within_fence, distance_meters) or raises ValueError with a message
    for the user; callers must not write anything before this passes.

    Rejected: no geofence for the property (in the caller's tenant), GPS
    accuracy worse than get_accuracy_warning's 100 m threshold, or definitely
    outside: distance - accuracy > radius. A missing accuracy counts as 0.
    """
    is_valid, error_msg = validate_coordinates(
        geolocation.latitude, geolocation.longitude, geolocation.accuracy,
    )
    if not is_valid:
        raise ValueError(f"Invalid coordinates: {error_msg}")

    geofence = (await db.execute(
        select(PropertyGeofence).where(
            PropertyGeofence.property_id == property_id,
            PropertyGeofence.tenant_id == tenant_id,
        )
    )).scalar_one_or_none()
    if geofence is None:
        raise ValueError(NO_GEOFENCE_MESSAGE)

    if get_accuracy_warning(geolocation.accuracy):
        raise ValueError(
            f"GPS accuracy too low ({geolocation.accuracy:.0f} m), move to an open area and try again."
        )

    is_within, distance, _ = is_within_geofence(
        geolocation.latitude, geolocation.longitude,
        geofence.center_lat, geofence.center_lng, geofence.radius_meters,
    )
    accuracy = geolocation.accuracy or 0.0
    if distance - accuracy > geofence.radius_meters:
        raise ValueError(
            f"You are {distance:.0f} m from the property; punches are only allowed within "
            f"{geofence.radius_meters} m. Move closer and try again."
        )
    return is_within, distance


class AttendanceService:
    @staticmethod
    async def create_punch_in(
        db: AsyncSession,
        user_id: str,
        property_id: str,
        tenant_id: str,
        punch_in_request: PunchInRequest,
    ) -> Tuple[AttendanceRecord, bool, Optional[str]]:
        now = datetime.now(timezone.utc)
        open_records = await _open_records(db, user_id, property_id, tenant_id)
        if any(not is_stale(r, now) for r in open_records):
            raise ValueError("You already have an active punch-in — punch out first")

        # Raises before anything is written, stale records included
        is_within, distance = await check_punch_location(
            db, property_id, tenant_id, punch_in_request.geolocation
        )

        # Only stale records are left: they no longer block a new shift
        for record in open_records:
            auto_close(record)

        attendance = AttendanceRecord(
            user_id=user_id, property_id=property_id, tenant_id=tenant_id,
            punch_in_time=now,
            punch_in_lat=punch_in_request.geolocation.latitude,
            punch_in_lon=punch_in_request.geolocation.longitude,
            punch_in_acc=punch_in_request.geolocation.accuracy,
            is_within_fence=is_within, distance_meters=distance,
            status="active", notes=punch_in_request.notes,
        )
        db.add(attendance)
        await db.commit()
        await db.refresh(attendance)
        return attendance, False, None

    @staticmethod
    async def create_punch_out(
        db: AsyncSession,
        user_id: str,
        property_id: str,
        tenant_id: str,
        punch_out_request: PunchOutRequest,
    ) -> Tuple[AttendanceRecord, bool, Optional[str]]:
        open_records = await _open_records(db, user_id, property_id, tenant_id)
        if not open_records:
            raise ValueError("No active punch in record found for this user")

        # Raises before any open record is touched
        is_within, distance = await check_punch_location(
            db, property_id, tenant_id, punch_out_request.geolocation
        )

        now = datetime.now(timezone.utc)
        attendance, older = open_records[0], open_records[1:]
        # Every open record is closed, so the user ends up punched out; only
        # the newest gets real hours, and only if it is a plausible shift.
        for record in older:
            auto_close(record)
        if is_stale(attendance, now):
            auto_close(attendance)
            await db.commit()
            await db.refresh(attendance)
            return attendance, True, (
                f"Your open shift from {_as_utc(attendance.punch_in_time):%d %b %Y %H:%M} UTC was older than "
                f"{STALE_SHIFT_HOURS} hours, so it was closed without hours. Ask your manager to correct it."
            )

        attendance.punch_out_time = now
        attendance.punch_out_lat = punch_out_request.geolocation.latitude
        attendance.punch_out_lon = punch_out_request.geolocation.longitude
        attendance.punch_out_acc = punch_out_request.geolocation.accuracy
        attendance.punch_out_within_fence = is_within
        attendance.punch_out_distance_meters = distance
        attendance.status = "completed"
        if punch_out_request.notes:
            attendance.notes = punch_out_request.notes

        duration = attendance.punch_out_time - _as_utc(attendance.punch_in_time)
        attendance.hours_worked = round(duration.total_seconds() / 3600, 2)

        await db.commit()
        await db.refresh(attendance)
        return attendance, False, None

    @staticmethod
    async def get_active_punch_in(
        db: AsyncSession, user_id: str, property_id: str, tenant_id: str
    ) -> Optional[AttendanceRecord]:
        result = await db.execute(
            select(AttendanceRecord).where(
                and_(
                    AttendanceRecord.user_id == user_id,
                    AttendanceRecord.property_id == property_id,
                    AttendanceRecord.tenant_id == tenant_id,
                    AttendanceRecord.status == "active",
                    AttendanceRecord.punch_out_time == None,
                )
            ).order_by(desc(AttendanceRecord.punch_in_time))
        )
        return result.scalars().first()

    @staticmethod
    async def get_user_totals(
        db: AsyncSession,
        user_id: str,
        property_id: str,
        tenant_id: str,
        day_start: datetime,
        week_start: datetime,
        now: Optional[datetime] = None,
    ) -> dict:
        """
        The user's hours at this property since day_start and since
        week_start (records counted by punch_in_time): completed shifts of at
        most MAX_PLAUSIBLE_HOURS plus the running shift (capped at
        MAX_SHIFT_HOURS, ignored once stale). Implausible completed records
        and auto-closed ones are counted in needs_review_this_week instead.
        """
        now = now or datetime.now(timezone.utc)
        day_start, week_start = _as_utc(day_start), _as_utc(week_start)
        result = await db.execute(
            select(AttendanceRecord).where(
                and_(
                    AttendanceRecord.user_id == user_id,
                    AttendanceRecord.property_id == property_id,
                    AttendanceRecord.tenant_id == tenant_id,
                    AttendanceRecord.punch_in_time >= min(day_start, week_start),
                )
            )
        )
        records = list(result.scalars().all())

        def hours_of(r: AttendanceRecord) -> Optional[float]:
            """Countable hours of a record, or None if it needs review / has none."""
            if r.status == "completed":
                if r.hours_worked is None or r.hours_worked > MAX_PLAUSIBLE_HOURS:
                    return None
                return r.hours_worked
            if r.status == "active" and r.punch_out_time is None and not is_stale(r, now):
                elapsed = (now - _as_utc(r.punch_in_time)).total_seconds() / 3600
                return min(max(elapsed, 0.0), MAX_SHIFT_HOURS)
            return None

        def total(start: datetime) -> float:
            return round(sum(h for r in records
                             if _as_utc(r.punch_in_time) >= start and (h := hours_of(r)) is not None), 2)

        def needs_review(r: AttendanceRecord) -> bool:
            return r.status == AUTO_CLOSED or (
                r.status == "completed" and r.hours_worked is not None and r.hours_worked > MAX_PLAUSIBLE_HOURS)

        open_shift = next((h for r in records if r.status == "active" and (h := hours_of(r)) is not None), 0.0)
        return {
            "day_start": day_start,
            "week_start": week_start,
            "hours_today": total(day_start),
            "hours_this_week": total(week_start),
            "open_shift_hours": round(open_shift, 2),
            "needs_review_this_week": sum(
                1 for r in records if _as_utc(r.punch_in_time) >= week_start and needs_review(r)),
        }

    @staticmethod
    async def get_attendance_history(
        db: AsyncSession,
        user_id: str,
        tenant_id: str,
        property_id: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        is_within_fence: Optional[bool] = None,
        status: Optional[str] = None,
        skip: int = 0,
        limit: int = 50,
    ) -> Tuple[List[AttendanceRecord], int]:
        conditions = and_(
            AttendanceRecord.user_id == user_id,
            AttendanceRecord.tenant_id == tenant_id,
        )
        filters = [AttendanceRecord.user_id == user_id, AttendanceRecord.tenant_id == tenant_id]
        if property_id:
            filters.append(AttendanceRecord.property_id == property_id)
        if start_date:
            filters.append(AttendanceRecord.punch_in_time >= start_date)
        if end_date:
            filters.append(AttendanceRecord.punch_in_time <= end_date)
        if is_within_fence is not None:
            filters.append(AttendanceRecord.is_within_fence == is_within_fence)
        if status:
            filters.append(AttendanceRecord.status == status)

        count_result = await db.execute(
            select(func.count()).select_from(AttendanceRecord).where(and_(*filters))
        )
        total_count = count_result.scalar() or 0

        records_result = await db.execute(
            select(AttendanceRecord)
            .where(and_(*filters))
            .order_by(desc(AttendanceRecord.punch_in_time))
            .offset(skip)
            .limit(limit)
        )
        records = records_result.scalars().all()
        return list(records), total_count

    @staticmethod
    async def get_daily_summary(
        db: AsyncSession, user_id: str, tenant_id: str, date: datetime
    ) -> dict:
        start_of_day = datetime.combine(date.date(), datetime.min.time()).replace(tzinfo=timezone.utc)
        end_of_day = start_of_day + timedelta(days=1)

        result = await db.execute(
            select(AttendanceRecord).where(
                and_(
                    AttendanceRecord.user_id == user_id,
                    AttendanceRecord.tenant_id == tenant_id,
                    AttendanceRecord.punch_in_time >= start_of_day,
                    AttendanceRecord.punch_in_time < end_of_day,
                    AttendanceRecord.status == "completed",
                )
            )
        )
        records = result.scalars().all()

        total_hours = sum(r.hours_worked or 0 for r in records)
        within_fence_count = sum(1 for r in records if r.is_within_fence)

        return {
            "date": date.date().isoformat(),
            "total_records": len(records),
            "total_hours_worked": round(total_hours, 2),
            "within_fence_count": within_fence_count,
            "outside_fence_count": len(records) - within_fence_count,
            "records": records,
        }


    @staticmethod
    async def get_property_attendance_today(
        db: AsyncSession,
        property_id: str,
        tenant_id: str,
    ) -> List[AttendanceRecord]:
        from datetime import timezone, timedelta
        today = datetime.now(timezone.utc).date()
        start = datetime.combine(today, datetime.min.time()).replace(tzinfo=timezone.utc)
        end = start + timedelta(days=1)

        result = await db.execute(
            select(AttendanceRecord).where(
                and_(
                    AttendanceRecord.property_id == property_id,
                    AttendanceRecord.tenant_id == tenant_id,
                    AttendanceRecord.punch_in_time >= start,
                    AttendanceRecord.punch_in_time < end,
                )
            ).order_by(AttendanceRecord.punch_in_time)
        )
        all_records = list(result.scalars().all())

        from collections import defaultdict
        user_records: dict = defaultdict(list)
        for r in all_records:
            user_records[str(r.user_id)].append(r)

        deduped = []
        for recs in user_records.values():
            active = [r for r in recs if r.status == "active"]
            if active:
                deduped.append(max(active, key=lambda r: r.punch_in_time))
            else:
                deduped.append(max(recs, key=lambda r: r.punch_in_time))

        return sorted(deduped, key=lambda r: r.punch_in_time)

    @staticmethod
    async def get_property_attendance_week(
        db: AsyncSession,
        property_id: str,
        tenant_id: str,
    ) -> List[AttendanceRecord]:
        start = datetime.now(timezone.utc) - timedelta(days=6)
        start = start.replace(hour=0, minute=0, second=0, microsecond=0)

        result = await db.execute(
            select(AttendanceRecord).where(
                and_(
                    AttendanceRecord.property_id == property_id,
                    AttendanceRecord.tenant_id == tenant_id,
                    AttendanceRecord.punch_in_time >= start,
                )
            ).order_by(AttendanceRecord.punch_in_time)
        )
        return list(result.scalars().all())


class GeofenceService:
    @staticmethod
    async def create_geofence(
        db: AsyncSession, tenant_id: str, geofence_data: PropertyGeofenceCreate
    ) -> PropertyGeofence:
        result = await db.execute(
            select(PropertyGeofence).where(
                PropertyGeofence.property_id == geofence_data.property_id,
                PropertyGeofence.tenant_id == tenant_id,
            )
        )
        if result.scalar_one_or_none():
            raise ValueError(f"Geofence already exists for property {geofence_data.property_id}")

        geofence = PropertyGeofence(
            property_id=geofence_data.property_id, tenant_id=tenant_id,
            property_name=geofence_data.property_name,
            center_lat=geofence_data.center_lat, center_lng=geofence_data.center_lng,
            radius_meters=geofence_data.radius_meters,
            address=geofence_data.address, city=geofence_data.city, country=geofence_data.country,
            alert_on_breach=geofence_data.alert_on_breach or True,
        )
        db.add(geofence)
        await db.commit()
        await db.refresh(geofence)
        return geofence

    @staticmethod
    async def update_geofence(
        db: AsyncSession, geofence_id: str, tenant_id: str, geofence_data: PropertyGeofenceCreate
    ) -> PropertyGeofence:
        # Another tenant's geofence behaves as not found.
        result = await db.execute(
            select(PropertyGeofence).where(
                PropertyGeofence.id == geofence_id,
                PropertyGeofence.tenant_id == tenant_id,
            )
        )
        geofence = result.scalar_one_or_none()
        if not geofence:
            raise ValueError(f"Geofence {geofence_id} not found")
        for field, value in geofence_data.model_dump(exclude_unset=True).items():
            if value is not None and field != "property_id":
                setattr(geofence, field, value)
        await db.commit()
        await db.refresh(geofence)
        return geofence

    @staticmethod
    async def get_geofence(
        db: AsyncSession, property_id: str, tenant_id: str
    ) -> Optional[PropertyGeofence]:
        result = await db.execute(
            select(PropertyGeofence).where(
                PropertyGeofence.property_id == property_id,
                PropertyGeofence.tenant_id == tenant_id,
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def list_geofences(
        db: AsyncSession, tenant_id: str, skip: int = 0, limit: int = 100
    ) -> Tuple[List[PropertyGeofence], int]:
        count_result = await db.execute(
            select(func.count()).select_from(PropertyGeofence).where(
                PropertyGeofence.tenant_id == tenant_id
            )
        )
        total = count_result.scalar() or 0

        result = await db.execute(
            select(PropertyGeofence)
            .where(PropertyGeofence.tenant_id == tenant_id)
            .offset(skip)
            .limit(limit)
        )
        return list(result.scalars().all()), total

    @staticmethod
    async def delete_geofence(db: AsyncSession, geofence_id: str, tenant_id: str) -> bool:
        # Another tenant's geofence behaves as not found.
        result = await db.execute(
            select(PropertyGeofence).where(
                PropertyGeofence.id == geofence_id,
                PropertyGeofence.tenant_id == tenant_id,
            )
        )
        geofence = result.scalar_one_or_none()
        if not geofence:
            raise ValueError(f"Geofence {geofence_id} not found")
        await db.delete(geofence)
        await db.commit()
        return True
