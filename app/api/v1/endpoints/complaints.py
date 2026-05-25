"""
Complaint & Error Log API Endpoints

Routes for managing complaints:
- Staff: Create and view own complaints
- Manager: Manage, assign, and track complaints
- Owner: View all complaints across organization
"""

from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_db, get_current_user, get_current_user_obj
from app.models.models import User
from app.schemas.complaints import (
    ComplaintCreate, ComplaintUpdate, ComplaintResolve, ComplaintResponse,
    ComplaintDetailResponse, ComplaintListResponse, ComplaintFilterParams,
    ManagerDashboardData, OwnerDashboardData, StaffDashboardData,
    ComplaintCommentCreate, ComplaintCommentResponse, ComplaintAssignmentCreate,
    BulkActionRequest, ExportRequest, ComplaintPriority, ComplaintStatus,
    ComplaintType, ComplaintCategory
)
from app.services.complaint_service import ComplaintService


# Create router
router = APIRouter(prefix="/complaints", tags=["Complaints & Error Log"])


# ===========================================================
# DEPENDENCY
# ===========================================================

async def get_complaint_service(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_obj)
) -> ComplaintService:
    """Dependency to get complaint service instance"""
    # Get user role from their role relationship
    user_role = "staff"
    if current_user.role_obj:
        if current_user.role_obj.role_level <= 2:
            user_role = "owner"
        elif current_user.role_obj.role_level == 3:
            user_role = "manager"
    
    return ComplaintService(
        db=db,
        tenant_id=current_user.tenant_id,
        property_id=current_user.property_id,
        user_id=current_user.id,
        user_role=user_role
    )


# ===========================================================
# COMPLAINT ENDPOINTS
# ===========================================================

@router.post("/", response_model=ComplaintResponse, status_code=201)
async def create_complaint(
    data: ComplaintCreate,
    service: ComplaintService = Depends(get_complaint_service)
) -> ComplaintResponse:
    """Create a new complaint
    
    Staff can create complaints about maintenance, housekeeping, etc.
    """
    try:
        result = await service.create_complaint(data)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/", response_model=tuple[List[ComplaintListResponse], int])
async def list_complaints(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    status: Optional[str] = None,
    priority: Optional[str] = None,
    category: Optional[str] = None,
    complaint_type: Optional[str] = None,
    search: Optional[str] = None,
    service: ComplaintService = Depends(get_complaint_service)
) -> tuple[List[ComplaintListResponse], int]:
    """List complaints with filters
    
    Manager sees property complaints, Owner sees all
    """
    try:
        filters = ComplaintFilterParams(
            status=ComplaintStatus(status) if status else None,
            priority=ComplaintPriority(priority) if priority else None,
            category=ComplaintCategory(category) if category else None,
            complaint_type=ComplaintType(complaint_type) if complaint_type else None,
            search=search
        )
        complaints, total = await service.list_complaints(filters, skip, limit)
        return complaints, total
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid filter value: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{complaint_id}", response_model=ComplaintDetailResponse)
async def get_complaint(
    complaint_id: UUID,
    service: ComplaintService = Depends(get_complaint_service)
) -> ComplaintDetailResponse:
    """Get detailed view of a complaint with comments and attachments"""
    try:
        complaint = await service.get_complaint(complaint_id)
        if not complaint:
            raise HTTPException(status_code=404, detail="Complaint not found")
        return complaint
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/{complaint_id}", response_model=ComplaintResponse)
async def update_complaint(
    complaint_id: UUID,
    data: ComplaintUpdate,
    service: ComplaintService = Depends(get_complaint_service)
) -> ComplaintResponse:
    """Update complaint details"""
    try:
        complaint = await service.update_complaint(complaint_id, data)
        if not complaint:
            raise HTTPException(status_code=404, detail="Complaint not found")
        return complaint
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{complaint_id}/resolve", response_model=ComplaintResponse)
async def resolve_complaint(
    complaint_id: UUID,
    data: ComplaintResolve,
    service: ComplaintService = Depends(get_complaint_service)
) -> ComplaintResponse:
    """Resolve or close a complaint
    
    Manager marks complaint as resolved with notes
    """
    try:
        if service.user_role not in ["manager", "owner"]:
            raise HTTPException(status_code=403, detail="Not authorized to resolve complaints")
        
        complaint = await service.resolve_complaint(complaint_id, data)
        if not complaint:
            raise HTTPException(status_code=404, detail="Complaint not found")
        return complaint
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{complaint_id}/escalate", response_model=ComplaintResponse)
async def escalate_complaint(
    complaint_id: UUID,
    reason: str = Query(..., min_length=5),
    service: ComplaintService = Depends(get_complaint_service)
) -> ComplaintResponse:
    """Escalate complaint to higher authority"""
    try:
        complaint = await service.escalate_complaint(complaint_id, reason)
        if not complaint:
            raise HTTPException(status_code=404, detail="Complaint not found")
        return complaint
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ===========================================================
# STAFF SPECIFIC ENDPOINTS
# ===========================================================

