"""
Attendance Endpoints - API routes for punch in/out and geolocation tracking
"""

from datetime import datetime, timezone
from typing import Any, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session

from app.core.security import get_current_user
from app.core.database import get_db_session
from app.models.models import User
from app.schemas.attendance import (
    PunchInRequest, PunchOutRequest, AttendanceRecordResponse,
    PunchInResponse, PunchOutResponse, PropertyGeofenceCreate,
    PropertyGeofenceResponse, GeolocationHistoryFilter
)
from app.services.attendance_service import AttendanceService, GeofenceService
from app.utils.exceptions import NotFoundException, ValidationException


router = APIRouter(prefix="/attendance", tags=["Attendance & Geolocation"])


# ===========================
# Punch In/Out Endpoints
# ===========================

@router.post("/punch-in", response_model=PunchInResponse, status_code=status.HTTP_201_CREATED)
def punch_in(
    *,
    db: Session = Depends(get_db_session),
    punch_request: PunchInRequest,
    current_user: User = Depends(get_current_user),
    property_id: str = Query(..., description="Property ID (UUID) for punch in")
) -> Any:
    try:
        attendance, has_warning, warning_msg = AttendanceService.create_punch_in(
            db=db, user_id=str(current_user.id), property_id=property_id,
            tenant_id=str(current_user.tenant_id), punch_in_request=punch_request
        )
        return PunchInResponse(
            success=True,
            message="Punched in successfully" if not has_warning else "Punched in (outside geofence)",
            attendance_id=str(attendance.id),
            is_within_fence=attendance.is_within_fence,
            distance_meters=attendance.distance_meters,
            warning=warning_msg
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error creating punch in record")


@router.post("/punch-out", response_model=PunchOutResponse, status_code=status.HTTP_200_OK)
def punch_out(
    *,
    db: Session = Depends(get_db_session),
    punch_request: PunchOutRequest,
    current_user: User = Depends(get_current_user),
    property_id: str = Query(..., description="Property ID (UUID) for punch out")
) -> Any:
    try:
        attendance, has_warning, warning_msg = AttendanceService.create_punch_out(
            db=db, user_id=str(current_user.id), property_id=property_id,
            tenant_id=str(current_user.tenant_id), punch_out_request=punch_request
        )
        return PunchOutResponse(
            success=True,
            message="Punched out successfully" if not has_warning else "Punched out (outside geofence)",
            attendance_id=str(attendance.id),
            hours_worked=attendance.hours_worked or 0,
            is_within_fence=attendance.punch_out_lat is not None,
            distance_meters=attendance.distance_meters,
            warning=warning_msg
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error creating punch out record")


@router.get("/status")
def get_punch_status(
    *,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
    property_id: str = Query(..., description="Property ID (UUID)")
) -> Any:
    try:
        attendance = AttendanceService.get_active_punch_in(
            db=db, user_id=str(current_user.id), property_id=property_id,
            tenant_id=str(current_user.tenant_id)
        )
        if not attendance:
            return {"punched_in": False, "message": "No active punch in"}

        duration = datetime.now(timezone.utc) - attendance.punch_in_time
        return {
            "punched_in": True,
            "attendance_id": str(attendance.id),
            "punch_in_time": attendance.punch_in_time,
            "hours_so_far": round(duration.total_seconds() / 3600, 2),
            "is_within_fence": attendance.is_within_fence,
            "punch_in_location": {"latitude": attendance.punch_in_lat, "longitude": attendance.punch_in_lon}
        }
    except Exception:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error fetching punch status")


# ===========================
# Attendance History
# ===========================

@router.get("/history")
def get_attendance_history(
    *,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
    property_id: Optional[str] = Query(None),
    start_date: Optional[datetime] = Query(None),
    end_date: Optional[datetime] = Query(None),
    is_within_fence: Optional[bool] = Query(None),
    status: Optional[str] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100)
) -> Any:
    try:
        records, total_count = AttendanceService.get_attendance_history(
            db=db, user_id=str(current_user.id), tenant_id=str(current_user.tenant_id),
            property_id=property_id, start_date=start_date, end_date=end_date,
            is_within_fence=is_within_fence, status=status, skip=skip, limit=limit
        )
        return {
            "total": total_count, "count": len(records),
            "records": [AttendanceRecordResponse.from_orm(r) for r in records],
            "page_info": {"skip": skip, "limit": limit, "has_more": (skip + limit) < total_count}
        }
    except Exception:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error fetching attendance history")


@router.get("/daily-summary")
def get_daily_summary(
    *,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
    date: Optional[datetime] = Query(None)
) -> Any:
    try:
        if not date:
            date = datetime.now(timezone.utc)
        return AttendanceService.get_daily_summary(
            db=db, user_id=str(current_user.id), tenant_id=str(current_user.tenant_id), date=date
        )
    except Exception:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error calculating daily summary")


# ===========================
# Geofence Management
# ===========================

@router.post("/geofence", response_model=PropertyGeofenceResponse, status_code=status.HTTP_201_CREATED)
def create_geofence(
    *,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
    geofence_data: PropertyGeofenceCreate
) -> Any:
    if current_user.role not in ["admin", "manager"]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only admins and managers can create geofences")
    try:
        geofence = GeofenceService.create_geofence(db=db, tenant_id=str(current_user.tenant_id), geofence_data=geofence_data)
        return PropertyGeofenceResponse.from_orm(geofence)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error creating geofence")


@router.get("/geofence/{property_id}", response_model=PropertyGeofenceResponse)
def get_geofence(
    *,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
    property_id: str
) -> Any:
    try:
        geofence = GeofenceService.get_geofence(db=db, property_id=property_id, tenant_id=str(current_user.tenant_id))
        if not geofence:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Geofence not found for property {property_id}")
        return PropertyGeofenceResponse.from_orm(geofence)
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error fetching geofence")


@router.put("/geofence/{geofence_id}", response_model=PropertyGeofenceResponse)
def update_geofence(
    *,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
    geofence_id: str,
    geofence_data: PropertyGeofenceCreate
) -> Any:
    if current_user.role not in ["admin", "manager"]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only admins and managers can update geofences")
    try:
        geofence = GeofenceService.update_geofence(db=db, geofence_id=geofence_id, geofence_data=geofence_data)
        return PropertyGeofenceResponse.from_orm(geofence)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error updating geofence")


@router.delete("/geofence/{geofence_id}")
def delete_geofence(
    *,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
    geofence_id: str
) -> Any:
    if current_user.role not in ["admin", "manager"]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only admins and managers can delete geofences")
    try:
        GeofenceService.delete_geofence(db=db, geofence_id=geofence_id)
        return {"success": True, "message": "Geofence deleted successfully"}
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error deleting geofence")


@router.get("/geofence")
def list_geofences(
    *,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500)
) -> Any:
    try:
        geofences, total_count = GeofenceService.list_geofences(db=db, tenant_id=str(current_user.tenant_id), skip=skip, limit=limit)
        return {
            "total": total_count, "count": len(geofences),
            "geofences": [PropertyGeofenceResponse.from_orm(g) for g in geofences],
            "page_info": {"skip": skip, "limit": limit, "has_more": (skip + limit) < total_count}
        }
    except Exception:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error fetching geofences")
