"""
Pydantic schemas for Employee Scheduling APIs
"""

from datetime import datetime
from typing import Optional, List
from enum import Enum

from pydantic import BaseModel, Field


# ═══════════════════════════════════════════════════════════════
# Enums
# ═══════════════════════════════════════════════════════════════

class AvailabilityStatus(str, Enum):
    AVAILABLE = "available"
    OFF = "off"
    LEAVE = "leave"
    HOLIDAY = "holiday"
    SICK = "sick"


class ScheduleStatus(str, Enum):
    DRAFT = "draft"
    ASSIGNED = "assigned"
    PUBLISHED = "published"
    COMPLETED = "completed"


class ShiftStatus(str, Enum):
    SCHEDULED = "scheduled"
    OFF = "off"
    CONFLICT = "conflict"
    COVERED = "covered"


class ReplacementRequestStatus(str, Enum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    ASSIGNED = "assigned"
    CANCELLED = "cancelled"


class ReplacementRequestType(str, Enum):
    DIRECT_ASSIGNMENT = "direct_assignment"
    SEND_REQUEST = "send_request"


class RequestPriority(str, Enum):
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"


class ShiftResponseType(str, Enum):
    ACCEPT = "accept"
    REJECT = "reject"


# ═══════════════════════════════════════════════════════════════
# Employee Availability Schemas
# ═══════════════════════════════════════════════════════════════

class EmployeeAvailabilityBase(BaseModel):
    availability_date: datetime
    status: AvailabilityStatus
    reason: Optional[str] = None
    notes: Optional[str] = None


class EmployeeAvailabilityCreate(EmployeeAvailabilityBase):
    employee_id: str


class EmployeeAvailabilityResponse(EmployeeAvailabilityBase):
    id: str
    employee_id: str
    property_id: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ═══════════════════════════════════════════════════════════════
# Shift Assignment Schemas
# ═══════════════════════════════════════════════════════════════

class ShiftAssignmentBase(BaseModel):
    shift_date: datetime
    shift_start_time: str = Field(..., pattern=r"^\d{2}:\d{2}$")
    shift_end_time: str = Field(..., pattern=r"^\d{2}:\d{2}$")
    shift_type: Optional[str] = None
    status: Optional[ShiftStatus] = ShiftStatus.SCHEDULED


class ShiftAssignmentCreate(ShiftAssignmentBase):
    pass


class ShiftAssignmentUpdate(BaseModel):
    shift_start_time: Optional[str] = None
    shift_end_time: Optional[str] = None
    shift_type: Optional[str] = None
    status: Optional[ShiftStatus] = None


class ShiftAssignmentResponse(ShiftAssignmentBase):
    id: str
    schedule_id: str
    employee_id: str
    property_id: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ═══════════════════════════════════════════════════════════════
# Weekly Schedule Schemas
# ═══════════════════════════════════════════════════════════════

class WeeklyScheduleBase(BaseModel):
    week_start_date: datetime
    week_end_date: datetime
    employee_id: str
    status: Optional[ScheduleStatus] = ScheduleStatus.DRAFT
    department_id: Optional[str] = None


class WeeklyScheduleCreate(WeeklyScheduleBase):
    pass


class WeeklyScheduleUpdate(BaseModel):
    status: Optional[ScheduleStatus] = None
    department_id: Optional[str] = None


class WeeklyScheduleResponse(WeeklyScheduleBase):
    id: str
    property_id: str
    assigned_by: Optional[str] = None
    assigned_at: Optional[datetime] = None
    published_at: Optional[datetime] = None
    shift_assignments: Optional[List[ShiftAssignmentResponse]] = []
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class BulkScheduleAssignmentRequest(BaseModel):
    """Bulk assign schedules for multiple employees"""
    employee_ids: List[str]
    week_start_date: datetime
    week_end_date: datetime
    department_id: Optional[str] = None


# ═══════════════════════════════════════════════════════════════
# Replacement Request Schemas
# ═══════════════════════════════════════════════════════════════

class ReplacementRequestBase(BaseModel):
    shift_date: datetime
    shift_start_time: str = Field(..., pattern=r"^\d{2}:\d{2}$")
    shift_end_time: str = Field(..., pattern=r"^\d{2}:\d{2}$")
    reason: Optional[str] = None
    priority: RequestPriority = RequestPriority.NORMAL
    request_type: ReplacementRequestType


class ReplacementRequestCreate(ReplacementRequestBase):
    original_employee_id: str
    replacement_employee_id: Optional[str] = None  # Required for direct_assignment


class ReplacementRequestUpdate(BaseModel):
    status: Optional[ReplacementRequestStatus] = None
    replacement_employee_id: Optional[str] = None


class ReplacementRequestResponse(ReplacementRequestBase):
    id: str
    shift_assignment_id: str
    original_employee_id: str
    replacement_employee_id: Optional[str] = None
    request_date: datetime
    status: ReplacementRequestStatus
    ai_recommended: bool
    created_by: Optional[str] = None
    responded_by: Optional[str] = None
    responded_at: Optional[datetime] = None
    response_reason: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ReplacementRequestWithDetails(ReplacementRequestResponse):
    """Include employee details in response"""
    original_employee_name: Optional[str] = None
    replacement_employee_name: Optional[str] = None
    original_employee_department: Optional[str] = None
    replacement_employee_department: Optional[str] = None


# ═══════════════════════════════════════════════════════════════
# Shift Response Schemas
# ═══════════════════════════════════════════════════════════════

class ShiftResponseCreate(BaseModel):
    replacement_request_id: str
    response_type: ShiftResponseType
    reason: Optional[str] = None


class ShiftResponseResponse(BaseModel):
    id: str
    replacement_request_id: str
    employee_id: str
    response_type: ShiftResponseType
    reason: Optional[str] = None
    responded_at: datetime
    created_at: datetime

    class Config:
        from_attributes = True


# ═══════════════════════════════════════════════════════════════
# AI Recommendation Schemas
# ═══════════════════════════════════════════════════════════════

class RecommendedEmployeeScore(BaseModel):
    employee_id: str
    employee_name: str
    department: str
    position: str
    compatibility_score: float = Field(..., ge=0, le=100)
    reason: str
    available: bool


class AIRecommendationRequest(BaseModel):
    shift_date: datetime
    shift_start_time: str = Field(..., pattern=r"^\d{2}:\d{2}$")
    shift_end_time: str = Field(..., pattern=r"^\d{2}:\d{2}$")
    department_id: Optional[str] = None
    priority: Optional[RequestPriority] = RequestPriority.NORMAL
    max_recommendations: int = Field(5, ge=1, le=20)


class AIRecommendationResponse(BaseModel):
    recommendations: List[RecommendedEmployeeScore]
    total_available: int
    timestamp: datetime


# ═══════════════════════════════════════════════════════════════
# Dashboard & Summary Schemas
# ═══════════════════════════════════════════════════════════════

class CriticalActionItem(BaseModel):
    """Critical action item for manager dashboard"""
    shift_assignment_id: str
    employee_id: str
    employee_name: str
    department: str
    shift_date: datetime
    shift_start_time: str
    shift_end_time: str
    reason_off: str
    urgency: str


class ConflictDetectionResult(BaseModel):
    """Result of conflict detection for a schedule"""
    has_conflicts: bool
    conflict_count: int
    conflicts: List[CriticalActionItem] = []
    replacement_requests_pending: int
    replacement_requests_urgent: int


class WeeklyScheduleWithConflicts(WeeklyScheduleResponse):
    conflicts: Optional[ConflictDetectionResult] = None
    total_hours: float
    working_days: int
    off_days: int


class EmployeeScheduleOverview(BaseModel):
    """Employee's schedule overview"""
    employee_id: str
    employee_name: str
    department: str
    current_week_schedule: Optional[WeeklyScheduleResponse] = None
    upcoming_off_days: List[EmployeeAvailabilityResponse] = []
    pending_shift_requests: List[ReplacementRequestResponse] = []


class StaffDashboardData(BaseModel):
    """Data for Staff Dashboard"""
    emergency_shift_requests: List[ReplacementRequestResponse]
    pending_requests_count: int
    accepted_requests_count: int
    rejected_requests_count: int
    current_week_schedule: Optional[WeeklyScheduleResponse] = None


class ManagerDashboardData(BaseModel):
    """Data for Manager Dashboard"""
    scheduling_progress: float  # 0-100
    employee_count: int
    scheduled_count: int
    unscheduled_count: int
    critical_actions: List[CriticalActionItem]
    pending_responses: List[ReplacementRequestResponse]
    weekly_schedule_count: int
