"""
Common Schemas

Shared Pydantic schemas used across multiple endpoints.
"""

from datetime import datetime
from typing import Generic, Optional, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class PaginationParams(BaseModel):
    """Query parameters for paginated responses"""

    skip: int = Field(default=0, ge=0)
    limit: int = Field(default=20, ge=1, le=100)


class PaginatedResponse(BaseModel, Generic[T]):
    """Generic paginated response wrapper"""

    total: int
    skip: int
    limit: int
    items: list[T]


class TimestampedModel(BaseModel):
    """Base model with timestamp fields for responses"""

    created_at: datetime
    updated_at: datetime


class ErrorResponse(BaseModel):
    """Standard error response format"""

    error: str
    detail: Optional[str] = None
    status_code: int


class SuccessResponse(BaseModel, Generic[T]):
    """Standard success response wrapper"""

    success: bool = True
    data: T
    message: Optional[str] = None