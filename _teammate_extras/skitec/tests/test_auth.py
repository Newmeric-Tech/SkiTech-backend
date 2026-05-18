"""
Authentication Tests

Tests for authentication endpoints and services.
"""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.models.user import User
from app.services.auth_service import AuthService


@pytest.mark.asyncio
async def test_authenticate_user_success(db_session: AsyncSession):
    """Test successful user authentication"""
    # Create test user
    user = User(
        email="test@example.com",
        username="testuser",
        hashed_password=hash_password("TestPassword123!"),
        first_name="Test",
        last_name="User",
        is_active=True,
    )
    db_session.add(user)
    await db_session.commit()

    # Test authentication
    auth_service = AuthService(db_session)
    authenticated_user = await auth_service.authenticate_user(
        username="testuser",
        password="TestPassword123!",
    )

    assert authenticated_user is not None
    assert authenticated_user.username == "testuser"


@pytest.mark.asyncio
async def test_authenticate_user_invalid_password(db_session: AsyncSession):
    """Test authentication with invalid password"""
    # Create test user
    user = User(
        email="test@example.com",
        username="testuser",
        hashed_password=hash_password("TestPassword123!"),
        first_name="Test",
        last_name="User",
        is_active=True,
    )
    db_session.add(user)
    await db_session.commit()

    # Test authentication with wrong password
    auth_service = AuthService(db_session)
    authenticated_user = await auth_service.authenticate_user(
        username="testuser",
        password="WrongPassword",
    )

    assert authenticated_user is None


@pytest.mark.asyncio
async def test_authenticate_user_not_found(db_session: AsyncSession):
    """Test authentication with non-existent user"""
    auth_service = AuthService(db_session)
    authenticated_user = await auth_service.authenticate_user(
        username="nonexistent",
        password="TestPassword123!",
    )

    assert authenticated_user is None


def test_generate_tokens(db_session):
    """Test token generation"""
    auth_service = AuthService(db_session)
    tokens = auth_service.generate_tokens(user_id=1, username="testuser")

    assert tokens.access_token is not None
    assert tokens.refresh_token is not None
    assert tokens.token_type == "bearer"


def test_validate_token(db_session):
    """Test token validation"""
    auth_service = AuthService(db_session)

    # Generate tokens
    tokens = auth_service.generate_tokens(user_id=1, username="testuser")

    # Validate token
    payload = auth_service.validate_token(tokens.access_token)

    assert payload is not None
    assert payload.get("user_id") == 1
    assert payload.get("sub") == "testuser"
