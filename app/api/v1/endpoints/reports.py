"""
Reports Routes - app/api/v1/endpoints/reports.py

GET /reports/occupancy          → property wise room occupancy (current snapshot)
GET /reports/occupancy-trend    → monthly occupancy % for the last N months
GET /reports/revenue            → monthly booking revenue per property (last 6 months)
GET /reports/audit              → audit trail with filters
"""

from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import and_, extract, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user, require_roles
from app.core.database import get_db
from app.models.models import AuditLog, Booking, Property, Room
from app.schemas.schemas import AuditReportResponse, OccupancyReportResponse

MONTH_LABELS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

router = APIRouter(prefix="/reports", tags=["Reports"])


# ── Occupancy Report ──────────────────────────────────────────────────────────

@router.get("/occupancy", response_model=OccupancyReportResponse)
async def get_occupancy_report(
    property_id: Optional[UUID] = None,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_roles(["Super Admin", "Tenant Admin", "Manager"])),
):
    """
    Property wise room occupancy report.
    Optional property_id filter — if not given, returns all properties.
    """
    tenant_id = UUID(user["tenant_id"])

    # Get properties
    prop_q = select(Property).where(
        Property.tenant_id == tenant_id,
        Property.deleted_at == None,
        Property.is_active == True,
    )
    if property_id:
        prop_q = prop_q.where(Property.id == property_id)

    prop_result = await db.execute(prop_q)
    properties = prop_result.scalars().all()

    reports = []
    for prop in properties:
        # Total rooms
        total_q = select(func.count(Room.id)).where(
            Room.property_id == prop.id,
            Room.tenant_id == tenant_id,
            Room.deleted_at == None,
        )
        total_rooms = (await db.execute(total_q)).scalar() or 0

        # Occupied rooms
        occupied_q = select(func.count(Room.id)).where(
            Room.property_id == prop.id,
            Room.tenant_id == tenant_id,
            Room.deleted_at == None,
            Room.status == "occupied",
        )
        occupied_rooms = (await db.execute(occupied_q)).scalar() or 0

        # Maintenance rooms
        maintenance_q = select(func.count(Room.id)).where(
            Room.property_id == prop.id,
            Room.tenant_id == tenant_id,
            Room.deleted_at == None,
            Room.status == "maintenance",
        )
        maintenance_rooms = (await db.execute(maintenance_q)).scalar() or 0

        available_rooms = total_rooms - occupied_rooms - maintenance_rooms
        occupancy_pct = round(
            (occupied_rooms / total_rooms * 100) if total_rooms > 0 else 0.0, 2
        )

        reports.append({
            "property_id": prop.id,
            "property_name": prop.name,
            "total_rooms": total_rooms,
            "occupied_rooms": occupied_rooms,
            "available_rooms": available_rooms,
            "maintenance_rooms": maintenance_rooms,
            "occupancy_percentage": occupancy_pct,
        })

    return {
        "period": "current",
        "reports": reports,
    }


# ── Revenue Report ────────────────────────────────────────────────────────────

@router.get("/revenue")
async def get_revenue_report(
    months: int = Query(default=6, ge=1, le=24),
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_roles(["Super Admin", "Tenant Admin", "Manager"])),
):
    """
    Monthly booking revenue per property for the last N months.
    Returns a list of month buckets, each with a per-property breakdown and a total.
    Only counts bookings with status != 'cancelled'.
    """
    tenant_id = UUID(user["tenant_id"])
    now = datetime.now(timezone.utc)

    # Build the list of (year, month) buckets to cover, oldest first
    buckets: list[tuple[int, int]] = []
    for i in range(months - 1, -1, -1):
        m = now.month - i
        y = now.year
        while m <= 0:
            m += 12
            y -= 1
        buckets.append((y, m))

    # Fetch active properties — Co Admin is scoped to their assigned property
    prop_q = select(Property).where(
        Property.tenant_id == tenant_id,
        Property.deleted_at == None,
        Property.is_active == True,
    )
    if user.get("role") == "Co Admin" and user.get("property_id"):
        prop_q = prop_q.where(Property.id == UUID(user["property_id"]))

    prop_result = await db.execute(prop_q)
    properties = prop_result.scalars().all()
    prop_map = {str(p.id): p.name for p in properties}

    # Aggregate revenue: SUM(total_amount) grouped by (property_id, year, month)
    rev_q = (
        select(
            Booking.property_id,
            extract("year", Booking.check_in).label("yr"),
            extract("month", Booking.check_in).label("mo"),
            func.sum(Booking.total_amount).label("revenue"),
        )
        .where(
            Booking.tenant_id == tenant_id,
            Booking.status != "cancelled",
            Booking.deleted_at == None,
        )
        .group_by(Booking.property_id, "yr", "mo")
    )
    rows = (await db.execute(rev_q)).all()

    # Index results: (prop_id_str, year, month) → revenue
    rev_index: dict[tuple[str, int, int], float] = {}
    for row in rows:
        key = (str(row.property_id), int(row.yr), int(row.mo))
        rev_index[key] = float(row.revenue or 0)

    result = []
    for yr, mo in buckets:
        month_label = MONTH_LABELS[mo - 1]
        per_property = []
        total = 0.0
        for prop in properties:
            amount = rev_index.get((str(prop.id), yr, mo), 0.0)
            per_property.append({"property_id": str(prop.id), "property_name": prop.name, "amount": amount})
            total += amount
        result.append({"month": month_label, "year": yr, "properties": per_property, "total": round(total, 2)})

    return {"months": months, "data": result, "properties": [{"id": k, "name": v} for k, v in prop_map.items()]}


