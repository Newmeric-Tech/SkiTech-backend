"""
Security - app/core/security.py

JWT token creation/validation and password hashing.
"""

from datetime import datetime, timedelta
from typing import Optional

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + (
        expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    to_encode.update({"exp": expire, "type": "access"})
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def create_refresh_token(data: dict) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    to_encode.update({"exp": expire, "type": "refresh"})
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_token(token: str) -> Optional[dict]:
    try:
        return jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
    except JWTError:
        return None


# -----------------------------------------------------------------
# RBAC permission map (role → list of permission strings)
# -----------------------------------------------------------------
ROLE_PERMISSIONS: dict[str, list[str]] = {
    "Super Admin": [
        "manage_all",
        "manage_property", "manage_staff",
        "view_sop", "create_sop", "update_sop", "delete_sop",
        "view_inventory", "manage_inventory",
        "view_vendor", "create_vendor", "update_vendor", "delete_vendor",
        "view_owner", "manage_owner",
        "view_department", "create_department", "update_department", "delete_department",
    ],
    "Tenant Admin": [
        "manage_property", "manage_staff",
        "view_sop", "create_sop", "update_sop", "delete_sop",
        "view_inventory", "manage_inventory",
        "view_vendor", "create_vendor", "update_vendor", "delete_vendor",
        "view_owner", "manage_owner",
        "view_department", "create_department", "update_department", "delete_department",
    ],
    "Manager": [
        "manage_staff",
        "view_sop", "create_sop", "update_sop",
        "view_inventory",
        "view_vendor",
        "view_department", "create_department", "update_department",
    ],
    "Staff": [
        "view_sop",
        "view_inventory",
        "view_department",
    ],
}


def has_permission(role: str, permission: str) -> bool:
    perms = ROLE_PERMISSIONS.get(role, [])
    return "manage_all" in perms or permission in perms
