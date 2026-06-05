"""
Subscriptions Routes - app/api/v1/endpoints/subscriptions.py

GET  /subscriptions/plans                   → list all plans
GET  /subscriptions/my-plan                 → current tenant's active plan + features
POST /subscriptions/select-plan             → tenant admin selects plan (free/downgrade)
POST /subscriptions/assign                  → superadmin assigns plan to tenant
POST /subscriptions/create-checkout-session → create Stripe checkout for paid upgrade
POST /subscriptions/create-portal-session   → Stripe billing portal (manage/cancel)
POST /subscriptions/webhook                 → Stripe webhook handler (signature verified)
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

import stripe
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user, require_roles
from app.core.config import settings
from app.core.database import get_db
from app.models.models import SubscriptionPlan, Tenant, TenantSubscription

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/subscriptions", tags=["Subscriptions"])

if settings.STRIPE_SECRET_KEY:
    stripe.api_key = settings.STRIPE_SECRET_KEY


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


class CheckoutSessionRequest(BaseModel):
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


def _build_my_plan_response(sub: TenantSubscription, plan: SubscriptionPlan) -> MyPlanResponse:
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


async def _get_or_create_stripe_customer(db: AsyncSession, tenant: Tenant, user: dict) -> str:
    """Return the tenant's Stripe customer ID, creating one if needed."""
    if tenant.stripe_customer_id:
        return tenant.stripe_customer_id

    email = tenant.contact_email or user.get("email", "")
    customer = stripe.Customer.create(
        email=email,
        name=tenant.business_name,
        metadata={"tenant_id": str(tenant.id)},
    )
    tenant.stripe_customer_id = customer["id"]
    await db.commit()
    return customer["id"]


# ── Routes ────────────────────────────────────────────────────────────────────

@router.get("/plans", response_model=List[PlanResponse])
async def list_plans(
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    result = await db.execute(select(SubscriptionPlan).order_by(SubscriptionPlan.price))
    return result.scalars().all()


@router.get("/my-plan", response_model=MyPlanResponse)
async def get_my_plan(
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
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

    return _build_my_plan_response(sub, plan)


@router.post("/select-plan", response_model=MyPlanResponse)
async def select_plan(
    data: SelectPlanRequest,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_roles(["Super Admin", "Tenant Admin"])),
):
    """Free plan switch (downgrade or free-to-free). Paid upgrades go through Stripe checkout."""
    tenant_id = UUID(user["tenant_id"])

    plan_result = await db.execute(
        select(SubscriptionPlan).where(SubscriptionPlan.id == data.plan_id)
    )
    plan = plan_result.scalar_one_or_none()
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")

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
    return _build_my_plan_response(new_sub, plan)


@router.post("/assign")
async def assign_plan(
    data: AssignPlanRequest,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_roles(["Super Admin"])),
):
    """Superadmin manually assigns a plan to any tenant without payment."""
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


@router.post("/create-checkout-session")
async def create_checkout_session(
    data: CheckoutSessionRequest,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_roles(["Super Admin", "Tenant Admin"])),
):
    """Create a Stripe Checkout Session for upgrading to a paid plan."""
    if not settings.STRIPE_SECRET_KEY:
        raise HTTPException(status_code=503, detail="Payment service not configured")

    tenant_id = UUID(user["tenant_id"])

    # Get plan
    plan_result = await db.execute(
        select(SubscriptionPlan).where(SubscriptionPlan.id == data.plan_id)
    )
    plan = plan_result.scalar_one_or_none()
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")
    if float(plan.price) <= 0:
        raise HTTPException(status_code=400, detail="Use select-plan for free plans")

    # Get tenant
    tenant_result = await db.execute(
        select(Tenant).where(Tenant.id == tenant_id)
    )
    tenant = tenant_result.scalar_one_or_none()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    try:
        customer_id = await _get_or_create_stripe_customer(db, tenant, user)

        frontend_url = settings.FRONTEND_URL.rstrip("/")
        session = stripe.checkout.Session.create(
            customer=customer_id,
            payment_method_types=["card"],
            line_items=[{
                "price_data": {
                    "currency": "inr",
                    "product_data": {
                        "name": f"SkiTech {plan.name} Plan",
                        "description": f"Up to {plan.max_properties or '∞'} properties · {plan.max_users or '∞'} users",
                    },
                    "unit_amount": int(float(plan.price) * 100),  # paise
                    "recurring": {"interval": "month"},
                },
                "quantity": 1,
            }],
            mode="subscription",
            success_url=f"{frontend_url}/owner/settings?tab=billing&payment=success",
            cancel_url=f"{frontend_url}/owner/settings?tab=billing&payment=cancelled",
            metadata={
                "tenant_id": str(tenant_id),
                "plan_id": str(plan.id),
            },
            subscription_data={
                "metadata": {
                    "tenant_id": str(tenant_id),
                    "plan_id": str(plan.id),
                }
            },
        )
    except stripe.StripeError as e:
        logger.error(f"Stripe error creating checkout: {e}")
        raise HTTPException(status_code=502, detail=f"Payment service error: {str(e)}")

    return {"session_url": session.url, "session_id": session.id}


