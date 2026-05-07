"""
KRA (Key Result Areas) Model - SQLAlchemy ORM Definition

Defines KRA entities for daily and weekly performance tracking.
Includes multi-tenant support with strict tenant-level isolation.
"""

from typing import Optional

from sqlalchemy import Boolean, Date, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, IdMixin, SoftDeleteMixin, TimestampMixin


class DailyKRA(Base, IdMixin, TimestampMixin, SoftDeleteMixin):
    """
    Daily KRA Model

    Tracks daily key result areas for hospitality operations.
    Includes guest metrics, operational tasks, and financial data.
    """

    __tablename__ = "daily_kras"

    # Multi-tenancy
    tenant_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    
    # User/Employee reference
    user_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    
    # Date tracking
    date: Mapped[Date] = mapped_column(Date, nullable=False, index=True)

    # Shift Operations
    shift_changeover_status: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Guest Metrics
    guest_checkin_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    guest_checkout_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Operational Metrics
    complaints_logged: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    room_availability_checked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    maintenance_tasks: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Financial Metrics
    cash_deposit_amount: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)

    # Reviews Tracking
    google_reviews_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Additional metadata
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_submitted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)

    def __repr__(self) -> str:
        return f"<DailyKRA (id={self.id}, tenant_id={self.tenant_id}, date={self.date}, user_id={self.user_id})>"


class WeeklyKRA(Base, IdMixin, TimestampMixin, SoftDeleteMixin):
    """
    Weekly KRA Model

    Tracks weekly key result areas for strategic operations.
    Focuses on content management and inventory oversight.
    """

    __tablename__ = "weekly_kras"

    # Multi-tenancy
    tenant_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    
    # User/Employee reference
    user_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    
    # Week tracking (ISO week)
    week_starting_date: Mapped[Date] = mapped_column(Date, nullable=False, index=True)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    week_number: Mapped[int] = mapped_column(Integer, nullable=False)

    # OTA (Online Travel Aggregator) Images
    ota_images_uploaded: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    ota_platforms: Mapped[Optional[str]] = mapped_column(
        Text, 
        nullable=True,
        comment="Comma-separated list of OTA platforms (e.g., Google,Booking.com,Expedia)"
    )

    # Supply Management
    supply_stock_reviewed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    supply_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Additional metadata
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_submitted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)

    def __repr__(self) -> str:
        return f"<WeeklyKRA (id={self.id}, tenant_id={self.tenant_id}, week={self.week_number}/{self.year}, user_id={self.user_id})>"


class MonthlyKRA(Base, IdMixin, TimestampMixin, SoftDeleteMixin):
    """
    Monthly KRA Model

    Tracks monthly key result areas including revenue reports.
    Supports S3 file uploads for revenue documentation.
    """

    __tablename__ = "monthly_kras"

    # Multi-tenancy
    tenant_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    
    # User/Employee reference
    user_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    
    # Month tracking
    month: Mapped[int] = mapped_column(Integer, nullable=False)
    year: Mapped[int] = mapped_column(Integer, nullable=False, index=True)

    # Revenue Report
    revenue_report_url: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="S3 URL for revenue report file upload"
    )

    # Additional metadata
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_submitted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)

    def __repr__(self) -> str:
        return f"<MonthlyKRA (id={self.id}, tenant_id={self.tenant_id}, month={self.month}/{self.year}, user_id={self.user_id})>"


class QuarterlyKRA(Base, IdMixin, TimestampMixin, SoftDeleteMixin):
    """
    Quarterly KRA Model

    Tracks quarterly key result areas including revenue reports.
    Supports S3 file uploads for revenue documentation.
    """

    __tablename__ = "quarterly_kras"

    # Multi-tenancy
    tenant_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    
    # User/Employee reference
    user_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    
    # Quarter tracking
    quarter: Mapped[int] = mapped_column(Integer, nullable=False)
    year: Mapped[int] = mapped_column(Integer, nullable=False, index=True)

    # Revenue Report
    revenue_report_url: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="S3 URL for revenue report file upload"
    )

    # Additional metadata
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_submitted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)

    def __repr__(self) -> str:
        return f"<QuarterlyKRA (id={self.id}, tenant_id={self.tenant_id}, quarter=Q{self.quarter}/{self.year}, user_id={self.user_id})>"
