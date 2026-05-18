"""
Complaint & Error Log Schemas - Request/Response Models

For Error & Complaint Log backend:
- Staff: Create complaints, view own complaints
- Owner: View all complaints across organization
- Manager: Manage complaints, assign staff, mark resolved, view dashboard
"""

from datetime import datetime
from enum import Enum
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, Field


# ===========================================================
# ENUMS
# ===========================================================

class ComplaintPriority(str, Enum):
    """Priority levels for complaints"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ComplaintStatus(str, Enum):
    """Status of complaints"""
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    RESOLVED = "resolved"
    ESCALATED = "escalated"
    CLOSED = "closed"


class ComplaintType(str, Enum):
    """Type of complaint/error/issue"""
    COMPLAINT = "complaint"
    ERROR = "error"
    HANDOVER = "handover"


class ComplaintCategory(str, Enum):
    """Category/Department for complaints"""
    MAINTENANCE = "maintenance"
    HOUSEKEEPING = "housekeeping"
    TECHNICAL = "technical"
    OPERATIONAL = "operational"
    SECURITY = "security"
    SAFETY = "safety"
    OTHER = "other"


class CommentType(str, Enum):
    """Internal or public comments"""
    PUBLIC = "public"
    INTERNAL = "internal"


# ===========================================================
# COMPLAINT COMMENT SCHEMAS
# ===========================================================

class ComplaintCommentCreate(BaseModel):
    """Create a comment on a complaint"""
    comment: str = Field(..., description="Comment text", min_length=1, max_length=2000)
    is_internal: bool = Field(default=False, description="Is this an internal note?")


class ComplaintCommentResponse(BaseModel):
    """Response model for complaint comments"""
    id: UUID
    complaint_id: UUID
    user_id: Optional[UUID]
    comment: str
    is_internal: bool
    created_at: datetime
    attachment_count: int
    
    class Config:
        from_attributes = True


# ===========================================================
# COMPLAINT ASSIGNMENT SCHEMAS
# ===========================================================

class ComplaintAssignmentCreate(BaseModel):
    """Assign complaint to staff"""
    assigned_to: UUID = Field(..., description="User ID to assign to")
    notes: Optional[str] = Field(None, description="Assignment notes", max_length=500)


class ComplaintAssignmentResponse(BaseModel):
    """Response model for complaint assignments"""
    id: UUID
    complaint_id: UUID
    assigned_to: UUID
    assigned_by: Optional[UUID]
    assigned_at: datetime
    completed_at: Optional[datetime]
    notes: Optional[str]
    
    class Config:
        from_attributes = True


# ===========================================================
# COMPLAINT ATTACHMENT SCHEMAS
# ===========================================================

class ComplaintAttachmentResponse(BaseModel):
    """Response model for attachments"""
    id: UUID
    complaint_id: UUID
    file_name: str
    file_path: str
    file_size: Optional[int]
    file_type: Optional[str]
    uploaded_by: Optional[UUID]
    created_at: datetime
    
    class Config:
        from_attributes = True


# ===========================================================
# MAIN COMPLAINT SCHEMAS
# ===========================================================

class ComplaintCreate(BaseModel):
    """Create a new complaint"""
    title: str = Field(..., description="Complaint title", min_length=5, max_length=255)
    description: str = Field(..., description="Detailed description", min_length=10, max_length=5000)
    category: ComplaintCategory = Field(..., description="Complaint category")
    complaint_type: ComplaintType = Field(default=ComplaintType.COMPLAINT, description="Type of issue")
    priority: ComplaintPriority = Field(default=ComplaintPriority.MEDIUM, description="Priority level")
    room_number: Optional[str] = Field(None, description="Room/Location number", max_length=50)
    location: Optional[str] = Field(None, description="Detailed location", max_length=255)


class ComplaintUpdate(BaseModel):
    """Update complaint details"""
    title: Optional[str] = Field(None, min_length=5, max_length=255)
    description: Optional[str] = Field(None, min_length=10, max_length=5000)
    category: Optional[ComplaintCategory] = None
    complaint_type: Optional[ComplaintType] = None
    priority: Optional[ComplaintPriority] = None
    room_number: Optional[str] = Field(None, max_length=50)
    location: Optional[str] = Field(None, max_length=255)


class ComplaintResolve(BaseModel):
    """Resolve/Close a complaint"""
    status: ComplaintStatus = Field(..., description="New status")
    resolution_notes: str = Field(..., description="Notes on resolution", min_length=10, max_length=2000)


class ComplaintResponse(BaseModel):
    """Response model for complaint - Basic info"""
    id: UUID
    tenant_id: UUID
    property_id: UUID
    
    title: str
    description: str
    category: str
    complaint_type: str
    priority: str
    status: str
    
    room_number: Optional[str]
    location: Optional[str]
    
    created_by: Optional[UUID]
    assigned_to: Optional[UUID]
    assigned_by: Optional[UUID]
    assigned_at: Optional[datetime]
    
    resolved_by: Optional[UUID]
    resolved_at: Optional[datetime]
    resolution_notes: Optional[str]
    
    created_at: datetime
    updated_at: datetime
    
    attachment_count: int
    comment_count: int
    
    class Config:
        from_attributes = True


class ComplaintDetailResponse(ComplaintResponse):
    """Detailed response with comments and assignments"""
    comments: List[ComplaintCommentResponse] = []
    assignments: List[ComplaintAssignmentResponse] = []
    attachments: List[ComplaintAttachmentResponse] = []


class ComplaintListResponse(BaseModel):
    """Response for complaint list view"""
    id: UUID
    title: str
    description: str
    category: str
    complaint_type: str
    priority: str
    status: str
    
    room_number: Optional[str]
    created_by: Optional[UUID]
    assigned_to: Optional[UUID]
    
    created_at: datetime
    resolved_at: Optional[datetime]
    
    attachment_count: int
    comment_count: int
    
    class Config:
        from_attributes = True


# ===========================================================
# DASHBOARD SCHEMAS
# ===========================================================

class ComplaintDashboardStats(BaseModel):
    """Statistics for dashboard"""
    total: int = Field(0, description="Total complaints")
    open: int = Field(0, description="Open complaints")
    in_progress: int = Field(0, description="In progress")
    resolved: int = Field(0, description="Resolved")
    escalated: int = Field(0, description="Escalated")
    
    total_critical: int = Field(0, description="Total critical priority")
    total_high: int = Field(0, description="Total high priority")


class ComplaintDashboardEvent(BaseModel):
    """Event for daily event dashboard"""
    id: UUID
    title: str
    description: str
    priority: str
    status: str
    complaint_type: str
    category: str
    room_number: Optional[str]
    created_at: datetime
    assigned_to: Optional[UUID]


class ComplaintDashboardNeedAttention(BaseModel):
    """High priority complaints needing urgent attention"""
    id: UUID
    title: str
    category: str
    complaint_type: str
    priority: str
    status: str
    room_number: Optional[str]
    
    created_by: Optional[UUID]
    assigned_to: Optional[UUID]
    created_at: datetime
    days_open: int


class ManagerDashboardData(BaseModel):
    """Manager Dashboard - Complete overview"""
    # Statistics
    total_complaints: int
    open_complaints: int
    in_progress_count: int
    resolved_today: int
    escalated_count: int
    
    # Breakdowns
    by_priority: dict = Field(default_factory=dict)  # {priority: count}
    by_status: dict = Field(default_factory=dict)    # {status: count}
    by_category: dict = Field(default_factory=dict)  # {category: count}
    by_type: dict = Field(default_factory=dict)      # {type: count}
    
    # Recent activities
    recent_complaints: List[ComplaintListResponse] = []
    need_attention: List[ComplaintDashboardNeedAttention] = []
    daily_events: List[ComplaintDashboardEvent] = []


class OwnerDashboardData(BaseModel):
    """Owner Dashboard - Overview of all complaints"""
    total_complaints: int
    total_critical: int
    total_high: int
    total_resolved: int
    resolution_rate: float  # Percentage
    
    by_property: dict = Field(default_factory=dict)
    by_category: dict = Field(default_factory=dict)
    by_status: dict = Field(default_factory=dict)
    
    critical_complaints: List[ComplaintListResponse] = []


class StaffDashboardData(BaseModel):
    """Staff Dashboard - Their complaints and assignments"""
    my_complaints_count: int
    pending_resolution: int
    resolved_by_me: int
    assigned_to_me: int
    
    my_complaints: List[ComplaintListResponse] = []
    complaints_assigned_to_me: List[ComplaintListResponse] = []


# ===========================================================
# FILTER & SEARCH SCHEMAS
# ===========================================================

class ComplaintFilterParams(BaseModel):
    """Filter parameters for complaint queries"""
    status: Optional[ComplaintStatus] = None
    priority: Optional[ComplaintPriority] = None
    category: Optional[ComplaintCategory] = None
    complaint_type: Optional[ComplaintType] = None
    assigned_to: Optional[UUID] = None
    created_by: Optional[UUID] = None
    date_from: Optional[datetime] = None
    date_to: Optional[datetime] = None
    room_number: Optional[str] = None
    search: Optional[str] = None  # Search in title/description


class BulkActionRequest(BaseModel):
    """Bulk action on multiple complaints"""
    complaint_ids: List[UUID] = Field(..., description="List of complaint IDs")
    action: str = Field(..., description="Action to perform (assign, resolve, escalate, close)")
    assigned_to: Optional[UUID] = Field(None, description="For assign action")
    status: Optional[ComplaintStatus] = Field(None, description="For status change")
    notes: Optional[str] = Field(None, description="Action notes")


class ExportRequest(BaseModel):
    """Request to export complaints"""
    format: str = Field(default="csv", description="Export format (csv, pdf, excel)")
    filters: ComplaintFilterParams = Field(default_factory=ComplaintFilterParams)
    include_fields: List[str] = Field(
        default=["id", "title", "category", "priority", "status", "created_at", "resolved_at"],
        description="Fields to include in export"
    )