@router.post("/create-portal-session")
async def create_portal_session(
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_roles(["Super Admin", "Tenant Admin"])),
):
    """Create a Stripe Customer Portal session to manage/cancel subscription."""
    if not settings.STRIPE_SECRET_KEY:
        raise HTTPException(status_code=503, detail="Payment service not configured")

    tenant_id = UUID(user["tenant_id"])
    tenant_result = await db.execute(select(Tenant).where(Tenant.id == tenant_id))
    tenant = tenant_result.scalar_one_or_none()

    if not tenant or not tenant.stripe_customer_id:
        raise HTTPException(status_code=404, detail="No billing account found. Please upgrade first.")

    try:
        frontend_url = settings.FRONTEND_URL.rstrip("/")
        session = stripe.billing_portal.Session.create(
            customer=tenant.stripe_customer_id,
            return_url=f"{frontend_url}/owner/settings?tab=billing",
        )
    except stripe.StripeError as e:
        logger.error(f"Stripe portal error: {e}")
        raise HTTPException(status_code=502, detail=f"Payment service error: {str(e)}")

    return {"portal_url": session.url}


@router.post("/webhook")
async def stripe_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Stripe webhook endpoint — verifies signature and processes payment events."""
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature", "")

    if settings.STRIPE_WEBHOOK_SECRET:
        try:
            event = stripe.Webhook.construct_event(
                payload, sig_header, settings.STRIPE_WEBHOOK_SECRET
            )
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid webhook payload")
        except stripe.SignatureVerificationError:
            raise HTTPException(status_code=400, detail="Invalid webhook signature")
    else:
        import json
        try:
            event = json.loads(payload)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid payload")
        logger.warning("Stripe webhook received without signature verification — set STRIPE_WEBHOOK_SECRET")

    event_type = event.get("type", "")
    logger.info(f"Stripe webhook event: {event_type}")

    if event_type == "checkout.session.completed":
        session_obj = event["data"]["object"]
        metadata = session_obj.get("metadata", {})
        tenant_id_str = metadata.get("tenant_id")
        plan_id_str = metadata.get("plan_id")
        stripe_sub_id = session_obj.get("subscription")
        stripe_customer_id = session_obj.get("customer")

        if not tenant_id_str or not plan_id_str:
            logger.error("Webhook: missing tenant_id or plan_id in metadata")
            return {"status": "ignored"}

        try:
            tenant_id = UUID(tenant_id_str)
            plan_id = UUID(plan_id_str)
        except ValueError:
            logger.error(f"Webhook: invalid UUID in metadata: {tenant_id_str}, {plan_id_str}")
            return {"status": "ignored"}

        # Verify plan exists
        plan_result = await db.execute(
            select(SubscriptionPlan).where(SubscriptionPlan.id == plan_id)
        )
        plan = plan_result.scalar_one_or_none()
        if not plan:
            logger.error(f"Webhook: plan {plan_id} not found")
            return {"status": "ignored"}

        # Store stripe_customer_id on tenant
        if stripe_customer_id:
            tenant_result = await db.execute(select(Tenant).where(Tenant.id == tenant_id))
            tenant = tenant_result.scalar_one_or_none()
            if tenant and not tenant.stripe_customer_id:
                tenant.stripe_customer_id = stripe_customer_id

        # Expire existing active subscriptions
        existing = await db.execute(
            select(TenantSubscription).where(
                TenantSubscription.tenant_id == tenant_id,
                TenantSubscription.status == "active",
            )
        )
        for old_sub in existing.scalars().all():
            old_sub.status = "expired"

        # Create new subscription record
        new_sub = TenantSubscription(
            tenant_id=tenant_id,
            plan_id=plan_id,
            start_date=datetime.utcnow(),
            status="active",
            stripe_subscription_id=stripe_sub_id,
        )
        db.add(new_sub)
        await db.commit()
        logger.info(f"Tenant {tenant_id} upgraded to plan {plan.name} via Stripe")

    elif event_type in ("customer.subscription.deleted", "customer.subscription.updated"):
        sub_obj = event["data"]["object"]
        stripe_sub_id = sub_obj.get("id")
        stripe_status = sub_obj.get("status")

        if stripe_sub_id and stripe_status in ("canceled", "unpaid", "past_due"):
            existing = await db.execute(
                select(TenantSubscription).where(
                    TenantSubscription.stripe_subscription_id == stripe_sub_id
                )
            )
            for sub in existing.scalars().all():
                sub.status = "expired"
            await db.commit()
            logger.info(f"Subscription {stripe_sub_id} marked expired (Stripe status: {stripe_status})")

    return {"status": "ok"}
