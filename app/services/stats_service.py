"""
Stats Service - app/services/stats_service.py

Business logic for all 3 dashboard stats:
  - Owner
  - Manager  
  - Staff
"""

from datetime import datetime, timedelta, date
from typing import Optional
from uuid import UUID

from sqlalchemy import func, select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import (
    Booking, Department, Employee, InventoryItem,
    LowStockAlert, Property, SOPItem, User,
)


# ── Helpers ──────────────────────────────────────────────────────────────────

def _time_ago(dt: datetime) -> str:
    """Convert datetime to human-readable time ago string."""
    diff = datetime.utcnow() - dt
    minutes = int(diff.total_seconds() / 60)
    if minutes < 1:
        return "Just now"
    if minutes < 60:
        return f"{minutes} min ago"
    hours = minutes // 60
    if hours < 24:
        return f"{hours} hr ago"
    days = hours // 24
    return f"{days} days ago"


def _get_week_days():
    """Return list of (day_name, date) for current week Mon-Sun."""
    today = date.today()
    monday = today - timedelta(days=today.weekday())
    return [(monday + timedelta(days=i)) for i in range(7)]


DAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


# ── Owner Stats ───────────────────────────────────────────────────────────────

async def get_owner_stats(
    db: AsyncSession,
    tenant_id: UUID,
    property_id: Optional[UUID] = None,
) -> dict:
    """
    Aggregated stats for Owner dashboard.
    If property_id given → single property, else → all tenant properties.
    """
    # Total properties
    prop_q = select(func.count(Property.id)).where(
        Property.tenant_id == tenant_id,
        Property.deleted_at == None,
        Property.is_active == True,
    )
    total_properties = (await db.execute(prop_q)).scalar() or 0

    # Total active staff
    emp_q = select(func.count(Employee.id)).where(
        Employee.tenant_id == tenant_id,
        Employee.deleted_at == None,
        Employee.is_active == True,
    )
    if property_id:
        emp_q = emp_q.where(Employee.property_id == property_id)
    total_staff = (await db.execute(emp_q)).scalar() or 0

    # Daily revenue — sum of today's completed bookings
    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    rev_q = select(func.coalesce(func.sum(Booking.total_amount), 0)).where(
        Booking.tenant_id == tenant_id,
        Booking.deleted_at == None,
        Booking.status.in_(["completed", "checked_in"]),
        Booking.check_in >= today_start,
    )
    if property_id:
        rev_q = rev_q.where(Booking.property_id == property_id)
    daily_revenue = float((await db.execute(rev_q)).scalar() or 0)

    # Pending SOP tasks
    sop_q = select(func.count(SOPItem.id)).where(
        SOPItem.tenant_id == tenant_id,
        SOPItem.deleted_at == None,
        SOPItem.status == "pending",
    )
    if property_id:
        sop_q = sop_q.where(SOPItem.property_id == property_id)
    pending_tasks = (await db.execute(sop_q)).scalar() or 0

    # Overdue SOP tasks
    overdue_q = select(func.count(SOPItem.id)).where(
        SOPItem.tenant_id == tenant_id,
        SOPItem.deleted_at == None,
        SOPItem.status == "pending",
        SOPItem.due_date < datetime.utcnow(),
    )
    if property_id:
        overdue_q = overdue_q.where(SOPItem.property_id == property_id)
    overdue_tasks = (await db.execute(overdue_q)).scalar() or 0

    # Revenue trend — last 7 days
    revenue_trend = []
    for i, day in enumerate(_get_week_days()):
        day_start = datetime.combine(day, datetime.min.time())
        day_end = day_start + timedelta(days=1)
        day_rev_q = select(func.coalesce(func.sum(Booking.total_amount), 0)).where(
            Booking.tenant_id == tenant_id,
            Booking.deleted_at == None,
            Booking.status.in_(["completed", "checked_in"]),
            Booking.check_in >= day_start,
            Booking.check_in < day_end,
        )
        if property_id:
            day_rev_q = day_rev_q.where(Booking.property_id == property_id)
        day_revenue = float((await db.execute(day_rev_q)).scalar() or 0)
        revenue_trend.append({"day": DAY_NAMES[i], "revenue": day_revenue})

    # Recent alerts — low stock alerts
    alert_q = select(LowStockAlert, InventoryItem, Property).join(
        InventoryItem, LowStockAlert.item_id == InventoryItem.id
    ).join(
        Property, LowStockAlert.property_id == Property.id
    ).where(
        LowStockAlert.tenant_id == tenant_id,
        LowStockAlert.is_resolved == False,
    ).order_by(LowStockAlert.triggered_at.desc()).limit(5)

    alert_result = await db.execute(alert_q)
    recent_alerts = []
    for alert, item, prop in alert_result.all():
        recent_alerts.append({
            "type": "low_stock",
            "title": f"Low inventory: {item.item_name}",
            "property_name": prop.name,
            "time_ago": _time_ago(alert.triggered_at),
            "severity": "warning",
        })

    return {
        "total_properties": total_properties,
        "total_staff": total_staff,
        "daily_revenue": daily_revenue,
        "pending_tasks": pending_tasks,
        "overdue_tasks": overdue_tasks,
        "revenue_trend": revenue_trend,
        "recent_alerts": recent_alerts,
    }


