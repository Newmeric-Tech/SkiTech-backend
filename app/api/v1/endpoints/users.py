"""
User Routes - app/api/v1/endpoints/users.py

GET    /users/me               → apna profile dekho
PUT    /users/me               → apna profile update karo
POST   /users/me/change-password → password change karo
GET    /users/                 → sab users list (Admin only)
GET    /users/{user_id}        → kisi bhi user ka detail (Admin only)
PUT    /users/{user_id}/role   → kisi ka role change karo (Admin only)
PUT    /users/{user_id}/deactivate → user deactivate karo (Admin only)
POST   /users/invite           → naya user invite karo (Admin only)
"""

import secrets
import string
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user, require_permission, require_roles
from app.core.database import get_db
from app.core.security import hash_password, verify_password
from app.models.models import Role, User
from app.schemas.schemas import (
    ChangePasswordRequest, UserInviteRequest, UserPropertyAssign,
    UserResponse, UserRoleUpdate, UserUpdate,
)
from datetime import datetime, timedelta

from app.utils.otp import generate_otp, send_invitation

router = APIRouter(prefix="/users", tags=["Users"])

# Maps frontend-friendly role labels → DB role names
ROLE_NAME_MAP: dict[str, str] = {
    # Frontend display names
    "Owner":       "Tenant Admin",
    "owner":       "Tenant Admin",
    "Manager":     "Manager",
    "manager":     "Manager",
    "Staff":       "Staff",
    "staff":       "Staff",
    "Superadmin":  "Super Admin",
    "superadmin":  "Super Admin",
    # DB names (pass-through)
    "Tenant Admin": "Tenant Admin",
    "Super Admin":  "Super Admin",
}


# ── Helpers ──────────────────────────────────────────────────────────────────

def _generate_temp_password(length: int = 12) -> str:
    """Generate a secure temporary password."""
    alphabet = string.ascii_letters + string.digits
    while True:
        pwd = "".join(secrets.choice(alphabet) for _ in range(length))
        # Ensure it meets password strength requirements
        if (
            any(c.isupper() for c in pwd)
            and any(c.islower() for c in pwd)
            and any(c.isdigit() for c in pwd)
        ):
            return pwd


async def _get_user_or_404(
    db: AsyncSession, user_id: UUID, tenant_id: UUID
) -> User:
    result = await db.execute(
        select(User).where(
            User.id == user_id,
            User.tenant_id == tenant_id,
            User.deleted_at == None,
        )
    )
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


# ── My Profile ───────────────────────────────────────────────────────────────

