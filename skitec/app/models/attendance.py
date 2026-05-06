"""
Attendance Model - SQLAlchemy ORM Definition

Tracks attendance records including punch in/out events with geolocation data.
Includes geofencing validation to ensure staff are within hotel premises.
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Boolean, String, Text, Integer, Float, DateTime, 
    ForeignKey, Index
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, IdMixin, TimestampMixin


class AttendanceRecord(Base, IdMixin, TimestampMixin):
    """
    Attendance Record Model
    
    Tracks employee punch in/out events with geolocation data.
    Stores latitude, longitude, accuracy, and geofence validation status.
    """

    __tablename__ = "attendance_records"
    __table_args__ = (
        Index("idx_user_id_date", "user_id", "punch_in_time"),
        Index("idx_property_id_date", "property_id", "punch_in_time"),
        Index("idx_is_within_geofence", "is_within_geofence"),
    )

    # User Information
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    property_id: Mapped[int] = mapped_column(
        nullable=False,
        index=True
    )

    # Punch In Details
    punch_in_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True
    )
    punch_in_latitude: Mapped[float] = mapped_column(
        Float(precision=10),
        nullable=False
    )
    punch_in_longitude: Mapped[float] = mapped_column(
        Float(precision=10),
        nullable=False
    )
    punch_in_accuracy: Mapped[Optional[float]] = mapped_column(
        Float(precision=10),
        nullable=True,
        comment="GPS accuracy in meters"
    )
    punch_in_address: Mapped[Optional[str]] = mapped_column(
        String(500),
        nullable=True
    )

    # Geofencing Validation
    is_within_geofence: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
        index=True
    )
    distance_from_hotel: Mapped[Optional[float]] = mapped_column(
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
    punch_out_latitude: Mapped[Optional[float]] = mapped_column(
        Float(precision=10),
        nullable=True
    )
    punch_out_longitude: Mapped[Optional[float]] = mapped_column(
        Float(precision=10),
        nullable=True
    )
    punch_out_accuracy: Mapped[Optional[float]] = mapped_column(
        Float(precision=10),
        nullable=True,
        comment="GPS accuracy in meters"
    )
    punch_out_address: Mapped[Optional[str]] = mapped_column(
        String(500),
        nullable=True
    )
    punch_out_within_geofence: Mapped[Optional[bool]] = mapped_column(
        Boolean,
        nullable=True
    )
    punch_out_distance: Mapped[Optional[float]] = mapped_column(
        Float(precision=10),
        nullable=True,
        comment="Distance in meters from hotel center at punch out"
    )

    # Duration
    hours_worked: Mapped[Optional[float]] = mapped_column(
        Float(precision=5),
        nullable=True,
        comment="Hours worked (calculated)"
    )

    # Status & Notes
    status: Mapped[str] = mapped_column(
        String(50),
        default="active",
        nullable=False,
        index=True,
        comment="active, completed, flagged"
    )
    notes: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True
    )

    def __repr__(self) -> str:
        return (
            f"<AttendanceRecord (id={self.id}, user_id={self.user_id}, "
            f"punch_in={self.punch_in_time}, within_geofence={self.is_within_geofence})>"
        )


class PropertyGeofence(Base, IdMixin, TimestampMixin):
    """
    Property Geofence Configuration Model
    
    Defines geofence boundaries for each property.
    Stores center coordinates and allowed radius.
    """

    __tablename__ = "property_geofences"
    __table_args__ = (
        Index("idx_property_id", "property_id"),
    )

    # Property Information
    property_id: Mapped[int] = mapped_column(
        nullable=False,
        index=True,
        unique=True
    )
    property_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False
    )

    # Geofence Center Point
    center_latitude: Mapped[float] = mapped_column(
        Float(precision=10),
        nullable=False
    )
    center_longitude: Mapped[float] = mapped_column(
        Float(precision=10),
        nullable=False
    )

    # Geofence Radius
    radius_meters: Mapped[int] = mapped_column(
        Integer,
        default=500,
        nullable=False,
        comment="Geofence radius in meters"
    )

    # Address Information
    address: Mapped[Optional[str]] = mapped_column(
        String(500),
        nullable=True
    )
    city: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True
    )
    state: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True
    )
    country: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True
    )
    zip_code: Mapped[Optional[str]] = mapped_column(
        String(20),
        nullable=True
    )

    # Status
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False
    )

    # Description
    description: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True
    )

    def __repr__(self) -> str:
        return (
            f"<PropertyGeofence (id={self.id}, property_id={self.property_id}, "
            f"property_name={self.property_name}, radius={self.radius_meters}m)>"
        )
