"""
FastAPI Dependencies - app/api/dependencies.py

JWT authentication + permission/role checking.
"""

from uuid import UUID

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import decode_token, has_permission

security = HTTPBearer()


def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> dict:
    """
    Decode JWT and return payload.
    Also sets user info on request.state for middleware.
    """
    payload = decode_token(credentials.credentials)

    if not payload or payload.get("type") != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )

    # Expose on request.state so AuditMiddleware can read it
    request.state.user_id = payload.get("user_id")
    request.state.tenant_id = payload.get("tenant_id")
    request.state.user_email = payload.get("email", "")
    request.state.role = payload.get("role")

    return payload


def require_permission(permission: str):
    """Route dependency: enforce a specific permission."""
    def checker(user: dict = Depends(get_current_user)) -> dict:
        role = user.get("role", "")
        if not has_permission(role, permission):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permission denied: '{permission}' required",
            )
        return user
    return checker


def require_roles(roles: list):
    """Route dependency: allow only specific roles."""
    def checker(user: dict = Depends(get_current_user)) -> dict:
        if user.get("role") not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access forbidden: insufficient role",
            )
        return user
    return checker


async def get_current_user_obj(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db),
):
    """
    Decode JWT, fetch the actual User ORM object from DB and return it.

    Use this dependency (instead of get_current_user) in endpoints that need
    User attributes such as .tenant_id, .property_id, .role_obj, etc.

    Existing endpoints that access user as a dict (user.get("role") etc.)
    continue to use get_current_user unchanged.
    """
    payload = decode_token(credentials.credentials)

    if not payload or payload.get("type") != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )

    user_id = payload.get("user_id") or payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload",
        )

    from app.models.models import User
    from sqlalchemy.orm import selectinload

    result = await db.execute(
        select(User)
        .options(selectinload(User.role_obj))   # NOTE: relationship is role_obj, not role
        .where(User.id == UUID(user_id))
    )
    user = result.scalar_one_or_none()

    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive",
        )

    # Expose on request.state for AuditMiddleware
    request.state.user_id    = str(user.id)
    request.state.tenant_id  = str(user.tenant_id)
    request.state.user_email = user.email
    request.state.role       = user.role_obj.name if user.role_obj else ""

    return user


def require_feature(feature_name: str):
    """Route dependency: enforce that tenant's active plan includes a feature. Super Admin bypasses."""
    async def checker(
        user: dict = Depends(get_current_user),
        db: AsyncSession = Depends(get_db),
    ) -> dict:
        # Super Admin has unrestricted access
        if user.get("role") == "Super Admin":
            return user

        from app.models.models import SubscriptionPlan, TenantSubscription
        tenant_id = UUID(user["tenant_id"])

        sub_result = await db.execute(
            select(TenantSubscription)
            .where(
                TenantSubscription.tenant_id == tenant_id,
                TenantSubscription.status == "active",
            )
            .order_by(TenantSubscription.created_at.desc())
            .limit(1)
        )
        sub = sub_result.scalar_one_or_none()
        if not sub:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No active subscription. Please contact your administrator.",
            )

        plan_result = await db.execute(
            select(SubscriptionPlan).where(SubscriptionPlan.id == sub.plan_id)
        )
        plan = plan_result.scalar_one_or_none()
        features = (plan.features or {}) if plan else {}

        if not features.get(feature_name, False):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Feature '{feature_name}' is not included in your subscription plan. Please upgrade.",
            )
        return user
    return checker