@router.get("/me/my-complaints", response_model=tuple[List[ComplaintListResponse], int])
async def get_my_complaints(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    service: ComplaintService = Depends(get_complaint_service)
) -> tuple[List[ComplaintListResponse], int]:
    """Get complaints created by current staff member"""
    try:
        complaints, total = await service.list_staff_complaints(skip, limit)
        return complaints, total
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ===========================================================
# ASSIGNMENT ENDPOINTS
# ===========================================================

@router.post("/{complaint_id}/assign", response_model=ComplaintResponse)
async def assign_complaint(
    complaint_id: UUID,
    data: ComplaintAssignmentCreate,
    service: ComplaintService = Depends(get_complaint_service)
) -> ComplaintResponse:
    """Assign complaint to a staff member
    
    Only manager/owner can assign
    """
    try:
        if service.user_role not in ["manager", "owner"]:
            raise HTTPException(status_code=403, detail="Not authorized to assign complaints")
        
        complaint = await service.assign_complaint(complaint_id, data)
        if not complaint:
            raise HTTPException(status_code=404, detail="Complaint not found")
        return complaint
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{complaint_id}/reassign", response_model=ComplaintResponse)
async def reassign_complaint(
    complaint_id: UUID,
    new_assigned_to: UUID = Query(...),
    notes: Optional[str] = None,
    service: ComplaintService = Depends(get_complaint_service)
) -> ComplaintResponse:
    """Reassign complaint to another staff member"""
    try:
        if service.user_role not in ["manager", "owner"]:
            raise HTTPException(status_code=403, detail="Not authorized to reassign complaints")
        
        complaint = await service.reassign_complaint(complaint_id, new_assigned_to, notes)
        if not complaint:
            raise HTTPException(status_code=404, detail="Complaint not found")
        return complaint
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/me/assigned-to-me", response_model=tuple[List[ComplaintListResponse], int])
async def get_complaints_assigned_to_me(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    service: ComplaintService = Depends(get_complaint_service)
) -> tuple[List[ComplaintListResponse], int]:
    """Get complaints assigned to current user"""
    try:
        complaints, total = await service.list_assigned_complaints(skip, limit)
        return complaints, total
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ===========================================================
# COMMENTS ENDPOINTS
# ===========================================================

@router.post("/{complaint_id}/comments", response_model=ComplaintCommentResponse, status_code=201)
async def add_comment(
    complaint_id: UUID,
    data: ComplaintCommentCreate,
    service: ComplaintService = Depends(get_complaint_service)
) -> ComplaintCommentResponse:
    """Add comment to complaint"""
    try:
        comment = await service.add_comment(complaint_id, data)
        if not comment:
            raise HTTPException(status_code=404, detail="Complaint not found")
        return comment
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{complaint_id}/comments", response_model=List[ComplaintCommentResponse])
async def get_complaint_comments(
    complaint_id: UUID,
    service: ComplaintService = Depends(get_complaint_service)
) -> List[ComplaintCommentResponse]:
    """Get all comments for a complaint"""
    try:
        comments = await service.get_comments(complaint_id)
        return comments
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ===========================================================
# DASHBOARD ENDPOINTS
# ===========================================================

