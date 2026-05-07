"""
All Pydantic schemas - app/schemas/schemas.py
"""

from datetime import datetime
from enum import Enum
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field, field_validator


# ===========================================================
# AUTH / USER
# ===========================================================

class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8)
    role: str = "Staff"  # Default role - users can only register as Staff or Manager, not as Tenant Admin
    tenant_id: UUID

    @field_validator("role")
    @classmethod
    def validate_role(cls, v: str) -> str:
        # Only allow Staff and Manager for self-registration
        # Tenant Admin and Super Admin must be assigned by administrators
        if v not in ["Staff", "Manager"]:
            raise ValueError(f"Role '{v}' cannot be self-assigned. Contact your administrator.")
        return v

    @field_validator("password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        if not any(c.isupper() for c in v):
            raise ValueError("Password must have at least one uppercase letter")
        if not any(c.islower() for c in v):
            raise ValueError("Password must have at least one lowercase letter")
        if not any(c.isdigit() for c in v):
            raise ValueError("Password must have at least one digit")
        return v


class LoginRequest(BaseModel):
    email: EmailStr
    password: str
    expected_role: Optional[str] = None

class OTPVerifyRequest(BaseModel):
    email: EmailStr
    otp: str


class RefreshTokenRequest(BaseModel):
    refresh_token: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class PasswordResetRequest(BaseModel):
    email: EmailStr


class PasswordResetConfirm(BaseModel):
    email: EmailStr
    otp: str
    new_password: str = Field(..., min_length=8)

class SuperAdminLoginRequest(BaseModel):
    email: EmailStr
    password: str

# ===========================================================
# PROPERTY
# ===========================================================

class PropertyCreate(BaseModel):
    name: str
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    country: Optional[str] = None
    postal_code: Optional[str] = None
    franchise_type: Optional[str] = "owner-operated"
    num_rooms: Optional[int] = None
    has_restaurant: Optional[bool] = False


class PropertyUpdate(BaseModel):
    name: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    country: Optional[str] = None
    postal_code: Optional[str] = None
    franchise_type: Optional[str] = None
    num_rooms: Optional[int] = None
    has_restaurant: Optional[bool] = None
    is_active: Optional[bool] = None


class PropertyResponse(BaseModel):
    id: UUID
    tenant_id: UUID
    name: str
    address: Optional[str]
    city: Optional[str]
    state: Optional[str]
    country: Optional[str]
    postal_code: Optional[str]
    franchise_type: Optional[str]
    num_rooms: Optional[int]
    has_restaurant: Optional[bool]
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True


# ===========================================================
# OWNER DETAILS
# ===========================================================

class OwnerDetailsCreate(BaseModel):
    owner_name: str
    phone: Optional[str] = None
    email: Optional[str] = None
    address: Optional[str] = None
    ownership_type: Optional[str] = None


class OwnerDetailsUpdate(BaseModel):
    owner_name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    address: Optional[str] = None
    ownership_type: Optional[str] = None


class OwnerDetailsResponse(BaseModel):
    id: UUID
    tenant_id: UUID
    property_id: UUID
    owner_name: str
    phone: Optional[str]
    email: Optional[str]
    address: Optional[str]
    ownership_type: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


# ===========================================================
# DEPARTMENT
# ===========================================================

class DepartmentCreate(BaseModel):
    name: str
    description: Optional[str] = None


class DepartmentUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None


class DepartmentResponse(BaseModel):
    id: UUID
    tenant_id: UUID
    property_id: UUID
    name: str
    description: Optional[str]
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True


# ===========================================================
# EMPLOYEE
# ===========================================================

class EmployeeCreate(BaseModel):
    first_name: str
    last_name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    employee_code: Optional[str] = None
    role_id: UUID
    department_id: Optional[UUID] = None
    position: Optional[str] = None
    start_date: Optional[datetime] = None


class EmployeeUpdate(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    department_id: Optional[UUID] = None
    position: Optional[str] = None
    is_active: Optional[bool] = None
    end_date: Optional[datetime] = None


class EmployeeResponse(BaseModel):
    id: UUID
    tenant_id: UUID
    property_id: UUID
    first_name: str
    last_name: str
    email: Optional[str]
    phone: Optional[str]
    employee_code: Optional[str]
    position: Optional[str]
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True


# ===========================================================
# VENDOR
# ===========================================================

class VendorCreate(BaseModel):
    name: str
    contact_person: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    address: Optional[str] = None


class VendorUpdate(BaseModel):
    name: Optional[str] = None
    contact_person: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    address: Optional[str] = None
    is_active: Optional[bool] = None


class VendorResponse(BaseModel):
    id: UUID
    tenant_id: UUID
    property_id: UUID
    name: str
    contact_person: Optional[str]
    phone: Optional[str]
    email: Optional[str]
    address: Optional[str]
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True


# ===========================================================
# INVENTORY
# ===========================================================

class InventoryCreate(BaseModel):
    item_name: str
    quantity: int = 0
    unit: Optional[str] = None
    reorder_level: Optional[int] = None
    department_id: Optional[UUID] = None


class InventoryUpdate(BaseModel):
    item_name: Optional[str] = None
    unit: Optional[str] = None
    reorder_level: Optional[int] = None
    department_id: Optional[UUID] = None


class InventoryResponse(BaseModel):
    id: UUID
    tenant_id: UUID
    property_id: UUID
    item_name: str
    quantity: int
    unit: Optional[str]
    reorder_level: Optional[int]
    department_id: Optional[UUID]
    created_at: datetime

    class Config:
        from_attributes = True


class StockAdjustRequest(BaseModel):
    quantity: int = Field(..., gt=0)
    notes: Optional[str] = None
    vendor_id: Optional[UUID] = None
    department_id: Optional[UUID] = None


class AdjustStockRequest(BaseModel):
    new_quantity: int = Field(..., ge=0)
    notes: Optional[str] = None


# ===========================================================
# SOP
# ===========================================================

class PriorityEnum(str, Enum):
    low = "low"
    medium = "medium"
    high = "high"


class StatusEnum(str, Enum):
    pending = "pending"
    in_progress = "in_progress"
    completed = "completed"


class SOPCategoryCreate(BaseModel):
    name: str
    description: Optional[str] = None


class SOPCategoryResponse(BaseModel):
    id: UUID
    tenant_id: UUID
    property_id: UUID
    name: str
    description: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


class SOPCreate(BaseModel):
    category_id: UUID
    title: str
    description: Optional[str] = None
    assigned_employee_id: Optional[UUID] = None
    assigned_user_id: Optional[UUID] = None
    department_id: Optional[UUID] = None
    priority: PriorityEnum = PriorityEnum.medium
    status: StatusEnum = StatusEnum.pending
    due_date: Optional[datetime] = None


class SOPUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    assigned_employee_id: Optional[UUID] = None
    assigned_user_id: Optional[UUID] = None
    department_id: Optional[UUID] = None
    priority: Optional[PriorityEnum] = None
    status: Optional[StatusEnum] = None
    due_date: Optional[datetime] = None


class SOPResponse(BaseModel):
    id: UUID
    tenant_id: UUID
    property_id: UUID
    category_id: UUID
    title: str
    description: Optional[str]
    priority: str
    status: str
    due_date: Optional[datetime]
    assigned_user_id: Optional[UUID] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class SOPExecutionResponse(BaseModel):
    id: UUID
    sop_id: UUID
    user_id: UUID
    property_id: UUID
    tenant_id: UUID
    status: str
    completed_at: Optional[datetime] = None
    proof_image: Optional[str] = None
    proof_submitted_at: Optional[datetime] = None
    proof_location_lat: Optional[float] = None
    proof_location_lng: Optional[float] = None
    proof_location_name: Optional[str] = None
    rejection_reason: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class SOPVersionCreate(BaseModel):
    content: str
    version_number: int


class SOPVersionResponse(BaseModel):
    id: UUID
    sop_item_id: UUID
    version_number: int
    content: str
    created_at: datetime

    class Config:
        from_attributes = True


# ===========================================================
# GOVERNANCE
# ===========================================================

class WorkflowCreate(BaseModel):
    name: str
    code: str
    description: Optional[str] = None


class WorkflowResponse(BaseModel):
    id: UUID
    name: str
    code: str
    description: Optional[str]
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True


class WorkflowInstanceCreate(BaseModel):
    workflow_id: UUID
    request_type: str
    request_id: UUID
    description: Optional[str] = None


class WorkflowInstanceResponse(BaseModel):
    id: UUID
    workflow_id: UUID
    request_type: str
    status: str
    current_step: int
    rejection_reason: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


class WorkflowRejectRequest(BaseModel):
    reason: str = Field(..., min_length=1)

# ===========================================================
# USERS
# ===========================================================

class UserResponse(BaseModel):
    id: UUID
    email: str
    first_name: Optional[str]
    last_name: Optional[str]
    phone_number: Optional[str]
    role_id: UUID
    tenant_id: UUID
    property_id: Optional[UUID]
    is_active: bool
    is_verified: bool
    last_login: Optional[datetime]
    created_at: datetime

    class Config:
        from_attributes = True


class UserUpdate(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    phone_number: Optional[str] = None
    property_id: Optional[UUID] = None


class UserRoleUpdate(BaseModel):
    role_id: UUID


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(..., min_length=8)

    @field_validator("new_password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        if not any(c.isupper() for c in v):
            raise ValueError("Password must have at least one uppercase letter")
        if not any(c.islower() for c in v):
            raise ValueError("Password must have at least one lowercase letter")
        if not any(c.isdigit() for c in v):
            raise ValueError("Password must have at least one digit")
        return v


class UserInviteRequest(BaseModel):
    email: EmailStr
    role: str = "Staff"
    property_id: Optional[UUID] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None

# ===========================================================
# STATS / DASHBOARD
# ===========================================================

# ── Shared ──────────────────────────────────────────────────

class WeeklyTaskDay(BaseModel):
    day: str
    done: int
    total: int


class RevenueDay(BaseModel):
    day: str
    revenue: float


class AlertItem(BaseModel):
    type: str          # "low_stock" | "late_checkin" | "maintenance" | "shift"
    title: str
    property_name: str
    time_ago: str
    severity: str      # "warning" | "info" | "success"


class TaskItem(BaseModel):
    id: UUID
    task: str
    assignee: str
    due: str
    status: str        # "done" | "pending" | "upcoming"


class StaffAttendanceItem(BaseModel):
    name: str
    dept: str
    check_in: Optional[str]
    status: str        # "in" | "absent"
    initials: str


# ── Owner Stats ──────────────────────────────────────────────

class OwnerStatsResponse(BaseModel):
    total_properties: int
    total_staff: int
    daily_revenue: float
    pending_tasks: int
    overdue_tasks: int
    revenue_trend: List[RevenueDay]
    recent_alerts: List[AlertItem]

    class Config:
        from_attributes = True


# ── Manager Stats ────────────────────────────────────────────

class ManagerStatsResponse(BaseModel):
    staff_present: int
    staff_total: int
    tasks_pending: int
    tasks_overdue: int
    checkins_today: int
    daily_revenue: float
    todays_tasks: List[TaskItem]
    staff_attendance: List[StaffAttendanceItem]
    weekly_tasks: List[WeeklyTaskDay]

    class Config:
        from_attributes = True


# ── Staff Stats ──────────────────────────────────────────────

class StaffStatsResponse(BaseModel):
    shift_hours: float
    my_tasks_today: int
    my_tasks_overdue: int
    completed_this_week: int
    pending_sops: int
    todays_tasks: List[TaskItem]
    weekly_performance: List[WeeklyTaskDay]

    class Config:
        from_attributes = True

# ===========================================================
# REPORTS
# ===========================================================

class OccupancyReport(BaseModel):
    property_id: UUID
    property_name: str
    total_rooms: int
    occupied_rooms: int
    available_rooms: int
    occupancy_percentage: float
    maintenance_rooms: int

    class Config:
        from_attributes = True


class OccupancyReportResponse(BaseModel):
    period: str
    reports: List[OccupancyReport]


class AuditLogResponse(BaseModel):
    id: UUID
    tenant_id: Optional[UUID]
    user_id: Optional[UUID]
    user_email: Optional[str]
    action: str
    resource_type: str
    resource_id: Optional[str]
    details: Optional[str]
    severity: str
    status: str
    ip_address: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


class AuditReportResponse(BaseModel):
    total: int
    page: int
    limit: int
    logs: List[AuditLogResponse]

# ===========================================================
# ROOMS & BOOKINGS
# ===========================================================

class RoomStatusEnum(str, Enum):
    available = "available"
    occupied = "occupied"
    maintenance = "maintenance"


class BookingStatusEnum(str, Enum):
    booked = "booked"
    checked_in = "checked_in"
    completed = "completed"
    cancelled = "cancelled"


class RoomCreate(BaseModel):
    room_number: str
    room_type: Optional[str] = None
    price_per_night: Optional[float] = None
    status: RoomStatusEnum = RoomStatusEnum.available


class RoomUpdate(BaseModel):
    room_number: Optional[str] = None
    room_type: Optional[str] = None
    price_per_night: Optional[float] = None
    status: Optional[RoomStatusEnum] = None


class RoomResponse(BaseModel):
    id: UUID
    tenant_id: UUID
    property_id: UUID
    room_number: str
    room_type: Optional[str]
    price_per_night: Optional[float]
    status: str
    created_at: datetime

    class Config:
        from_attributes = True


class BookingCreate(BaseModel):
    room_id: UUID
    customer_name: Optional[str] = None
    customer_phone: Optional[str] = None
    check_in: datetime
    check_out: datetime
    total_amount: Optional[float] = None

    @field_validator("check_out", mode="after")
    @classmethod
    def check_out_after_check_in(cls, v, info):
        check_in = info.data.get("check_in")
        if check_in and v <= check_in:
            raise ValueError("check_out must be after check_in")
        return v


class BookingUpdate(BaseModel):
    customer_name: Optional[str] = None
    customer_phone: Optional[str] = None
    check_in: Optional[datetime] = None
    check_out: Optional[datetime] = None
    total_amount: Optional[float] = None
    status: Optional[BookingStatusEnum] = None


class BookingResponse(BaseModel):
    id: UUID
    tenant_id: UUID
    property_id: UUID
    room_id: UUID
    customer_name: Optional[str]
    customer_phone: Optional[str]
    check_in: datetime
    check_out: datetime
    total_amount: Optional[float]
    status: str
    created_at: datetime

    class Config:
        from_attributes = True

