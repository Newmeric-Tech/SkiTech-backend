"""
Superadmin Endpoints - app/api/v1/endpoints/superadmin.py

Platform-level routes restricted to Super Admin role only.
Queries across all tenants without tenant_id scoping.
"""

import csv
import io
import logging
from datetime import datetime, timezone, timedelta
from typing import Any, List, Optional
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Response, status

logger = logging.getLogger(__name__)
from sqlalchemy import func, select, and_, or_, update, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user, require_roles
from app.core.database import get_db
from app.models.models import (
    AuditLog, DemoRequest, Property, Role, RolePermission, User,
)

router = APIRouter(prefix="/superadmin", tags=["Superadmin"])

require_superadmin = require_roles(["Super Admin"])


# ── Overview ─────────────────────────────────────────────────────────────────

@router.get("/overview")
async def get_overview(
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_superadmin),
) -> Any:
    total_props = (await db.execute(
        select(func.count()).select_from(Property).where(Property.deleted_at == None)
    )).scalar() or 0

    active_users = (await db.execute(
        select(func.count()).select_from(User).where(
            User.is_active == True, User.deleted_at == None
        )
    )).scalar() or 0

    recent_logs = (await db.execute(
        select(AuditLog).order_by(AuditLog.created_at.desc()).limit(10)
    )).scalars().all()

    top_props_result = (await db.execute(
        select(Property).where(Property.deleted_at == None).limit(5)
    )).scalars().all()

    top_properties = [
        {
            "id": str(p.id),
            "name": p.name,
            "location": f"{p.city or ''}, {p.country or ''}".strip(", "),
            "user_count": 0,
            "health_score": 100,
        }
        for p in top_props_result
    ]

    severity_map = {"low": "info", "medium": "info", "high": "warning", "critical": "critical"}

    recent_activity = [
        {
            "id": str(log.id),
            "action": log.action,
            "detail": log.details or f"{log.resource_type} {log.action}",
            "type": "system",
            "created_at": log.created_at.isoformat() if log.created_at else "",
        }
        for log in recent_logs
    ]

    return {
        "stats": {
            "total_properties": total_props,
            "active_users": active_users,
            "open_tickets": 0,
            "platform_uptime": 99.9,
            "properties_change": "+0%",
            "users_change": "+0%",
            "tickets_change": "0",
            "uptime_change": "0%",
        },
        "recent_activity": recent_activity,
        "top_properties": top_properties,
    }


# ── Analytics ─────────────────────────────────────────────────────────────────

@router.get("/analytics")
async def get_analytics(
    period: str = Query("30d"),
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_superadmin),
) -> Any:
    total_users = (await db.execute(
        select(func.count()).select_from(User).where(User.deleted_at == None)
    )).scalar() or 0

    total_props = (await db.execute(
        select(func.count()).select_from(Property).where(Property.deleted_at == None)
    )).scalar() or 0

    props_by_city_result = (await db.execute(
        select(Property.city, func.count().label("count"))
        .where(Property.deleted_at == None, Property.city != None)
        .group_by(Property.city)
        .limit(10)
    )).all()

    top_props_result = (await db.execute(
        select(Property).where(Property.deleted_at == None).limit(5)
    )).scalars().all()

    return {
        "kpis": {
            "monthly_revenue": 0,
            "total_users": total_users,
            "total_properties": total_props,
            "avg_occupancy": 0,
            "churn_rate": 0,
            "nps_score": 0,
        },
        "revenue_data": [],
        "user_growth": [],
        "properties_by_region": [
            {"region": row.city, "count": row.count} for row in props_by_city_result
        ],
        "top_properties": [
            {
                "name": p.name,
                "owner": "",
                "occupancy": 0,
                "revenue": 0,
                "growth": 0,
            }
            for p in top_props_result
        ],
    }


# ── Audit ─────────────────────────────────────────────────────────────────────

