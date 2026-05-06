"""
Attendance Endpoints - API routes for punch in/out and geolocation tracking

Provides endpoints for:
- Punch in/out operations with geolocation
- Attendance history and reports
- Geofence management
- Location-based compliance tracking
"""

from datetime import datetime, timezone
from typing import Any, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session

from app.core.security import get_current_user
from app.models.user import User
from app.schemas.attendance import (
    PunchInRequest, PunchOutRequest, AttendanceRecordResponse,
    PunchInResponse, PunchOutResponse, PropertyGeofenceCreate,
    PropertyGeofenceResponse, GeolocationHistoryFilter
)
from app.services.attendance_service import AttendanceService, GeofenceService
from app.utils.exceptions import NotFoundException, ValidationException
from db_connection import get_db


router = APIRouter(
    prefix="/attendance",
    tags=["Attendance & Geolocation"]
)


# ===========================
# Punch In/Out Endpoints
# ===========================

@router.post(
    "/punch-in",
    response_model=PunchInResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Punch In with Geolocation",
    description="Record employee punch in with geolocation data"
)
def punch_in(
    *,
    db: Session = Depends(get_db),
    punch_request: PunchInRequest,
    current_user: User = Depends(get_current_user),
    property_id: int = Query(..., description="Property ID for punch in")
) -> Any:
    """
    Create a punch in record with geolocation validation.
    
    The system will validate if the employee is within the hotel premises
    using geofencing. If outside, a warning will be returned.
    
    Query Parameters:
        - property_id: ID of the property/hotel
    
    Request Body:
        - geolocation: Device geolocation data (latitude, longitude, accuracy)
        - device_info: Information about the device (browser, OS)
        - notes: Optional notes about punch in
    
    Returns:
        - success: Whether punch in was successful
        - message: Status message
        - attendance_id: ID of created attendance record
        - is_within_geofence: Whether punch in was within geofence
        - distance_from_hotel: Distance from hotel center in meters
        - warning: Warning message if punch in was outside geofence
    """
    try:
        # Create punch in record
        attendance, has_warning, warning_msg = AttendanceService.create_punch_in(
            db=db,
            user_id=current_user.id,
            property_id=property_id,
            punch_in_request=punch_request
        )

        return PunchInResponse(
            success=True,
            message="Punched in successfully" if not has_warning else "Punched in (outside geofence)",
            attendance_id=attendance.id,
            is_within_geofence=attendance.is_within_geofence,
            distance_from_hotel=attendance.distance_from_hotel,
            warning=warning_msg
        )

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error creating punch in record"
        )


@router.post(
    "/punch-out",
    response_model=PunchOutResponse,
    status_code=status.HTTP_200_OK,
    summary="Punch Out with Geolocation",
    description="Record employee punch out with geolocation data"
)
def punch_out(
    *,
    db: Session = Depends(get_db),
    punch_request: PunchOutRequest,
    current_user: User = Depends(get_current_user),
    property_id: int = Query(..., description="Property ID for punch out")
) -> Any:
    """
    Create a punch out record and complete the attendance session.
    
    Query Parameters:
        - property_id: ID of the property/hotel
    
    Request Body:
        - geolocation: Device geolocation data
        - device_info: Device information
        - notes: Optional notes
    
    Returns:
        - success: Whether punch out was successful
        - message: Status message
        - attendance_id: ID of updated attendance record
        - hours_worked: Total hours worked in this session
        - is_within_geofence: Whether punch out was within geofence
        - distance_from_hotel: Distance from hotel center
        - warning: Warning if punch out was outside geofence
    """
    try:
        # Create punch out record
        attendance, has_warning, warning_msg = AttendanceService.create_punch_out(
            db=db,
            user_id=current_user.id,
            property_id=property_id,
            punch_out_request=punch_request
        )

        return PunchOutResponse(
            success=True,
            message="Punched out successfully" if not has_warning else "Punched out (outside geofence)",
            attendance_id=attendance.id,
            hours_worked=attendance.hours_worked or 0,
            is_within_geofence=attendance.punch_out_within_geofence or False,
            distance_from_hotel=attendance.punch_out_distance,
            warning=warning_msg
        )

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error creating punch out record"
        )


