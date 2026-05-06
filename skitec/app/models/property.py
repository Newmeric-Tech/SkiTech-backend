"""
Property Model - SQLAlchemy ORM Definition

Represents a hotel property in the system.
Includes contact details, operational status, and configuration.
"""

from typing import Optional

from sqlalchemy import Boolean, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, IdMixin, SoftDeleteMixin, TimestampMixin


class Property(Base, IdMixin, TimestampMixin, SoftDeleteMixin):
    """
    Property Model

    Represents a hotel property managed by the system.
    Stores property details, contact information, and operational status.
    """

    __tablename__ = "properties"

    # Basic Information
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    code: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Location
    address: Mapped[str] = mapped_column(String(255), nullable=False)
    city: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    country: Mapped[str] = mapped_column(String(100), nullable=False)
    postal_code: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)

    # Contact
    contact_email: Mapped[str] = mapped_column(String(255), nullable=False)
    contact_phone: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)

    # Operational
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
    number_of_rooms: Mapped[int] = mapped_column(nullable=False)

    # Configuration (JSON stored as string - consider using JSONB for PostgreSQL)
    # settings: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    def __repr__(self) -> str:
        return f"<Property (id={self.id}, name={self.name}, code={self.code})>"
