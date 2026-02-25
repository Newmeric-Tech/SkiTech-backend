"""
Authentication Service

Handles user authentication logic without consuming HTTP requests/responses.
Provides methods for login, token validation, and credential verification.
Called by auth endpoints.
"""

from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    verify_password,
)
from app.models.user import User
from app.schemas.user import TokenResponse


class AuthService:
    """Service for authentication operations"""

    def __init__(self, db: AsyncSession):
        """
        Initialize auth service with database session

        Args:
            db: SQLAlchemy async session
        """
        self.db = db

    async def authenticate_user(self, username: str, password: str) -> Optional[User]:
        """
        Authenticate user by username and password

        Args:
            username: Username to authenticate
            password: Plain text password to verify

        Returns:
            User object if authentication successful, None otherwise
        """
        result = await self.db.execute(
            select(User).where(User.username == username).where(User.is_active == True)
        )
        user = result.scalar_one_or_none()

        if not user:
            return None

        if not verify_password(password, user.hashed_password):
            return None

        return user

    async def validate_token(self, token: str) -> Optional[dict]:
        """
        Validate JWT token

        Args:
            token: JWT token string

        Returns:
            Token payload if valid, None if invalid
        """
        payload = decode_token(token)
        if not payload or payload.get("type") != "access":
            return None
        return payload

    def generate_tokens(self, user_id: int, username: str) -> TokenResponse:
        """
        Generate access and refresh tokens

        Args:
            user_id: User ID to encode in token
            username: Username to encode in token

        Returns:
            TokenResponse with both tokens
        """
        access_token = create_access_token(
            data={"sub": username, "user_id": user_id, "type": "access"}
        )
        refresh_token = create_refresh_token(
            data={"sub": username, "user_id": user_id, "type": "refresh"}
        )

        return TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=1800,  # 30 minutes in seconds
        )
