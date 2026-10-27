"""
Missed punch-out corrections - app/services/attendance_correction_service.py

A shift auto-closed for a missing punch-out (status auto_closed, hours
NULL) can be corrected: its owner claims when they left (after the
punch-in, at most STALE_SHIFT_HOURS later, not in the future) with a
reason; a reviewer approves or rejects. Approval completes the record
with hours from the approved time, in the same transaction.

Reviewers: a Staff member's request -> a Manager of that property, or
Super Admin / Tenant Admin / Co Admin; anyone else's -> those admins only.
Nobody reviews their own request, and the reviewer's current role is
re-checked (the token's may be stale). One pending request per record:
a new one replaces the pending one. Rows are never deleted.
"""
from datetime import datetime, timedelta, timezone
from typing import Dict, Iterable, List, Optional, Tuple
from uuid import UUID, uuid4

from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.attendance import AttendanceCorrectionRequest, AttendanceRecord
from app.models.models import Property, User
from app.schemas.attendance import AttendanceCorrectionCreate
from app.services.attendance_service import AUTO_CLOSED, STALE_SHIFT_HOURS, _as_utc
from app.services.geofence_request_service import RequestConflict, RequestForbidden, RequestNotFound
from app.services.geofence_scope import GEOFENCE_ADMIN_ROLES, assigned_property, caller_tenant, current_role
from app.services.inbox_service import create_inbox_item, mark_inbox_items_actioned

PENDING = "pending"
INBOX_MODULE = "attendance"
INBOX_ITEM_TYPE = "attendance_correction_request"
ADMIN_ROLES = GEOFENCE_ADMIN_ROLES  # Super Admin, Tenant Admin, Co Admin


def _uid(user: dict) -> UUID:
    return UUID(str(user["user_id"]))


def hours_between(punch_in: datetime, punch_out: datetime) -> float:
    return round((_as_utc(punch_out) - _as_utc(punch_in)).total_seconds() / 3600, 2)


def _validate_claim(record: AttendanceRecord, claimed: datetime, now: datetime) -> datetime:
    if claimed.tzinfo is None:
        raise ValueError("Give the punch-out time with a timezone.")
    claimed = claimed.astimezone(timezone.utc)
    punch_in = _as_utc(record.punch_in_time)
    if claimed <= punch_in:
        raise ValueError("The punch-out time must be after the punch-in time.")
    if claimed - punch_in > timedelta(hours=STALE_SHIFT_HOURS):
        raise ValueError(f"The punch-out time must be within {STALE_SHIFT_HOURS} hours of the punch-in.")
    if claimed > now + timedelta(minutes=1):
        raise ValueError("The punch-out time can't be in the future.")
    return claimed


async def _close_inbox(db: AsyncSession, request: AttendanceCorrectionRequest) -> None:
    await mark_inbox_items_actioned(
        db, tenant_id=request.tenant_id, source_record_id=request.id, item_type=INBOX_ITEM_TYPE)


