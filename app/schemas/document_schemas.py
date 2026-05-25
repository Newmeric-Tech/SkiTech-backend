"""
Document Management Schemas - app/schemas/document_schemas.py

Pydantic models for request/response validation
"""

from typing import List, Optional
from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, Field, ConfigDict
from enum import Enum


# ===========================================================
# ENUMS
# ===========================================================

class DocumentStatus(str, Enum):
    PENDING_REVIEW = "pending_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    ACTIVE = "active"
    ARCHIVED = "archived"


class ReviewStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    APPROVED = "approved"
    REJECTED = "rejected"


class ApprovalStatus(str, Enum):
    PENDING = "pending"
    AWAITING_APPROVAL = "awaiting_approval"
    APPROVED = "approved"
    REJECTED = "rejected"
    CONDITIONAL_APPROVAL = "conditional_approval"


class AccessScope(str, Enum):
    ORGANIZATION_WIDE = "organization_wide"
    DEPARTMENT = "department"
    PRIVATE = "private"


class PermissionLevel(str, Enum):
    VIEW = "view"
    COMMENT = "comment"
    EDIT = "edit"
    DOWNLOAD = "download"


class SignatureStatus(str, Enum):
    PENDING = "pending"
    SIGNED = "signed"
    REJECTED = "rejected"


# ===========================================================
# DOCUMENT UPLOAD & RESPONSE SCHEMAS
# ===========================================================

class DocumentUploadRequest(BaseModel):
    """Request model for uploading a document"""
    title: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    category: str = Field(..., min_length=1, max_length=100)
    department: Optional[str] = None
    tags: Optional[str] = None
    access_scope: AccessScope = AccessScope.ORGANIZATION_WIDE
    assigned_compliance_reviewer: Optional[UUID] = None
    is_confidential: bool = False
    retention_period: Optional[int] = None
    expiry_date: Optional[datetime] = None
    requires_signature: bool = False


class DocumentMetadataResponse(BaseModel):
    """Response model for document metadata"""
    id: UUID
    tenant_id: UUID
    property_id: Optional[UUID]
    title: str
    description: Optional[str]
    category: str
    department: Optional[str]
    file_name: str
    file_size: int
    file_type: str
    file_extension: str
    tags: Optional[str]
    access_scope: AccessScope
    status: DocumentStatus
    approval_status: ApprovalStatus
    upload_date: datetime
    last_modified: Optional[datetime]
    uploaded_by: Optional[UUID]
    owner_id: Optional[UUID]
    assigned_compliance_reviewer: Optional[UUID]
    is_confidential: bool
    retention_period: Optional[int]
    expiry_date: Optional[datetime]
    requires_signature: bool

    model_config = ConfigDict(from_attributes=True)


class DocumentDetailResponse(DocumentMetadataResponse):
    """Detailed document response with relations"""
    reviews: List['DocumentReviewResponse'] = []
    approvals: List['DocumentApprovalResponse'] = []
    versions: List['DocumentVersionResponse'] = []
    shares: List['DocumentShareResponse'] = []
    activity_logs: List['DocumentActivityLogResponse'] = []
    signatures: List['DocumentSignatureResponse'] = []


# ===========================================================
# DOCUMENT VERSION SCHEMAS
# ===========================================================

class DocumentVersionResponse(BaseModel):
    """Response model for document versions"""
    id: UUID
    document_id: UUID
    version_number: int
    file_size: int
    uploaded_by: Optional[UUID]
    change_description: Optional[str]
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ===========================================================
# DOCUMENT REVIEW SCHEMAS
# ===========================================================

class DocumentReviewRequest(BaseModel):
    """Request model for creating/updating a document review"""
    review_status: ReviewStatus
    comments: Optional[str] = None
    rejection_reason: Optional[str] = None
    requires_additional_info: bool = False
    additional_info_request: Optional[str] = None


class DocumentReviewResponse(BaseModel):
    """Response model for document reviews"""
    id: UUID
    document_id: UUID
    reviewer_id: Optional[UUID]
    reviewer_role: Optional[str]
    review_status: ReviewStatus
    review_priority: str
    comments: Optional[str]
    rejection_reason: Optional[str]
    assigned_at: datetime
    review_started_at: Optional[datetime]
    completed_at: Optional[datetime]
    requires_additional_info: bool
    additional_info_request: Optional[str]

    model_config = ConfigDict(from_attributes=True)


class AssignReviewerRequest(BaseModel):
    """Request model for assigning a reviewer"""
    reviewer_id: UUID
    review_priority: str = "medium"


# ===========================================================
# DOCUMENT APPROVAL SCHEMAS
# ===========================================================

class DocumentApprovalRequest(BaseModel):
    """Request model for approving/rejecting a document"""
    approval_status: ApprovalStatus
    approval_reason: Optional[str] = None
    conditions: Optional[dict] = None