@router.get("/audit")
async def get_audit(
    search: Optional[str] = Query(None),
    action: Optional[str] = Query(None),
    severity: Optional[str] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, le=200),
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_superadmin),
) -> Any:
    filters = []
    if action:
        filters.append(AuditLog.action == action)
    if severity:
        db_severity = {"info": "low", "warning": "medium", "critical": "critical"}.get(severity, severity)
        filters.append(AuditLog.severity == db_severity)
    if search:
        filters.append(
            or_(
                AuditLog.user_email.ilike(f"%{search}%"),
                AuditLog.action.ilike(f"%{search}%"),
                AuditLog.details.ilike(f"%{search}%"),
            )
        )

    query = select(AuditLog).order_by(AuditLog.created_at.desc()).offset(skip).limit(limit)
    if filters:
        query = query.where(and_(*filters))

    count_query = select(func.count()).select_from(AuditLog)
    if filters:
        count_query = count_query.where(and_(*filters))

    total = (await db.execute(count_query)).scalar() or 0
    logs = (await db.execute(query)).scalars().all()

    severity_map = {"low": "info", "medium": "warning", "high": "warning", "critical": "critical"}

    return {
        "events": [
            {
                "id": str(log.id),
                "timestamp": log.created_at.isoformat() if log.created_at else "",
                "user": log.user_email or "system",
                "action": log.action,
                "resource": log.resource_type,
                "details": log.details or "",
                "severity": severity_map.get(log.severity or "low", "info"),
            }
            for log in logs
        ],
        "total": total,
        "log_size": f"{total} records",
    }


@router.get("/audit/export")
async def export_audit(
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_superadmin),
) -> Response:
    logs = (await db.execute(
        select(AuditLog).order_by(AuditLog.created_at.desc()).limit(1000)
    )).scalars().all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Timestamp", "User", "Action", "Resource", "Details", "Severity"])
    for log in logs:
        writer.writerow([
            log.created_at.isoformat() if log.created_at else "",
            log.user_email or "",
            log.action,
            log.resource_type,
            log.details or "",
            log.severity or "low",
        ])

    return Response(
        content=output.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=audit_log.csv"},
    )


# ── Health ─────────────────────────────────────────────────────────────────────

@router.get("/health")
async def get_health(
    user: dict = Depends(require_superadmin),
) -> Any:
    now = datetime.now(timezone.utc).isoformat()
    return {
        "services": [
            {"id": 1, "name": "API Server", "status": "healthy", "uptime": 99.9, "last_checked": now, "latency": 12},
            {"id": 2, "name": "Database", "status": "healthy", "uptime": 99.95, "last_checked": now, "latency": 5},
            {"id": 3, "name": "Auth Service", "status": "healthy", "uptime": 100.0, "last_checked": now, "latency": 8},
            {"id": 4, "name": "File Storage", "status": "healthy", "uptime": 99.8, "last_checked": now, "latency": 30},
        ],
        "latency_data": [],
        "error_rate_data": [],
        "incidents": [],
        "resource_usage": [
            {"name": "CPU", "value": 28},
            {"name": "Memory", "value": 54},
            {"name": "Disk", "value": 41},
            {"name": "Network", "value": 17},
        ],
    }


# ── Properties ────────────────────────────────────────────────────────────────

@router.get("/properties")
async def list_properties(
    search: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, le=200),
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_superadmin),
) -> Any:
    filters = [Property.deleted_at == None]
    if search:
        filters.append(Property.name.ilike(f"%{search}%"))
    if status == "active":
        filters.append(Property.is_active == True)
    elif status == "inactive":
        filters.append(Property.is_active == False)

    props = (await db.execute(
        select(Property).where(and_(*filters)).offset(skip).limit(limit)
    )).scalars().all()

    return [
        {
            "id": str(p.id),
            "name": p.name,
            "owner": "",
            "location": f"{p.city or ''}, {p.country or ''}".strip(", "),
            "units": p.num_rooms or 0,
            "staff": 0,
            "occupancy": 0,
            "health": 100,
            "status": "active" if p.is_active else "inactive",
        }
        for p in props
    ]


@router.post("/properties", status_code=status.HTTP_201_CREATED)
async def create_property(
    data: dict,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_superadmin),
) -> Any:
    raise HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail="Property creation requires a valid tenant_id. Use the owner portal to create properties.",
    )


