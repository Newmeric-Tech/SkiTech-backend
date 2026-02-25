"""
Governance Schemas - Request & Response Models

Pydantic schemas for governance and workflow endpoints.
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class GovernanceWorkflowBase(BaseModel):
    """Base governance workflow schema"""

    name: str = Field(..., min_length=1, max_length=255)
    code: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = None


class GovernanceWorkflowCreate(GovernanceWorkflowBase):
    """Schema for workflow creation"""

    pass


class GovernanceWorkflowResponse(GovernanceWorkflowBase):
    """Schema for workflow response"""

    id: int
    is_active: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class WorkflowInstanceBase(BaseModel):
    """Base workflow instance schema"""

    workflow_id: int = Field(..., gt=0)
    request_type: str = Field(..., min_length=1, max_length=100)
    request_id: int = Field(..., gt=0)
    description: Optional[str] = None


class WorkflowInstanceCreate(WorkflowInstanceBase):
    """Schema for workflow instance creation"""

    requested_by_id: int = Field(..., gt=0)


class WorkflowInstanceApprove(BaseModel):
    """Schema for workflow approval"""

    approved: bool


class WorkflowInstanceReject(BaseModel):
    """Schema for workflow rejection"""

    rejection_reason: str = Field(..., min_length=1, max_length=500)


class WorkflowInstanceResponse(WorkflowInstanceBase):
    """Schema for workflow instance response"""

    id: int
    requested_by_id: int
    current_approver_id: Optional[int]
    status: str
    current_step: int
    rejection_reason: Optional[str]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
