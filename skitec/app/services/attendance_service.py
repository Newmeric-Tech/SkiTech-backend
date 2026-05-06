"""
Attendance Service

Handles business logic for:
- Punch in/out operations
- Geofence validation
- Attendance record management
- Geofence configuration
"""

from datetime import datetime, timezone, timedelta
from typing import Optional, Tuple, List

from sqlalchemy import and_, desc, func
from sqlalchemy.orm import Session

from app.models.attendance import AttendanceRecord, PropertyGeofence
from app.schemas.attendance import (
    PunchInRequest, PunchOutRequest, PropertyGeofenceCreate
)
from app.utils.geolocation import is_within_geofence, validate_coordinates


class AttendanceService:
    """Service for managing attendance records with geolocation"""

    @staticmethod
    def create_punch_in(
        db: Session,
        user_id: str,  # UUID
        property_id: str,  # UUID
        tenant_id: str,  # UUID
        punch_in_request: PunchInRequest
    ) -> Tuple[AttendanceRecord, bool, Optional[str]]:
        """
        Create a punch in record with geolocation validation.
        
        Args:
            db: Database session
            user_id: ID of the user punching in (UUID)
            property_id: ID of the property (UUID)
            tenant_id: ID of the tenant (UUID)
            punch_in_request: Punch in request with geolocation data
        
        Returns:
            Tuple of (attendance_record, warning_flag, warning_message)
        """
        # Validate coordinates
        is_valid, error_msg = validate_coordinates(
            punch_in_request.geolocation.latitude,
            punch_in_request.geolocation.longitude,
            punch_in_request.geolocation.accuracy
        )
        if not is_valid:
            raise ValueError(f"Invalid coordinates: {error_msg}")

        # Get property geofence
        geofence = db.query(PropertyGeofence).filter(
            PropertyGeofence.property_id == property_id,
            PropertyGeofence.tenant_id == tenant_id
        ).first()

        # Check if within geofence
        is_within = False
        distance = None
        warning = None

        if geofence:
            is_within, distance, status = is_within_geofence(
                punch_in_request.geolocation.latitude,
                punch_in_request.geolocation.longitude,
                geofence.center_lat,
                geofence.center_lng,
                geofence.radius_meters
            )
            
            # Generate warning if outside geofence
            if not is_within:
                warning = f"Punch in outside geofence. Distance: {distance:.2f}m from property center."

        # Create attendance record
        attendance = AttendanceRecord(
            user_id=user_id,
            property_id=property_id,
            tenant_id=tenant_id,
            punch_in_time=datetime.now(timezone.utc),
            punch_in_lat=punch_in_request.geolocation.latitude,
            punch_in_lon=punch_in_request.geolocation.longitude,
            punch_in_acc=punch_in_request.geolocation.accuracy,
            is_within_fence=is_within,
            distance_meters=distance,
            status="active",
            notes=punch_in_request.notes
        )

        db.add(attendance)
        db.commit()
        db.refresh(attendance)

        return attendance, bool(warning), warning

    @staticmethod
    def create_punch_out(
        db: Session,
        user_id: str,  # UUID
        property_id: str,  # UUID
        tenant_id: str,  # UUID
        punch_out_request: PunchOutRequest
    ) -> Tuple[AttendanceRecord, bool, Optional[str]]:
        """
        Create a punch out record and complete attendance session.
        
        Args:
            db: Database session
            user_id: ID of the user punching out (UUID)
            property_id: ID of the property (UUID)
            tenant_id: ID of the tenant (UUID)
            punch_out_request: Punch out request with geolocation data
        
        Returns:
            Tuple of (attendance_record, warning_flag, warning_message)
        """
        # Validate coordinates
        is_valid, error_msg = validate_coordinates(
            punch_out_request.geolocation.latitude,
            punch_out_request.geolocation.longitude,
            punch_out_request.geolocation.accuracy
        )
        if not is_valid:
            raise ValueError(f"Invalid coordinates: {error_msg}")

        # Get active attendance record
        attendance = db.query(AttendanceRecord).filter(
            and_(
                AttendanceRecord.user_id == user_id,
                AttendanceRecord.property_id == property_id,
                AttendanceRecord.tenant_id == tenant_id,
                AttendanceRecord.status == "active",
                AttendanceRecord.punch_out_time == None
            )
        ).order_by(desc(AttendanceRecord.punch_in_time)).first()

        if not attendance:
            raise ValueError("No active punch in record found for this user")

        # Get property geofence
        geofence = db.query(PropertyGeofence).filter(
            PropertyGeofence.property_id == property_id,
            PropertyGeofence.tenant_id == tenant_id
        ).first()

        # Check if within geofence
        is_within = False
        distance = None
        warning = None

        if geofence:
            is_within, distance, status = is_within_geofence(
                punch_out_request.geolocation.latitude,
                punch_out_request.geolocation.longitude,
                geofence.center_lat,
                geofence.center_lng,
                geofence.radius_meters
            )
            
            # Generate warning if outside geofence
            if not is_within:
                warning = f"Punch out outside geofence. Distance: {distance:.2f}m from property center."

        # Update attendance record
        attendance.punch_out_time = datetime.now(timezone.utc)
        attendance.punch_out_lat = punch_out_request.geolocation.latitude
        attendance.punch_out_lon = punch_out_request.geolocation.longitude
        attendance.status = "completed"
        
        if punch_out_request.notes:
            attendance.notes = punch_out_request.notes

        # Calculate hours worked
        duration = attendance.punch_out_time - attendance.punch_in_time
        hours_worked = duration.total_seconds() / 3600
        attendance.hours_worked = round(hours_worked, 2)

        db.commit()
        db.refresh(attendance)

        return attendance, bool(warning), warning

    @staticmethod
    def get_active_punch_in(
        db: Session,
        user_id: str,  # UUID
        property_id: str,  # UUID
        tenant_id: str  # UUID
    ) -> Optional[AttendanceRecord]:
        """
        Get active punch in record for user.
        
        Args:
            db: Database session
            user_id: User ID (UUID)
            property_id: Property ID (UUID)
            tenant_id: Tenant ID (UUID)
        
        Returns:
            Active attendance record or None
        """
        return db.query(AttendanceRecord).filter(
            and_(
                AttendanceRecord.user_id == user_id,
                AttendanceRecord.property_id == property_id,
                AttendanceRecord.tenant_id == tenant_id,
                AttendanceRecord.status == "active",
                AttendanceRecord.punch_out_time == None
            )
        ).order_by(desc(AttendanceRecord.punch_in_time)).first()

    @staticmethod
    def get_attendance_history(
        db: Session,
        user_id: str,  # UUID
        tenant_id: str,  # UUID
        property_id: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        is_within_fence: Optional[bool] = None,
        status: Optional[str] = None,
        skip: int = 0,
        limit: int = 50
    ) -> Tuple[List[AttendanceRecord], int]:
        """
        Get attendance history with filtering options.
        
        Args:
            db: Database session
            user_id: User ID (UUID)
            tenant_id: Tenant ID (UUID)
            property_id: Filter by property (optional, UUID)
            start_date: Filter from date (optional)
            end_date: Filter to date (optional)
            is_within_fence: Filter by geofence status (optional)
            status: Filter by status (optional)
            skip: Pagination skip
            limit: Pagination limit
        
        Returns:
            Tuple of (records, total_count)
        """
        query = db.query(AttendanceRecord).filter(
            and_(
                AttendanceRecord.user_id == user_id,
                AttendanceRecord.tenant_id == tenant_id
            )
        )

        # Apply filters
        if property_id:
            query = query.filter(AttendanceRecord.property_id == property_id)
        
        if start_date:
            query = query.filter(AttendanceRecord.punch_in_time >= start_date)
        
        if end_date:
            query = query.filter(AttendanceRecord.punch_in_time <= end_date)
        
        if is_within_fence is not None:
            query = query.filter(AttendanceRecord.is_within_fence == is_within_fence)
        
        if status:
            query = query.filter(AttendanceRecord.status == status)

        # Get total count
        total_count = query.count()

        # Apply pagination and order
        records = query.order_by(
            desc(AttendanceRecord.punch_in_time)
        ).offset(skip).limit(limit).all()

        return records, total_count

    @staticmethod
    def get_daily_summary(
        db: Session,
        user_id: str,  # UUID
        tenant_id: str,  # UUID
        date: datetime
    ) -> dict:
        """
        Get daily attendance summary for a user.
        
        Args:
            db: Database session
            user_id: User ID (UUID)
            tenant_id: Tenant ID (UUID)
            date: Date to summarize
        
        Returns:
            Dictionary with daily statistics
        """
        # Get records for the day
        start_of_day = datetime.combine(date.date(), datetime.min.time()).replace(tzinfo=timezone.utc)
        end_of_day = start_of_day + timedelta(days=1)

        records = db.query(AttendanceRecord).filter(
            and_(
                AttendanceRecord.user_id == user_id,
                AttendanceRecord.tenant_id == tenant_id,
                AttendanceRecord.punch_in_time >= start_of_day,
                AttendanceRecord.punch_in_time < end_of_day,
                AttendanceRecord.status == "completed"
            )
        ).all()

        total_hours = sum(r.hours_worked or 0 for r in records)
        within_fence_count = sum(1 for r in records if r.is_within_fence)
        outside_fence_count = len(records) - within_fence_count

        return {
            "date": date.date().isoformat(),
            "total_records": len(records),
            "total_hours_worked": round(total_hours, 2),
            "within_fence_count": within_fence_count,
            "outside_fence_count": outside_fence_count,
            "records": records
        }