@router.put("/properties/{property_id}")
async def update_property(
    property_id: str,
    data: dict,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_superadmin),
) -> Any:
    result = await db.execute(
        select(Property).where(Property.id == property_id, Property.deleted_at == None)
    )
    prop = result.scalar_one_or_none()
    if not prop:
        raise HTTPException(status_code=404, detail="Property not found")

    if "name" in data:
        prop.name = data["name"]
    if "is_active" in data:
        prop.is_active = data["is_active"]

    await db.commit()
    await db.refresh(prop)
    return {
        "id": str(prop.id),
        "name": prop.name,
        "status": "active" if prop.is_active else "inactive",
    }


@router.delete("/properties/{property_id}")
async def delete_property(
    property_id: str,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_superadmin),
) -> Any:
    result = await db.execute(
        select(Property).where(Property.id == property_id, Property.deleted_at == None)
    )
    prop = result.scalar_one_or_none()
    if not prop:
        raise HTTPException(status_code=404, detail="Property not found")

    prop.deleted_at = datetime.now(timezone.utc)
    await db.commit()
    return {"success": True, "message": "Property deleted"}


# ── Roles ─────────────────────────────────────────────────────────────────────

@router.get("/roles")
async def list_roles(
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_superadmin),
) -> Any:
    roles = (await db.execute(select(Role))).scalars().all()

    result = []
    for r in roles:
        user_count = (await db.execute(
            select(func.count()).select_from(User).where(
                User.role_id == r.id, User.deleted_at == None
            )
        )).scalar() or 0
        perm_count = (await db.execute(
            select(func.count()).select_from(RolePermission).where(RolePermission.role_id == r.id)
        )).scalar() or 0
        result.append({
            "id": str(r.id),
            "name": r.name,
            "description": r.description or "",
            "user_count": user_count,
            "permission_count": perm_count,
            "color": "#3B82F6",
            "is_system": True,
        })
    return result


@router.post("/roles", status_code=status.HTTP_201_CREATED)
async def create_role(
    data: dict,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_superadmin),
) -> Any:
    name = data.get("name", "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Role name is required")

    existing = (await db.execute(select(Role).where(Role.name == name))).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=400, detail=f"Role '{name}' already exists")

    role = Role(
        name=name,
        description=data.get("description", ""),
        role_level=99,
    )
    db.add(role)
    await db.commit()
    await db.refresh(role)
    return {
        "id": str(role.id),
        "name": role.name,
        "description": role.description or "",
        "user_count": 0,
        "permission_count": 0,
        "color": "#3B82F6",
        "is_system": False,
    }


@router.put("/roles/{role_id}")
async def update_role(
    role_id: str,
    data: dict,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_superadmin),
) -> Any:
    role = (await db.execute(select(Role).where(Role.id == role_id))).scalar_one_or_none()
    if not role:
        raise HTTPException(status_code=404, detail="Role not found")

    if "name" in data:
        role.name = data["name"]
    if "description" in data:
        role.description = data["description"]

    await db.commit()
    await db.refresh(role)
    return {"id": str(role.id), "name": role.name, "description": role.description or ""}


@router.delete("/roles/{role_id}")
async def delete_role(
    role_id: str,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_superadmin),
) -> Any:
    role = (await db.execute(select(Role).where(Role.id == role_id))).scalar_one_or_none()
    if not role:
        raise HTTPException(status_code=404, detail="Role not found")

    user_count = (await db.execute(
        select(func.count()).select_from(User).where(User.role_id == role.id, User.deleted_at == None)
    )).scalar() or 0
    if user_count > 0:
        raise HTTPException(status_code=400, detail=f"Cannot delete role with {user_count} active users")

    await db.delete(role)
    await db.commit()
    return {"success": True, "message": "Role deleted"}


# ── Settings ──────────────────────────────────────────────────────────────────

_platform_settings: dict = {
    "platform_name": "SkiTech",
    "support_email": "support@skitech.com",
    "timezone": "UTC",
    "session_timeout": 30,
    "two_factor_required": False,
    "maintenance_mode": False,
    "email_alerts": True,
    "slack_webhook": "",
}


