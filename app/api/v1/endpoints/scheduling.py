"""
Employee Scheduling Endpoints - app/api/v1/endpoints/scheduling.py
"""

from datetime import datetime
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user, get_current_user_obj
from app.core.database import get_db
from app.models.models import User
from app.schemas.scheduling import (
    EmployeeAvailabilityCreate, EmployeeAvailabilityResponse,
    WeeklyScheduleCreate, WeeklyScheduleResponse, WeeklyScheduleUpdate,
    ShiftAssignmentCreate, ShiftAssignmentResponse,
    ReplacementRequestCreate, ReplacementRequestResponse, ReplacementRequestWithDetails,
    ReplacementRequestUpdate, ShiftResponseCreate, ShiftResponseResponse,
    AIRecommendationRequest, AIRecommendationResponse,
    ManagerDashboardData, StaffDashboardData, ConflictDetectionResult,
    BulkScheduleAssignmentRequest
)
from app.services.scheduling_service import SchedulingService


router = APIRouter(prefix="/scheduling", tags=["Scheduling"])


# ─────────────────────────────────────────────────────────────
# Dependency: Get Scheduling Service
# ─────────────────────────────────────────────────────────────

async def get_scheduling_service(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_obj)
) -> SchedulingService:
    """Get scheduling service instance with current context"""
    if not current_user.property_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User must be assigned to a property"
        )
    return SchedulingService(
        db=db,
        tenant_id=current_user.tenant_id,
        property_id=current_user.property_id,
        user_id=current_user.id
    )


# ═════════════════════════════════════════════════════════════
# EMPLOYEE AVAILABILITY ENDPOINTS
# ═════════════════════════════════════════════════════════════

@router.post("/availability", response_model=EmployeeAvailabilityResponse)
async def create_availability(
    employee_id: str,
    data: EmployeeAvailabilityCreate,
    service: SchedulingService = Depends(get_scheduling_service),
    db: AsyncSession = Depends(get_db)
):
    """Create employee availability record"""
    try:
        availability = await service.create_availability(
            UUID(employee_id), data
        )
        await db.commit()
        await db.refresh(availability)
        return availability
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/availability/bulk")
async def bulk_create_availability(
    employee_id: str,
    start_date: datetime,
    end_date: datetime,
    status: str,
    reason: str = None,
    service: SchedulingService = Depends(get_scheduling_service),
    db: AsyncSession = Depends(get_db)
):
    """Bulk create availability records for date range"""
    try:
        availabilities = await service.bulk_create_availability(
            UUID(employee_id), start_date, end_date, status, reason
        )
        await db.commit()
        return {
            "created": len(availabilities),
            "start_date": start_date,
            "end_date": end_date,
            "status": status
        }
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=400, detail=str(e))


# ═════════════════════════════════════════════════════════════
# WEEKLY SCHEDULE ENDPOINTS
# ═════════════════════════════════════════════════════════════

@router.post("/schedules", response_model=WeeklyScheduleResponse)
async def create_schedule(
    data: WeeklyScheduleCreate,
    service: SchedulingService = Depends(get_scheduling_service),
    db: AsyncSession = Depends(get_db)
):
    """Create weekly schedule for employee"""
    try:
        schedule = await service.create_weekly_schedule(UUID(data.employee_id), data)
        await db.commit()
        await db.refresh(schedule)
        return schedule
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/schedules/bulk", response_model=dict)
async def bulk_create_schedules(
    data: BulkScheduleAssignmentRequest,
    service: SchedulingService = Depends(get_scheduling_service),
    db: AsyncSession = Depends(get_db)
):
    """Bulk create schedules for multiple employees"""
    try:
        employee_ids = [UUID(eid) for eid in data.employee_ids]
        schedules = await service.bulk_create_weekly_schedules(
            employee_ids, data.week_start_date, data.week_end_date, 
            UUID(data.department_id) if data.department_id else None
        )
        await db.commit()
        return {
            "created": len(schedules),
            "week_start": data.week_start_date,
            "week_end": data.week_end_date,
            "employee_count": len(employee_ids)
        }
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/schedules/{schedule_id}", response_model=WeeklyScheduleResponse)
async def get_schedule(
    schedule_id: str,
    service: SchedulingService = Depends(get_scheduling_service)
):
    """Get weekly schedule with shift assignments"""
    schedule = await service.get_weekly_schedule(UUID(schedule_id))
    if not schedule:
        raise HTTPException(status_code=404, detail="Schedule not found")
    return schedule


