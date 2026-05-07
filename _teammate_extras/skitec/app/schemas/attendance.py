"""
Attendance Schemas - Pydantic Data Validation Models

Defines request/response schemas for punch in/out operations.
Validates geolocation data and response formatting.
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, validator


class GeolocationData(BaseModel):
    """Geolocation data from client device"""
    
    latitude: float = Field(
        ...,
        ge=-90,
        le=90,
        description="Latitude coordinate (-90 to 90)"
    )
    longitude: float = Field(
        ...,
        ge=-180,
        le=180,
        description="Longitude coordinate (-180 to 180)"
    )
    accuracy: Optional[float] = Field(
        None,
        ge=0,
        description="GPS accuracy in meters"
    )
    address: Optional[str] = Field(
        None,
        max_length=500,
        description="Human-readable address"
    )

    class Config:
        """Pydantic config"""
        json_schema_extra = {
            "example": {
                "latitude": 28.5244,
                "longitude": 77.1855,
                "accuracy": 15.0,
                "address": "New Delhi, India"
            }
        }


class PunchInRequest(BaseModel):
    """Request model for punch in operation"""
    
    geolocation: GeolocationData = Field(
        ...,
        description="Current geolocation of the device"
    )
    device_info: Optional[str] = Field(
        None,
        max_length=255,
        description="Device information (browser, OS, etc.)"
    )
    notes: Optional[str] = Field(
        None,
        max_length=500,
        description="Additional notes for punch in"
    )

    class Config:
        """Pydantic config"""
        json_schema_extra = {
            "example": {
                "geolocation": {
                    "latitude": 28.5244,
                    "longitude": 77.1855,
                    "accuracy": 15.0,
                    "address": "Hotel Main Entrance"
                },
                "device_info": "Chrome 120.0 on Windows",
                "notes": "Punched in on time"
            }
        }


class PunchOutRequest(BaseModel):
    """Request model for punch out operation"""
    
    geolocation: GeolocationData = Field(
        ...,
        description="Current geolocation of the device"
    )
    device_info: Optional[str] = Field(
        None,
        max_length=255,
        description="Device information (browser, OS, etc.)"
    )
    notes: Optional[str] = Field(
        None,
        max_length=500,
        description="Additional notes for punch out"
    )

    class Config:
        """Pydantic config"""
        json_schema_extra = {
            "example": {
                "geolocation": {
                    "latitude": 28.5245,
                    "longitude": 77.1856,
                    "accuracy": 12.0,
                    "address": "Hotel Main Entrance"
                },
                "device_info": "Chrome 120.0 on Windows",
                "notes": "Completed shift"
            }
        }


class AttendanceRecordResponse(BaseModel):
    """Response model for attendance record"""
    
    id: str  # UUID as string
    user_id: str
    property_id: str
    tenant_id: str
    
    # Punch In
    punch_in_time: datetime
    punch_in_lat: float
    punch_in_lon: float
    punch_in_acc: Optional[float]
    is_within_fence: bool
    distance_meters: Optional[float]
    
    # Punch Out
    punch_out_time: Optional[datetime] = None
    punch_out_lat: Optional[float] = None
    punch_out_lon: Optional[float] = None
    
    # Duration
    hours_worked: Optional[float] = None
    
    # Status
    status: str
    notes: Optional[str]
    
    # Timestamps
    created_at: datetime
    updated_at: datetime

    class Config:
        """Pydantic config"""
        from_attributes = True
        json_schema_extra = {
            "example": {
                "id": "550e8400-e29b-41d4-a716-446655440000",
                "user_id": "550e8400-e29b-41d4-a716-446655440001",
                "property_id": "550e8400-e29b-41d4-a716-446655440002",
                "tenant_id": "550e8400-e29b-41d4-a716-446655440003",
                "punch_in_time": "2026-05-05T08:30:00+00:00",
                "punch_in_lat": 28.5244,
                "punch_in_lon": 77.1855,
                "punch_in_acc": 15.0,
                "is_within_fence": True,
                "distance_meters": 45.5,
                "status": "active",
                "hours_worked": None,
                "created_at": "2026-05-05T08:30:00+00:00",
                "updated_at": "2026-05-05T08:30:00+00:00"
            }
        }


class PunchInResponse(BaseModel):
    """Response model for punch in operation"""
    
    success: bool
    message: str
    attendance_id: str  # UUID as string
    is_within_fence: bool
    distance_meters: Optional[float]
    warning: Optional[str] = None
    
    class Config:
        """Pydantic config"""
        json_schema_extra = {
            "example": {
                "success": True,
                "message": "Punched in successfully",
                "attendance_id": "550e8400-e29b-41d4-a716-446655440000",
                "is_within_fence": True,
                "distance_meters": 45.5,
                "warning": None
            }
        }


class PunchOutResponse(BaseModel):
    """Response model for punch out operation"""
    
    success: bool
    message: str
    attendance_id: str  # UUID as string
    hours_worked: float
    is_within_fence: bool
    distance_meters: Optional[float]
    warning: Optional[str] = None

    class Config:
        """Pydantic config"""
        json_schema_extra = {
            "example": {
                "success": True,
                "message": "Punched out successfully",
                "attendance_id": "550e8400-e29b-41d4-a716-446655440000",
                "hours_worked": 8.5,
                "is_within_fence": True,
                "distance_meters": 50.2,
                "warning": None
            }
        }


class PropertyGeofenceCreate(BaseModel):
    """Request model for creating property geofence"""
    
    property_id: str = Field(
        ...,
        description="UUID of the property"
    )
    property_name: Optional[str] = Field(
        None,
        max_length=255,
        description="Name of the property"
    )
    center_lat: float = Field(
        ...,
        ge=-90,
        le=90,
        description="Latitude of geofence center"
    )
    center_lng: float = Field(
        ...,
        ge=-180,
        le=180,
        description="Longitude of geofence center"
    )
    radius_meters: int = Field(
        default=500,
        ge=50,
        le=5000,
        description="Geofence radius in meters (50-5000)"
    )
    address: Optional[str] = Field(
        None,
        max_length=255
    )
    city: Optional[str] = Field(
        None,
        max_length=100
    )
    country: Optional[str] = Field(
        None,
        max_length=100
    )
    alert_on_breach: Optional[bool] = Field(
        default=True,
        description="Alert when breach detected"
    )

    class Config:
        """Pydantic config"""
        json_schema_extra = {
            "example": {
                "property_id": "550e8400-e29b-41d4-a716-446655440000",
                "property_name": "Grand Hotel Delhi",
                "center_lat": 28.5244,
                "center_lng": 77.1855,
                "radius_meters": 500,
                "address": "123 Main Street",
                "city": "New Delhi",
                "country": "India"
            }
        }


class PropertyGeofenceResponse(BaseModel):
    """Response model for property geofence"""
    
    id: str  # UUID as string
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
        """Pydantic config"""
        from_attributes = True


class GeolocationHistoryFilter(BaseModel):
    """Filter model for geolocation history queries"""
    
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    is_within_geofence: Optional[bool] = None
    status: Optional[str] = None
    page: int = Field(default=1, ge=1)
    limit: int = Field(default=50, ge=1, le=100)

    class Config:
        """Pydantic config"""
        json_schema_extra = {
            "example": {
                "start_date": "2026-05-01T00:00:00+00:00",
                "end_date": "2026-05-05T23:59:59+00:00",
                "is_within_geofence": True,
                "page": 1,
                "limit": 50
            }
        }