async def create_correction(
    db: AsyncSession, user: dict, data: AttendanceCorrectionCreate, now: Optional[datetime] = None
) -> AttendanceCorrectionRequest:
    now = now or datetime.now(timezone.utc)
    tenant_id = caller_tenant(user)
    requester = _uid(user)
    record = tenant_id and (await db.execute(
        select(AttendanceRecord).where(
            AttendanceRecord.id == data.attendance_id,
            AttendanceRecord.tenant_id == tenant_id,
            AttendanceRecord.user_id == requester,  # only your own shifts
        )
    )).scalar_one_or_none()
    if not record:
        raise RequestNotFound()
    if record.status != AUTO_CLOSED:
        raise RequestConflict("Only a shift that was closed without a punch-out can be corrected.")
    claimed = _validate_claim(record, data.claimed_punch_out_time, now)

    role = await current_role(db, user) or user.get("role") or "Staff"
    pending = (await db.execute(
        select(AttendanceCorrectionRequest).where(
            AttendanceCorrectionRequest.attendance_id == record.id,
            AttendanceCorrectionRequest.status == PENDING,
        ).with_for_update()
    )).scalars().all()
    for old in pending:
        old.status = "cancelled"
        old.reviewed_by = requester
        old.reviewed_at = now
        old.review_note = "Replaced by a newer request"
        await _close_inbox(db, old)
    await db.flush()

    request = AttendanceCorrectionRequest(
        id=uuid4(), tenant_id=tenant_id, property_id=record.property_id, attendance_id=record.id,
        requested_by=requester, requester_role=role, claimed_punch_out_time=claimed,
        reason=data.reason.strip(), status=PENDING, created_at=now,
    )
    db.add(request)
    hours = hours_between(record.punch_in_time, claimed)
    await create_inbox_item(
        db,
        tenant_id=tenant_id,
        property_id=record.property_id,
        source_module=INBOX_MODULE,
        item_type=INBOX_ITEM_TYPE,
        source_record_id=request.id,
        # "manager" items reach the property's managers and the owners
        recipient_role="manager" if role == "Staff" else "owner",
        title="Missed punch-out correction requested",
        body=f"A shift that was closed without a punch-out is claimed as {hours} h. Approve or reject it.",
    )
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise RequestConflict("Another correction for this shift was just submitted. Reload and try again.")
    await db.refresh(request)
    return request


def _reviewer_may_see(user: dict):
    """Filter for the requests a reviewer is responsible for (beyond their own)."""
    role = user.get("role")
    if role == "Manager":
        prop = assigned_property(user)
        return (AttendanceCorrectionRequest.requester_role == "Staff") & (
            AttendanceCorrectionRequest.property_id == prop) if prop else None
    if role in ADMIN_ROLES:
        prop = assigned_property(user)  # property-scoped Co Admin
        return (AttendanceCorrectionRequest.property_id == prop) if prop else True
    return None


async def list_corrections(
    db: AsyncSession, user: dict, status: Optional[str] = None, mine_only: bool = False, limit: int = 100,
) -> List[AttendanceCorrectionRequest]:
    tenant_id = caller_tenant(user)
    if tenant_id is None:
        return []
    own = AttendanceCorrectionRequest.requested_by == _uid(user)
    review_scope = None if mine_only else _reviewer_may_see(user)
    if review_scope is None:
        visible = own
    elif review_scope is True:
        visible = True
    else:
        visible = or_(own, review_scope)
    q = select(AttendanceCorrectionRequest).where(AttendanceCorrectionRequest.tenant_id == tenant_id)
    if visible is not True:
        q = q.where(visible)
    if status:
        q = q.where(AttendanceCorrectionRequest.status == status)
    q = q.order_by(AttendanceCorrectionRequest.created_at.desc(), AttendanceCorrectionRequest.id).limit(limit)
    return list((await db.execute(q)).scalars().all())


async def _get_locked(db: AsyncSession, request_id: UUID, user: dict) -> AttendanceCorrectionRequest:
    tenant_id = caller_tenant(user)
    request = tenant_id and (await db.execute(
        select(AttendanceCorrectionRequest).where(
            AttendanceCorrectionRequest.id == request_id,
            AttendanceCorrectionRequest.tenant_id == tenant_id,
        ).with_for_update()
    )).scalar_one_or_none()
    if not request:
        raise RequestNotFound()
    return request


