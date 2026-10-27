"""
Attendance Models

Tracks punch in/out events with geolocation data and geofence validation.
"""

from datetime import datetime
from typing import Optional
from uuid import UUID

from uuid import uuid4

from sqlalchemy import (
    Boolean, String, Text, Integer, Float, DateTime,
    ForeignKey, UUID as SQLUUID, CheckConstraint, Index, func, text,
)
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, UUIDMixin, TimestampMixin


class AttendanceRecord(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "attendance_records"

    tenant_id: Mapped[UUID] = mapped_column(
        SQLUUID, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[UUID] = mapped_column(
        SQLUUID, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    property_id: Mapped[UUID] = mapped_column(
        SQLUUID, ForeignKey("properties.id", ondelete="RESTRICT"), nullable=False, index=True
    )

    punch_in_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    punch_in_lat: Mapped[float] = mapped_column(Float(precision=10), nullable=False)
    punch_in_lon: Mapped[float] = mapped_column(Float(precision=10), nullable=False)
    punch_in_acc: Mapped[Optional[float]] = mapped_column(Float(precision=10), nullable=True)

    is_within_fence: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    distance_meters: Mapped[Optional[float]] = mapped_column(Float(precision=10), nullable=True)

    punch_out_time: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    punch_out_lat: Mapped[Optional[float]] = mapped_column(Float(precision=10), nullable=True)
    punch_out_lon: Mapped[Optional[float]] = mapped_column(Float(precision=10), nullable=True)
    # Punch-out location check (migration 027); NULL on rows closed before it
    # and on stale rows auto-closed without a punch-out location.
    punch_out_acc: Mapped[Optional[float]] = mapped_column(Float(precision=10), nullable=True)
    punch_out_within_fence: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    punch_out_distance_meters: Mapped[Optional[float]] = mapped_column(Float(precision=10), nullable=True)

    hours_worked: Mapped[Optional[float]] = mapped_column(Float(precision=5), nullable=True)

    status: Mapped[str] = mapped_column(String(20), default="active", nullable=False, index=True)
    current_status: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class PropertyGeofence(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "property_geofences"

    id: Mapped[UUID] = mapped_column(SQLUUID, primary_key=True, index=True)
    tenant_id: Mapped[UUID] = mapped_column(
        SQLUUID, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    property_id: Mapped[UUID] = mapped_column(
        SQLUUID, ForeignKey("properties.id", ondelete="NO ACTION"), nullable=False, unique=True
    )

    property_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    center_lat: Mapped[float] = mapped_column(Float(precision=10), nullable=False)
    center_lng: Mapped[float] = mapped_column(Float(precision=10), nullable=False)
    radius_meters: Mapped[int] = mapped_column(Integer, nullable=False)
    address: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    city: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    country: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    alert_on_breach: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )


class GeofenceChangeRequest(Base):
    """
    A proposed punch location for a property (migration 028). Managers can
    only propose; Super Admin / Tenant Admin / Co Admin approve, which
    applies it to property_geofences. Rows are never deleted, so every
    request and decision is kept.
    """
    __tablename__ = "geofence_change_requests"

    id: Mapped[UUID] = mapped_column(SQLUUID, primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(
        SQLUUID, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    property_id: Mapped[UUID] = mapped_column(
        SQLUUID, ForeignKey("properties.id", ondelete="CASCADE"), nullable=False, index=True
    )
    requested_by: Mapped[Optional[UUID]] = mapped_column(
        SQLUUID, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )

    center_lat: Mapped[float] = mapped_column(Float, nullable=False)
    center_lng: Mapped[float] = mapped_column(Float, nullable=False)
    radius_meters: Mapped[int] = mapped_column(Integer, nullable=False)
    address: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending", server_default="pending")
    reviewed_by: Mapped[Optional[UUID]] = mapped_column(
        SQLUUID, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    review_note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow, server_default=func.now()
    )

    __table_args__ = (
        CheckConstraint(
            "status IN ('pending','approved','rejected','cancelled')", name="ck_geofence_request_status"
        ),
        CheckConstraint(
            "radius_meters BETWEEN 20 AND 2000", name="ck_geofence_request_radius"
        ),
        # At most one pending request per property; a second concurrent
        # submit fails here instead of leaving two pending.
        Index(
            "uq_geofence_request_pending", "property_id",
            unique=True, postgresql_where=text("status = 'pending'"), sqlite_where=text("status = 'pending'"),
        ),
    )


class AttendanceCorrectionRequest(Base):
    """
    A claimed punch-out time for an auto_closed attendance record (migration
    029). The record's owner submits it; a Manager of the property (for a
    Staff requester) or Super Admin / Tenant Admin / Co Admin approve it,
    which completes the record with hours from the approved time. Rows are
    never deleted, so every request and decision is kept.
    """
    __tablename__ = "attendance_correction_requests"

    id: Mapped[UUID] = mapped_column(SQLUUID, primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(
        SQLUUID, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    property_id: Mapped[UUID] = mapped_column(
        SQLUUID, ForeignKey("properties.id", ondelete="CASCADE"), nullable=False, index=True
    )
    attendance_id: Mapped[UUID] = mapped_column(
        SQLUUID, ForeignKey("attendance_records.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    requested_by: Mapped[Optional[UUID]] = mapped_column(
        SQLUUID, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    # Role of the requester when they asked; decides who may review
    requester_role: Mapped[str] = mapped_column(String(50), nullable=False)

    claimed_punch_out_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)

    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending", server_default="pending")
    reviewed_by: Mapped[Optional[UUID]] = mapped_column(
        SQLUUID, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    review_note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow, server_default=func.now()
    )

    __table_args__ = (
        CheckConstraint(
            "status IN ('pending','approved','rejected','cancelled')", name="ck_attendance_correction_status"
        ),
        Index(
            "uq_attendance_correction_pending", "attendance_id",
            unique=True, postgresql_where=text("status = 'pending'"), sqlite_where=text("status = 'pending'"),
        ),
    )
