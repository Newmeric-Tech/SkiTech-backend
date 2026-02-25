"""
User Service

Handles user management business logic.
CRUD operations, role management, and user-related queries.
"""

from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.core.security import hash_password
from app.models.user import User
from app.schemas.user import UserCreate, UserUpdate


class UserService:
    """Service for user operations"""

    def __init__(self, db: AsyncSession):
        """
        Initialize user service with database session

        Args:
            db: SQLAlchemy async session
        """
        self.db = db

    async def get_user_by_id(self, user_id: int) -> Optional[User]:
        """
        Get user by ID

        Args:
            user_id: User ID to retrieve

        Returns:
            User object if found, None otherwise
        """
        result = await self.db.execute(select(User).where(User.id == user_id))
        return result.scalar_one_or_none()

    async def get_user_by_username(self, username: str) -> Optional[User]:
        """
        Get user by username

        Args:
            username: Username to search for

        Returns:
            User object if found, None otherwise
        """
        result = await self.db.execute(select(User).where(User.username == username))
        return result.scalar_one_or_none()

    async def get_user_by_email(self, email: str) -> Optional[User]:
        """
        Get user by email

        Args:
            email: Email to search for

        Returns:
            User object if found, None otherwise
        """
        result = await self.db.execute(select(User).where(User.email == email))
        return result.scalar_one_or_none()

    async def create_user(self, user_data: UserCreate) -> User:
        """
        Create new user

        Args:
            user_data: UserCreate schema with user details

        Returns:
            Created User object
        """
        user = User(
            email=user_data.email,
            username=user_data.username,
            hashed_password=hash_password(user_data.password),
            first_name=user_data.first_name,
            last_name=user_data.last_name,
            phone=user_data.phone,
            role="staff",  # Default role
        )
        self.db.add(user)
        await self.db.commit()
        await self.db.refresh(user)
        return user

    async def update_user(self, user: User, update_data: UserUpdate) -> User:
        """
        Update existing user

        Args:
            user: User object to update
            update_data: UserUpdate schema with new values

        Returns:
            Updated User object
        """
        update_dict = update_data.dict(exclude_unset=True)
        for field, value in update_dict.items():
            setattr(user, field, value)

        await self.db.commit()
        await self.db.refresh(user)
        return user

    async def delete_user(self, user: User) -> None:
        """
        Soft delete user (deactivate)

        Args:
            user: User object to delete
        """
        user.is_active = False
        await self.db.commit()

    async def list_users(self, skip: int = 0, limit: int = 20) -> tuple[list[User], int]:
        """
        List all active users with pagination

        Args:
            skip: Number of records to skip
            limit: Number of records to return

        Returns:
            Tuple of (users list, total count)
        """
        # Get total count
        count_result = await self.db.execute(
            select(User).where(User.is_active == True).count()
        )
        total = count_result.scalar()

        # Get paginated results
        result = await self.db.execute(
            select(User)
            .where(User.is_active == True)
            .offset(skip)
            .limit(limit)
        )
        users = result.scalars().all()
        return users, total
