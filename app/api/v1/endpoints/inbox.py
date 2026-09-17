"""
Inbox Endpoints - app/api/v1/endpoints/inbox.py

Cross-module "needs your attention" feed. Items are written at the moment
a source event fires (see app/services/inbox_service.py) — this router
only reads/updates them, it never computes items from source tables live.

v1 sources: complaints (escalated) and inventory (low stock) only. SOP
approvals and shift-replacement requests are held back — see
DEVELOPMENT_LOG.md ("Architecture Debt") for why — but the shared list
endpoint and role-scoping below are written to take on new item_type /
source_module values without redesign once those sources are added.

Shared endpoint, filtered server-side by role, same shape as Complaints:
  owner   (Tenant Admin / Co Admin / Super Admin) -> sees "manager" and
          "owner" scoped items tenant-wide (Co Admin further scoped to
          their one property)
  manager -> sees "manager" scoped items for their own property
  staff   -> sees only items addressed to them personally
"""

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user
from app.core.database import get_db as get_db_session
from app.models.inbox import InboxItem
from app.schemas.common import PaginatedResponse
from app.schemas.inbox import InboxItemResponse, InboxUnreadCountResponse

router = APIRouter(prefix="/inbox", tags=["Inbox"])


async def get_inbox_context(user: dict = Depends(get_current_user)) -> dict:
    role = user.get("role", "")
    if role in ("Tenant Admin", "Co Admin", "Super Admin"):
        tier = "owner"
    elif role == "Manager":
        tier = "manager"
    else:
        tier = "staff"

    return {
        "tenant_id": UUID(user["tenant_id"]),
        "user_id": UUID(user["user_id"]),
        "role": role,
        "tier": tier,
        "property_id": UUID(user["property_id"]) if user.get("property_id") else None,
    }


def _scope_query(q, ctx: dict):
    q = q.where(InboxItem.tenant_id == ctx["tenant_id"])

    if ctx["tier"] == "owner":
        q = q.where(or_(
            InboxItem.recipient_role.in_(["manager", "owner"]),
            InboxItem.recipient_user_id == ctx["user_id"],
        ))
        # Co Admin is scoped to one property even though it inherits owner tier
        if ctx["property_id"]:
            q = q.where(InboxItem.property_id == ctx["property_id"])
    elif ctx["tier"] == "manager":
        q = q.where(or_(
            InboxItem.recipient_role == "manager",
            InboxItem.recipient_user_id == ctx["user_id"],
        ))
        if ctx["property_id"]:
            q = q.where(InboxItem.property_id == ctx["property_id"])
    else:
        q = q.where(InboxItem.recipient_user_id == ctx["user_id"])

    return q


async def _get_scoped_item(db: AsyncSession, item_id: UUID, ctx: dict) -> InboxItem:
    q = _scope_query(select(InboxItem), ctx).where(InboxItem.id == item_id)
    item = (await db.execute(q)).scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Inbox item not found")
    return item


@router.get("", response_model=PaginatedResponse[InboxItemResponse])
async def list_inbox_items(
    status_filter: Optional[str] = Query(None, alias="status"),
    source_module: Optional[str] = Query(None),
    item_type: Optional[str] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db_session),
    ctx: dict = Depends(get_inbox_context),
):
    q = _scope_query(select(InboxItem), ctx)

    if status_filter:
        q = q.where(InboxItem.status == status_filter)
    else:
        # Default view excludes dismissed items but still shows actioned ones
        # (actioned = resolved-but-visible, dismissed = manually cleared)
        q = q.where(InboxItem.status != "dismissed")

    if source_module:
        q = q.where(InboxItem.source_module == source_module)
    if item_type:
        q = q.where(InboxItem.item_type == item_type)

    total = (await db.execute(
        select(func.count()).select_from(q.order_by(None).subquery())
    )).scalar() or 0

    q = q.order_by(InboxItem.created_at.desc()).offset(skip).limit(limit)
    items = (await db.execute(q)).scalars().all()

    return PaginatedResponse(
        total=total, skip=skip, limit=limit,
        items=[InboxItemResponse.from_orm(i) for i in items],
    )


@router.get("/unread-count", response_model=InboxUnreadCountResponse)
async def unread_count(
    db: AsyncSession = Depends(get_db_session),
    ctx: dict = Depends(get_inbox_context),
):
    q = _scope_query(select(func.count()).select_from(InboxItem), ctx)
    q = q.where(InboxItem.status == "unread")
    count = (await db.execute(q)).scalar() or 0
    return InboxUnreadCountResponse(unread_count=count)


@router.put("/{item_id}/read", response_model=InboxItemResponse)
async def mark_read(
    item_id: UUID,
    db: AsyncSession = Depends(get_db_session),
    ctx: dict = Depends(get_inbox_context),
):
    from datetime import datetime

    item = await _get_scoped_item(db, item_id, ctx)
    if item.status == "unread":
        item.status = "read"
        item.read_at = datetime.utcnow()
        await db.commit()
        await db.refresh(item)
    return InboxItemResponse.from_orm(item)


@router.put("/{item_id}/actioned", response_model=InboxItemResponse)
async def mark_actioned(
    item_id: UUID,
    db: AsyncSession = Depends(get_db_session),
    ctx: dict = Depends(get_inbox_context),
):
    from datetime import datetime

    item = await _get_scoped_item(db, item_id, ctx)
    item.status = "actioned"
    if not item.read_at:
        item.read_at = datetime.utcnow()
    await db.commit()
    await db.refresh(item)
    return InboxItemResponse.from_orm(item)


@router.put("/{item_id}/dismiss", response_model=InboxItemResponse)
async def dismiss(
    item_id: UUID,
    db: AsyncSession = Depends(get_db_session),
    ctx: dict = Depends(get_inbox_context),
):
    """Manually clear an item that has no source-side resolution path
    (e.g. low-stock alerts — see DEVELOPMENT_LOG.md)."""
    item = await _get_scoped_item(db, item_id, ctx)
    item.status = "dismissed"
    await db.commit()
    await db.refresh(item)
    return InboxItemResponse.from_orm(item)
