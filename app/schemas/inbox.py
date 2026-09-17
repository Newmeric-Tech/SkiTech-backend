"""
Inbox Schemas - app/schemas/inbox.py
"""

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel


class InboxItemResponse(BaseModel):
    id: UUID
    tenant_id: UUID
    property_id: Optional[UUID]
    source_module: str
    item_type: str
    source_record_id: UUID
    recipient_user_id: Optional[UUID]
    recipient_role: Optional[str]
    title: str
    body: str
    status: str
    created_at: datetime
    read_at: Optional[datetime]

    class Config:
        from_attributes = True


class InboxUnreadCountResponse(BaseModel):
    unread_count: int
