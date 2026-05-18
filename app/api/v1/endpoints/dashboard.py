"""
Dashboard Endpoints - app/api/v1/endpoints/dashboard.py

Owner dashboard data: summary stats, task trend, and alerts.
Separate from /stats so the owner page's dashboardAPI calls resolve.
"""

from datetime import datetime, timedelta
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user
from app.core.database import get_db
from app.models.models import InventoryItem, LowStockAlert, Property, SOPItem

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])

DAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def _get_week_days():
    from datetime import date
    today = date.today()
    monday = today - timedelta(days=today.weekday())
    return [(monday + timedelta(days=i)) for i in range(7)]


@router.get("/")
async def dashboard_summary(
    property_id: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    tid = UUID(user["tenant_id"])

    base = [SOPItem.tenant_id == tid, SOPItem.deleted_at == None]
    if property_id:
        base.append(SOPItem.property_id == UUID(property_id))

    total_sops = (await db.execute(
        select(func.count(SOPItem.id)).where(*base)
    )).scalar() or 0

    completed = (await db.execute(
        select(func.count(SOPItem.id)).where(*base, SOPItem.status == "completed")
    )).scalar() or 0

    pending = total_sops - completed
    rate = round(completed / total_sops * 100, 1) if total_sops > 0 else 0.0

    return {
        "total_sops": total_sops,
        "total_tasks": total_sops,
        "completed_tasks": completed,
        "pending_tasks": pending,
        "completion_rate": rate,
    }


@router.get("/tasks-trend")
async def tasks_trend(
    property_id: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    tid = UUID(user["tenant_id"])
    trend = []
    for i, day in enumerate(_get_week_days()):
        day_start = datetime.combine(day, datetime.min.time())
        day_end = day_start + timedelta(days=1)

        filters = [
            SOPItem.tenant_id == tid,
            SOPItem.deleted_at == None,
            SOPItem.created_at >= day_start,
            SOPItem.created_at < day_end,
        ]
        if property_id:
            filters.append(SOPItem.property_id == UUID(property_id))

        count = (await db.execute(
            select(func.count(SOPItem.id)).where(*filters)
        )).scalar() or 0

        trend.append({"day": DAY_NAMES[i], "tasks": count})

    return trend


@router.get("/alerts")
async def alerts(
    property_id: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    tid = UUID(user["tenant_id"])

    filters = [
        LowStockAlert.tenant_id == tid,
        LowStockAlert.is_resolved == False,
    ]
    if property_id:
        filters.append(LowStockAlert.property_id == UUID(property_id))

    q = (
        select(LowStockAlert, InventoryItem)
        .join(InventoryItem, LowStockAlert.item_id == InventoryItem.id)
        .where(*filters)
        .order_by(LowStockAlert.triggered_at.desc())
        .limit(10)
    )
    rows = (await db.execute(q)).all()

    return [
        {
            "id": str(alert.id),
            "message": f"Low stock: {item.item_name} (qty: {item.quantity})",
            "created_at": alert.triggered_at.isoformat() if alert.triggered_at else "",
        }
        for alert, item in rows
    ]