class GeofenceService:
    """Service for managing property geofences"""

    @staticmethod
    def create_geofence(
        db: Session,
        tenant_id: str,  # UUID
        geofence_data: PropertyGeofenceCreate
    ) -> PropertyGeofence:
        """
        Create a new property geofence.
        
        Args:
            db: Database session
            tenant_id: Tenant ID (UUID)
            geofence_data: Geofence configuration data
        
        Returns:
            Created geofence record
        """
        # Check if geofence already exists for property
        existing = db.query(PropertyGeofence).filter(
            PropertyGeofence.property_id == geofence_data.property_id,
            PropertyGeofence.tenant_id == tenant_id
        ).first()

        if existing:
            raise ValueError(f"Geofence already exists for property {geofence_data.property_id}")

        geofence = PropertyGeofence(
            property_id=geofence_data.property_id,
            tenant_id=tenant_id,
            property_name=geofence_data.property_name,
            center_lat=geofence_data.center_lat,
            center_lng=geofence_data.center_lng,
            radius_meters=geofence_data.radius_meters,
            address=geofence_data.address,
            city=geofence_data.city,
            country=geofence_data.country,
            alert_on_breach=geofence_data.alert_on_breach or True
        )

        db.add(geofence)
        db.commit()
        db.refresh(geofence)

        return geofence

    @staticmethod
    def update_geofence(
        db: Session,
        geofence_id: str,  # UUID
        geofence_data: PropertyGeofenceCreate
    ) -> PropertyGeofence:
        """
        Update an existing property geofence.
        
        Args:
            db: Database session
            geofence_id: Geofence ID (UUID)
            geofence_data: Updated geofence data
        
        Returns:
            Updated geofence record
        """
        geofence = db.query(PropertyGeofence).filter(
            PropertyGeofence.id == geofence_id
        ).first()

        if not geofence:
            raise ValueError(f"Geofence {geofence_id} not found")

        # Update fields
        for field, value in geofence_data.dict(exclude_unset=True).items():
            if value is not None and field != 'property_id':
                setattr(geofence, field, value)

        db.commit()
        db.refresh(geofence)

        return geofence

    @staticmethod
    def get_geofence(
        db: Session,
        property_id: str,  # UUID
        tenant_id: str  # UUID
    ) -> Optional[PropertyGeofence]:
        """
        Get geofence for a property.
        
        Args:
            db: Database session
            property_id: Property ID (UUID)
            tenant_id: Tenant ID (UUID)
        
        Returns:
            Geofence record or None
        """
        return db.query(PropertyGeofence).filter(
            PropertyGeofence.property_id == property_id,
            PropertyGeofence.tenant_id == tenant_id
        ).first()

    @staticmethod
    def list_geofences(
        db: Session,
        tenant_id: str,  # UUID
        skip: int = 0,
        limit: int = 100
    ) -> Tuple[List[PropertyGeofence], int]:
        """
        List all geofences for a tenant.
        
        Args:
            db: Database session
            tenant_id: Tenant ID (UUID)
            skip: Pagination skip
            limit: Pagination limit
        
        Returns:
            Tuple of (geofences, total_count)
        """
        query = db.query(PropertyGeofence).filter(
            PropertyGeofence.tenant_id == tenant_id
        )
        total_count = query.count()
        geofences = query.offset(skip).limit(limit).all()

        return geofences, total_count

    @staticmethod
    def delete_geofence(
        db: Session,
        geofence_id: str  # UUID
    ) -> bool:
        """
        Delete a geofence.
        
        Args:
            db: Database session
            geofence_id: Geofence ID (UUID)
        
        Returns:
            True if successful
        """
        geofence = db.query(PropertyGeofence).filter(
            PropertyGeofence.id == geofence_id
        ).first()

        if not geofence:
            raise ValueError(f"Geofence {geofence_id} not found")

        db.delete(geofence)
        db.commit()

        return True
