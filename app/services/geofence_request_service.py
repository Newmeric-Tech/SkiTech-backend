"""
Geofence change requests - app/services/geofence_request_service.py

A Manager proposes a punch location (centre + radius) for their property;
Super Admin / Tenant Admin / Co Admin approve or reject it. Approval
writes property_geofences in the same transaction. The live geofence is
never touched by a request until it is approved.

Rules:
- One pending request per property: a new request replaces the pending
  one (marked cancelled, "Replaced by a newer request"); a concurrent
  second submit hits the partial unique index and gets RequestConflict.
- Only pending requests can be reviewed or cancelled (RequestConflict).
- Nobody reviews their own request (RequestForbidden); the requester can
  cancel it instead.
- Out-of-scope ids behave as missing (RequestNotFound / PropertyNotInScope).
"""
from datetime import datetime, timezone
from typing import Dict, Iterable, List, Optional, Tuple
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.attendance import GeofenceChangeRequest, PropertyGeofence
from app.models.models import Property, User
from app.schemas.attendance import GeofenceChangeRequestCreate
from app.services.geofence_scope import (
    assigned_property, caller_tenant, property_in_scope, still_geofence_admin,
)
from app.services.inbox_service import create_inbox_item, mark_inbox_items_actioned

REQUEST_ROLES = ("Super Admin", "Tenant Admin", "Co Admin", "Manager")
PENDING = "pending"

# Inbox (app/services/inbox_service.py): one item per pending request,
# addressed to the owner tier (Tenant Admin / Co Admin / Super Admin; a
# property-scoped Co Admin only sees their property's), flipped to
# "actioned" once the request is approved, rejected, cancelled or replaced.
INBOX_MODULE = "attendance"
INBOX_ITEM_TYPE = "geofence_change_request"


async def _close_inbox_item(db: AsyncSession, request: "GeofenceChangeRequest") -> None:
    await mark_inbox_items_actioned(
        db, tenant_id=request.tenant_id, source_record_id=request.id, item_type=INBOX_ITEM_TYPE)


class RequestNotFound(LookupError):
    pass


class RequestConflict(Exception):
    pass


class RequestForbidden(Exception):
    pass


def _user_id(user: dict) -> UUID:
    return UUID(str(user["user_id"]))


async def create_request(
    db: AsyncSession, user: dict, data: GeofenceChangeRequestCreate
) -> GeofenceChangeRequest:
    property_id = await property_in_scope(db, data.property_id, user)
    tenant_id = caller_tenant(user)
    requester = _user_id(user)
    now = datetime.now(timezone.utc)

    pending = (await db.execute(
        select(GeofenceChangeRequest).where(
            GeofenceChangeRequest.tenant_id == tenant_id,
            GeofenceChangeRequest.property_id == property_id,
            GeofenceChangeRequest.status == PENDING,
        ).with_for_update()
    )).scalars().all()
    for old in pending:
        old.status = "cancelled"
        old.reviewed_by = requester
        old.reviewed_at = now
        old.review_note = "Replaced by a newer request"
        await _close_inbox_item(db, old)
    # The cancel must reach the partial unique index before the new row does
    await db.flush()

    request = GeofenceChangeRequest(
        id=uuid4(), tenant_id=tenant_id, property_id=property_id, requested_by=requester,
        center_lat=data.center_lat, center_lng=data.center_lng, radius_meters=data.radius_meters,
        address=data.address, note=data.note, status=PENDING, created_at=now,
    )
    db.add(request)
    await create_inbox_item(
        db,
        tenant_id=tenant_id,
        property_id=property_id,
        source_module=INBOX_MODULE,
        item_type=INBOX_ITEM_TYPE,
        source_record_id=request.id,
        recipient_role="owner",
        title="Punch location change requested",
        body=(f"New punch location proposed: {data.center_lat:.6f}, {data.center_lng:.6f}, "
              f"radius {data.radius_meters} m. It takes effect only after you approve it."),
    )
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise RequestConflict(
            "Another change request for this property was just submitted. Reload and try again."
        )
    await db.refresh(request)
    return request


async def list_requests(
    db: AsyncSession, user: dict, status: Optional[str] = None, property_id: Optional[UUID] = None,
    limit: int = 100,
) -> List[GeofenceChangeRequest]:
    tenant_id = caller_tenant(user)
    if tenant_id is None:
        return []
    q = select(GeofenceChangeRequest).where(GeofenceChangeRequest.tenant_id == tenant_id)
    if user.get("role") == "Manager":
        q = q.where(GeofenceChangeRequest.requested_by == _user_id(user))
    else:
        limited_to = assigned_property(user)  # property-scoped Co Admin
        if limited_to is not None:
            q = q.where(GeofenceChangeRequest.property_id == limited_to)
    if status:
        q = q.where(GeofenceChangeRequest.status == status)
    if property_id is not None:
        q = q.where(GeofenceChangeRequest.property_id == property_id)
    q = q.order_by(GeofenceChangeRequest.created_at.desc(), GeofenceChangeRequest.id).limit(limit)
    return list((await db.execute(q)).scalars().all())


