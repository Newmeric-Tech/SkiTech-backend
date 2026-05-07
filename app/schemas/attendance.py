"""
Attendance Schemas - Pydantic Data Validation Models

Request/response schemas for punch in/out operations and geofence management.
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, validator


class GeolocationData(BaseModel):
    latitude: float = Field(..., ge=-90, le=90, description="Latitude coordinate (-90 to 90)")
    longitude: float = Field(..., ge=-180, le=180, description="Longitude coordinate (-180 to 180)")
    accuracy: Optional[float] = Field(None, ge=0, description="GPS accuracy in meters")
    address: Optional[str] = Field(None, max_length=500, description="Human-readable address")

    class Config:
        json_schema_extra = {
            "example": {
                "latitude": 28.5244,
                "longitude": 77.1855,
                "accuracy": 15.0,
                "address": "New Delhi, India"
            }
        }


class PunchInRequest(BaseModel):
    geolocation: GeolocationData
    device_info: Optional[str] = Field(None, max_length=255)
    notes: Optional[str] = Field(None, max_length=500)


class PunchOutRequest(BaseModel):
    geolocation: GeolocationData
    device_info: Optional[str] = Field(None, max_length=255)
    notes: Optional[str] = Field(None, max_length=500)


class AttendanceRecordResponse(BaseModel):
    id: str
    user_id: str
    property_id: str
    tenant_id: str
    punch_in_time: datetime
    punch_in_lat: float
    punch_in_lon: float
    punch_in_acc: Optional[float]
    is_within_fence: bool
    distance_meters: Optional[float]
    punch_out_time: Optional[datetime] = None
    punch_out_lat: Optional[float] = None
    punch_out_lon: Optional[float] = None
    hours_worked: Optional[float] = None
    status: str
    notes: Optional[str]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class PunchInResponse(BaseModel):
    success: bool
    message: str
    attendance_id: str
    is_within_fence: bool
    distance_meters: Optional[float]
    warning: Optional[str] = None


class PunchOutResponse(BaseModel):
    success: bool
    message: str
    attendance_id: str
    hours_worked: float
    is_within_fence: bool
    distance_meters: Optional[float]
    warning: Optional[str] = None


class PropertyGeofenceCreate(BaseModel):
    property_id: str = Field(..., description="UUID of the property")
    property_name: Optional[str] = Field(None, max_length=255)
    center_lat: float = Field(..., ge=-90, le=90)
    center_lng: float = Field(..., ge=-180, le=180)
    radius_meters: int = Field(default=500, ge=50, le=5000)
    address: Optional[str] = Field(None, max_length=255)
    city: Optional[str] = Field(None, max_length=100)
    country: Optional[str] = Field(None, max_length=100)
    alert_on_breach: Optional[bool] = Field(default=True)


class PropertyGeofenceResponse(BaseModel):
    id: str
    property_id: str
    tenant_id: str
    property_name: Optional[str]
    center_lat: float
    center_lng: float
    radius_meters: int
    address: Optional[str]
    city: Optional[str]
    country: Optional[str]
    alert_on_breach: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class GeolocationHistoryFilter(BaseModel):
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    is_within_geofence: Optional[bool] = None
    status: Optional[str] = None
    page: int = Field(default=1, ge=1)
    limit: int = Field(default=50, ge=1, le=100)
