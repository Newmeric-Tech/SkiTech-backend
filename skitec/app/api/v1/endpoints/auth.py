"""
Example Auth Router

Authentication endpoints: login, token refresh, logout.
Demonstrates API structure and convention.

Keep auth logic in services, not in route handlers.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from app.schemas.user import LoginRequest, RefreshTokenRequest, TokenResponse
from app.services.auth_service import AuthService
from app.utils.exceptions import InvalidCredentialsError

router = APIRouter(
    prefix="/auth",
    tags=["Authentication"],
    responses={401: {"description": "Unauthorized"}},
)


@router.post("/login", response_model=TokenResponse)
async def login(
    credentials: LoginRequest,
    db: AsyncSession = Depends(get_db_session),
) -> TokenResponse:
    """
    User login endpoint

    Returns access and refresh tokens on successful authentication.

    Args:
        credentials: LoginRequest with username and password
        db: Database session

    Returns:
        TokenResponse with access_token and refresh_token

    Raises:
        HTTPException: 401 if credentials invalid
    """
    auth_service = AuthService(db)

    # Authenticate user
    user = await auth_service.authenticate_user(
        username=credentials.username,
        password=credentials.password,
    )

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )

    # Generate tokens
    tokens = auth_service.generate_tokens(user_id=user.id, username=user.username)

    return tokens


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(
    request: RefreshTokenRequest,
    db: AsyncSession = Depends(get_db_session),
) -> TokenResponse:
    """
    Refresh access token using refresh token

    Args:
        request: RefreshTokenRequest with refresh_token
        db: Database session

    Returns:
        TokenResponse with new access_token

    Raises:
        HTTPException: 401 if refresh token invalid
    """
    auth_service = AuthService(db)

    # Validate refresh token
    payload = auth_service.validate_token(request.refresh_token)
    if not payload or payload.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
        )

    # Generate new tokens
    tokens = auth_service.generate_tokens(
        user_id=payload["user_id"],
        username=payload["sub"],
    )

    return tokens


@router.post("/logout")
async def logout() -> dict:
    """
    Logout endpoint

    JWT tokens are stateless, so logout is typically a frontend operation.
    This endpoint can be used to:
    - Invalidate token on a blocklist (optional)
    - Log the logout action to audit trail

    Returns:
        Success message
    """
    return {"message": "Successfully logged out"}
