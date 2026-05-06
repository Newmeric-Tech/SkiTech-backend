"""
User Model - SQLAlchemy ORM Definition

Defines User entity with fields for authentication, roles, and profile.
Includes relationships to properties and roles.
"""

from typing import Optional

from sqlalchemy import Boolean, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, IdMixin, SoftDeleteMixin, TimestampMixin


class User(Base, IdMixin, TimestampMixin, SoftDeleteMixin):
    """
    User Model

    Represents a user in the system.
    Supports multiple roles and property assignments.
    """

    __tablename__ = "users"

    # Authentication
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    username: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)

    # Profile
    first_name: Mapped[str] = mapped_column(String(255), nullable=False)
    last_name: Mapped[str] = mapped_column(String(255), nullable=False)
    phone: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)

    # Status
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Role
    role: Mapped[str] = mapped_column(
        String(50),
        default="staff",
        nullable=False,
        index=True,
    )

    # Relationships
    # property_assignments: Mapped[list["PropertyUser"]] = relationship(
    #     "PropertyUser", back_populates="user", cascade="all, delete-orphan"
    # )

    def __repr__(self) -> str:
        return f"<User (id={self.id}, email={self.email}, role={self.role})>"