# ── Occupancy Trend ───────────────────────────────────────────────────────────

@router.get("/occupancy-trend")
async def get_occupancy_trend(
    months: int = Query(default=6, ge=1, le=24),
    property_id: Optional[UUID] = None,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_roles(["Super Admin", "Tenant Admin", "Manager"])),
):
    """
    Monthly average occupancy % derived from bookings vs total rooms.
    Uses completed/checked_in bookings with check_in date falling in that month.
    """
    tenant_id = UUID(user["tenant_id"])
    now = datetime.now(timezone.utc)

    buckets: list[tuple[int, int]] = []
    for i in range(months - 1, -1, -1):
        m = now.month - i
        y = now.year
        while m <= 0:
            m += 12
            y -= 1
        buckets.append((y, m))

    # Total rooms (static denominator)
    room_q = select(func.count(Room.id)).where(
        Room.tenant_id == tenant_id,
        Room.deleted_at == None,
    )
    if property_id:
        room_q = room_q.where(Room.property_id == property_id)
    total_rooms = (await db.execute(room_q)).scalar() or 0

    # Bookings per month
    booking_q = (
        select(
            extract("year", Booking.check_in).label("yr"),
            extract("month", Booking.check_in).label("mo"),
            func.count(Booking.id).label("cnt"),
        )
        .where(
            Booking.tenant_id == tenant_id,
            Booking.status.in_(["booked", "checked_in", "completed"]),
            Booking.deleted_at == None,
        )
        .group_by("yr", "mo")
    )
    if property_id:
        booking_q = booking_q.where(Booking.property_id == property_id)
    rows = (await db.execute(booking_q)).all()

    book_index = {(int(r.yr), int(r.mo)): int(r.cnt) for r in rows}

    result = []
    for yr, mo in buckets:
        cnt = book_index.get((yr, mo), 0)
        occ = round((cnt / total_rooms * 100), 1) if total_rooms > 0 else 0.0
        result.append({"month": MONTH_LABELS[mo - 1], "year": yr, "occupancy": min(occ, 100.0)})

    return {"months": months, "data": result}


# ── Audit Report ──────────────────────────────────────────────────────────────

@router.get("/audit", response_model=AuditReportResponse)
async def get_audit_report(
    resource_type: Optional[str] = None,
    action: Optional[str] = None,
    severity: Optional[str] = None,
    user_id: Optional[UUID] = None,
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=50, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_roles(["Super Admin", "Tenant Admin"])),
):
    """
    Audit trail report with optional filters.
    Only Super Admin and Tenant Admin can access.
    """
    tenant_id = UUID(current_user["tenant_id"])

    # Base query
    base_q = select(AuditLog).where(
        AuditLog.tenant_id == tenant_id,
    )

    # Optional filters
    if resource_type:
        base_q = base_q.where(AuditLog.resource_type == resource_type)
    if action:
        base_q = base_q.where(AuditLog.action == action)
    if severity:
        base_q = base_q.where(AuditLog.severity == severity)
    if user_id:
        base_q = base_q.where(AuditLog.user_id == user_id)

    # Total count
    count_q = select(func.count()).select_from(base_q.subquery())
    total = (await db.execute(count_q)).scalar() or 0

    # Paginated results — latest first
    offset = (page - 1) * limit
    logs_q = base_q.order_by(AuditLog.created_at.desc()).offset(offset).limit(limit)
    logs_result = await db.execute(logs_q)
    logs = logs_result.scalars().all()

    return {
        "total": total,
        "page": page,
        "limit": limit,
        "logs": logs,
    }