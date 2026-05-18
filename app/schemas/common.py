"""Common schemas - app/schemas/common.py"""

from datetime import datetime
from typing import Generic, List, Optional, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class PaginatedResponse(BaseModel, Generic[T]):
    total: int
    skip: int
    limit: int
    items: List[T]


class ErrorResponse(BaseModel):
    error: str
    detail: Optional[str] = None
    status_code: int


class SuccessResponse(BaseModel, Generic[T]):
    success: bool = True
    data: T
    message: Optional[str] = None