async def _ensure_reviewer(db: AsyncSession, request: AttendanceCorrectionRequest, user: dict) -> UUID:
    """403/404 unless the caller may review this request now; returns their id."""
    reviewer = _uid(user)
    token_role = user.get("role")
    limited_to = assigned_property(user)
    in_scope = (
        (token_role in ADMIN_ROLES and (limited_to is None or limited_to == request.property_id))
        or (token_role == "Manager" and request.requester_role == "Staff" and limited_to == request.property_id)
    )
    if request.requested_by == reviewer:
        raise RequestForbidden("You can't review your own request. Cancel it instead.")
    if not in_scope:
        # Visible to its requester only; anyone else outside scope sees nothing
        raise RequestNotFound()
    if request.status != PENDING:
        raise RequestConflict(f"This request is already {request.status}.")
    stored = await current_role(db, user)
    allowed = ADMIN_ROLES + (("Manager",) if request.requester_role == "Staff" else ())
    if stored not in allowed or (token_role == "Manager" and stored != "Manager"):
        raise RequestForbidden("Your role no longer allows reviewing this request. Sign in again.")
    return reviewer


def _close(request: AttendanceCorrectionRequest, status: str, reviewer: UUID, note: Optional[str]) -> None:
    request.status = status
    request.reviewed_by = reviewer
    request.reviewed_at = datetime.now(timezone.utc)
    request.review_note = note


async def approve_correction(
    db: AsyncSession, user: dict, request_id: UUID, review_note: Optional[str] = None
) -> Tuple[AttendanceCorrectionRequest, AttendanceRecord]:
    request = await _get_locked(db, request_id, user)
    reviewer = await _ensure_reviewer(db, request, user)
    record = (await db.execute(
        select(AttendanceRecord).where(
            AttendanceRecord.id == request.attendance_id,
            AttendanceRecord.tenant_id == request.tenant_id,
        ).with_for_update()
    )).scalar_one_or_none()
    if record is None or record.status != AUTO_CLOSED:
        raise RequestConflict("This shift has changed since the request was made; it can only be rejected.")

    record.punch_out_time = request.claimed_punch_out_time
    record.hours_worked = hours_between(record.punch_in_time, request.claimed_punch_out_time)
    record.status = "completed"
    _close(request, "approved", reviewer, review_note)
    await _close_inbox(db, request)
    await db.commit()
    await db.refresh(request)
    await db.refresh(record)
    return request, record


async def reject_correction(
    db: AsyncSession, user: dict, request_id: UUID, review_note: Optional[str] = None
) -> AttendanceCorrectionRequest:
    request = await _get_locked(db, request_id, user)
    reviewer = await _ensure_reviewer(db, request, user)
    _close(request, "rejected", reviewer, review_note)
    await _close_inbox(db, request)
    await db.commit()
    await db.refresh(request)
    return request


async def cancel_correction(db: AsyncSession, user: dict, request_id: UUID) -> AttendanceCorrectionRequest:
    request = await _get_locked(db, request_id, user)
    requester = _uid(user)
    if request.requested_by != requester:
        raise RequestNotFound()
    if request.status != PENDING:
        raise RequestConflict(f"This request is already {request.status}.")
    _close(request, "cancelled", requester, None)
    await _close_inbox(db, request)
    await db.commit()
    await db.refresh(request)
    return request


async def details_for(db: AsyncSession, requests: Iterable[AttendanceCorrectionRequest]) -> Tuple[Dict, Dict, Dict]:
    """(user names, property names, attendance id -> punch_in_time) for the requests."""
    requests = list(requests)
    user_ids = {u for r in requests for u in (r.requested_by, r.reviewed_by) if u}
    property_ids = {r.property_id for r in requests}
    record_ids = {r.attendance_id for r in requests}
    users, props, punch_ins = {}, {}, {}
    if user_ids:
        for row in (await db.execute(
            select(User.id, User.first_name, User.last_name).where(User.id.in_(user_ids))
        )).all():
            users[row.id] = " ".join(filter(None, [row.first_name, row.last_name])) or None
    if property_ids:
        for row in (await db.execute(select(Property.id, Property.name).where(Property.id.in_(property_ids)))).all():
            props[row.id] = row.name
    if record_ids:
        for row in (await db.execute(
            select(AttendanceRecord.id, AttendanceRecord.punch_in_time).where(AttendanceRecord.id.in_(record_ids))
        )).all():
            punch_ins[row.id] = row.punch_in_time
    return users, props, punch_ins
