"""
Subscriptions Routes - app/api/v1/endpoints/subscriptions.py

GET  /subscriptions/plans           → list all plans (superadmin)
GET  /subscriptions/my-plan         → current tenant's active plan + features
POST /subscriptions/assign          → assign a plan to a tenant (superadmin)
"""

from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user, require_roles
from app.core.database import get_db
from app.models.models import SubscriptionPlan, TenantSubscription

router = APIRouter(prefix="/subscriptions", tags=["Subscriptions"])


# ── Schemas ───────────────────────────────────────────────────────────────────

class PlanResponse(BaseModel):
    id: UUID
    name: str
    price: float
    max_properties: Optional[int]
    max_users: Optional[int]
    features: Optional[Dict[str, Any]]

    class Config:
        from_attributes = True


class MyPlanResponse(BaseModel):
    subscription_id: UUID
    status: str
    start_date: datetime
    end_date: Optional[datetime]
    plan: PlanResponse
    features: Dict[str, Any]


class AssignPlanRequest(BaseModel):
    tenant_id: UUID
    plan_id: UUID
    start_date: Optional[datetime] = None


class SelectPlanRequest(BaseModel):
    plan_id: UUID


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _get_active_subscription(db: AsyncSession, tenant_id: UUID):
    result = await db.execute(
        select(TenantSubscription)
        .where(
            TenantSubscription.tenant_id == tenant_id,
            TenantSubscription.status == "active",
        )
        .order_by(TenantSubscription.created_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def _auto_assign_starter(db: AsyncSession, tenant_id: UUID):
    """Find the lowest-price plan and assign it as the tenant's active subscription."""
    plan_result = await db.execute(
        select(SubscriptionPlan).order_by(SubscriptionPlan.price).limit(1)
    )
    starter = plan_result.scalar_one_or_none()
    if not starter:
        raise HTTPException(status_code=503, detail="No subscription plans configured. Contact support.")
    sub = TenantSubscription(
        tenant_id=tenant_id,
        plan_id=starter.id,
        start_date=datetime.utcnow(),
        status="active",
    )
    db.add(sub)
    await db.commit()
    await db.refresh(sub)
    return sub, starter


# ── Routes ────────────────────────────────────────────────────────────────────

@router.get("/plans", response_model=List[PlanResponse])
async def list_plans(
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """List all subscription plans."""
    result = await db.execute(select(SubscriptionPlan).order_by(SubscriptionPlan.price))
    return result.scalars().all()


@router.get("/my-plan", response_model=MyPlanResponse)
async def get_my_plan(
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """Get the current tenant's active subscription plan. Auto-assigns Starter if none exists."""
    tenant_id = UUID(user["tenant_id"])

    sub = await _get_active_subscription(db, tenant_id)

    if not sub:
        sub, plan = await _auto_assign_starter(db, tenant_id)
    else:
        plan_result = await db.execute(
            select(SubscriptionPlan).where(SubscriptionPlan.id == sub.plan_id)
        )
        plan = plan_result.scalar_one_or_none()
        if not plan:
            raise HTTPException(status_code=404, detail="Subscription plan not found")

    features = plan.features or {}

    return MyPlanResponse(
        subscription_id=sub.id,
        status=sub.status,
        start_date=sub.start_date,
        end_date=sub.end_date,
        plan=PlanResponse(
            id=plan.id,
            name=plan.name,
            price=float(plan.price),
            max_properties=plan.max_properties,
            max_users=plan.max_users,
            features=features,
        ),
        features=features,
    )


@router.post("/select-plan", response_model=MyPlanResponse)
async def select_plan(
    data: SelectPlanRequest,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_roles(["Super Admin", "Tenant Admin"])),
):
    """Allow a Tenant Admin to choose their subscription plan."""
    tenant_id = UUID(user["tenant_id"])

    plan_result = await db.execute(
        select(SubscriptionPlan).where(SubscriptionPlan.id == data.plan_id)
    )
    plan = plan_result.scalar_one_or_none()
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")

    # Expire any existing active subscriptions
    existing = await db.execute(
        select(TenantSubscription).where(
            TenantSubscription.tenant_id == tenant_id,
            TenantSubscription.status == "active",
        )
    )
    for old_sub in existing.scalars().all():
        old_sub.status = "expired"

    new_sub = TenantSubscription(
        tenant_id=tenant_id,
        plan_id=plan.id,
        start_date=datetime.utcnow(),
        status="active",
    )
    db.add(new_sub)
    await db.commit()
    await db.refresh(new_sub)

    features = plan.features or {}
    return MyPlanResponse(
        subscription_id=new_sub.id,
        status=new_sub.status,
        start_date=new_sub.start_date,
        end_date=new_sub.end_date,
        plan=PlanResponse(
            id=plan.id,
            name=plan.name,
            price=float(plan.price),
            max_properties=plan.max_properties,
            max_users=plan.max_users,
            features=features,
        ),
        features=features,
    )


@router.post("/assign")
async def assign_plan(
    data: AssignPlanRequest,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_roles(["Super Admin"])),
):
    """Assign a subscription plan to a tenant. Deactivates the previous active plan."""
    existing = await db.execute(
        select(TenantSubscription).where(
            TenantSubscription.tenant_id == data.tenant_id,
            TenantSubscription.status == "active",
        )
    )
    for sub in existing.scalars().all():
        sub.status = "expired"

    plan_result = await db.execute(
        select(SubscriptionPlan).where(SubscriptionPlan.id == data.plan_id)
    )
    if not plan_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Plan not found")

    new_sub = TenantSubscription(
        tenant_id=data.tenant_id,
        plan_id=data.plan_id,
        start_date=data.start_date or datetime.utcnow(),
        status="active",
    )
    db.add(new_sub)
    await db.commit()
    await db.refresh(new_sub)
    return {"message": "Plan assigned successfully", "subscription_id": str(new_sub.id)}
