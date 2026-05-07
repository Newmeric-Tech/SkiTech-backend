"""
Workforce Schemas - Request & Response Models

Pydantic schemas for workforce management endpoints.
"""

from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, EmailStr, Field


class WorkforceBase(BaseModel):
    """Base workforce schema"""

    first_name: str = Field(..., min_length=1, max_length=255)
    last_name: str = Field(..., min_length=1, max_length=255)
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    employee_id: str = Field(..., min_length=1, max_length=100)
    position: str = Field(..., min_length=1, max_length=100)
    department: str = Field(..., min_length=1, max_length=100)
    property_id: int = Field(..., gt=0)
    start_date: date
    end_date: Optional[date] = None
    scheduled_hours_per_week: int = Field(..., gt=0, le=168)
    notes: Optional[str] = None


class WorkforceCreate(WorkforceBase):
    """Schema for workforce entry creation"""

    pass


class WorkforceUpdate(BaseModel):
    """Schema for workforce entry updates"""

    first_name: Optional[str] = Field(None, min_length=1, max_length=255)
    last_name: Optional[str] = Field(None, min_length=1, max_length=255)
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    position: Optional[str] = Field(None, min_length=1, max_length=100)
    department: Optional[str] = Field(None, min_length=1, max_length=100)
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    scheduled_hours_per_week: Optional[int] = Field(None, gt=0, le=168)
    is_active: Optional[bool] = None
    notes: Optional[str] = None


class WorkforceResponse(WorkforceBase):
    """Schema for workforce entry response"""

    id: int
    is_active: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class WorkforceSummary(BaseModel):
    """Summary schema for workforce in list views"""

    id: int
    first_name: str
    last_name: str
    employee_id: str
    position: str
    department: str
    is_active: bool
