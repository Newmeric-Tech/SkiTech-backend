"""
Attendance Endpoints - API routes for punch in/out and geolocation tracking
"""

from datetime import datetime, timezone
from typing import Any, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user, require_permission
from app.core.database import get_db
from app.schemas.attendance import (
    PunchInRequest, PunchOutRequest, AttendanceRecordResponse,
    PunchInResponse, PunchOutResponse, PropertyGeofenceCreate,
    PropertyGeofenceResponse, GeolocationHistoryFilter,
)
from app.services.attendance_service import AttendanceService, GeofenceService

router = APIRouter(prefix="/attendance", tags=["Attendance & Geolocation"])


# ===========================
# Punch In/Out Endpoints
# ===========================

@router.post("/punch-in", response_model=PunchInResponse, status_code=status.HTTP_201_CREATED)
async def punch_in(
    punch_request: PunchInRequest,
    property_id: str = Query(..., description="Property ID (UUID) for punch in"),
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
) -> Any:
    try:
        attendance, has_warning, warning_msg = await AttendanceService.create_punch_in(
            db=db,
            user_id=user["user_id"],
            property_id=property_id,
            tenant_id=user["tenant_id"],
            punch_in_request=punch_request,
        )
        return PunchInResponse(
            success=True,
            message="Punched in successfully" if not has_warning else "Punched in (outside geofence)",
            attendance_id=str(attendance.id),
            is_within_fence=attendance.is_within_fence,
            distance_meters=attendance.distance_meters,
            warning=warning_msg,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error creating punch in record")


@router.post("/punch-out", response_model=PunchOutResponse, status_code=status.HTTP_200_OK)
async def punch_out(
    punch_request: PunchOutRequest,
    property_id: str = Query(..., description="Property ID (UUID) for punch out"),
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
) -> Any:
    try:
        attendance, has_warning, warning_msg = await AttendanceService.create_punch_out(
            db=db,
            user_id=user["user_id"],
            property_id=property_id,
            tenant_id=user["tenant_id"],
            punch_out_request=punch_request,
        )
        return PunchOutResponse(
            success=True,
            message="Punched out successfully" if not has_warning else "Punched out (outside geofence)",
            attendance_id=str(attendance.id),
            hours_worked=attendance.hours_worked or 0,
            is_within_fence=attendance.punch_out_lat is not None,
            distance_meters=attendance.distance_meters,
            warning=warning_msg,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error creating punch out record")


@router.get("/status")
async def get_punch_status(
    property_id: str = Query(..., description="Property ID (UUID)"),
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
) -> Any:
    try:
        attendance = await AttendanceService.get_active_punch_in(
            db=db,
            user_id=user["user_id"],
            property_id=property_id,
            tenant_id=user["tenant_id"],
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
            "punch_in_location": {"latitude": attendance.punch_in_lat, "longitude": attendance.punch_in_lon},
        }
    except Exception:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error fetching punch status")


# ===========================
# Attendance History
# ===========================

@router.get("/history")
async def get_attendance_history(
    property_id: Optional[str] = Query(None),
    start_date: Optional[datetime] = Query(None),
    end_date: Optional[datetime] = Query(None),
    is_within_fence: Optional[bool] = Query(None),
    attendance_status: Optional[str] = Query(None, alias="status"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
) -> Any:
    try:
        records, total_count = await AttendanceService.get_attendance_history(
            db=db,
            user_id=user["user_id"],
            tenant_id=user["tenant_id"],
            property_id=property_id,
            start_date=start_date,
            end_date=end_date,
            is_within_fence=is_within_fence,
            status=attendance_status,
            skip=skip,
            limit=limit,
        )
        return {
            "total": total_count,
            "count": len(records),
            "records": [AttendanceRecordResponse.model_validate(r) for r in records],
            "page_info": {"skip": skip, "limit": limit, "has_more": (skip + limit) < total_count},
        }
    except Exception:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error fetching attendance history")


@router.get("/daily-summary")
async def get_daily_summary(
    date: Optional[datetime] = Query(None),
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
) -> Any:
    try:
        if not date:
            date = datetime.now(timezone.utc)
        return await AttendanceService.get_daily_summary(
            db=db,
            user_id=user["user_id"],
            tenant_id=user["tenant_id"],
            date=date,
        )
    except Exception:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error calculating daily summary")


# ===========================
# Geofence Management
# ===========================

@router.post("/geofence", response_model=PropertyGeofenceResponse, status_code=status.HTTP_201_CREATED)
async def create_geofence(
    geofence_data: PropertyGeofenceCreate,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
) -> Any:
    if user.get("role") not in ["Admin", "Tenant Admin", "Manager", "Super Admin"]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only admins and managers can create geofences")
    try:
        geofence = await GeofenceService.create_geofence(
            db=db, tenant_id=user["tenant_id"], geofence_data=geofence_data
        )
        return PropertyGeofenceResponse.model_validate(geofence)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error creating geofence")


@router.get("/geofence/{property_id}", response_model=PropertyGeofenceResponse)
async def get_geofence(
    property_id: str,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
) -> Any:
    try:
        geofence = await GeofenceService.get_geofence(
            db=db, property_id=property_id, tenant_id=user["tenant_id"]
        )
        if not geofence:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Geofence not found for property {property_id}")
        return PropertyGeofenceResponse.model_validate(geofence)
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error fetching geofence")


@router.put("/geofence/{geofence_id}", response_model=PropertyGeofenceResponse)
async def update_geofence(
    geofence_id: str,
    geofence_data: PropertyGeofenceCreate,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
) -> Any:
    if user.get("role") not in ["Admin", "Tenant Admin", "Manager", "Super Admin"]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only admins and managers can update geofences")
    try:
        geofence = await GeofenceService.update_geofence(
            db=db, geofence_id=geofence_id, geofence_data=geofence_data
        )
        return PropertyGeofenceResponse.model_validate(geofence)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error updating geofence")


@router.delete("/geofence/{geofence_id}")
async def delete_geofence(
    geofence_id: str,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
) -> Any:
    if user.get("role") not in ["Admin", "Tenant Admin", "Manager", "Super Admin"]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only admins and managers can delete geofences")
    try:
        await GeofenceService.delete_geofence(db=db, geofence_id=geofence_id)
        return {"success": True, "message": "Geofence deleted successfully"}
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error deleting geofence")


@router.get("/property/{property_id}/today")
async def get_property_attendance_today(
    property_id: str,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_permission("manage_staff")),
) -> Any:
    try:
        records = await AttendanceService.get_property_attendance_today(
            db=db, property_id=property_id, tenant_id=user["tenant_id"]
        )
        today_str = __import__("datetime").date.today().isoformat()
        present = [r for r in records if r.status in ("active", "completed")]
        return {
            "property_id": property_id,
            "date": today_str,
            "total_staff": len(records),
            "present": len(present),
            "absent": 0,
            "records": [
                {
                    "user_id": str(r.user_id),
                    "user_name": str(r.user_id),
                    "punch_in_time": r.punch_in_time.isoformat() if r.punch_in_time else None,
                    "punch_out_time": r.punch_out_time.isoformat() if r.punch_out_time else None,
                    "hours_worked": r.hours_worked,
                    "status": r.status,
                    "is_within_fence": r.is_within_fence,
                }
                for r in records
            ],
        }
    except Exception:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error fetching property attendance")


@router.get("/geofence")
async def list_geofences(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
) -> Any:
    try:
        geofences, total_count = await GeofenceService.list_geofences(
            db=db, tenant_id=user["tenant_id"], skip=skip, limit=limit
        )
        return {
            "total": total_count,
            "count": len(geofences),
            "geofences": [PropertyGeofenceResponse.model_validate(g) for g in geofences],
            "page_info": {"skip": skip, "limit": limit, "has_more": (skip + limit) < total_count},
        }
    except Exception:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error fetching geofences")
