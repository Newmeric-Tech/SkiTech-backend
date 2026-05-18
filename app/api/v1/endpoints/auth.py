"""
Auth Routes - app/api/v1/endpoints/auth.py

POST /auth/register
POST /auth/verify-otp
POST /auth/login
POST /auth/refresh
POST /auth/forgot-password
POST /auth/reset-password
POST /auth/logout
"""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import (
    create_access_token, create_refresh_token, decode_token,
    hash_password, verify_password,
)
from app.models.models import DemoRequest, User, Role
from app.schemas.schemas import (
    LoginRequest, OTPVerifyRequest, PasswordResetConfirm,
    PasswordResetRequest, RefreshTokenRequest, RegisterRequest, TokenResponse, SuperAdminLoginRequest
)
from app.utils.otp import send_otp, verify_otp

router = APIRouter(prefix="/auth", tags=["Authentication"])

ROLE_NAME_MAP = {
    "owner": "Tenant Admin",
    "manager": "Manager",
    "staff": "Staff",
    "superadmin": "Super Admin",
    # Also support direct DB names in case they're sent directly
    "Tenant Admin": "Tenant Admin",
    "Manager": "Manager",
    "Staff": "Staff",
    "Super Admin": "Super Admin",
}

@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register(data: RegisterRequest, db: AsyncSession = Depends(get_db)):
    """Register a new user and send OTP email for verification."""
    try:
        # Check duplicate email (both active and soft-deleted users)
        result = await db.execute(select(User).where(User.email == data.email))
        existing_user = result.scalar_one_or_none()
        
        if existing_user:
            if existing_user.deleted_at is None:
                raise HTTPException(status_code=400, detail="Email already registered")
            else:
                raise HTTPException(status_code=400, detail="This email was previously registered. Please contact support.")

        # Resolve role by name
        role_result = await db.execute(select(Role).where(Role.name == data.role))
        role = role_result.scalar_one_or_none()
        if not role:
            raise HTTPException(status_code=400, detail=f"Role '{data.role}' not found")

        user = User(
            email=data.email,
            password_hash=hash_password(data.password),
            tenant_id=data.tenant_id,
            role_id=role.id,
            is_active=True,
            is_verified=False,
        )
        db.add(user)
        
        try:
            await db.commit()
        except IntegrityError as e:
            await db.rollback()
            error_msg = str(e).lower()
            if "duplicate key" in error_msg or "unique constraint" in error_msg:
                raise HTTPException(status_code=400, detail="Email already registered")
            raise HTTPException(status_code=400, detail=f"Database error: {error_msg[:100]}")

        # Send OTP and verify it was sent
        otp_sent = send_otp(data.email, purpose="verification")
        
        if not otp_sent:
            # OTP failed to send - still return user created but inform them
            return {
                "message": "Registration successful, but OTP email failed to send. Please check your email configuration or try the verify-otp endpoint manually if you have the OTP.",
                "email": data.email,
                "warning": "OTP email delivery failed"
            }

        return {
            "message": "Registration successful. Check your email for the OTP.",
            "email": data.email,
        }
    
    except HTTPException:
        raise  # Re-raise HTTPExceptions as-is
    except Exception as e:
        import logging
        logger = logging.getLogger("skitech")
        logger.error(f"[REGISTER ERROR] {type(e).__name__}: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500, 
            detail=f"Registration failed: {type(e).__name__}: {str(e)[:100]}"
        )


@router.post("/verify-otp")
async def verify_otp_route(data: OTPVerifyRequest, db: AsyncSession = Depends(get_db)):
    """Verify email OTP and activate account."""
    if not verify_otp(data.email, data.otp):
        raise HTTPException(status_code=400, detail="Invalid or expired OTP")

    result = await db.execute(select(User).where(User.email == data.email))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Prevent verification of soft-deleted accounts
    if user.deleted_at is not None:
        raise HTTPException(status_code=404, detail="This account has been deleted")

    user.is_verified = True
    await db.commit()

    return {"message": "Email verified. You can now log in."}


