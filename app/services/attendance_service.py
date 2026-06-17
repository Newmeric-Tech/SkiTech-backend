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
from app.schemas.attendance import PunchInRequest, PunchOutRequest, PropertyGeofenceCreate
from app.utils.geolocation import is_within_geofence, validate_coordinates, get_accuracy_warning


class AttendanceService:
    @staticmethod
    async def create_punch_in(
        db: AsyncSession,
        user_id: str,
        property_id: str,
        tenant_id: str,
        punch_in_request: PunchInRequest,
    ) -> Tuple[AttendanceRecord, bool, Optional[str]]:
        is_valid, error_msg = validate_coordinates(
            punch_in_request.geolocation.latitude,
            punch_in_request.geolocation.longitude,
            punch_in_request.geolocation.accuracy,
        )
        if not is_valid:
            raise ValueError(f"Invalid coordinates: {error_msg}")

        result = await db.execute(
            select(PropertyGeofence).where(
                PropertyGeofence.property_id == property_id,
                PropertyGeofence.tenant_id == tenant_id,
            )
        )
        geofence = result.scalar_one_or_none()

        is_within = False
        distance = None
        warnings = []

        if geofence:
            is_within, distance, _ = is_within_geofence(
                punch_in_request.geolocation.latitude,
                punch_in_request.geolocation.longitude,
                geofence.center_lat, geofence.center_lng, geofence.radius_meters,
            )
            if not is_within:
                warnings.append(f"Punch in outside geofence. Distance: {distance:.2f}m from property center.")

        accuracy_warning = get_accuracy_warning(punch_in_request.geolocation.accuracy)
        if accuracy_warning:
            warnings.append(accuracy_warning)
        warning = " ".join(warnings) or None

        attendance = AttendanceRecord(
            user_id=user_id, property_id=property_id, tenant_id=tenant_id,
            punch_in_time=datetime.now(timezone.utc),
            punch_in_lat=punch_in_request.geolocation.latitude,
            punch_in_lon=punch_in_request.geolocation.longitude,
            punch_in_acc=punch_in_request.geolocation.accuracy,
            is_within_fence=is_within, distance_meters=distance,
            status="active", notes=punch_in_request.notes,
        )
        db.add(attendance)
        await db.commit()
        await db.refresh(attendance)
        return attendance, bool(warning), warning

    @staticmethod
    async def create_punch_out(
        db: AsyncSession,
        user_id: str,
        property_id: str,
        tenant_id: str,
        punch_out_request: PunchOutRequest,
    ) -> Tuple[AttendanceRecord, bool, Optional[str]]:
        is_valid, error_msg = validate_coordinates(
            punch_out_request.geolocation.latitude,
            punch_out_request.geolocation.longitude,
            punch_out_request.geolocation.accuracy,
        )
        if not is_valid:
            raise ValueError(f"Invalid coordinates: {error_msg}")

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
        attendance = result.scalars().first()

        if not attendance:
            raise ValueError("No active punch in record found for this user")

        geo_result = await db.execute(
            select(PropertyGeofence).where(
                PropertyGeofence.property_id == property_id,
                PropertyGeofence.tenant_id == tenant_id,
            )
        )
        geofence = geo_result.scalar_one_or_none()

        is_within = False
        distance = None
        warnings = []

        if geofence:
            is_within, distance, _ = is_within_geofence(
                punch_out_request.geolocation.latitude,
                punch_out_request.geolocation.longitude,
                geofence.center_lat, geofence.center_lng, geofence.radius_meters,
            )
            if not is_within:
                warnings.append(f"Punch out outside geofence. Distance: {distance:.2f}m from property center.")

        accuracy_warning = get_accuracy_warning(punch_out_request.geolocation.accuracy)
        if accuracy_warning:
            warnings.append(accuracy_warning)
        warning = " ".join(warnings) or None

        attendance.punch_out_time = datetime.now(timezone.utc)
        attendance.punch_out_lat = punch_out_request.geolocation.latitude
        attendance.punch_out_lon = punch_out_request.geolocation.longitude
        attendance.status = "completed"
        if punch_out_request.notes:
            attendance.notes = punch_out_request.notes

        duration = attendance.punch_out_time - attendance.punch_in_time
        attendance.hours_worked = round(duration.total_seconds() / 3600, 2)

        await db.commit()
        await db.refresh(attendance)
        return attendance, bool(warning), warning

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
        db: AsyncSession, geofence_id: str, geofence_data: PropertyGeofenceCreate
    ) -> PropertyGeofence:
        result = await db.execute(
            select(PropertyGeofence).where(PropertyGeofence.id == geofence_id)
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
    async def delete_geofence(db: AsyncSession, geofence_id: str) -> bool:
        result = await db.execute(
            select(PropertyGeofence).where(PropertyGeofence.id == geofence_id)
        )
        geofence = result.scalar_one_or_none()
        if not geofence:
            raise ValueError(f"Geofence {geofence_id} not found")
        await db.delete(geofence)
        await db.commit()
        return True
