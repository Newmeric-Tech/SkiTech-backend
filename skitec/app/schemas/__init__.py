"""
Schemas Module - Initialization

Exports all Pydantic schemas for API validation.
"""

from app.schemas.common import (
    ErrorResponse,
    PaginatedResponse,
    PaginationParams,
    SuccessResponse,
    TimestampedModel,
)
from app.schemas.governance import (
    GovernanceWorkflowCreate,
    GovernanceWorkflowResponse,
    WorkflowInstanceApprove,
    WorkflowInstanceCreate,
    WorkflowInstanceReject,
    WorkflowInstanceResponse,
)
from app.schemas.property import (
    PropertyCreate,
    PropertyResponse,
    PropertySummary,
    PropertyUpdate,
)
from app.schemas.user import (
    LoginRequest,
    RefreshTokenRequest,
    TokenResponse,
    UserCreate,
    UserResponse,
    UserUpdate,
)
from app.schemas.workforce import (
    WorkforceCreate,
    WorkforceSummary,
    WorkforceUpdate,
    WorkforceResponse,
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
]
