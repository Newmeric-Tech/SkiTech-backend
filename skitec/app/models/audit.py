"""
Audit Log Model - SQLAlchemy ORM Definition

Tracks all significant system actions for compliance and audit purposes.
Immutable records of who did what, when, and from where.
"""

from typing import Optional

from sqlalchemy import String, Text, Integer
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, IdMixin, TimestampMixin


class AuditLog(Base, IdMixin, TimestampMixin):
    """
    Audit Log Model

    Immutable record of system actions for compliance and audit trails.
    Never soft-deleted - always permanent record.
    """

    __tablename__ = "audit_logs"

    # Actor Information
    user_id: Mapped[Optional[int]] = mapped_column(nullable=True, index=True)
    username: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # Action Details
    action: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    resource_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    resource_id: Mapped[Optional[int]] = mapped_column(nullable=True, index=True)

    # Context
    details: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON string
    property_id: Mapped[Optional[int]] = mapped_column(nullable=True, index=True)

    # Technical Details
    ip_address: Mapped[Optional[str]] = mapped_column(String(45), nullable=True)
    user_agent: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    # Result
    status: Mapped[str] = mapped_column(String(50), default="success", nullable=False)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    def __repr__(self) -> str:
        return (
            f"<AuditLog (id={self.id}, action={self.action}, "
            f"resource_type={self.resource_type})>"
        )
