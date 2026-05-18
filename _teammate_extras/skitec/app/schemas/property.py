"""
Property Schemas - Request & Response Models

Pydantic schemas for property-related endpoints.
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr, Field


class PropertyBase(BaseModel):
    """Base property schema"""

    name: str = Field(..., min_length=1, max_length=255)
    code: str = Field(..., min_length=1, max_length=50)
    description: Optional[str] = None
    address: str = Field(..., min_length=1, max_length=255)
    city: str = Field(..., min_length=1, max_length=100)
    country: str = Field(..., min_length=1, max_length=100)
    postal_code: Optional[str] = None
    contact_email: EmailStr
    contact_phone: Optional[str] = None
    number_of_rooms: int = Field(..., gt=0)


class PropertyCreate(PropertyBase):
    """Schema for property creation"""

    pass


class PropertyUpdate(BaseModel):
    """Schema for property updates"""

    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    address: Optional[str] = Field(None, min_length=1, max_length=255)
    city: Optional[str] = Field(None, min_length=1, max_length=100)
    country: Optional[str] = Field(None, min_length=1, max_length=100)
    postal_code: Optional[str] = None
    contact_email: Optional[EmailStr] = None
    contact_phone: Optional[str] = None
    number_of_rooms: Optional[int] = Field(None, gt=0)
    is_active: Optional[bool] = None


class PropertyResponse(PropertyBase):
    """Schema for property response"""

    id: int
    is_active: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class PropertySummary(BaseModel):
    """Summary schema for properties in list views"""

    id: int
    name: str
    code: str
    city: str
    country: str
    is_active: bool
    number_of_rooms: int