# ── Manager Stats ─────────────────────────────────────────────────────────────

async def get_manager_stats(
    db: AsyncSession,
    tenant_id: UUID,
    property_id: UUID,
) -> dict:
    """Stats for Manager dashboard — scoped to a single property."""
    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    today_end = today_start + timedelta(days=1)

    # Total staff for this property
    total_staff_q = select(func.count(Employee.id)).where(
        Employee.property_id == property_id,
        Employee.tenant_id == tenant_id,
        Employee.deleted_at == None,
        Employee.is_active == True,
    )
    total_staff = (await db.execute(total_staff_q)).scalar() or 0

    # Staff present — employees with no end_date (active, on shift)
    # Simple heuristic: active employees with start_date <= today
    present_q = select(func.count(Employee.id)).where(
        Employee.property_id == property_id,
        Employee.tenant_id == tenant_id,
        Employee.deleted_at == None,
        Employee.is_active == True,
        Employee.start_date <= datetime.utcnow(),
    )
    staff_present = min((await db.execute(present_q)).scalar() or 0, total_staff)

    # Tasks pending (SOPs)
    pending_q = select(func.count(SOPItem.id)).where(
        SOPItem.property_id == property_id,
        SOPItem.tenant_id == tenant_id,
        SOPItem.deleted_at == None,
        SOPItem.status == "pending",
    )
    tasks_pending = (await db.execute(pending_q)).scalar() or 0

    # Tasks overdue
    overdue_q = select(func.count(SOPItem.id)).where(
        SOPItem.property_id == property_id,
        SOPItem.tenant_id == tenant_id,
        SOPItem.deleted_at == None,
        SOPItem.status == "pending",
        SOPItem.due_date < datetime.utcnow(),
    )
    tasks_overdue = (await db.execute(overdue_q)).scalar() or 0

    # Check-ins today
    checkin_q = select(func.count(Booking.id)).where(
        Booking.property_id == property_id,
        Booking.tenant_id == tenant_id,
        Booking.deleted_at == None,
        Booking.check_in >= today_start,
        Booking.check_in < today_end,
    )
    checkins_today = (await db.execute(checkin_q)).scalar() or 0

    # Daily revenue
    rev_q = select(func.coalesce(func.sum(Booking.total_amount), 0)).where(
        Booking.property_id == property_id,
        Booking.tenant_id == tenant_id,
        Booking.deleted_at == None,
        Booking.status.in_(["completed", "checked_in"]),
        Booking.check_in >= today_start,
        Booking.check_in < today_end,
    )
    daily_revenue = float((await db.execute(rev_q)).scalar() or 0)

    # Today's tasks (SOPs due today)
    tasks_q = select(SOPItem, Employee).outerjoin(
        Employee, SOPItem.assigned_employee_id == Employee.id
    ).where(
        SOPItem.property_id == property_id,
        SOPItem.tenant_id == tenant_id,
        SOPItem.deleted_at == None,
        SOPItem.due_date >= today_start,
        SOPItem.due_date < today_end,
    ).limit(10)

    tasks_result = await db.execute(tasks_q)
    todays_tasks = []
    for sop, emp in tasks_result.all():
        assignee = f"{emp.first_name} {emp.last_name}" if emp else "Unassigned"
        due_str = sop.due_date.strftime("%I:%M %p") if sop.due_date else "—"
        todays_tasks.append({
            "id": sop.id,
            "task": sop.title,
            "assignee": assignee,
            "due": due_str,
            "status": sop.status,
        })

    # Staff attendance list
    emp_list_q = select(Employee, Department).outerjoin(
        Department, Employee.department_id == Department.id
    ).where(
        Employee.property_id == property_id,
        Employee.tenant_id == tenant_id,
        Employee.deleted_at == None,
        Employee.is_active == True,
    ).limit(10)

    emp_result = await db.execute(emp_list_q)
    staff_attendance = []
    for emp, dept in emp_result.all():
        initials = (
            (emp.first_name[0] if emp.first_name else "") +
            (emp.last_name[0] if emp.last_name else "")
        ).upper()
        staff_attendance.append({
            "name": f"{emp.first_name} {emp.last_name}",
            "dept": dept.name if dept else "—",
            "check_in": emp.start_date.strftime("%I:%M") if emp.start_date else "—",
            "status": "in" if emp.is_active else "absent",
            "initials": initials,
        })

    # Weekly task completion
    weekly_tasks = []
    for i, day in enumerate(_get_week_days()):
        day_start = datetime.combine(day, datetime.min.time())
        day_end = day_start + timedelta(days=1)

        total_q = select(func.count(SOPItem.id)).where(
            SOPItem.property_id == property_id,
            SOPItem.tenant_id == tenant_id,
            SOPItem.deleted_at == None,
            SOPItem.due_date >= day_start,
            SOPItem.due_date < day_end,
        )
        done_q = select(func.count(SOPItem.id)).where(
            SOPItem.property_id == property_id,
            SOPItem.tenant_id == tenant_id,
            SOPItem.deleted_at == None,
            SOPItem.status == "completed",
            SOPItem.due_date >= day_start,
            SOPItem.due_date < day_end,
        )
        total = (await db.execute(total_q)).scalar() or 0
        done = (await db.execute(done_q)).scalar() or 0
        weekly_tasks.append({"day": DAY_NAMES[i], "done": done, "total": total})

    return {
        "staff_present": staff_present,
        "staff_total": total_staff,
        "tasks_pending": tasks_pending,
        "tasks_overdue": tasks_overdue,
        "checkins_today": checkins_today,
        "daily_revenue": daily_revenue,
        "todays_tasks": todays_tasks,
        "staff_attendance": staff_attendance,
        "weekly_tasks": weekly_tasks,
    }


