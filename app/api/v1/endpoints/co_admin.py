"""
Co-Admin Endpoints - app/api/v1/endpoints/co_admin.py

Two-sided flow:
  - Owner side: Tenant Admin submits a co-admin request for a partner on their property
  - Superadmin side: Super Admin reviews, approves (auto-invites), or rejects requests
"""

import secrets
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user, require_roles, get_db
from app.models.models import CoAdminRequest, Property, Role, Tenant, User

# Owner-side routes (Tenant Admin submits requests)
owner_router = APIRouter(prefix="/co-admin", tags=["Co Admin"])

# Superadmin-side routes (Super Admin manages requests)
admin_router = APIRouter(prefix="/superadmin/co-admin-requests", tags=["Co Admin - Admin"])

require_tenant_admin = require_roles(["Tenant Admin"])
require_superadmin   = require_roles(["Super Admin"])


# ── Owner: submit a co-admin request ─────────────────────────────────────────

@owner_router.post("/requests", status_code=status.HTTP_201_CREATED)
async def submit_co_admin_request(
    data: dict,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_tenant_admin),
) -> Any:
    tenant_id   = user.get("tenant_id")
    property_id = data.get("property_id")
    proposed_email = (data.get("proposed_email") or "").strip().lower()
    proposed_name  = (data.get("proposed_name") or "").strip()

    if not property_id:
        raise HTTPException(status_code=400, detail="property_id is required")
    if not proposed_email:
        raise HTTPException(status_code=400, detail="proposed_email is required")
    if not proposed_name:
        raise HTTPException(status_code=400, detail="proposed_name is required")

    # Validate the property belongs to this tenant
    prop = (await db.execute(
        select(Property).where(
            Property.id == UUID(property_id),
            Property.tenant_id == UUID(tenant_id),
            Property.deleted_at == None,
        )
    )).scalar_one_or_none()
    if not prop:
        raise HTTPException(status_code=404, detail="Property not found or does not belong to your account")

    # Check for duplicate pending request for same email + property
    duplicate = (await db.execute(
        select(CoAdminRequest).where(
            CoAdminRequest.proposed_email == proposed_email,
            CoAdminRequest.property_id == UUID(property_id),
            CoAdminRequest.status == "pending",
        )
    )).scalar_one_or_none()
    if duplicate:
        raise HTTPException(status_code=409, detail="A pending co-admin request for this email and property already exists")

    req = CoAdminRequest(
        requesting_user_id=UUID(user["user_id"]),
        tenant_id=UUID(tenant_id),
        property_id=UUID(property_id),
        proposed_email=proposed_email,
        proposed_name=proposed_name,
        status="pending",
    )
    db.add(req)
    await db.commit()
    await db.refresh(req)

    return {
        "id": str(req.id),
        "status": req.status,
        "proposed_email": req.proposed_email,
        "proposed_name": req.proposed_name,
        "property_id": str(req.property_id),
        "created_at": req.created_at.isoformat() if req.created_at else "",
    }


@owner_router.get("/requests")
async def list_my_co_admin_requests(
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_tenant_admin),
) -> Any:
    tenant_id = user.get("tenant_id")

    requests = (await db.execute(
        select(CoAdminRequest).where(
            CoAdminRequest.tenant_id == UUID(tenant_id)
        ).order_by(CoAdminRequest.created_at.desc())
    )).scalars().all()

    result = []
    for r in requests:
        prop = (await db.execute(select(Property).where(Property.id == r.property_id))).scalar_one_or_none()
        result.append({
            "id": str(r.id),
            "status": r.status,
            "proposed_email": r.proposed_email,
            "proposed_name": r.proposed_name,
            "property_id": str(r.property_id),
            "property_name": prop.name if prop else "",
            "superadmin_note": r.superadmin_note,
            "created_at": r.created_at.isoformat() if r.created_at else "",
        })
    return result


# ── Superadmin: view all requests ─────────────────────────────────────────────