@router.put("/schedules/{schedule_id}/publish")
async def publish_schedule(
    schedule_id: str,
    service: SchedulingService = Depends(get_scheduling_service),
    db: AsyncSession = Depends(get_db)
):
    """Publish weekly schedule"""
    try:
        schedule = await service.publish_schedule(UUID(schedule_id))
        await db.commit()
        return {"status": "published", "schedule_id": schedule_id}
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=400, detail=str(e))


# ═════════════════════════════════════════════════════════════
# SHIFT ASSIGNMENT ENDPOINTS
# ═════════════════════════════════════════════════════════════

@router.post("/shifts", response_model=ShiftAssignmentResponse)
async def create_shift(
    schedule_id: str,
    employee_id: str,
    data: ShiftAssignmentCreate,
    service: SchedulingService = Depends(get_scheduling_service),
    db: AsyncSession = Depends(get_db)
):
    """Create shift assignment"""
    try:
        shift = await service.create_shift_assignment(
            UUID(schedule_id), UUID(employee_id), data
        )
        await db.commit()
        await db.refresh(shift)
        return shift
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=400, detail=str(e))


# ═════════════════════════════════════════════════════════════
# CONFLICT DETECTION ENDPOINTS
# ═════════════════════════════════════════════════════════════

@router.get("/schedules/{schedule_id}/conflicts", response_model=ConflictDetectionResult)
async def detect_conflicts(
    schedule_id: str,
    service: SchedulingService = Depends(get_scheduling_service)
):
    """Detect conflicts in schedule (employee off on assigned days)"""
    conflicts = await service.detect_schedule_conflicts(UUID(schedule_id))
    return conflicts


# ═════════════════════════════════════════════════════════════
# REPLACEMENT REQUEST ENDPOINTS
# ═════════════════════════════════════════════════════════════

@router.post("/replacement-requests", response_model=ReplacementRequestResponse)
async def create_replacement_request(
    shift_assignment_id: str,
    original_employee_id: str,
    data: ReplacementRequestCreate,
    service: SchedulingService = Depends(get_scheduling_service),
    db: AsyncSession = Depends(get_db)
):
    """Create replacement request for off employee"""
    try:
        replacement_emp_id = None
        if data.replacement_employee_id:
            replacement_emp_id = UUID(data.replacement_employee_id)
        
        request = await service.create_replacement_request(
            UUID(shift_assignment_id),
            UUID(original_employee_id),
            replacement_emp_id,
            data
        )
        await db.commit()
        await db.refresh(request)
        return request
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/replacement-requests/{request_id}", response_model=ReplacementRequestResponse)
async def get_replacement_request(
    request_id: str,
    service: SchedulingService = Depends(get_scheduling_service)
):
    """Get replacement request details"""
    request = await service.get_replacement_request(UUID(request_id))
    if not request:
        raise HTTPException(status_code=404, detail="Request not found")
    return request