# ── Staff Stats ───────────────────────────────────────────────────────────────

async def get_staff_stats(
    db: AsyncSession,
    tenant_id: UUID,
    user_id: UUID,
) -> dict:
    """Stats for Staff dashboard — scoped to the logged-in user only."""
    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    today_end = today_start + timedelta(days=1)
    week_start = datetime.combine(_get_week_days()[0], datetime.min.time())

    # Get employee record for this user
    emp_q = select(Employee).where(
        Employee.user_id == user_id,
        Employee.tenant_id == tenant_id,
        Employee.deleted_at == None,
    )
    emp_result = await db.execute(emp_q)
    employee = emp_result.scalar_one_or_none()

    # Shift hours — simple calculation from start_date
    shift_hours = 0.0
    if employee and employee.start_date:
        start = employee.start_date.replace(tzinfo=None)
        diff = datetime.utcnow() - start
        shift_hours = round(min(diff.total_seconds() / 3600, 12), 1)

    # My tasks today
    base_sop_filter = [
        SOPItem.tenant_id == tenant_id,
        SOPItem.deleted_at == None,
    ]
    if employee:
        base_sop_filter.append(SOPItem.assigned_employee_id == employee.id)

    my_today_q = select(func.count(SOPItem.id)).where(
        *base_sop_filter,
        SOPItem.due_date >= today_start,
        SOPItem.due_date < today_end,
    )
    my_tasks_today = (await db.execute(my_today_q)).scalar() or 0

    # My overdue tasks
    overdue_q = select(func.count(SOPItem.id)).where(
        *base_sop_filter,
        SOPItem.status == "pending",
        SOPItem.due_date < datetime.utcnow(),
    )
    my_tasks_overdue = (await db.execute(overdue_q)).scalar() or 0

    # Completed this week
    completed_q = select(func.count(SOPItem.id)).where(
        *base_sop_filter,
        SOPItem.status == "completed",
        SOPItem.due_date >= week_start,
    )
    completed_this_week = (await db.execute(completed_q)).scalar() or 0

    # Pending SOPs to read
    pending_sop_q = select(func.count(SOPItem.id)).where(
        SOPItem.tenant_id == tenant_id,
        SOPItem.deleted_at == None,
        SOPItem.status == "pending",
        SOPItem.assigned_employee_id == (employee.id if employee else None),
    )
    pending_sops = (await db.execute(pending_sop_q)).scalar() or 0

    # Today's task list
    tasks_list_q = select(SOPItem).where(
        *base_sop_filter,
        SOPItem.due_date >= today_start,
        SOPItem.due_date < today_end,
    ).limit(10)

    tasks_result = await db.execute(tasks_list_q)
    todays_tasks = []
    for sop in tasks_result.scalars().all():
        due_str = sop.due_date.strftime("%I:%M %p") if sop.due_date else "—"
        todays_tasks.append({
            "id": sop.id,
            "task": sop.title,
            "assignee": "Me",
            "due": due_str,
            "status": sop.status,
        })

    # Weekly performance
    weekly_performance = []
    for i, day in enumerate(_get_week_days()):
        day_start = datetime.combine(day, datetime.min.time())
        day_end = day_start + timedelta(days=1)

        total_q = select(func.count(SOPItem.id)).where(
            *base_sop_filter,
            SOPItem.due_date >= day_start,
            SOPItem.due_date < day_end,
        )
        done_q = select(func.count(SOPItem.id)).where(
            *base_sop_filter,
            SOPItem.status == "completed",
            SOPItem.due_date >= day_start,
            SOPItem.due_date < day_end,
        )
        total = (await db.execute(total_q)).scalar() or 0
        done = (await db.execute(done_q)).scalar() or 0
        weekly_performance.append({"day": DAY_NAMES[i], "done": done, "total": total})

    return {
        "shift_hours": shift_hours,
        "my_tasks_today": my_tasks_today,
        "my_tasks_overdue": my_tasks_overdue,
        "completed_this_week": completed_this_week,
        "pending_sops": pending_sops,
        "todays_tasks": todays_tasks,
        "weekly_performance": weekly_performance,
    }