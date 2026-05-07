"""
Example Users Router

User management endpoints: list, get, create, update, delete.
Demonstrates RBAC and standard CRUD patterns.
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from ....core.database import get_db_session
from ....core.security import RolePermissions
from ....schemas.common import PaginatedResponse
from ....schemas.user import UserCreate, UserResponse, UserUpdate
from ....services.user_service import UserService
from ....utils.exceptions import ConflictError, NotFoundError, ValidationError

router = APIRouter(
    prefix="/users",
    tags=["Users"],
    responses={
        404: {"description": "User not found"},
        401: {"description": "Unauthorized"},
        403: {"description": "Insufficient permissions"},
    },
)


# Dependency: Current user (token validation)
# In a real implementation, extract/validate JWT token
async def get_current_user():
    """Get current authenticated user from JWT token"""
    # TODO: Implement JWT token validation
    pass


@router.get("", response_model=PaginatedResponse[UserResponse])
async def list_users(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db_session),
) -> PaginatedResponse[UserResponse]:
    """
    List users with pagination

    Args:
        skip: Number of records to skip
        limit: Number of records to return
        db: Database session

    Returns:
        PaginatedResponse with user list
    """
    user_service = UserService(db)
    users, total = await user_service.list_users(skip=skip, limit=limit)

    return PaginatedResponse(
        total=total,
        skip=skip,
        limit=limit,
        items=[UserResponse.from_orm(u) for u in users],
    )


@router.get("/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: int,
    db: AsyncSession = Depends(get_db_session),
) -> UserResponse:
    """
    Get user by ID

    Args:
        user_id: User ID to retrieve
        db: Database session

    Returns:
        UserResponse with user details

    Raises:
        HTTPException: 404 if user not found
    """
    user_service = UserService(db)
    user = await user_service.get_user_by_id(user_id)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    return UserResponse.from_orm(user)


@router.post("", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def create_user(
    user_data: UserCreate,
    db: AsyncSession = Depends(get_db_session),
) -> UserResponse:
    """
    Create new user

    Args:
        user_data: UserCreate schema with user details
        db: Database session

    Returns:
        UserResponse with created user details

    Raises:
        HTTPException: 409 if user already exists
    """
    user_service = UserService(db)

    # Check if user already exists
    existing_user = await user_service.get_user_by_username(user_data.username)
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Username already exists",
        )

    existing_email = await user_service.get_user_by_email(user_data.email)
    if existing_email:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered",
        )

    # Create user
    user = await user_service.create_user(user_data)
    return UserResponse.from_orm(user)


@router.put("/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: int,
    update_data: UserUpdate,
    db: AsyncSession = Depends(get_db_session),
) -> UserResponse:
    """
    Update user

    Args:
        user_id: User ID to update
        update_data: UserUpdate schema with new values
        db: Database session

    Returns:
        UserResponse with updated user details

    Raises:
        HTTPException: 404 if user not found
    """
    user_service = UserService(db)
    user = await user_service.get_user_by_id(user_id)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    user = await user_service.update_user(user, update_data)
    return UserResponse.from_orm(user)


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(
    user_id: int,
    db: AsyncSession = Depends(get_db_session),
) -> None:
    """
    Delete user (soft delete)

    Args:
        user_id: User ID to delete
        db: Database session

    Raises:
        HTTPException: 404 if user not found
    """
    user_service = UserService(db)
    user = await user_service.get_user_by_id(user_id)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    await user_service.delete_user(user)
