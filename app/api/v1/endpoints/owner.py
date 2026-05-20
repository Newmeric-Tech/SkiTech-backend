"""
Owner Router - app/api/v1/endpoints/owner.py

Owner/Property Owner endpoints for managing properties and viewing activity logs.
Includes activity log retrieval with property-based filtering.
"""

from datetime import datetime, timedelta
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Query, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user, get_db, require_roles
from app.models.models import Property, OwnerDetails, User
from app.schemas.schemas import (
    ActivityLogDetailedResponse,
    ActivityLogListResponse,
    ActivityLogSummaryResponse,
    ActivityLogAnalyticsResponse,
    AuditLogResponse,
)
from app.services.activity_log_service import ActivityLogService
from app.repositories.activity_log_repository import ActivityLogRepository

router = APIRouter(prefix="/owners", tags=["Owners"])


# ===========================================================
# ACTIVITY LOG ENDPOINTS
# ===========================================================

@router.get("/activity-logs", response_model=ActivityLogListResponse)
async def get_activity_logs(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=500),
    action_type: Optional[str] = Query(None),
    severity: Optional[str] = Query(None),
    resource_type: Optional[str] = Query(None),
    start_date: Optional[datetime] = Query(None),
    end_date: Optional[datetime] = Query(None),
    user: dict = Depends(require_roles(["Property Owner", "Owner"])),
    db: AsyncSession = Depends(get_db),
):
    """
    Get activity logs for all properties owned by the current user.
    
    Query Parameters:
    - skip: Number of records to skip (pagination)
    - limit: Number of records to return (max 500)
    - action_type: Filter by action type (e.g., 'CREATE', 'UPDATE', 'DELETE', 'LOGIN')
    - severity: Filter by severity (low, medium, warning, critical)
    - resource_type: Filter by resource type (e.g., 'property', 'employee', 'inventory')
    - start_date: Filter logs from this date
    - end_date: Filter logs until this date
    
    Returns:
        ActivityLogListResponse: Paginated list of activity logs
    """
    try:
        tenant_id = UUID(user["tenant_id"])
        user_id = UUID(user["user_id"])

        logs, total = await ActivityLogService.get_activity_logs(
            db=db,
            tenant_id=tenant_id,
            user_id=user_id,
            skip=skip,
            limit=limit,
            start_date=start_date,
            end_date=end_date,
            action_type=action_type,
            severity=severity,
            resource_type=resource_type,
        )

        return ActivityLogListResponse(
            total=total,
            page=skip // limit + 1,
            limit=limit,
            logs=[ActivityLogDetailedResponse.from_orm(log) for log in logs],
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving activity logs: {str(e)}"
        )


@router.get("/activity-logs/{property_id}", response_model=ActivityLogListResponse)
async def get_property_activity_logs(
    property_id: UUID,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=500),
    action_type: Optional[str] = Query(None),
    severity: Optional[str] = Query(None),
    start_date: Optional[datetime] = Query(None),
    end_date: Optional[datetime] = Query(None),
    user: dict = Depends(require_roles(["Property Owner", "Owner"])),
    db: AsyncSession = Depends(get_db),
):
    """
    Get activity logs for a specific property.
    Only accessible to the owner of that property.
    
    Path Parameters:
    - property_id: The property ID to fetch logs for
    
    Returns:
        ActivityLogListResponse: Paginated logs for the specific property
    """
    try:
        tenant_id = UUID(user["tenant_id"])
        user_id = UUID(user["user_id"])

        logs, total = await ActivityLogService.get_property_activity_logs(
            db=db,
            tenant_id=tenant_id,
            property_id=property_id,
            user_id=user_id,
            skip=skip,
            limit=limit,
            start_date=start_date,
            end_date=end_date,
            action_type=action_type,
            severity=severity,
        )

        return ActivityLogListResponse(
            total=total,
            page=skip // limit + 1,
            limit=limit,
            logs=[ActivityLogDetailedResponse.from_orm(log) for log in logs],
        )
    except PermissionError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving property logs: {str(e)}"
        )


