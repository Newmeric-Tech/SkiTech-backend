"""
Schemas Module - Initialization

Exports all Pydantic schemas for API validation.
"""

from .common import (
    ErrorResponse,
    PaginatedResponse,
    PaginationParams,
    SuccessResponse,
    TimestampedModel,
)
from .governance import (
    GovernanceWorkflowCreate,
    GovernanceWorkflowResponse,
    WorkflowInstanceApprove,
    WorkflowInstanceCreate,
    WorkflowInstanceReject,
    WorkflowInstanceResponse,
)
from .property import (
    PropertyCreate,
    PropertyResponse,
    PropertySummary,
    PropertyUpdate,
)
from .user import (
    LoginRequest,
    RefreshTokenRequest,
    TokenResponse,
    UserCreate,
    UserResponse,
    UserUpdate,
)
from .workforce import (
    WorkforceCreate,
    WorkforceSummary,
    WorkforceUpdate,
    WorkforceResponse,
)
from .kra import (
    DailyKRACreate,
    DailyKRAResponse,
    DailyKRAUpdate,
    DailyKRAListResponse,
    WeeklyKRACreate,
    WeeklyKRAResponse,
    WeeklyKRAUpdate,
    WeeklyKRAListResponse,
)
from .attendance import (
    GeolocationData,
    PunchInRequest,
    PunchOutRequest,
    AttendanceRecordResponse,
    PunchInResponse,
    PunchOutResponse,
    PropertyGeofenceCreate,
    PropertyGeofenceResponse,
    GeolocationHistoryFilter,
)

__all__ = [
    # Common
    "PaginationParams",
    "PaginatedResponse",
    "TimestampedModel",
    "ErrorResponse",
    "SuccessResponse",
    # User
    "UserCreate",
    "UserResponse",
    "UserUpdate",
    "LoginRequest",
    "TokenResponse",
    "RefreshTokenRequest",
    # Property
    "PropertyCreate",
    "PropertyResponse",
    "PropertyUpdate",
    "PropertySummary",
    # Workforce
    "WorkforceCreate",
    "WorkforceResponse",
    "WorkforceUpdate",
    "WorkforceSummary",
    # Governance
    "GovernanceWorkflowCreate",
    "GovernanceWorkflowResponse",
    "WorkflowInstanceCreate",
    "WorkflowInstanceResponse",
    "WorkflowInstanceApprove",
    "WorkflowInstanceReject",
    # KRA
    "DailyKRACreate",
    "DailyKRAResponse",
    "DailyKRAUpdate",
    "DailyKRAListResponse",
    "WeeklyKRACreate",
    "WeeklyKRAResponse",
    "WeeklyKRAUpdate",
    "WeeklyKRAListResponse",
    # Attendance & Geolocation
    "GeolocationData",
    "PunchInRequest",
    "PunchOutRequest",
    "AttendanceRecordResponse",
    "PunchInResponse",
    "PunchOutResponse",
    "PropertyGeofenceCreate",
    "PropertyGeofenceResponse",
    "GeolocationHistoryFilter",
]