@router.post("/replacement-requests/{request_id}/accept", response_model=ReplacementRequestResponse)
async def accept_replacement(
    request_id: str,
    employee_id: str,
    service: SchedulingService = Depends(get_scheduling_service),
    db: AsyncSession = Depends(get_db)
):
    """Accept replacement request"""
    try:
        request = await service.accept_replacement_request(
            UUID(request_id), UUID(employee_id)
        )
        await db.commit()
        await db.refresh(request)
        return request
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/replacement-requests/{request_id}/reject", response_model=ReplacementRequestResponse)
async def reject_replacement(
    request_id: str,
    employee_id: str,
    reason: str = None,
    service: SchedulingService = Depends(get_scheduling_service),
    db: AsyncSession = Depends(get_db)
):
    """Reject replacement request"""
    try:
        request = await service.reject_replacement_request(
            UUID(request_id), UUID(employee_id), reason
        )
        await db.commit()
        await db.refresh(request)
        return request
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/replacement-requests/{request_id}/assign", response_model=ReplacementRequestResponse)
async def direct_assign_replacement(
    request_id: str,
    replacement_employee_id: str,
    service: SchedulingService = Depends(get_scheduling_service),
    db: AsyncSession = Depends(get_db)
):
    """Directly assign replacement employee (manager action)"""
    try:
        request = await service.direct_assign_replacement(
            UUID(request_id), UUID(replacement_employee_id)
        )
        await db.commit()
        await db.refresh(request)
        return request
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=400, detail=str(e))


# ═════════════════════════════════════════════════════════════
# AI RECOMMENDATIONS ENDPOINTS
# ═════════════════════════════════════════════════════════════

@router.post("/recommendations", response_model=AIRecommendationResponse)
async def get_recommendations(
    original_employee_id: str,
    data: AIRecommendationRequest,
    service: SchedulingService = Depends(get_scheduling_service)
):
    """Get AI-recommended replacement employees"""
    try:
        department_id = None
        if data.department_id:
            department_id = UUID(data.department_id)
        
        recommendations = await service.get_ai_recommendations(
            data.shift_date,
            data.shift_start_time,
            data.shift_end_time,
            UUID(original_employee_id),
            department_id,
            data.max_recommendations
        )
        return recommendations
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# ═════════════════════════════════════════════════════════════
# DASHBOARD ENDPOINTS
# ═════════════════════════════════════════════════════════════

@router.get("/dashboard/manager", response_model=ManagerDashboardData)
async def get_manager_dashboard(
    week_start: Optional[datetime] = None,
    week_end: Optional[datetime] = None,
    service: SchedulingService = Depends(get_scheduling_service)
):
    """Get manager dashboard data (defaults to current week)"""
    from datetime import timedelta
    if week_start is None:
        today = datetime.utcnow()
        week_start = today - timedelta(days=today.weekday())
    if week_end is None:
        week_end = week_start + timedelta(days=6)
    try:
        data = await service.get_manager_dashboard_data(week_start, week_end)
        return data
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/dashboard/staff", response_model=StaffDashboardData)
async def get_staff_dashboard(
    employee_id: str,
    service: SchedulingService = Depends(get_scheduling_service)
):
    """Get staff dashboard data"""
    try:
        data = await service.get_staff_dashboard_data(UUID(employee_id))
        return data
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/me", response_model=StaffDashboardData)
async def get_my_schedule(
    service: SchedulingService = Depends(get_scheduling_service),
    current_user: User = Depends(get_current_user_obj)
):
    """
    Get the current user's own scheduling dashboard.
    Returns pending replacement requests where the user is involved,
    plus their current week schedule.
    """
    try:
        data = await service.get_staff_dashboard_data(current_user.id)
        return data
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# ═════════════════════════════════════════════════════════════
# SHIFT RESPONSE ENDPOINTS
# ═════════════════════════════════════════════════════════════

@router.post("/shift-responses", response_model=ShiftResponseResponse)
async def submit_shift_response(
    data: ShiftResponseCreate,
    employee_id: str,
    service: SchedulingService = Depends(get_scheduling_service),
    db: AsyncSession = Depends(get_db)
):
    """Submit employee response to shift request (accept/reject)"""
    try:
        # This would be implemented in service
        # For now, we'll return a placeholder
        response = {
            "id": "response_id",
            "replacement_request_id": data.replacement_request_id,
            "employee_id": employee_id,
            "response_type": data.response_type,
            "reason": data.reason,
            "responded_at": datetime.utcnow(),
            "created_at": datetime.utcnow()
        }
        return response
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
