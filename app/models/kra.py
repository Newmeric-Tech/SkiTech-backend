"""
KRA (Key Result Areas) Models

Tracks daily, weekly, monthly, and quarterly performance metrics.
Uses UUID PKs (UUIDMixin) to match the live database schema (these tables
predate the Alembic migration that documents them and were never created
with integer ids, despite an earlier version of this file assuming so).
"""

import uuid
from typing import Optional

from sqlalchemy import Boolean, Date, Float, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, SoftDeleteMixin, TimestampMixin, UUIDMixin


class DailyKRA(Base, UUIDMixin, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "daily_kras"

    tenant_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)
    date: Mapped[Date] = mapped_column(Date, nullable=False, index=True)

    shift_changeover_status: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    guest_checkin_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    guest_checkout_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    complaints_logged: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    room_availability_checked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    maintenance_tasks: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    cash_deposit_amount: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    google_reviews_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_submitted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)


class WeeklyKRA(Base, UUIDMixin, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "weekly_kras"

    tenant_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)
    week_starting_date: Mapped[Date] = mapped_column(Date, nullable=False, index=True)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    week_number: Mapped[int] = mapped_column(Integer, nullable=False)

    ota_images_uploaded: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    ota_platforms: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    supply_stock_reviewed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    supply_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_submitted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)


class MonthlyKRA(Base, UUIDMixin, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "monthly_kras"

    tenant_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)
    month: Mapped[int] = mapped_column(Integer, nullable=False)
    year: Mapped[int] = mapped_column(Integer, nullable=False, index=True)

    revenue_amount: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    guest_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    occupancy_rate: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    revenue_report_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_submitted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)


class QuarterlyKRA(Base, UUIDMixin, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "quarterly_kras"

    tenant_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)
    quarter: Mapped[int] = mapped_column(Integer, nullable=False)
    year: Mapped[int] = mapped_column(Integer, nullable=False, index=True)

    revenue_amount: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    guest_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    occupancy_rate: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    revenue_report_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_submitted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