@router.get("/me", response_model=UserResponse)
async def get_me(
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Get currently logged in user's profile."""
    result = await db.execute(
        select(User).where(User.id == UUID(current_user["user_id"]))
    )
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


@router.put("/me", response_model=UserResponse)
async def update_me(
    data: UserUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Update currently logged in user's profile."""
    result = await db.execute(
        select(User).where(User.id == UUID(current_user["user_id"]))
    )
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(user, k, v)

    await db.commit()
    await db.refresh(user)
    return user


@router.post("/me/change-password")
async def change_password(
    data: ChangePasswordRequest,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Change password for currently logged in user."""
    result = await db.execute(
        select(User).where(User.id == UUID(current_user["user_id"]))
    )
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if not verify_password(data.current_password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect",
        )

    user.password_hash = hash_password(data.new_password)
    await db.commit()
    return {"message": "Password changed successfully"}


# ── Admin — User Management ───────────────────────────────────────────────────

@router.get("/", response_model=list[UserResponse])
async def list_users(
    property_id: UUID = None,
    role: str = None,
    skip: int = 0,
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_roles(["Super Admin", "Tenant Admin", "Manager"])),
):
    """List users in the tenant. Optionally filter by property or role."""
    q = (
        select(User)
        .join(Role, User.role_id == Role.id)
        .where(
            User.tenant_id == UUID(current_user["tenant_id"]),
            User.deleted_at == None,
        )
    )

    # Non-superadmin callers never see Super Admin accounts
    if current_user.get("role") != "Super Admin":
        q = q.where(Role.name != "Super Admin")

    if property_id:
        q = q.where(User.property_id == property_id)

    if role:
        q = q.where(Role.name == role)

    result = await db.execute(q.offset(skip).limit(limit))
    return result.scalars().all()


@router.get("/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_roles(["Super Admin", "Tenant Admin", "Manager"])),
):
    """Get a specific user's details."""
    return await _get_user_or_404(db, user_id, UUID(current_user["tenant_id"]))


@router.put("/{user_id}/role", response_model=UserResponse)
async def update_user_role(
    user_id: UUID,
    data: UserRoleUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_roles(["Super Admin", "Tenant Admin"])),
):
    """Change a user's role. Only Super Admin and Tenant Admin can do this."""
    user = await _get_user_or_404(db, user_id, UUID(current_user["tenant_id"]))

    # Verify the role exists
    role_result = await db.execute(
        select(Role).where(Role.id == data.role_id)
    )
    role = role_result.scalar_one_or_none()
    if not role:
        raise HTTPException(status_code=404, detail="Role not found")

    user.role_id = data.role_id
    await db.commit()
    await db.refresh(user)
    return user


@router.put("/{user_id}/property", response_model=UserResponse)
async def assign_user_property(
    user_id: UUID,
    data: UserPropertyAssign,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_roles(["Super Admin", "Tenant Admin"])),
):
    """Assign or reassign a property to a user (Manager/Staff)."""
    from app.models.models import Property
    user = await _get_user_or_404(db, user_id, UUID(current_user["tenant_id"]))

    if data.property_id:
        prop_result = await db.execute(
            select(Property).where(
                Property.id == data.property_id,
                Property.tenant_id == UUID(current_user["tenant_id"]),
            )
        )
        if not prop_result.scalar_one_or_none():
            raise HTTPException(status_code=404, detail="Property not found")
        user.property_id = data.property_id
    else:
        user.property_id = None

    await db.commit()
    await db.refresh(user)
    return user


@router.put("/{user_id}/deactivate", response_model=UserResponse)
async def deactivate_user(
    user_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_roles(["Super Admin", "Tenant Admin"])),
):
    """Deactivate a user. They won't be able to login."""
    # Prevent self-deactivation
    if str(user_id) == current_user["user_id"]:
        raise HTTPException(
            status_code=400,
            detail="You cannot deactivate your own account",
        )

    user = await _get_user_or_404(db, user_id, UUID(current_user["tenant_id"]))
    user.is_active = False
    await db.commit()
    await db.refresh(user)
    return user


@router.put("/{user_id}/activate", response_model=UserResponse)
async def activate_user(
    user_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_roles(["Super Admin", "Tenant Admin"])),
):
    """Re-activate a previously deactivated user."""
    result = await db.execute(
        select(User).where(
            User.id == user_id,
            User.tenant_id == UUID(current_user["tenant_id"]),
        )
    )
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    user.is_active = True
    await db.commit()
    await db.refresh(user)
    return user


@router.post("/invite", response_model=UserResponse, status_code=201)
async def invite_user(
    data: UserInviteRequest,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_roles(["Super Admin", "Tenant Admin"])),
):
    """
    Invite a new user to the tenant.
    Creates account with a temp password and sends OTP for verification.
    """
    # Check duplicate email
    existing = await db.execute(
        select(User).where(User.email == data.email)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Email already registered")

    # Resolve role — map frontend labels ("Owner") → DB names ("Tenant Admin")
    db_role_name = ROLE_NAME_MAP.get(data.role, data.role)
    role_result = await db.execute(
        select(Role).where(Role.name == db_role_name)
    )
    role = role_result.scalar_one_or_none()
    if not role:
        raise HTTPException(
            status_code=400,
            detail=f"Role '{data.role}' not found. Valid roles: Owner, Manager, Staff",
        )

    # Generate temp password
    temp_password = _generate_temp_password()

    user = User(
        email=data.email,
        password_hash=hash_password(temp_password),
        first_name=data.first_name,
        last_name=data.last_name,
        tenant_id=UUID(current_user["tenant_id"]),
        role_id=role.id,
        property_id=data.property_id,
        is_active=True,
        is_verified=False,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    # Generate OTP, persist to DB, then send full invite email
    otp = generate_otp()
    user.otp_code = otp
    user.otp_expires_at = datetime.utcnow() + timedelta(seconds=300)
    await db.commit()
    send_invitation(data.email, temp_password, otp)

    return user