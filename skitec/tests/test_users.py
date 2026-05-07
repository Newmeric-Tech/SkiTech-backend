"""
User Endpoints Tests

Tests for user CRUD endpoints.
"""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.models.user import User


@pytest.mark.asyncio
async def test_create_user(db_session: AsyncSession, test_client):
    """Test user creation endpoint"""
    response = test_client.post(
        "/api/v1/users",
        json={
            "email": "newuser@example.com",
            "username": "newuser",
            "password": "SecurePassword123!",
            "first_name": "New",
            "last_name": "User",
        },
    )

    assert response.status_code == 201
    data = response.json()
    assert data["email"] == "newuser@example.com"
    assert data["username"] == "newuser"


@pytest.mark.asyncio
async def test_create_user_duplicate_username(db_session: AsyncSession, test_client):
    """Test user creation with duplicate username"""
    # Create first user
    user = User(
        email="test@example.com",
        username="testuser",
        hashed_password=hash_password("TestPassword123!"),
        first_name="Test",
        last_name="User",
    )
    db_session.add(user)
    await db_session.commit()

    # Try to create user with same username
    response = test_client.post(
        "/api/v1/users",
        json={
            "email": "other@example.com",
            "username": "testuser",
            "password": "SecurePassword123!",
            "first_name": "Other",
            "last_name": "User",
        },
    )

    assert response.status_code == 409  # Conflict


@pytest.mark.asyncio
async def test_get_user(db_session: AsyncSession, test_client):
    """Test get user endpoint"""
    # Create test user
    user = User(
        email="test@example.com",
        username="testuser",
        hashed_password=hash_password("TestPassword123!"),
        first_name="Test",
        last_name="User",
    )
    db_session.add(user)
    await db_session.commit()

    # Get user
    response = test_client.get(f"/api/v1/users/{user.id}")

    assert response.status_code == 200
    data = response.json()
    assert data["email"] == "test@example.com"
    assert data["username"] == "testuser"
