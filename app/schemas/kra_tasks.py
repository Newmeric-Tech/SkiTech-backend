"""
Pydantic schemas for assigned KRA tasks - app/schemas/kra_tasks.py
"""
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, List, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

Frequency = Literal["daily", "weekly", "monthly", "quarterly"]
DisplayStatus = Literal["pending", "delayed", "completed", "completed_delayed"]


class _Input(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class DefinitionCreate(_Input):
    property_id: UUID
    title: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = None
    frequency: Frequency
    value_label: Optional[str] = Field(None, min_length=1, max_length=100)


class DefinitionUpdate(_Input):
    title: str = Field(None, min_length=1, max_length=200)
    description: Optional[str] = None
    value_label: Optional[str] = Field(None, min_length=1, max_length=100)
    is_active: bool = None
    frequency: Frequency = None   # only while the task has never been assigned


class DefinitionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    property_id: UUID
    title: str
    description: Optional[str] = None
    frequency: Frequency
    value_label: Optional[str] = None
    created_by: Optional[UUID] = None
    is_active: bool
    created_at: datetime
    updated_at: datetime


class AssignRequest(_Input):
    user_ids: List[UUID] = Field(..., min_length=1, max_length=200)
    today: date


class AssignmentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    property_id: UUID
    definition_id: UUID
    assignee_id: UUID
    assignee_name: Optional[str] = None
    assigned_by: Optional[UUID] = None
    start_date: date
    is_active: bool
    ended_at: Optional[datetime] = None


class AssignResponse(BaseModel):
    created: List[AssignmentResponse]
    skipped_user_ids: List[UUID]   # already actively assigned


class OccurrenceDelay(_Input):
    reason: Optional[str] = None


class OccurrenceComplete(_Input):
    note: Optional[str] = None
    value: Optional[Annotated[Decimal, Field(ge=0, max_digits=14, decimal_places=2)]] = None


class OccurrenceResponse(BaseModel):
    id: UUID
    tenant_id: UUID
    property_id: UUID
    assignment_id: UUID
    definition_id: UUID
    assignee_id: UUID
    assignee_name: Optional[str] = None
    title: str
    description: Optional[str] = None
    frequency: Frequency
    value_label: Optional[str] = None
    period_start: date
    period_end: date
    status: Literal["pending", "delayed", "completed"]
    display_status: DisplayStatus
    was_delayed: bool
    delayed_at: Optional[datetime] = None
    delay_reason: Optional[str] = None
    completed_at: Optional[datetime] = None
    completion_note: Optional[str] = None
    completion_value: Optional[float] = None
    created_at: datetime
    updated_at: datetime


class OccurrencePage(BaseModel):
    items: List[OccurrenceResponse]
    total: int
    skip: int
    limit: int


class SummaryCounts(BaseModel):
    pending: int
    delayed: int
    completed: int              # includes completed_with_delay
    completed_with_delay: int
    total: int


class FrequencySummary(SummaryCounts):
    frequency: Frequency


class SummaryResponse(BaseModel):
    property_id: Optional[UUID] = None   # None = the caller's whole tenant
    period_from: Optional[date] = None
    period_to: Optional[date] = None
    by_frequency: List[FrequencySummary]
    totals: SummaryCounts
