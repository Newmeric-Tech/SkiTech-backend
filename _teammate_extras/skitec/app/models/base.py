"""
Base Model for SQLAlchemy ORM

Provides common fields and functionality for all models.
Uses declarative base pattern for clean, maintainable ORM definitions.
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Declarative base for all SQLAlchemy models"""

    pass


class TimestampMixin:
    """
    Mixin to add created_at and updated_at timestamps to models

    Automatically tracks creation and modification times.
    """

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class IdMixin:
    """Mixin to add primary key to models"""

    id: Mapped[int] = mapped_column(primary_key=True, index=True)


class SoftDeleteMixin:
    """
    Mixin to add soft delete functionality

    Instead of permanently deleting records, mark them as deleted.
    Queries should filter out soft-deleted records unless explicitly included.
    """

    deleted_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        default=None,
        nullable=True,
    )

    def soft_delete(self) -> None:
        """Mark record as deleted"""
        self.deleted_at = datetime.utcnow()