@admin_router.get("")
async def list_co_admin_requests(
    status_filter: str = Query(None, alias="status"),
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_superadmin),
) -> Any:
    query = select(CoAdminRequest).order_by(CoAdminRequest.created_at.desc())
    if status_filter:
        query = query.where(CoAdminRequest.status == status_filter)

    requests = (await db.execute(query)).scalars().all()

    result = []
    for r in requests:
        prop    = (await db.execute(select(Property).where(Property.id == r.property_id))).scalar_one_or_none()
        tenant  = (await db.execute(select(Tenant).where(Tenant.id == r.tenant_id))).scalar_one_or_none()
        requester = (await db.execute(select(User).where(User.id == r.requesting_user_id))).scalar_one_or_none()
        result.append({
            "id": str(r.id),
            "status": r.status,
            "proposed_email": r.proposed_email,
            "proposed_name": r.proposed_name,
            "property_id": str(r.property_id),
            "property_name": prop.name if prop else "",
            "tenant_id": str(r.tenant_id),
            "tenant_name": tenant.business_name if tenant else "",
            "requester_name": f"{requester.first_name or ''} {requester.last_name or ''}".strip() if requester else "",
            "requester_email": requester.email if requester else "",
            "superadmin_note": r.superadmin_note,
            "created_at": r.created_at.isoformat() if r.created_at else "",
        })
    return result


# ── Superadmin: approve (auto-invite) ─────────────────────────────────────────

@admin_router.post("/{request_id}/approve", status_code=status.HTTP_200_OK)
async def approve_co_admin_request(
    request_id: str,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_superadmin),
) -> Any:
    req = (await db.execute(
        select(CoAdminRequest).where(CoAdminRequest.id == UUID(request_id))
    )).scalar_one_or_none()
    if not req:
        raise HTTPException(status_code=404, detail="Co-admin request not found")
    if req.status != "pending":
        raise HTTPException(status_code=400, detail=f"Request is already '{req.status}'")

    # Check if a user with this email already exists
    existing = (await db.execute(
        select(User).where(User.email == req.proposed_email)
    )).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=409, detail="A user with this email already exists")

    # Resolve Co Admin role
    co_admin_role = (await db.execute(
        select(Role).where(Role.name == "Co Admin")
    )).scalar_one_or_none()
    if not co_admin_role:
        raise HTTPException(status_code=500, detail="Co Admin role not found — run seed_roles.py")

    # Create the user
    from app.core.security import hash_password
    temp_password = secrets.token_urlsafe(16)
    parts = req.proposed_name.split(" ", 1)
    first_name = parts[0]
    last_name  = parts[1] if len(parts) > 1 else ""

    new_user = User(
        email=req.proposed_email,
        password_hash=hash_password(temp_password),
        first_name=first_name,
        last_name=last_name,
        role_id=co_admin_role.id,
        tenant_id=req.tenant_id,       # existing tenant — NOT a new one
        property_id=req.property_id,   # scoped to the requested property
        is_active=True,
        is_verified=False,
    )
    db.add(new_user)
    await db.commit()
    await db.refresh(new_user)

    # Generate OTP
    from app.utils.otp import generate_otp, send_invitation
    otp = generate_otp()
    new_user.otp_code = otp
    new_user.otp_expires_at = datetime.utcnow() + timedelta(seconds=300)
    await db.commit()

    # Send invite email in background
    background_tasks.add_task(send_invitation, req.proposed_email, temp_password, otp)

    # Mark request as approved
    req.status = "approved"
    req.invited_user_id = new_user.id
    await db.commit()

    return {
        "success": True,
        "message": f"Co Admin invite sent to {req.proposed_email}",
        "invited_user_id": str(new_user.id),
        "temp_password": temp_password,
    }


# ── Superadmin: reject ────────────────────────────────────────────────────────

@admin_router.post("/{request_id}/reject", status_code=status.HTTP_200_OK)
async def reject_co_admin_request(
    request_id: str,
    data: dict,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_superadmin),
) -> Any:
    req = (await db.execute(
        select(CoAdminRequest).where(CoAdminRequest.id == UUID(request_id))
    )).scalar_one_or_none()
    if not req:
        raise HTTPException(status_code=404, detail="Co-admin request not found")
    if req.status != "pending":
        raise HTTPException(status_code=400, detail=f"Request is already '{req.status}'")

    req.status = "rejected"
    req.superadmin_note = data.get("note", "")
    await db.commit()

    return {"success": True, "message": "Request rejected"}
