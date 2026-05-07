"""
Workforce Model - SQLAlchemy ORM Definition

Represents workforce/employee records, including scheduling and status.
Tracks work history and related information.
"""

from datetime import date
from typing import Optional

from sqlalchemy import Date, String, Text, Boolean, Integer
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, IdMixin, SoftDeleteMixin, TimestampMixin


class WorkforceEntry(Base, IdMixin, TimestampMixin, SoftDeleteMixin):
    """
    Workforce/Employee Model

    Represents an employee or workforce member at a property.
    Tracks employment details, schedule, and status.
    """

    __tablename__ = "workforce_entries"

    # Employee Information
    first_name: Mapped[str] = mapped_column(String(255), nullable=False)
    last_name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True)
    phone: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)

    # Property Assignment
    property_id: Mapped[int] = mapped_column(nullable=False, index=True)

    # Employment Details
    employee_id: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    position: Mapped[str] = mapped_column(String(100), nullable=False)
    department: Mapped[str] = mapped_column(String(100), nullable=False, index=True)

    # Employment Status
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)

    # Schedule
    scheduled_hours_per_week: Mapped[int] = mapped_column(Integer, nullable=False)

    # Additional Notes
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    def __repr__(self) -> str:
        return (
            f"<WorkforceEntry (id={self.id}, employee_id={self.employee_id}, "
            f"position={self.position})>"
        )
