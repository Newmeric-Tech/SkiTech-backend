"""
Assigned KRA tasks - app/models/kra_tasks.py (migration 030)

A KraDefinition is a task with a frequency, built for one property. A
KraAssignment gives it to one user. A KraOccurrence is that user's task for
one period: pending -> completed, or pending -> delayed -> completed, with
was_delayed staying true so a late finish can be told from an on-time one.

Separate from the older self-submitted KRA forms in app/models/kra.py.
"""
from datetime import date, datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID

from sqlalchemy import (
    Boolean, CheckConstraint, Date, DateTime, ForeignKey, Index, Numeric, String, Text,
    UniqueConstraint, text,
)
from sqlalchemy.dialects.postgresql import UUID as SQLUUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, SoftDeleteMixin, TimestampMixin, UUIDMixin

FREQUENCIES = ("daily", "weekly", "monthly", "quarterly")
OCCURRENCE_STATUSES = ("pending", "delayed", "completed")


class KraDefinition(Base, UUIDMixin, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "kra_definitions"
    __table_args__ = (
        CheckConstraint("frequency IN ('daily','weekly','monthly','quarterly')", name="ck_kra_definition_frequency"),
    )

    tenant_id: Mapped[UUID] = mapped_column(
        SQLUUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    property_id: Mapped[UUID] = mapped_column(
        SQLUUID(as_uuid=True), ForeignKey("properties.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    frequency: Mapped[str] = mapped_column(String(20), nullable=False)
    value_label: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    created_by: Mapped[Optional[UUID]] = mapped_column(
        SQLUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=text("true"))


class KraAssignment(Base, UUIDMixin):
    __tablename__ = "kra_assignments"
    __table_args__ = (
        # One active assignment per user and task; ended ones stay as history.
        Index("uq_kra_assignment_active", "definition_id", "assignee_id", unique=True,
              postgresql_where=text("is_active"), sqlite_where=text("is_active")),
    )

    tenant_id: Mapped[UUID] = mapped_column(
        SQLUUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    property_id: Mapped[UUID] = mapped_column(
        SQLUUID(as_uuid=True), ForeignKey("properties.id", ondelete="CASCADE"), nullable=False, index=True
    )
    definition_id: Mapped[UUID] = mapped_column(
        SQLUUID(as_uuid=True), ForeignKey("kra_definitions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    assignee_id: Mapped[UUID] = mapped_column(
        SQLUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    assigned_by: Mapped[Optional[UUID]] = mapped_column(
        SQLUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=text("true"))
    ended_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


class KraOccurrence(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "kra_occurrences"
    __table_args__ = (
        UniqueConstraint("assignment_id", "period_start", name="uq_kra_occurrence_period"),
        CheckConstraint("status IN ('pending','delayed','completed')", name="ck_kra_occurrence_status"),
    )

    tenant_id: Mapped[UUID] = mapped_column(
        SQLUUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    property_id: Mapped[UUID] = mapped_column(
        SQLUUID(as_uuid=True), ForeignKey("properties.id", ondelete="CASCADE"), nullable=False, index=True
    )
    assignment_id: Mapped[UUID] = mapped_column(
        SQLUUID(as_uuid=True), ForeignKey("kra_assignments.id", ondelete="CASCADE"), nullable=False
    )
    definition_id: Mapped[UUID] = mapped_column(
        SQLUUID(as_uuid=True), ForeignKey("kra_definitions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    assignee_id: Mapped[UUID] = mapped_column(
        SQLUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending", server_default="pending")
    was_delayed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=text("false"))
    delayed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    delay_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    completion_note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    completion_value: Mapped[Optional[Decimal]] = mapped_column(Numeric(14, 2), nullable=True)