@router.get(
    "/status",
    summary="Check Current Punch Status",
    description="Get current punch in status for employee"
)
def get_punch_status(
    *,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    property_id: int = Query(..., description="Property ID")
) -> Any:
    """
    Check if user currently has an active punch in.
    
    Returns:
        - punched_in: Whether user is currently punched in
        - attendance_id: ID of active record (if punched in)
        - punch_in_time: Time of punch in
        - hours_so_far: Hours worked so far (if punched in)
        - is_within_geofence: Whether current punch in is within geofence
    """
    try:
        attendance = AttendanceService.get_active_punch_in(
            db=db,
            user_id=current_user.id,
            property_id=property_id
        )

        if not attendance:
            return {
                "punched_in": False,
                "message": "No active punch in"
            }

        # Calculate hours so far
        duration = datetime.now(timezone.utc) - attendance.punch_in_time
        hours_so_far = round(duration.total_seconds() / 3600, 2)

        return {
            "punched_in": True,
            "attendance_id": attendance.id,
            "punch_in_time": attendance.punch_in_time,
            "hours_so_far": hours_so_far,
            "is_within_geofence": attendance.is_within_geofence,
            "punch_in_location": {
                "latitude": attendance.punch_in_latitude,
                "longitude": attendance.punch_in_longitude,
                "address": attendance.punch_in_address
            }
        }

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error fetching punch status"
        )


# ===========================
# Attendance History Endpoints
# ===========================

@router.get(
    "/history",
    response_model=dict,
    summary="Get Attendance History",
    description="Retrieve attendance records with filtering options"
)
def get_attendance_history(
    *,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    property_id: Optional[int] = Query(None),
    start_date: Optional[datetime] = Query(None),
    end_date: Optional[datetime] = Query(None),
    is_within_geofence: Optional[bool] = Query(None),
    status: Optional[str] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100)
) -> Any:
    """
    Get attendance history for current user.
    
    Query Parameters:
        - property_id: Filter by property
        - start_date: Filter from date (ISO format)
        - end_date: Filter to date (ISO format)
        - is_within_geofence: Filter by geofence status
        - status: Filter by status (active, completed)
        - skip: Pagination skip
        - limit: Pagination limit (1-100)
    
    Returns:
        - total: Total number of records
        - count: Number of records in this page
        - records: List of attendance records
        - page_info: Pagination information
    """
    try:
        records, total_count = AttendanceService.get_attendance_history(
            db=db,
            user_id=current_user.id,
            property_id=property_id,
            start_date=start_date,
            end_date=end_date,
            is_within_geofence=is_within_geofence,
            status=status,
            skip=skip,
            limit=limit
        )

        return {
            "total": total_count,
            "count": len(records),
            "records": [AttendanceRecordResponse.from_orm(r) for r in records],
            "page_info": {
                "skip": skip,
                "limit": limit,
                "has_more": (skip + limit) < total_count
            }
        }

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error fetching attendance history"
        )


@router.get(
    "/daily-summary",
    summary="Get Daily Attendance Summary",
    description="Get attendance summary for a specific date"
)
def get_daily_summary(
    *,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    date: Optional[datetime] = Query(None, description="Date in ISO format (default: today)")
) -> Any:
    """
    Get daily attendance summary for the user.
    
    Query Parameters:
        - date: Date to summarize (ISO format, default: today)
    
    Returns:
        - date: Date summarized
        - total_records: Number of attendance records
        - total_hours_worked: Total hours worked
        - within_geofence_count: Records within geofence
        - outside_geofence_count: Records outside geofence
    """
    try:
        if not date:
            date = datetime.now(timezone.utc)

        summary = AttendanceService.get_daily_summary(
            db=db,
            user_id=current_user.id,
            date=date
        )

        return summary

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error calculating daily summary"
        )


# ===========================
# Geofence Management Endpoints
# ===========================