class DocumentApprovalResponse(BaseModel):
    """Response model for document approvals"""
    id: UUID
    document_id: UUID
    approver_id: Optional[UUID]
    approver_role: Optional[str]
    approval_status: ApprovalStatus
    approval_reason: Optional[str]
    conditions: Optional[dict]
    assigned_at: datetime
    decided_at: Optional[datetime]

    model_config = ConfigDict(from_attributes=True)


class AssignApproverRequest(BaseModel):
    """Request model for assigning an approver"""
    approver_id: UUID
    approver_role: Optional[str] = None


# ===========================================================
# DOCUMENT SHARE SCHEMAS
# ===========================================================

class DocumentShareRequest(BaseModel):
    """Request model for sharing a document"""
    shared_with_user_id: Optional[UUID] = None
    shared_with_department_id: Optional[UUID] = None
    permission_level: PermissionLevel = PermissionLevel.VIEW
    expires_at: Optional[datetime] = None


class DocumentShareResponse(BaseModel):
    """Response model for document shares"""
    id: UUID
    document_id: UUID
    shared_with_user_id: Optional[UUID]
    shared_with_department_id: Optional[UUID]
    shared_by: Optional[UUID]
    permission_level: PermissionLevel
    shared_at: datetime
    expires_at: Optional[datetime]
    is_active: bool

    model_config = ConfigDict(from_attributes=True)


# ===========================================================
# DOCUMENT SIGNATURE SCHEMAS
# ===========================================================

class DocumentSignatureRequest(BaseModel):
    """Request model for requesting signatures"""
    signer_id: Optional[UUID] = None
    signer_name: str = Field(..., min_length=1)
    signer_email: str = Field(..., min_length=1)
    signer_role: Optional[str] = None


class DocumentSignatureSubmitRequest(BaseModel):
    """Request model for submitting a signature"""
    signature_image: str  # base64 encoded image


class DocumentSignatureDeclineRequest(BaseModel):
    """Request model for declining to sign"""
    decline_reason: str = Field(..., min_length=1)


class DocumentSignatureResponse(BaseModel):
    """Response model for document signatures"""
    id: UUID
    document_id: UUID
    signer_id: Optional[UUID]
    signer_name: str
    signer_email: str
    signer_role: Optional[str]
    signature_status: SignatureStatus
    signature_request_sent_at: Optional[datetime]
    signed_at: Optional[datetime]
    decline_reason: Optional[str]
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ===========================================================
# DOCUMENT ACTIVITY LOG SCHEMAS
# ===========================================================

class DocumentActivityLogResponse(BaseModel):
    """Response model for document activity logs"""
    id: UUID
    document_id: UUID
    action: str
    activity_type: str
    performed_by: Optional[UUID]
    performed_by_name: Optional[str]
    performed_by_role: Optional[str]
    details: Optional[dict]
    description: Optional[str]
    ip_address: Optional[str]
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ===========================================================
# DOCUMENT TEMPLATE SCHEMAS
# ===========================================================

class DocumentTemplateRequest(BaseModel):
    """Request model for creating/updating document templates"""
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    category: str = Field(..., min_length=1, max_length=100)
    template_content: str = Field(..., min_length=1)
    required_fields: Optional[list] = None


class DocumentTemplateResponse(BaseModel):
    """Response model for document templates"""
    id: UUID
    tenant_id: UUID
    name: str
    description: Optional[str]
    category: str
    template_content: str
    required_fields: Optional[list]
    usage_count: int
    is_active: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ===========================================================
# OPERATIONS & NOTIFICATIONS
# ===========================================================

class DocumentOperationResponse(BaseModel):
    """Response model for document operations"""
    success: bool
    message: str
    document_id: Optional[UUID] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class DocumentNotification(BaseModel):
    """Model for document-related notifications"""
    id: UUID
    user_id: UUID
    document_id: UUID
    action: str  # uploaded / reviewed / approved / shared / etc.
    message: str
    is_read: bool = False
    created_at: datetime


class DocumentStats(BaseModel):
    """Statistics for document dashboard"""
    total_files: int
    pending_reviews: int
    approved_docs: int
    rejected_docs: int
    recent_uploads: int
    shared_files: int
    total_size_gb: float


class DocumentSearchRequest(BaseModel):
    """Request model for document search"""
    query: Optional[str] = None
    category: Optional[str] = None
    status: Optional[DocumentStatus] = None
    department: Optional[str] = None
    uploaded_by: Optional[UUID] = None
    date_from: Optional[datetime] = None
    date_to: Optional[datetime] = None
    tags: Optional[List[str]] = None
    skip: int = 0
    limit: int = 20


class DocumentSearchResponse(BaseModel):
    """Response model for document search results"""
    total: int
    documents: List[DocumentMetadataResponse]
    skip: int
    limit: int


# Update forward references
DocumentDetailResponse.model_rebuild()
