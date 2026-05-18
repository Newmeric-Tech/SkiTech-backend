"""
Attendance Models

Tracks punch in/out events with geolocation data and geofence validation.
"""

from datetime import datetime
from typing import Optional
from uuid import UUID

from sqlalchemy import (
    Boolean, String, Text, Integer, Float, DateTime,
    ForeignKey, UUID as SQLUUID
)
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class AttendanceRecord(Base):
    __tablename__ = "attendance_records"

    id: Mapped[UUID] = mapped_column(SQLUUID, primary_key=True, index=True)
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

    hours_worked: Mapped[Optional[float]] = mapped_column(Float(precision=5), nullable=True)

    status: Mapped[str] = mapped_column(String(20), default="active", nullable=False, index=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )


class PropertyGeofence(Base):
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
