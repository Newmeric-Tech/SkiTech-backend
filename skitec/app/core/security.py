"""
Security & Authentication Module

Handles JWT token generation, validation, and password hashing.
Provides RBAC-ready authorization utilities.
Uses bcrypt for password hashing and python-jose for JWT operations.
"""

from datetime import datetime, timedelta
from typing import Optional

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import settings

# Password hashing context
pwd_context = CryptContext(
    schemes=["bcrypt"],
    deprecated="auto",
)


def hash_password(password: str) -> str:
    """
    Hash a plaintext password

    Args:
        password: Plain text password to hash

    Returns:
        Hashed password string
    """
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Verify a plaintext password against its hash

    Args:
        plain_password: Plain text password to verify
        hashed_password: Hashed password to compare against

    Returns:
        True if password matches, False otherwise
    """
    return pwd_context.verify(plain_password, hashed_password)


def create_access_token(
    data: dict,
    expires_delta: Optional[timedelta] = None,
) -> str:
    """
    Create JWT access token

    Args:
        data: Dictionary to encode in token (typically user claims)
        expires_delta: Custom expiration time, defaults to config value

    Returns:
        Encoded JWT token string
    """
    to_encode = data.copy()

    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(
            minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES
        )

    to_encode.update({"exp": expire, "type": "access"})

    encoded_jwt = jwt.encode(
        to_encode,
        settings.SECRET_KEY,
        algorithm=settings.ALGORITHM,
    )

    return encoded_jwt


def create_refresh_token(data: dict) -> str:
    """
    Create JWT refresh token

    Args:
        data: Dictionary to encode in token

    Returns:
        Encoded JWT refresh token string
    """
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)

    to_encode.update({"exp": expire, "type": "refresh"})

    encoded_jwt = jwt.encode(
        to_encode,
        settings.SECRET_KEY,
        algorithm=settings.ALGORITHM,
    )

    return encoded_jwt


def decode_token(token: str) -> Optional[dict]:
    """
    Decode and validate JWT token

    Args:
        token: JWT token string to decode

    Returns:
        Token payload dictionary if valid, None if invalid
    """
    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM],
        )
        return payload
    except JWTError:
        return None


# RBAC Role Definitions
class RolePermissions:
    """
    Role-Based Access Control role definitions

    Extend this class to add new roles and their permissions.
    Permissions can be enforced in route handlers via dependencies.
    """

    ROLES = {
        "super_admin": {
            "permissions": [
                "manage_users",
                "manage_properties",
                "manage_roles",
                "view_all_reports",
                "approve_workflows",
                "audit_logs",
            ],
        },
        "property_manager": {
            "permissions": [
                "manage_property",
                "manage_workforce",
                "view_property_reports",
                "submit_workflows",
            ],
        },
        "staff": {
            "permissions": [
                "view_schedule",
                "submit_time_entries",
                "view_own_data",
            ],
        },
        "auditor": {
            "permissions": [
                "view_all_reports",
                "audit_logs",
                "export_data",
            ],
        },
    }

    @classmethod
    def get_role_permissions(cls, role: str) -> set[str]:
        """Get permissions for a specific role"""
        return set(cls.ROLES.get(role, {}).get("permissions", []))

    @classmethod
    def has_permission(cls, role: str, permission: str) -> bool:
        """Check if role has specific permission"""
        permissions = cls.get_role_permissions(role)
        return permission in permissions