@router.get("/settings")
async def get_settings(
    user: dict = Depends(require_superadmin),
) -> Any:
    return _platform_settings


@router.put("/settings")
async def update_settings(
    data: dict,
    user: dict = Depends(require_superadmin),
) -> Any:
    _platform_settings.update(data)
    return _platform_settings


# ── Users ─────────────────────────────────────────────────────────────────────

@router.get("/users")
async def list_users(
    search: Optional[str] = Query(None),
    role: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, le=200),
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_superadmin),
) -> Any:
    filters = [User.deleted_at == None, User.is_verified == True]
    if search:
        filters.append(
            or_(
                User.email.ilike(f"%{search}%"),
                User.first_name.ilike(f"%{search}%"),
                User.last_name.ilike(f"%{search}%"),
            )
        )
    if status == "suspended":
        filters.append(User.is_active == False)
    elif status == "active":
        filters.append(User.is_active == True)

    users = (await db.execute(
        select(User).where(and_(*filters)).offset(skip).limit(limit)
    )).scalars().all()

    result = []
    for u in users:
        role_obj = (await db.execute(
            select(Role).where(Role.id == u.role_id)
        )).scalar_one_or_none()
        role_name = role_obj.name if role_obj else "Unknown"

        if role and role_name != role:
            continue

        name = " ".join(filter(None, [u.first_name, u.last_name])) or u.email.split("@")[0]
        result.append({
            "id": str(u.id),
            "name": name,
            "email": u.email,
            "role": role_name,
            "property": str(u.property_id) if u.property_id else "",
            "last_active": u.last_login.isoformat() if u.last_login else "",
            "status": "active" if u.is_active else "suspended",
        })

    return result


@router.post("/users/invite", status_code=status.HTTP_201_CREATED)
async def invite_user(
    data: dict,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_superadmin),
) -> Any:
    email = data.get("email", "").strip().lower()
    if not email:
        raise HTTPException(status_code=400, detail="Email is required")

    existing = (await db.execute(
        select(User).where(User.email == email)
    )).scalar_one_or_none()
    if existing:
        if existing.deleted_at is not None:
            raise HTTPException(status_code=400, detail="This email was previously used and deleted. Please use a different email.")
        raise HTTPException(status_code=400, detail="User with this email already exists")

    _ROLE_MAP = {
        "Owner": "Tenant Admin", "owner": "Tenant Admin",
        "Manager": "Manager", "manager": "Manager",
        "Staff": "Staff", "staff": "Staff",
        "Superadmin": "Super Admin", "superadmin": "Super Admin",
        "Tenant Admin": "Tenant Admin", "Super Admin": "Super Admin",
    }
    raw_role = data.get("role", "Staff")
    role_name = _ROLE_MAP.get(raw_role, raw_role)
    role_obj = (await db.execute(select(Role).where(Role.name == role_name))).scalar_one_or_none()
    if not role_obj:
        raise HTTPException(status_code=400, detail=f"Role '{raw_role}' not found. Valid: Owner, Manager, Staff")

    full_name = data.get("full_name", "")
    parts = full_name.split(" ", 1)
    first_name = parts[0] if parts else ""
    last_name = parts[1] if len(parts) > 1 else ""

    from app.core.security import hash_password
    import secrets
    temp_password = secrets.token_urlsafe(16)

    tenant_id = data.get("tenant_id") or (user.get("tenant_id") or None)
    if not tenant_id:
        raise HTTPException(
            status_code=400,
            detail="tenant_id is required when inviting a user. Provide the target tenant's ID.",
        )

    new_user = User(
        email=email,
        password_hash=hash_password(temp_password),
        first_name=first_name,
        last_name=last_name,
        role_id=role_obj.id,
        tenant_id=tenant_id,
        property_id=data.get("property_id"),
        is_active=True,
        is_verified=False,
    )
    db.add(new_user)
    await db.commit()
    await db.refresh(new_user)

    from app.utils.otp import send_invitation
    background_tasks.add_task(send_invitation, email, temp_password)

    return {
        "id": str(new_user.id),
        "name": full_name,
        "email": new_user.email,
        "role": role_name,
        "property": data.get("property_id", ""),
        "last_active": "",
        "status": "pending",
    }