@router.post(
    "/geofence",
    response_model=PropertyGeofenceResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create Property Geofence",
    description="Create geofence for a property (Admin only)"
)
def create_geofence(
    *,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    geofence_data: PropertyGeofenceCreate
) -> Any:
    """
    Create a geofence for a property.
    
    Requires admin or manager role.
    
    Request Body:
        - property_id: ID of the property
        - property_name: Name of the property
        - center_latitude: Latitude of geofence center
        - center_longitude: Longitude of geofence center
        - radius_meters: Geofence radius (50-5000 meters)
        - address: Optional address
        - city, state, country, zip_code: Optional location details
    
    Returns:
        Created geofence details
    """
    # Check authorization (admin/manager only)
    if current_user.role not in ["admin", "manager"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admins and managers can create geofences"
        )

    try:
        geofence = GeofenceService.create_geofence(
            db=db,
            geofence_data=geofence_data
        )

        return PropertyGeofenceResponse.from_orm(geofence)

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error creating geofence"
        )


@router.get(
    "/geofence/{property_id}",
    response_model=PropertyGeofenceResponse,
    summary="Get Property Geofence",
    description="Get geofence configuration for a property"
)
def get_geofence(
    *,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    property_id: int
) -> Any:
    """
    Get geofence configuration for a property.
    
    Path Parameters:
        - property_id: ID of the property
    
    Returns:
        Geofence details or 404 if not found
    """
    try:
        geofence = GeofenceService.get_geofence(db=db, property_id=property_id)

        if not geofence:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Geofence not found for property {property_id}"
            )

        return PropertyGeofenceResponse.from_orm(geofence)

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error fetching geofence"
        )


@router.put(
    "/geofence/{geofence_id}",
    response_model=PropertyGeofenceResponse,
    summary="Update Property Geofence",
    description="Update geofence configuration (Admin only)"
)
def update_geofence(
    *,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    geofence_id: int,
    geofence_data: PropertyGeofenceCreate
) -> Any:
    """
    Update a property geofence.
    
    Requires admin or manager role.
    
    Path Parameters:
        - geofence_id: ID of the geofence
    
    Returns:
        Updated geofence details
    """
    # Check authorization
    if current_user.role not in ["admin", "manager"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admins and managers can update geofences"
        )

    try:
        geofence = GeofenceService.update_geofence(
            db=db,
            geofence_id=geofence_id,
            geofence_data=geofence_data
        )

        return PropertyGeofenceResponse.from_orm(geofence)

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error updating geofence"
        )


@router.delete(
    "/geofence/{geofence_id}",
    summary="Delete Property Geofence",
    description="Delete geofence configuration (Admin only)"
)
def delete_geofence(
    *,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    geofence_id: int
) -> Any:
    """
    Delete a property geofence.
    
    Requires admin or manager role.
    
    Path Parameters:
        - geofence_id: ID of the geofence
    
    Returns:
        Success message
    """
    # Check authorization
    if current_user.role not in ["admin", "manager"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admins and managers can delete geofences"
        )

    try:
        GeofenceService.delete_geofence(db=db, geofence_id=geofence_id)

        return {
            "success": True,
            "message": "Geofence deleted successfully"
        }

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error deleting geofence"
        )


@router.get(
    "/geofence",
    response_model=dict,
    summary="List All Geofences",
    description="List all property geofences"
)
def list_geofences(
    *,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500)
) -> Any:
    """
    List all property geofences.
    
    Query Parameters:
        - skip: Pagination skip
        - limit: Pagination limit (1-500)
    
    Returns:
        - total: Total number of geofences
        - count: Number in this page
        - geofences: List of geofences
    """
    try:
        geofences, total_count = GeofenceService.list_geofences(
            db=db,
            skip=skip,
            limit=limit
        )

        return {
            "total": total_count,
            "count": len(geofences),
            "geofences": [PropertyGeofenceResponse.from_orm(g) for g in geofences],
            "page_info": {
                "skip": skip,
                "limit": limit,
                "has_more": (skip + limit) < total_count
            }
        }

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error fetching geofences"
        )
