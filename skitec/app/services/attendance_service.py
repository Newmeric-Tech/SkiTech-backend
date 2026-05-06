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
        user_id: int,
        property_id: int,
        punch_in_request: PunchInRequest
    ) -> Tuple[AttendanceRecord, bool, Optional[str]]:
        """
        Create a punch in record with geolocation validation.
        
        Args:
            db: Database session
            user_id: ID of the user punching in
            property_id: ID of the property
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
            PropertyGeofence.is_active == True
        ).first()

        # Check if within geofence
        is_within = False
        distance = None
        warning = None

        if geofence:
            is_within, distance, status = is_within_geofence(
                punch_in_request.geolocation.latitude,
                punch_in_request.geolocation.longitude,
                geofence.center_latitude,
                geofence.center_longitude,
                geofence.radius_meters
            )
            
            # Generate warning if outside geofence
            if not is_within:
                warning = f"Punch in outside geofence. Distance: {distance:.2f}m from property center."

        # Create attendance record
        attendance = AttendanceRecord(
            user_id=user_id,
            property_id=property_id,
            punch_in_time=datetime.now(timezone.utc),
            punch_in_latitude=punch_in_request.geolocation.latitude,
            punch_in_longitude=punch_in_request.geolocation.longitude,
            punch_in_accuracy=punch_in_request.geolocation.accuracy,
            punch_in_address=punch_in_request.geolocation.address,
            is_within_geofence=is_within,
            distance_from_hotel=distance,
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
        user_id: int,
        property_id: int,
        punch_out_request: PunchOutRequest
    ) -> Tuple[AttendanceRecord, bool, Optional[str]]:
        """
        Create a punch out record and complete attendance session.
        
        Args:
            db: Database session
            user_id: ID of the user punching out
            property_id: ID of the property
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
                AttendanceRecord.status == "active",
                AttendanceRecord.punch_out_time == None
            )
        ).order_by(desc(AttendanceRecord.punch_in_time)).first()

        if not attendance:
            raise ValueError("No active punch in record found for this user")

        # Get property geofence
        geofence = db.query(PropertyGeofence).filter(
            PropertyGeofence.property_id == property_id,
            PropertyGeofence.is_active == True
        ).first()

        # Check if within geofence
        is_within = False
        distance = None
        warning = None

        if geofence:
            is_within, distance, status = is_within_geofence(
                punch_out_request.geolocation.latitude,
                punch_out_request.geolocation.longitude,
                geofence.center_latitude,
                geofence.center_longitude,
                geofence.radius_meters
            )
            
            # Generate warning if outside geofence
            if not is_within:
                warning = f"Punch out outside geofence. Distance: {distance:.2f}m from property center."

        # Update attendance record
        attendance.punch_out_time = datetime.now(timezone.utc)
        attendance.punch_out_latitude = punch_out_request.geolocation.latitude
        attendance.punch_out_longitude = punch_out_request.geolocation.longitude
        attendance.punch_out_accuracy = punch_out_request.geolocation.accuracy
        attendance.punch_out_address = punch_out_request.geolocation.address
        attendance.punch_out_within_geofence = is_within
        attendance.punch_out_distance = distance
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
        user_id: int,
        property_id: int
    ) -> Optional[AttendanceRecord]:
        """
        Get active punch in record for user.
        
        Args:
            db: Database session
            user_id: User ID
            property_id: Property ID
        
        Returns:
            Active attendance record or None
        """
        return db.query(AttendanceRecord).filter(
            and_(
                AttendanceRecord.user_id == user_id,
                AttendanceRecord.property_id == property_id,
                AttendanceRecord.status == "active",
                AttendanceRecord.punch_out_time == None
            )
        ).order_by(desc(AttendanceRecord.punch_in_time)).first()

    @staticmethod
    def get_attendance_history(
        db: Session,
        user_id: int,
        property_id: Optional[int] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        is_within_geofence: Optional[bool] = None,
        status: Optional[str] = None,
        skip: int = 0,
        limit: int = 50
    ) -> Tuple[List[AttendanceRecord], int]:
        """
        Get attendance history with filtering options.
        
        Args:
            db: Database session
            user_id: User ID
            property_id: Filter by property (optional)
            start_date: Filter from date (optional)
            end_date: Filter to date (optional)
            is_within_geofence: Filter by geofence status (optional)
            status: Filter by status (optional)
            skip: Pagination skip
            limit: Pagination limit
        
        Returns:
            Tuple of (records, total_count)
        """
        query = db.query(AttendanceRecord).filter(
            AttendanceRecord.user_id == user_id
        )

        # Apply filters
        if property_id:
            query = query.filter(AttendanceRecord.property_id == property_id)
        
        if start_date:
            query = query.filter(AttendanceRecord.punch_in_time >= start_date)
        
        if end_date:
            query = query.filter(AttendanceRecord.punch_in_time <= end_date)
        
        if is_within_geofence is not None:
            query = query.filter(AttendanceRecord.is_within_geofence == is_within_geofence)
        
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
        user_id: int,
        date: datetime
    ) -> dict:
        """
        Get daily attendance summary for a user.
        
        Args:
            db: Database session
            user_id: User ID
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
                AttendanceRecord.punch_in_time >= start_of_day,
                AttendanceRecord.punch_in_time < end_of_day,
                AttendanceRecord.status == "completed"
            )
        ).all()

        total_hours = sum(r.hours_worked or 0 for r in records)
        within_geofence_count = sum(1 for r in records if r.is_within_geofence)
        outside_geofence_count = len(records) - within_geofence_count

        return {
            "date": date.date().isoformat(),
            "total_records": len(records),
            "total_hours_worked": round(total_hours, 2),
            "within_geofence_count": within_geofence_count,
            "outside_geofence_count": outside_geofence_count,
            "records": records
        }


class GeofenceService:
    """Service for managing property geofences"""

    @staticmethod
    def create_geofence(
        db: Session,
        geofence_data: PropertyGeofenceCreate
    ) -> PropertyGeofence:
        """
        Create a new property geofence.
        
        Args:
            db: Database session
            geofence_data: Geofence configuration data
        
        Returns:
            Created geofence record
        """
        # Check if geofence already exists for property
        existing = db.query(PropertyGeofence).filter(
            PropertyGeofence.property_id == geofence_data.property_id
        ).first()

        if existing:
            raise ValueError(f"Geofence already exists for property {geofence_data.property_id}")

        geofence = PropertyGeofence(
            property_id=geofence_data.property_id,
            property_name=geofence_data.property_name,
            center_latitude=geofence_data.center_latitude,
            center_longitude=geofence_data.center_longitude,
            radius_meters=geofence_data.radius_meters,
            address=geofence_data.address,
            city=geofence_data.city,
            state=geofence_data.state,
            country=geofence_data.country,
            zip_code=geofence_data.zip_code,
            is_active=True,
            description=geofence_data.description
        )

        db.add(geofence)
        db.commit()
        db.refresh(geofence)

        return geofence

    @staticmethod
    def update_geofence(
        db: Session,
        geofence_id: int,
        geofence_data: PropertyGeofenceCreate
    ) -> PropertyGeofence:
        """
        Update an existing property geofence.
        
        Args:
            db: Database session
            geofence_id: Geofence ID
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
            setattr(geofence, field, value)

        db.commit()
        db.refresh(geofence)

        return geofence

    @staticmethod
    def get_geofence(
        db: Session,
        property_id: int
    ) -> Optional[PropertyGeofence]:
        """
        Get geofence for a property.
        
        Args:
            db: Database session
            property_id: Property ID
        
        Returns:
            Geofence record or None
        """
        return db.query(PropertyGeofence).filter(
            PropertyGeofence.property_id == property_id
        ).first()

    @staticmethod
    def list_geofences(
        db: Session,
        skip: int = 0,
        limit: int = 100
    ) -> Tuple[List[PropertyGeofence], int]:
        """
        List all geofences.
        
        Args:
            db: Database session
            skip: Pagination skip
            limit: Pagination limit
        
        Returns:
            Tuple of (geofences, total_count)
        """
        total_count = db.query(PropertyGeofence).count()
        geofences = db.query(PropertyGeofence).offset(skip).limit(limit).all()

        return geofences, total_count

    @staticmethod
    def delete_geofence(
        db: Session,
        geofence_id: int
    ) -> bool:
        """
        Delete a geofence (soft delete via is_active).
        
        Args:
            db: Database session
            geofence_id: Geofence ID
        
        Returns:
            True if successful
        """
        geofence = db.query(PropertyGeofence).filter(
            PropertyGeofence.id == geofence_id
        ).first()

        if not geofence:
            raise ValueError(f"Geofence {geofence_id} not found")

        geofence.is_active = False
        db.commit()

        return True