@router.post("/login", response_model=TokenResponse)
async def login(data: LoginRequest, request: Request, db: AsyncSession = Depends(get_db)):
    """
    Authenticate and return JWT tokens.
    If expected_role is provided, validates that the user's actual role matches.
    """
    result = await db.execute(
        select(User).where(
            User.email == data.email,
            User.is_active == True,
            User.deleted_at == None,
        )
    )
    user = result.scalar_one_or_none()
 
    if not user or not verify_password(data.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")
 
    if not user.is_verified:
        raise HTTPException(
            status_code=403,
            detail="Email not verified. Check your inbox for the OTP.",
        )
 
    # Load actual role from DB
    role_result = await db.execute(select(Role).where(Role.id == user.role_id))
    role = role_result.scalar_one_or_none()
    actual_role = role.name if role else "Staff"
 
    # ── Role validation ───────────────────────────────────────────────────────
    if data.expected_role:
        expected_db_role = ROLE_NAME_MAP.get(data.expected_role)
 
        if not expected_db_role:
            raise HTTPException(
                status_code=400,
                detail=f"Unknown role selected: '{data.expected_role}'",
            )
 
        if actual_role != expected_db_role:
            raise HTTPException(
                status_code=403,
                detail=f"Access denied. Your account is not registered as '{expected_db_role}'. "
                       f"Please select the correct role.",
            )
    # ─────────────────────────────────────────────────────────────────────────
 
    # Update last login
    user.last_login = datetime.utcnow()
    await db.commit()
 
    payload = {
        "sub": str(user.id),
        "user_id": str(user.id),
        "tenant_id": str(user.tenant_id) if user.tenant_id else "",
        "property_id": str(user.property_id) if user.property_id else "",
        "email": user.email,
        "role": actual_role,
        "first_name": user.first_name or "",
        "last_name": user.last_name or "",
    }

    return TokenResponse(
        access_token=create_access_token(payload),
        refresh_token=create_refresh_token(payload),
    )


@router.post("/superadmin-login", response_model=TokenResponse)
async def superadmin_login(
    data: SuperAdminLoginRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """
    Dedicated Super Admin login endpoint.
    Only accessible to users with Super Admin role.
    """
    # Find user by email (active, not deleted)
    result = await db.execute(
        select(User).where(
            User.email == data.email,
            User.is_active == True,
            User.deleted_at == None,
        )
    )
    user = result.scalar_one_or_none()

    if not user or not verify_password(data.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    if not user.is_verified:
        raise HTTPException(
            status_code=403,
            detail="Email not verified. Check your inbox for the OTP.",
        )

    # Load role and verify it's Super Admin
    role_result = await db.execute(select(Role).where(Role.id == user.role_id))
    role = role_result.scalar_one_or_none()
    role_name = role.name if role else ""

    # CRITICAL: Reject anyone who is not Super Admin
    if role_name != "Super Admin":
        raise HTTPException(
            status_code=403,
            detail="Access denied. This portal is restricted to Super Admins only.",
        )

    # Update last login
    user.last_login = datetime.utcnow()
    await db.commit()

    payload = {
        "sub": str(user.id),
        "user_id": str(user.id),
        "tenant_id": str(user.tenant_id) if user.tenant_id else "",
        "property_id": str(user.property_id) if user.property_id else "",
        "email": user.email,
        "role": role_name,
        "first_name": user.first_name or "",
        "last_name": user.last_name or "",
    }

    return TokenResponse(
        access_token=create_access_token(payload),
        refresh_token=create_refresh_token(payload),
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(data: RefreshTokenRequest):
    """Issue a new access token using a valid refresh token."""
    payload = decode_token(data.refresh_token)
    if not payload or payload.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token")

    new_payload = {k: v for k, v in payload.items() if k not in ("exp", "type")}
    return TokenResponse(
        access_token=create_access_token(new_payload),
        refresh_token=create_refresh_token(new_payload),
    )


@router.post("/forgot-password")
async def forgot_password(data: PasswordResetRequest, db: AsyncSession = Depends(get_db)):
    """Send OTP for password reset."""
    result = await db.execute(
        select(User).where(
            User.email == data.email,
            User.deleted_at == None,
        )
    )
    user = result.scalar_one_or_none()
    # Always return success to avoid email enumeration
    if user:
        send_otp(data.email, purpose="password_reset")
    return {"message": "If that email is registered, an OTP has been sent."}


@router.post("/reset-password")
async def reset_password(data: PasswordResetConfirm, db: AsyncSession = Depends(get_db)):
    """Reset password using OTP."""
    if not verify_otp(data.email, data.otp):
        raise HTTPException(status_code=400, detail="Invalid or expired OTP")

    result = await db.execute(
        select(User).where(
            User.email == data.email,
            User.deleted_at == None,
        )
    )
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    user.password_hash = hash_password(data.new_password)
    await db.commit()

    return {"message": "Password reset successfully."}


@router.post("/logout")
async def logout():
    """Logout (JWT is stateless — client discards the token)."""
    return {"message": "Logged out successfully."}


@router.post("/demo-request", status_code=201)
async def submit_demo_request(
    data: dict,
    db: AsyncSession = Depends(get_db),
):
    """Public endpoint — no auth required. Saves a demo request from the landing page."""
    row = DemoRequest(
        name=data.get("name", ""),
        email=data.get("email", ""),
        company=data.get("company"),
        phone=data.get("phone"),
        portfolio_size=data.get("size"),
        role=data.get("role"),
        message=data.get("message"),
        status="pending",
    )
    db.add(row)
    await db.commit()
    return {"success": True, "message": "Demo request received"}