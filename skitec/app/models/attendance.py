"""
Attendance Model - SQLAlchemy ORM Definition

Tracks attendance records including punch in/out events with geolocation data.
Includes geofencing validation to ensure staff are within hotel premises.
Aligned with existing database schema using UUIDs and tenant support.
"""

from datetime import datetime
from typing import Optional
from uuid import UUID

from sqlalchemy import (
    Boolean, String, Text, Integer, Float, DateTime, 
    ForeignKey, Index, UUID as SQLUUID
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class AttendanceRecord(Base):
    """
    Attendance Record Model
    
    Tracks employee punch in/out events with geolocation data.
    Stores latitude, longitude, accuracy, and geofence validation status.
    Aligned with existing database schema.
    """

    __tablename__ = "attendance_records"

    # Primary Keys & Relationships
    id: Mapped[UUID] = mapped_column(SQLUUID, primary_key=True, index=True)
    tenant_id: Mapped[UUID] = mapped_column(
        SQLUUID,
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    user_id: Mapped[UUID] = mapped_column(
        SQLUUID,
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True
    )
    property_id: Mapped[UUID] = mapped_column(
        SQLUUID,
        ForeignKey("properties.id", ondelete="RESTRICT"),
        nullable=False,
        index=True
    )

    # Punch In Details
    punch_in_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True
    )
    punch_in_lat: Mapped[float] = mapped_column(
        Float(precision=10),
        nullable=False
    )
    punch_in_lon: Mapped[float] = mapped_column(
        Float(precision=10),
        nullable=False
    )
    punch_in_acc: Mapped[Optional[float]] = mapped_column(
        Float(precision=10),
        nullable=True,
        comment="GPS accuracy in meters"
    )

    # Geofencing Validation
    is_within_fence: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
        index=True
    )
    distance_meters: Mapped[Optional[float]] = mapped_column(
        Float(precision=10),
        nullable=True,
        comment="Distance in meters from hotel center"
    )

    # Punch Out Details (Optional)
    punch_out_time: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True
    )
    punch_out_lat: Mapped[Optional[float]] = mapped_column(
        Float(precision=10),
        nullable=True
    )
    punch_out_lon: Mapped[Optional[float]] = mapped_column(
        Float(precision=10),
        nullable=True
    )

    # Duration
    hours_worked: Mapped[Optional[float]] = mapped_column(
        Float(precision=5),
        nullable=True,
        comment="Hours worked (calculated)"
    )

    # Status & Notes
    status: Mapped[str] = mapped_column(
        String(20),
        default="active",
        nullable=False,
        index=True,
        comment="active, completed, flagged"
    )
    notes: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True
    )

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow
    )

    def __repr__(self) -> str:
        return (
            f"<AttendanceRecord (id={self.id}, user_id={self.user_id}, "
            f"punch_in={self.punch_in_time}, within_fence={self.is_within_fence})>"
        )


class PropertyGeofence(Base):
    """
    Property Geofence Configuration Model
    
    Defines geofence boundaries for each property.
    Stores center coordinates and allowed radius.
    Aligned with existing database schema.
    """

    __tablename__ = "property_geofences"

    # Primary Keys & Relationships
    id: Mapped[UUID] = mapped_column(SQLUUID, primary_key=True, index=True)
    tenant_id: Mapped[UUID] = mapped_column(
        SQLUUID,
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    property_id: Mapped[UUID] = mapped_column(
        SQLUUID,
        ForeignKey("properties.id", ondelete="NO ACTION"),
        nullable=False,
        unique=True
    )

    # Property Information
    property_name: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True
    )

    # Geofence Center Point
    center_lat: Mapped[float] = mapped_column(
        Float(precision=10),
        nullable=False
    )
    center_lng: Mapped[float] = mapped_column(
        Float(precision=10),
        nullable=False
    )

    # Geofence Radius
    radius_meters: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="Geofence radius in meters"
    )

    # Address Information
    address: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True
    )
    city: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True
    )
    country: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True
    )

    # Alert Configuration
    alert_on_breach: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False
    )

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow
    )

    def __repr__(self) -> str:
        return (
            f"<PropertyGeofence (id={self.id}, property_id={self.property_id}, "
            f"property_name={self.property_name}, radius={self.radius_meters}m)>"
        )