async def _get_for_update(db: AsyncSession, request_id: UUID, user: dict) -> GeofenceChangeRequest:
    tenant_id = caller_tenant(user)
    request = tenant_id and (await db.execute(
        select(GeofenceChangeRequest).where(
            GeofenceChangeRequest.id == request_id,
            GeofenceChangeRequest.tenant_id == tenant_id,
        ).with_for_update()
    )).scalar_one_or_none()
    if not request:
        raise RequestNotFound()
    limited_to = assigned_property(user)
    if user.get("role") != "Manager" and limited_to is not None and limited_to != request.property_id:
        raise RequestNotFound()
    return request


ROLE_CHANGED = "Your role no longer allows reviewing location requests. Sign in again."


def _ensure_reviewable(request: GeofenceChangeRequest, reviewer: UUID) -> None:
    if request.status != PENDING:
        raise RequestConflict(f"This request is already {request.status}.")
    if request.requested_by == reviewer:
        raise RequestForbidden("You can't review your own request. Cancel it instead, or ask another admin.")


def _close(request: GeofenceChangeRequest, status: str, reviewer: UUID, note: Optional[str]) -> None:
    request.status = status
    request.reviewed_by = reviewer
    request.reviewed_at = datetime.now(timezone.utc)
    request.review_note = note


async def approve_request(
    db: AsyncSession, user: dict, request_id: UUID, review_note: Optional[str] = None
) -> Tuple[GeofenceChangeRequest, PropertyGeofence]:
    """Apply the proposed location to the live geofence (created if missing)
    and close the request, in one transaction."""
    request = await _get_for_update(db, request_id, user)
    reviewer = _user_id(user)
    _ensure_reviewable(request, reviewer)
    if not await still_geofence_admin(db, user):
        raise RequestForbidden(ROLE_CHANGED)

    live = (await db.execute(
        select(Property.id).where(
            Property.id == request.property_id,
            Property.tenant_id == request.tenant_id,
            Property.deleted_at == None,
        )
    )).scalar_one_or_none()
    if live is None:
        raise RequestConflict("This property has been deleted; the request can only be rejected.")

    geofence = (await db.execute(
        select(PropertyGeofence).where(
            PropertyGeofence.property_id == request.property_id,
            PropertyGeofence.tenant_id == request.tenant_id,
        ).with_for_update()
    )).scalar_one_or_none()
    if geofence is None:
        geofence = PropertyGeofence(id=uuid4(), tenant_id=request.tenant_id, property_id=request.property_id,
                                    center_lat=request.center_lat, center_lng=request.center_lng,
                                    radius_meters=request.radius_meters, address=request.address,
                                    alert_on_breach=True)
        db.add(geofence)
    else:
        geofence.center_lat = request.center_lat
        geofence.center_lng = request.center_lng
        geofence.radius_meters = request.radius_meters
        if request.address:
            geofence.address = request.address
    _close(request, "approved", reviewer, review_note)
    await _close_inbox_item(db, request)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise RequestConflict("The punch location changed at the same time. Reload and try again.")
    await db.refresh(request)
    await db.refresh(geofence)
    return request, geofence


async def reject_request(
    db: AsyncSession, user: dict, request_id: UUID, review_note: Optional[str] = None
) -> GeofenceChangeRequest:
    request = await _get_for_update(db, request_id, user)
    _ensure_reviewable(request, _user_id(user))
    if not await still_geofence_admin(db, user):
        raise RequestForbidden(ROLE_CHANGED)
    _close(request, "rejected", _user_id(user), review_note)
    await _close_inbox_item(db, request)
    await db.commit()
    await db.refresh(request)
    return request


async def cancel_request(db: AsyncSession, user: dict, request_id: UUID) -> GeofenceChangeRequest:
    request = await _get_for_update(db, request_id, user)
    requester = _user_id(user)
    if request.requested_by != requester:
        raise RequestForbidden("Only the person who made the request can cancel it.")
    if request.status != PENDING:
        raise RequestConflict(f"This request is already {request.status}.")
    _close(request, "cancelled", requester, None)
    await _close_inbox_item(db, request)
    await db.commit()
    await db.refresh(request)
    return request


async def names_for(db: AsyncSession, requests: Iterable[GeofenceChangeRequest]) -> Tuple[Dict, Dict]:
    """(user id -> full name, property id -> name) for the given requests."""
    requests = list(requests)
    user_ids = {u for r in requests for u in (r.requested_by, r.reviewed_by) if u}
    property_ids = {r.property_id for r in requests}
    users, props = {}, {}
    if user_ids:
        for row in (await db.execute(
            select(User.id, User.first_name, User.last_name).where(User.id.in_(user_ids))
        )).all():
            users[row.id] = " ".join(filter(None, [row.first_name, row.last_name])) or None
    if property_ids:
        for row in (await db.execute(
            select(Property.id, Property.name).where(Property.id.in_(property_ids))
        )).all():
            props[row.id] = row.name
    return users, props