@router.put("/users/{user_id}/suspend")
async def suspend_user(
    user_id: str,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_superadmin),
) -> Any:
    if user_id == user.get("user_id"):
        raise HTTPException(status_code=400, detail="Cannot suspend your own account")

    target = (await db.execute(
        select(User).where(User.id == user_id, User.deleted_at == None)
    )).scalar_one_or_none()
    if not target:
        raise HTTPException(status_code=404, detail="User not found")

    target.is_active = False
    await db.commit()
    return {"success": True, "message": "User suspended"}


@router.put("/users/{user_id}/activate")
async def activate_user(
    user_id: str,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_superadmin),
) -> Any:
    target = (await db.execute(
        select(User).where(User.id == user_id, User.deleted_at == None)
    )).scalar_one_or_none()
    if not target:
        raise HTTPException(status_code=404, detail="User not found")

    target.is_active = True
    await db.commit()
    return {"success": True, "message": "User activated"}


@router.delete("/users/{user_id}")
async def delete_user(
    user_id: str,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_superadmin),
) -> Any:
    if user_id == user.get("user_id"):
        raise HTTPException(status_code=400, detail="Cannot delete your own account")

    try:
        uid = UUID(user_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid user_id format")

    target = (await db.execute(
        select(User).where(User.id == uid, User.deleted_at == None)
    )).scalar_one_or_none()
    if not target:
        raise HTTPException(status_code=404, detail="User not found")

    try:
        target.deleted_at = datetime.utcnow()   # naive UTC — matches DateTime column
        target.is_active = False
        await db.commit()
        return {"success": True, "message": "User deleted"}
    except Exception as e:
        await db.rollback()
        logger.error(f"[DELETE USER] {type(e).__name__}: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to delete user: {type(e).__name__}: {str(e)[:300]}",
        )


@router.put("/users/{user_id}/role")
async def update_user_role(
    user_id: str,
    data: dict,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_superadmin),
) -> Any:
    target = (await db.execute(
        select(User).where(User.id == user_id, User.deleted_at == None)
    )).scalar_one_or_none()
    if not target:
        raise HTTPException(status_code=404, detail="User not found")

    role_name = data.get("role", "")
    role_obj = (await db.execute(select(Role).where(Role.name == role_name))).scalar_one_or_none()
    if not role_obj:
        raise HTTPException(status_code=400, detail=f"Role '{role_name}' not found")

    target.role_id = role_obj.id
    await db.commit()
    return {"success": True, "message": f"User role updated to {role_name}"}


# ── Demo Requests ─────────────────────────────────────────────────────────────

@router.get("/demo-requests")
async def list_demo_requests(
    search: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_superadmin),
) -> Any:
    q = select(DemoRequest).order_by(DemoRequest.created_at.desc())
    if status:
        q = q.where(DemoRequest.status == status)
    if search:
        term = f"%{search}%"
        q = q.where(or_(
            DemoRequest.name.ilike(term),
            DemoRequest.email.ilike(term),
            DemoRequest.company.ilike(term),
        ))
    rows = (await db.execute(q)).scalars().all()
    return [
        {
            "id": str(r.id),
            "name": r.name,
            "email": r.email,
            "company": r.company,
            "phone": r.phone,
            "portfolio_size": r.portfolio_size,
            "role": r.role,
            "message": r.message,
            "status": r.status,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
    ]


@router.put("/demo-requests/{request_id}/status")
async def update_demo_status(
    request_id: str,
    data: dict,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_superadmin),
) -> Any:
    from uuid import UUID as _UUID
    row = (await db.execute(
        select(DemoRequest).where(DemoRequest.id == _UUID(request_id))
    )).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Demo request not found")
    row.status = data.get("status", row.status)
    await db.commit()
    return {"success": True, "status": row.status}