@router.get("/dashboard/manager", response_model=ManagerDashboardData)
async def get_manager_dashboard(
    service: ComplaintService = Depends(get_complaint_service)
) -> ManagerDashboardData:
    """Manager dashboard with all statistics
    
    Shows:
    - Total complaints, open, in progress, resolved today, escalated
    - Statistics by priority, status, category, type
    - Recent complaints
    - Need attention (high priority)
    - Daily events dashboard
    """
    try:
        if service.user_role not in ["manager", "owner"]:
            raise HTTPException(status_code=403, detail="Not authorized to view manager dashboard")
        
        dashboard = await service.get_manager_dashboard()
        return dashboard
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/dashboard/owner", response_model=OwnerDashboardData)
async def get_owner_dashboard(
    service: ComplaintService = Depends(get_complaint_service)
) -> OwnerDashboardData:
    """Owner dashboard - overview of all properties
    
    Shows:
    - Total complaints across organization
    - Critical and high priority counts
    - Resolution rate
    - Breakdown by property, category, status
    - List of critical complaints
    """
    try:
        if service.user_role != "owner":
            raise HTTPException(status_code=403, detail="Not authorized to view owner dashboard")
        
        dashboard = await service.get_owner_dashboard()
        return dashboard
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/dashboard/staff", response_model=StaffDashboardData)
async def get_staff_dashboard(
    service: ComplaintService = Depends(get_complaint_service)
) -> StaffDashboardData:
    """Staff dashboard - personal view
    
    Shows:
    - My complaints count
    - Pending resolution
    - Resolved by me
    - Assigned to me
    - My complaints list
    - Complaints assigned to me
    """
    try:
        dashboard = await service.get_staff_dashboard()
        return dashboard
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ===========================================================
# STATISTICS & REPORTS
# ===========================================================

@router.get("/statistics/summary", response_model=dict)
async def get_statistics(
    status: Optional[str] = None,
    service: ComplaintService = Depends(get_complaint_service)
) -> dict:
    """Get complaint statistics
    
    Returns breakdown by priority, status, and average resolution time
    """
    try:
        filters = ComplaintFilterParams(
            status=ComplaintStatus(status) if status else None
        )
        stats = await service.get_statistics(filters)
        return stats
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid filter value: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ===========================================================
# BULK OPERATIONS
# ===========================================================

@router.post("/bulk/actions", response_model=dict)
async def bulk_action(
    request: BulkActionRequest,
    service: ComplaintService = Depends(get_complaint_service)
) -> dict:
    """Perform bulk actions on multiple complaints
    
    Actions: assign, resolve, escalate, close
    """
    try:
        if service.user_role not in ["manager", "owner"]:
            raise HTTPException(status_code=403, detail="Not authorized for bulk actions")
        
        if len(request.complaint_ids) == 0:
            raise HTTPException(status_code=400, detail="No complaints specified")
        
        if len(request.complaint_ids) > 100:
            raise HTTPException(status_code=400, detail="Maximum 100 complaints per batch")
        
        processed = 0
        failed = 0
        
        for complaint_id in request.complaint_ids:
            try:
                if request.action == "assign" and request.assigned_to:
                    await service.assign_complaint(
                        complaint_id,
                        ComplaintAssignmentCreate(assigned_to=request.assigned_to, notes=request.notes)
                    )
                elif request.action == "resolve" and request.status:
                    await service.resolve_complaint(
                        complaint_id,
                        ComplaintResolve(status=request.status, resolution_notes=request.notes or "Bulk action")
                    )
                elif request.action == "escalate":
                    await service.escalate_complaint(complaint_id, request.notes or "Bulk escalation")
                processed += 1
            except Exception:
                failed += 1
        
        return {
            "total": len(request.complaint_ids),
            "processed": processed,
            "failed": failed,
            "action": request.action
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ===========================================================
# EXPORT ENDPOINTS
# ===========================================================

@router.post("/export")
async def export_complaints(
    request: ExportRequest,
    service: ComplaintService = Depends(get_complaint_service)
) -> dict:
    """Export complaints to CSV, PDF, or Excel
    
    Returns download link or file directly
    """
    try:
        if service.user_role not in ["manager", "owner"]:
            raise HTTPException(status_code=403, detail="Not authorized to export complaints")
        
        # TODO: Implement export functionality
        # This would typically generate a file and return a download URL
        return {
            "status": "pending",
            "format": request.format,
            "message": "Export processing. Download link will be available shortly."
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ===========================================================
# HEALTH CHECK
# ===========================================================

@router.get("/health", response_model=dict)
async def health_check() -> dict:
    """Health check for complaints service"""
    return {
        "status": "healthy",
        "service": "complaints",
        "version": "1.0"
    }