@router.get("/activity-logs/summary/dashboard", response_model=ActivityLogSummaryResponse)
async def get_activity_summary(
    days: int = Query(7, ge=1, le=90),
    user: dict = Depends(require_roles(["Property Owner", "Owner"])),
    db: AsyncSession = Depends(get_db),
):
    """
    Get activity log summary statistics for owner's properties.
    
    Query Parameters:
    - days: Number of days to include in summary (default: 7, max: 90)
    
    Returns:
        ActivityLogSummaryResponse: Statistics including total events, warnings, critical, etc.
    """
    try:
        tenant_id = UUID(user["tenant_id"])
        user_id = UUID(user["user_id"])

        summary = await ActivityLogService.get_activity_summary(
            db=db,
            tenant_id=tenant_id,
            user_id=user_id,
            days=days,
        )

        return ActivityLogSummaryResponse(**summary)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving summary: {str(e)}"
        )


@router.get("/activity-logs/critical/recent", response_model=list[ActivityLogDetailedResponse])
async def get_recent_critical_events(
    limit: int = Query(10, ge=1, le=100),
    user: dict = Depends(require_roles(["Property Owner", "Owner"])),
    db: AsyncSession = Depends(get_db),
):
    """
    Get recent critical severity events for owner's properties.
    Useful for quick status checks and alerts.
    
    Query Parameters:
    - limit: Number of critical events to return (max 100)
    
    Returns:
        List of critical activity logs
    """
    try:
        tenant_id = UUID(user["tenant_id"])
        user_id = UUID(user["user_id"])

        logs = await ActivityLogService.get_critical_events(
            db=db,
            tenant_id=tenant_id,
            user_id=user_id,
            limit=limit,
        )

        return [ActivityLogDetailedResponse.from_orm(log) for log in logs]
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving critical events: {str(e)}"
        )


@router.get("/activity-logs/analytics/detailed", response_model=ActivityLogAnalyticsResponse)
async def get_activity_analytics(
    days: int = Query(7, ge=1, le=90),
    user: dict = Depends(require_roles(["Property Owner", "Owner"])),
    db: AsyncSession = Depends(get_db),
):
    """
    Get comprehensive activity analytics for owner's properties.
    
    Query Parameters:
    - days: Period for analytics (default: 7 days, max: 90 days)
    
    Returns:
        ActivityLogAnalyticsResponse: Detailed analytics with summary and critical events
    """
    try:
        tenant_id = UUID(user["tenant_id"])
        user_id = UUID(user["user_id"])

        summary = await ActivityLogService.get_activity_summary(
            db=db,
            tenant_id=tenant_id,
            user_id=user_id,
            days=days,
        )

        critical_events = await ActivityLogService.get_critical_events(
            db=db,
            tenant_id=tenant_id,
            user_id=user_id,
            limit=10,
        )

        return ActivityLogAnalyticsResponse(
            period_days=days,
            summary=ActivityLogSummaryResponse(**summary),
            critical_events=[ActivityLogDetailedResponse.from_orm(log) for log in critical_events],
            top_users=[],  # Can be populated with additional queries
            action_distribution=summary.get("by_action", []),
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving analytics: {str(e)}"
        )


