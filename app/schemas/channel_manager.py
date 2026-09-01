from typing import Dict, Any, Optional
from pydantic import BaseModel, Field
from uuid import UUID
from datetime import datetime

class TestConnectionRequest(BaseModel):
    provider_name: str = Field(..., description="Provider name: e.g. channex, mews, cloudbeds, siteminder, little_hotelier")
    credentials: Dict[str, Any] = Field(..., description="API credentials required by the specific provider")

class IntegrationCreate(BaseModel):
    provider_name: str = Field(..., description="Provider name")
    property_id: UUID = Field(..., description="Target property UUID")
    credentials: Dict[str, Any] = Field(..., description="API credentials required by the specific provider")

class IntegrationOut(BaseModel):
    id: UUID
    provider_name: str
    property_id: UUID
    property_name: Optional[str] = None
    connection_status: str
    last_sync_at: Optional[datetime] = None
    error_message: Optional[str] = None

    class Config:
        from_attributes = True  # Pydantic v2 support for ORM objects (ORM mode)
        orm_mode = True         # Pydantic v1 backward compatibility


class ReservationOut(BaseModel):
    id: UUID
    external_id: str
    status: str
    guest_name: str
    guest_email: Optional[str] = None
    guest_phone: Optional[str] = None
    room_number: Optional[str] = None
    room_type: Optional[str] = None
    check_in_date: datetime
    check_out_date: datetime
    num_nights: int
    num_adults: int
    num_children: int
    total_amount: float
    currency: str
    booking_source: Optional[str] = None
    special_requests: Optional[str] = None
    booked_at: Optional[datetime] = None
    synced_at: datetime

    class Config:
        from_attributes = True
        orm_mode = True
