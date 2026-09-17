"""
Inbox Model - app/models/inbox.py

Cross-module "needs your attention" feed. Rows are written at the moment a
source event fires (write-at-source-event) — never computed on read. See
app/services/inbox_service.py for the write helpers and DEVELOPMENT_LOG.md
("Architecture Debt") for why SOP approvals and shift-replacement requests
are not yet wired as sources.

recipient_user_id / recipient_role are an either-or pair: a row targets one
specific person (e.g. a document reviewer) or a role-wide queue (e.g.
"manager" — visible to both Manager and Owner via role-hierarchy scoping in
the /inbox endpoint), matching how Complaints already scopes visibility.
status tracks the inbox item's own lifecycle only, independent of the
source record's status — some sources (inventory's LowStockAlert) have no
"resolved" write path of their own, so the inbox item must be dismissible
on its own.
"""

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, String, Text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin, UUIDMixin


class InboxItem(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "inbox_items"

    tenant_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)
    property_id: Mapped[Optional[uuid.UUID]] = mapped_column(PG_UUID(as_uuid=True), nullable=True, index=True)

    source_module: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    item_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    source_record_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)

    recipient_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(PG_UUID(as_uuid=True), nullable=True, index=True)
    recipient_role: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, index=True)

    title: Mapped[str] = mapped_column(String(255), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)

    status: Mapped[str] = mapped_column(String(20), nullable=False, default="unread", server_default="unread", index=True)
    read_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