@router.get("/activity-logs/export/csv")
async def export_activity_logs_csv(
    start_date: Optional[datetime] = Query(None),
    end_date: Optional[datetime] = Query(None),
    user: dict = Depends(require_roles(["Property Owner", "Owner"])),
    db: AsyncSession = Depends(get_db),
):
    """
    Export activity logs as CSV for data analysis.
    Includes all logs for owner's properties within the date range.
    
    Query Parameters:
    - start_date: Start date for export
    - end_date: End date for export
    
    Returns:
        CSV file download
    """
    try:
        import csv
        from io import StringIO
        from fastapi.responses import StreamingResponse

        tenant_id = UUID(user["tenant_id"])
        user_id = UUID(user["user_id"])

        logs, _ = await ActivityLogService.get_activity_logs(
            db=db,
            tenant_id=tenant_id,
            user_id=user_id,
            skip=0,
            limit=10000,
            start_date=start_date,
            end_date=end_date,
        )

        # Create CSV
        output = StringIO()
        writer = csv.writer(output)
        writer.writerow([
            "Timestamp", "User", "Email", "Action", "Resource Type",
            "Resource ID", "Details", "Severity", "Status", "IP Address"
        ])

        for log in logs:
            writer.writerow([
                log.created_at,
                log.user_id or "System",
                log.user_email or "-",
                log.action,
                log.resource_type,
                log.resource_id or "-",
                log.details or "-",
                log.severity,
                log.status,
                log.ip_address or "-",
            ])

        output.seek(0)
        return StreamingResponse(
            iter([output.getvalue()]),
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=activity-logs.csv"}
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error exporting logs: {str(e)}"
        )


# ===========================================================
# PROPERTY MANAGEMENT ENDPOINTS
# ===========================================================

@router.get("/properties")
async def get_owner_properties(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=500),
    user: dict = Depends(require_roles(["Property Owner", "Owner"])),
    db: AsyncSession = Depends(get_db),
):
    """
    Get all properties owned by the current user.
    
    Returns:
        List of properties with basic information
    """
    try:
        from sqlalchemy import select

        tenant_id = UUID(user["tenant_id"])
        
        # Get properties for this owner from OwnerDetails
        query = (
            select(Property)
            .join(OwnerDetails, OwnerDetails.property_id == Property.id)
            .where(
                OwnerDetails.tenant_id == tenant_id,
                Property.tenant_id == tenant_id,
            )
            .offset(skip)
            .limit(limit)
        )
        
        result = await db.execute(query)
        properties = result.scalars().all()

        return {
            "total": len(properties),
            "properties": [
                {
                    "id": str(p.id),
                    "name": p.name,
                    "address": p.address,
                    "city": p.city,
                    "state": p.state,
                    "num_rooms": p.num_rooms,
                    "is_active": p.is_active,
                }
                for p in properties
            ]
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving properties: {str(e)}"
        )


@router.get("/dashboard/overview")
async def get_dashboard_overview(
    user: dict = Depends(require_roles(["Property Owner", "Owner"])),
    db: AsyncSession = Depends(get_db),
):
    """
    Get dashboard overview with key metrics for owner.
    
    Returns:
        Dashboard data with activity summary, recent logs, and critical events
    """
    try:
        tenant_id = UUID(user["tenant_id"])
        user_id = UUID(user["user_id"])

        # Get summary
        summary = await ActivityLogService.get_activity_summary(
            db=db,
            tenant_id=tenant_id,
            user_id=user_id,
            days=7,
        )

        # Get recent critical events
        critical_events = await ActivityLogService.get_critical_events(
            db=db,
            tenant_id=tenant_id,
            user_id=user_id,
            limit=5,
        )

        # Get properties
        properties_query = (
            select(Property)
            .join(OwnerDetails, OwnerDetails.property_id == Property.id)
            .where(
                OwnerDetails.tenant_id == tenant_id,
                Property.tenant_id == tenant_id,
            )
        )
        
        properties_result = await db.execute(properties_query)
        properties = properties_result.scalars().all()

        return {
            "summary": summary,
            "critical_events": [
                {
                    "id": str(log.id),
                    "action": log.action,
                    "resource_type": log.resource_type,
                    "details": log.details,
                    "severity": log.severity,
                    "timestamp": log.created_at,
                    "user": log.user_email,
                }
                for log in critical_events
            ],
            "properties_count": len(properties),
            "properties": [
                {
                    "id": str(p.id),
                    "name": p.name,
                    "is_active": p.is_active,
                }
                for p in properties
            ],
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving dashboard: {str(e)}"
        )
