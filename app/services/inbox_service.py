"""
Inbox Service - app/services/inbox_service.py

Write-at-source-event helpers for the inbox_items feed. Source services
(ComplaintService, inventory's _record_movement, and — once their frontend
gaps close — SOP/Scheduling) call these instead of constructing InboxItem
rows directly, so creation dedup and "flip to actioned" logic live in one
place.

Callers are expected to commit as part of their own existing transaction —
these helpers only `db.add()` / mutate in-session objects.
"""

from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.inbox import InboxItem


async def create_inbox_item(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    property_id: Optional[UUID],
    source_module: str,
    item_type: str,
    source_record_id: UUID,
    title: str,
    body: str,
    recipient_user_id: Optional[UUID] = None,
    recipient_role: Optional[str] = None,
) -> Optional[InboxItem]:
    """
    Create an inbox item for a source event, unless an open (unread/read)
    item already exists for this exact source_record_id + item_type.

    The dedup check exists because upstream source tables don't dedup
    themselves — e.g. LowStockAlert gets a new row on every stock movement
    that leaves an item under its reorder level, even if the previous
    alert was never resolved. Without this check, Inbox would accumulate
    duplicate entries for the same underlying condition.
    """
    existing = (await db.execute(
        select(InboxItem.id).where(
            InboxItem.tenant_id == tenant_id,
            InboxItem.source_record_id == source_record_id,
            InboxItem.item_type == item_type,
            InboxItem.status.in_(["unread", "read"]),
        )
    )).scalar_one_or_none()
    if existing:
        return None

    item = InboxItem(
        tenant_id=tenant_id,
        property_id=property_id,
        source_module=source_module,
        item_type=item_type,
        source_record_id=source_record_id,
        recipient_user_id=recipient_user_id,
        recipient_role=recipient_role,
        title=title,
        body=body,
        status="unread",
    )
    db.add(item)
    return item


async def mark_inbox_items_actioned(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    source_record_id: UUID,
    item_type: Optional[str] = None,
) -> None:
    """Flip any open inbox items pointing at this source record to actioned."""
    q = select(InboxItem).where(
        InboxItem.tenant_id == tenant_id,
        InboxItem.source_record_id == source_record_id,
        InboxItem.status.in_(["unread", "read"]),
    )
    if item_type:
        q = q.where(InboxItem.item_type == item_type)

    result = await db.execute(q)
    for item in result.scalars().all():
        item.status = "actioned"
