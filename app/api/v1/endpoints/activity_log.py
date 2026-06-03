"""
Master Activity Log API Endpoints

Routes for viewing and filtering audit/activity logs:
- Owner / Manager: View property-scoped activity logs
- Superadmin: View all logs (handled via owner_properties fallback)
"""

from typing import List, Optional
from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_db, get_current_user, get_current_user_obj
from app.models.models import User, AuditLog
from app.services.activity_log_service import ActivityLogService

router = APIRouter(prefix="/activity-log", tags=["Master Activity Log"])


# ─── Pydantic-free response helpers ──────────────────────────
def _fmt_log(log: AuditLog) -> dict:
    """Map AuditLog ORM row → frontend-friendly dict."""
    # Map backend severity → frontend display labels
    severity_map = {
        "low":      "Info",
        "medium":   "Info",
        "high":     "Warning",
        "critical": "Critical",
    }
    return {
        "id":          str(log.id),
        "timestamp":   log.created_at.strftime("%Y-%m-%d %H:%M:%S") if log.created_at else "",
        "user":        log.user_email or "system",
        "actionType":  log.action,
        "resource":    log.resource_type,
        "resource_id": log.resource_id,
        "details":     log.details or "",
        "severity":    severity_map.get(log.severity or "low", "Info"),
        "raw_severity": log.severity,
        "status":      log.status,
        "ip_address":  str(log.ip_address) if log.ip_address else None,
        "property_id": str(log.property_id) if log.property_id else None,
    }


# ─── GET /activity-log/summary ────────────────────────────────
@router.get("/summary")
async def get_activity_summary(
    days: int = Query(7, ge=1, le=365, description="Number of days to summarise"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_obj),
):
    """
    Return activity statistics for the current user's properties.

    Stats returned:
    - total_events, warnings, critical, log_size_gb
    - by_action, by_resource, by_severity
    """
    summary = await ActivityLogService.get_activity_summary(
        db=db,
        tenant_id=current_user.tenant_id,
        user_id=current_user.id,
        days=days,
    )
    return summary


# ─── GET /activity-log/ ───────────────────────────────────────
@router.get("/")
async def list_activity_logs(
    skip: int = Query(0,   ge=0),
    limit: int = Query(50,  ge=1, le=200),
    severity: Optional[str] = Query(None, description="Filter by raw severity: low|medium|high|critical"),
    action_type: Optional[str] = Query(None, description="Filter by action, e.g. CREATE, UPDATE"),
    resource_type: Optional[str] = Query(None, description="Filter by resource type"),
    start_date: Optional[datetime] = Query(None),
    end_date: Optional[datetime] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_obj),
):
    """
    List activity logs with optional filters.
    Returns [items, total_count].
    """
    logs, total = await ActivityLogService.get_activity_logs(
        db=db,
        tenant_id=current_user.tenant_id,
        user_id=current_user.id,
        skip=skip,
        limit=limit,
        start_date=start_date,
        end_date=end_date,
        action_type=action_type,
        severity=severity,
        resource_type=resource_type,
    )
    return [list(map(_fmt_log, logs)), total]


# ─── GET /activity-log/critical ───────────────────────────────
@router.get("/critical")
async def get_critical_events(
    limit: int = Query(10, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_obj),
):
    """Return the most recent critical-severity events."""
    logs = await ActivityLogService.get_critical_events(
        db=db,
        tenant_id=current_user.tenant_id,
        user_id=current_user.id,
        limit=limit,
    )
    return list(map(_fmt_log, logs))
