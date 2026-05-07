"""
WorkforceEntry Model

Used by KRA compliance calculations to look up employees per property.
Uses integer IDs (separate from the UUID-based Employee model in models.py).
"""

from datetime import date
from typing import Optional

from sqlalchemy import Date, String, Text, Boolean, Integer
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, IdMixin, SoftDeleteMixin, TimestampMixin


class WorkforceEntry(Base, IdMixin, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "workforce_entries"

    first_name: Mapped[str] = mapped_column(String(255), nullable=False)
    last_name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True)
    phone: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)

    property_id: Mapped[int] = mapped_column(nullable=False, index=True)

    employee_id: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    position: Mapped[str] = mapped_column(String(100), nullable=False)
    department: Mapped[str] = mapped_column(String(100), nullable=False, index=True)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)

    scheduled_hours_per_week: Mapped[int] = mapped_column(Integer, nullable=False)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
