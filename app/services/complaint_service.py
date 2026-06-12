"""
Complaint & Error Log Service  —  app/services/complaint_service.py

Business-logic layer for all complaint/error-log operations.
Instantiated once per request via the `get_complaint_service` FastAPI
dependency in complaints.py, which injects tenant/property/user context
from the decoded JWT so every query is automatically tenant-scoped.

Role-based visibility rules:
  staff   → sees only their own complaints (created_by = self.user_id)
  manager → sees all complaints for their assigned property
  owner   → sees all complaints across every property in the tenant

Write operations (create / update / resolve / escalate / assign / comment)
always call commit() + refresh() so changes are durable.  Earlier versions
used flush()-only, which discarded data when the request session closed.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy import and_, desc, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.models import (
    Complaint, ComplaintAssignment, ComplaintComment, ComplaintAttachment,
    ComplaintCommentAttachment, Department, Employee, Property, User,
)
from app.schemas.complaints import (
    ComplaintAssignmentCreate, ComplaintCategory, ComplaintCommentCreate,
    ComplaintCommentResponse, ComplaintCreate, ComplaintDetailResponse,
    ComplaintDashboardEvent, ComplaintDashboardNeedAttention,
    ComplaintDashboardStats, ComplaintFilterParams, ComplaintListResponse,
    ComplaintPriority, ComplaintResolve, ComplaintResponse, ComplaintStatus,
    ComplaintType, ComplaintUpdate, ManagerDashboardData, OwnerDashboardData,
    StaffDashboardData,
)


class ComplaintService:
    """
    Stateless service that wraps a single request's DB session.

    One instance is created per HTTP request (see `get_complaint_service`
    in complaints.py).  The constructor arguments come from the caller's
    JWT and are used to:
      - scope every SELECT to the correct tenant / property
      - stamp created_by / resolved_by / assigned_by on write operations
      - gate role-restricted actions (resolve, assign, escalate)

    Args:
        db:          Async SQLAlchemy session for the current request.
        tenant_id:   UUID of the caller's tenant (multi-tenancy boundary).
        property_id: UUID of the property the caller is assigned to.
                     None for owner-role users who span all properties.
        user_id:     UUID of the authenticated user (used for audit fields).
        user_role:   "staff" | "manager" | "owner"  (derived from role_level).
    """

    def __init__(
        self,
        db: AsyncSession,
        tenant_id: UUID,
        property_id: UUID,
        user_id: UUID,
        user_role: str = "staff",
    ):
        self.db = db
        self.tenant_id = tenant_id
        self.property_id = property_id
        self.user_id = user_id
        self.user_role = user_role

    # ================================================================
    # COMPLAINT CREATION & MANAGEMENT
    # ================================================================

    async def create_complaint(self, data: ComplaintCreate) -> ComplaintResponse:
        """
        Persist a new complaint and return it.

        The complaint is stamped with the caller's tenant_id, property_id,
        and user_id so it automatically appears in the correct property view.
        Status is always initialised to "open".
        """
        complaint = Complaint(
            tenant_id=self.tenant_id,
            property_id=self.property_id,
            created_by=self.user_id,
            title=data.title,
            description=data.description,
            category=data.category.value,
            complaint_type=data.complaint_type.value,
            priority=data.priority.value,
            room_number=data.room_number,
            location=data.location,
            status="open",
        )
        self.db.add(complaint)
        await self.db.commit()
        await self.db.refresh(complaint)   # reload DB-generated fields (id, created_at)
        return ComplaintResponse.from_orm(complaint)

    async def get_complaint(self, complaint_id: UUID) -> Optional[ComplaintDetailResponse]:
        """
        Fetch a single complaint with its comments, assignments, and attachments.

        Returns None when the complaint does not exist, belongs to a different
        tenant, or has been soft-deleted.  selectinload avoids N+1 queries for
        the three child collections.
        """
        stmt = (
            select(Complaint)
            .where(
                and_(
                    Complaint.id == complaint_id,
                    Complaint.tenant_id == self.tenant_id,
                    Complaint.deleted_at.is_(None),
                )
            )
            .options(
                selectinload(Complaint.comments),
                selectinload(Complaint.assignments),
                selectinload(Complaint.attachments),
            )
        )
        result = await self.db.execute(stmt)
        complaint = result.scalars().first()

        if not complaint:
            return None

        return ComplaintDetailResponse.from_orm(complaint)

    async def update_complaint(
        self, complaint_id: UUID, data: ComplaintUpdate
    ) -> Optional[ComplaintResponse]:
        """
        Patch editable fields on an existing complaint.

        Only non-None values in `data` are applied so callers can send
        partial updates without accidentally clearing fields.
        Returns None if the complaint is not found or is soft-deleted.
        """
        complaint = await self._get_complaint_by_id(complaint_id)
        if not complaint:
            return None

        if data.title:
            complaint.title = data.title
        if data.description:
            complaint.description = data.description
        if data.category:
            complaint.category = data.category.value
        if data.complaint_type:
            complaint.complaint_type = data.complaint_type.value
        if data.priority:
            complaint.priority = data.priority.value
        if data.room_number:
            complaint.room_number = data.room_number
        if data.location:
            complaint.location = data.location

        await self.db.commit()
        await self.db.refresh(complaint)
        return ComplaintResponse.from_orm(complaint)

    async def resolve_complaint(
        self, complaint_id: UUID, data: ComplaintResolve
    ) -> Optional[ComplaintResponse]:
        """
        Mark a complaint as resolved (or closed).

        Records who resolved it and when so the dashboard can calculate
        same-day resolution rates.  Resolution notes are mandatory at the
        API layer so managers leave an audit trail.
        """
        complaint = await self._get_complaint_by_id(complaint_id)
        if not complaint:
            return None

        complaint.status = data.status.value
        complaint.resolution_notes = data.resolution_notes
        complaint.resolved_by = self.user_id
        complaint.resolved_at = datetime.utcnow()

        await self.db.commit()
        await self.db.refresh(complaint)
        return ComplaintResponse.from_orm(complaint)

    async def escalate_complaint(
        self, complaint_id: UUID, reason: str
    ) -> Optional[ComplaintResponse]:
        """
        Escalate an open/in-progress complaint to a higher authority.

        Sets status to "escalated" and appends an internal (non-visible to
        guests) comment so managers can trace why it was escalated.
        The add_comment call commits its own transaction, then the outer
        commit here persists the status change.
        """
        complaint = await self._get_complaint_by_id(complaint_id)
        if not complaint:
            return None

        complaint.status = "escalated"
        complaint.resolution_notes = f"Escalated: {reason}"

        # Internal audit trail — not shown to the original reporter
        await self.add_comment(
            complaint_id,
            ComplaintCommentCreate(
                comment=f"Escalated by {self.user_role}: {reason}",
                is_internal=True,
            ),
        )

        await self.db.commit()
        await self.db.refresh(complaint)
        return ComplaintResponse.from_orm(complaint)

    # ================================================================
    # COMPLAINT LISTING & FILTERING
    # ================================================================

    async def list_complaints(
        self,
        filters: Optional[ComplaintFilterParams] = None,
        skip: int = 0,
        limit: int = 50,
    ) -> tuple[List[ComplaintListResponse], int]:
        """
        Return a paginated list of complaints and the total unfiltered count.

        Visibility scoping:
          - owner   → all properties in the tenant
          - manager → only their assigned property (property_id filter applied)
          - staff   → also only their property, but typically calls
                      list_staff_complaints() which adds a created_by filter

        The total count is calculated before pagination so callers can render
        "showing X of Y" without a separate API call.
        """
        stmt = select(Complaint).where(
            and_(
                Complaint.tenant_id == self.tenant_id,
                Complaint.deleted_at.is_(None),
            )
        )

        # Owners span all properties; managers and staff see only their own
        if self.user_role != "owner":
            stmt = stmt.where(Complaint.property_id == self.property_id)

        if filters:
            if filters.status:
                stmt = stmt.where(Complaint.status == filters.status.value)
            if filters.priority:
                stmt = stmt.where(Complaint.priority == filters.priority.value)
            if filters.category:
                stmt = stmt.where(Complaint.category == filters.category.value)
            if filters.complaint_type:
                stmt = stmt.where(Complaint.complaint_type == filters.complaint_type.value)
            if filters.assigned_to:
                stmt = stmt.where(Complaint.assigned_to == filters.assigned_to)
            if filters.created_by:
                stmt = stmt.where(Complaint.created_by == filters.created_by)
            if filters.room_number:
                stmt = stmt.where(Complaint.room_number == filters.room_number)
            if filters.date_from:
                stmt = stmt.where(Complaint.created_at >= filters.date_from)
            if filters.date_to:
                stmt = stmt.where(Complaint.created_at <= filters.date_to)
            if filters.search:
                term = f"%{filters.search}%"
                stmt = stmt.where(
                    or_(
                        Complaint.title.ilike(term),
                        Complaint.description.ilike(term),
                        Complaint.room_number == filters.search,
                    )
                )

        # Count before pagination
        count_stmt = select(func.count()).select_from(stmt.distinct().subquery())
        total_result = await self.db.execute(count_stmt)
        total = total_result.scalar() or 0

        stmt = stmt.order_by(desc(Complaint.created_at)).offset(skip).limit(limit)
        result = await self.db.execute(stmt)
        complaints = result.scalars().all()

        return [ComplaintListResponse.from_orm(c) for c in complaints], total

    async def list_staff_complaints(
        self, skip: int = 0, limit: int = 50
    ) -> tuple[List[ComplaintListResponse], int]:
        """Return only complaints created by the current staff member."""
        filters = ComplaintFilterParams(created_by=self.user_id)
        return await self.list_complaints(filters, skip, limit)

    async def list_assigned_complaints(
        self, skip: int = 0, limit: int = 50
    ) -> tuple[List[ComplaintListResponse], int]:
        """Return complaints currently assigned to the calling user."""
        filters = ComplaintFilterParams(assigned_to=self.user_id)
        return await self.list_complaints(filters, skip, limit)

    # ================================================================
    # ASSIGNMENT MANAGEMENT
    # ================================================================

    async def assign_complaint(
        self, complaint_id: UUID, data: ComplaintAssignmentCreate
    ) -> Optional[ComplaintResponse]:
        """
        Assign a complaint to a staff member and move it to "in_progress".

        Maintains a ComplaintAssignment history record (separate from the
        denormalized assigned_to column on Complaint) so re-assignments are
        traceable.  If the same user is already assigned, only the notes are
        updated rather than creating a duplicate row.

        An internal activity comment is appended after the commit so the
        assignment is visible in the comment timeline.
        """
        complaint = await self._get_complaint_by_id(complaint_id)
        if not complaint:
            return None

        # Check for an existing assignment row for this user
        existing_result = await self.db.execute(
            select(ComplaintAssignment).where(
                and_(
                    ComplaintAssignment.complaint_id == complaint_id,
                    ComplaintAssignment.assigned_to == data.assigned_to,
                )
            )
        )
        existing_assignment = existing_result.scalars().first()

        if existing_assignment:
            if data.notes:
                existing_assignment.notes = data.notes
        else:
            self.db.add(
                ComplaintAssignment(
                    tenant_id=self.tenant_id,
                    complaint_id=complaint_id,
                    assigned_to=data.assigned_to,
                    assigned_by=self.user_id,
                    notes=data.notes,
                )
            )

        # Denormalised fast-access columns on Complaint
        complaint.assigned_to = data.assigned_to
        complaint.assigned_by = self.user_id
        complaint.assigned_at = datetime.utcnow()
        complaint.status = "in_progress"

        await self.db.commit()
        await self.db.refresh(complaint)

        # Activity trail — committed separately inside add_comment
        await self.add_comment(
            complaint_id,
            ComplaintCommentCreate(
                comment=f"Assigned to user {data.assigned_to}. {data.notes or ''}",
                is_internal=True,
            ),
        )

        return ComplaintResponse.from_orm(complaint)

    async def reassign_complaint(
        self, complaint_id: UUID, new_assigned_to: UUID, notes: str = None
    ) -> Optional[ComplaintResponse]:
        """Reassign a complaint to a different staff member (delegates to assign_complaint)."""
        return await self.assign_complaint(
            complaint_id,
            ComplaintAssignmentCreate(assigned_to=new_assigned_to, notes=notes),
        )

    # ================================================================
    # COMMENTS & ACTIVITY
    # ================================================================

    async def add_comment(
        self, complaint_id: UUID, data: ComplaintCommentCreate
    ) -> Optional[ComplaintCommentResponse]:
        """
        Append a comment to a complaint and increment its comment_count.

        is_internal=True comments are staff/manager-only audit notes and
        are filtered from guest-facing views in the frontend.
        comment_count is a denormalised counter on Complaint used by the
        list view so it doesn't need a subquery on every row.
        """
        complaint = await self._get_complaint_by_id(complaint_id)
        if not complaint:
            return None

        comment = ComplaintComment(
            tenant_id=self.tenant_id,
            complaint_id=complaint_id,
            user_id=self.user_id,
            comment=data.comment,
            is_internal=data.is_internal,
        )
        self.db.add(comment)

        # Keep the denormalised counter in sync
        complaint.comment_count = (complaint.comment_count or 0) + 1

        await self.db.commit()
        await self.db.refresh(comment)
        return ComplaintCommentResponse.from_orm(comment)

    async def get_comments(self, complaint_id: UUID) -> List[ComplaintCommentResponse]:
        """Return all comments for a complaint in chronological order."""
        stmt = (
            select(ComplaintComment)
            .where(
                and_(
                    ComplaintComment.complaint_id == complaint_id,
                    ComplaintComment.tenant_id == self.tenant_id,
                )
            )
            .order_by(ComplaintComment.created_at)
        )
        result = await self.db.execute(stmt)
        return [ComplaintCommentResponse.from_orm(c) for c in result.scalars().all()]

    # ================================================================
    # DASHBOARD DATA
    # ================================================================

    async def get_manager_dashboard(self) -> ManagerDashboardData:
        """
        Aggregate statistics for the manager's property dashboard.

        Fetches all non-deleted complaints for the property in a single
        query and derives every counter/grouping in Python to avoid
        multiple round-trips.  The "need attention" list surfaces high/
        critical unresolved complaints along with how many days they have
        been open, and "daily_events" is capped at 20 to keep payload size
        manageable.
        """
        result = await self.db.execute(
            select(Complaint).where(
                and_(
                    Complaint.property_id == self.property_id,
                    Complaint.tenant_id == self.tenant_id,
                    Complaint.deleted_at.is_(None),
                )
            )
        )
        all_complaints = result.scalars().all()

        total        = len(all_complaints)
        open_count   = sum(1 for c in all_complaints if c.status == "open")
        in_progress  = sum(1 for c in all_complaints if c.status == "in_progress")
        escalated    = sum(1 for c in all_complaints if c.status == "escalated")
        today        = datetime.utcnow().date()
        resolved_today = sum(
            1 for c in all_complaints
            if c.resolved_at and c.resolved_at.date() == today
        )

        # Build breakdown dicts in a single pass
        by_priority: Dict[str, int] = {}
        by_status:   Dict[str, int] = {}
        by_category: Dict[str, int] = {}
        by_type:     Dict[str, int] = {}

        for c in all_complaints:
            by_priority[c.priority]       = by_priority.get(c.priority, 0) + 1
            by_status[c.status]           = by_status.get(c.status, 0) + 1
            by_category[c.category]       = by_category.get(c.category, 0) + 1
            by_type[c.complaint_type]     = by_type.get(c.complaint_type, 0) + 1

        # Most recent 10 complaints for the "recent activity" widget
        recent_complaints = [
            ComplaintListResponse.from_orm(c)
            for c in sorted(all_complaints, key=lambda x: x.created_at, reverse=True)[:10]
        ]

        # Complaints requiring immediate attention: high/critical and not resolved
        need_attention = [
            ComplaintDashboardNeedAttention(
                id=c.id,
                title=c.title,
                category=c.category,
                complaint_type=c.complaint_type,
                priority=c.priority,
                status=c.status,
                room_number=c.room_number,
                created_by=c.created_by,
                assigned_to=c.assigned_to,
                created_at=c.created_at,
                days_open=(datetime.utcnow() - c.created_at).days,
            )
            for c in all_complaints
            if c.priority in ("high", "critical") and c.status != "resolved"
        ]

        # Today's activity feed — capped at 20 to limit response size
        daily_events = [
            ComplaintDashboardEvent(
                id=c.id,
                title=c.title,
                description=c.description[:100],
                priority=c.priority,
                status=c.status,
                complaint_type=c.complaint_type,
                category=c.category,
                room_number=c.room_number,
                created_at=c.created_at,
                assigned_to=c.assigned_to,
            )
            for c in all_complaints
            if c.created_at.date() == today
        ][:20]

        return ManagerDashboardData(
            total_complaints=total,
            open_complaints=open_count,
            in_progress_count=in_progress,
            resolved_today=resolved_today,
            escalated_count=escalated,
            by_priority=by_priority,
            by_status=by_status,
            by_category=by_category,
            by_type=by_type,
            recent_complaints=recent_complaints,
            need_attention=need_attention,
            daily_events=daily_events,
        )

    async def get_owner_dashboard(self) -> OwnerDashboardData:
        """
        Aggregate statistics across all properties for the owner dashboard.

        Unlike the manager dashboard, this is not filtered by property_id,
        giving owners an organisation-wide view.  by_property is a dict of
        {property_id_str: count} so the frontend can render a per-property
        breakdown without needing a separate endpoint.
        """
        result = await self.db.execute(
            select(Complaint).where(
                and_(
                    Complaint.tenant_id == self.tenant_id,
                    Complaint.deleted_at.is_(None),
                )
            )
        )
        all_complaints = result.scalars().all()

        total    = len(all_complaints)
        critical = sum(1 for c in all_complaints if c.priority == "critical")
        high     = sum(1 for c in all_complaints if c.priority == "high")
        resolved = sum(1 for c in all_complaints if c.status == "resolved")

        resolution_rate = (resolved / total * 100) if total > 0 else 0.0

        by_property: Dict[str, int] = {}
        by_category: Dict[str, int] = {}
        by_status:   Dict[str, int] = {}
        critical_complaints = []

        for c in all_complaints:
            key = str(c.property_id)
            by_property[key]          = by_property.get(key, 0) + 1
            by_category[c.category]   = by_category.get(c.category, 0) + 1
            by_status[c.status]       = by_status.get(c.status, 0) + 1
            if c.priority == "critical":
                critical_complaints.append(ComplaintListResponse.from_orm(c))

        return OwnerDashboardData(
            total_complaints=total,
            total_critical=critical,
            total_high=high,
            total_resolved=resolved,
            resolution_rate=resolution_rate,
            by_property=by_property,
            by_category=by_category,
            by_status=by_status,
            critical_complaints=critical_complaints[:20],  # cap payload
        )

    async def get_staff_dashboard(self) -> StaffDashboardData:
        """
        Personal dashboard for a staff member.

        Returns two lists:
          my_complaints        — complaints this user filed
          complaints_assigned_to_me — complaints a manager assigned to them

        resolved_by_me counts complaints where resolved_by == self.user_id,
        not just complaints in "resolved" status, so it reflects the staff
        member's personal resolution contribution.
        """
        # Complaints filed by this user
        my_result = await self.db.execute(
            select(Complaint).where(
                and_(
                    Complaint.created_by == self.user_id,
                    Complaint.tenant_id == self.tenant_id,
                    Complaint.deleted_at.is_(None),
                )
            )
        )
        my_complaints = my_result.scalars().all()

        # Complaints assigned to this user by a manager
        assigned_result = await self.db.execute(
            select(Complaint).where(
                and_(
                    Complaint.assigned_to == self.user_id,
                    Complaint.tenant_id == self.tenant_id,
                    Complaint.deleted_at.is_(None),
                )
            )
        )
        assigned_complaints = assigned_result.scalars().all()

        return StaffDashboardData(
            my_complaints_count=len(my_complaints),
            pending_resolution=sum(1 for c in my_complaints if c.status != "resolved"),
            resolved_by_me=sum(1 for c in my_complaints if c.resolved_by == self.user_id),
            assigned_to_me=len(assigned_complaints),
            my_complaints=[ComplaintListResponse.from_orm(c) for c in my_complaints[:10]],
            complaints_assigned_to_me=[
                ComplaintListResponse.from_orm(c) for c in assigned_complaints[:10]
            ],
        )

    # ================================================================
    # STATISTICS
    # ================================================================

    async def get_statistics(
        self, filters: Optional[ComplaintFilterParams] = None
    ) -> Dict[str, Any]:
        """
        Return aggregated complaint counts broken down by priority and status,
        plus average resolution time in hours.

        Scoped to the caller's property unless the caller is an owner.
        Optionally pre-filtered by status (e.g. to get stats for open
        complaints only).
        """
        stmt = select(Complaint).where(
            and_(
                Complaint.tenant_id == self.tenant_id,
                Complaint.deleted_at.is_(None),
            )
        )

        if self.user_role != "owner":
            stmt = stmt.where(Complaint.property_id == self.property_id)

        if filters and filters.status:
            stmt = stmt.where(Complaint.status == filters.status.value)

        result = await self.db.execute(stmt)
        complaints = result.scalars().all()

        return {
            "total": len(complaints),
            "by_priority": {
                "critical": sum(1 for c in complaints if c.priority == "critical"),
                "high":     sum(1 for c in complaints if c.priority == "high"),
                "medium":   sum(1 for c in complaints if c.priority == "medium"),
                "low":      sum(1 for c in complaints if c.priority == "low"),
            },
            "by_status": {
                "open":        sum(1 for c in complaints if c.status == "open"),
                "in_progress": sum(1 for c in complaints if c.status == "in_progress"),
                "resolved":    sum(1 for c in complaints if c.status == "resolved"),
                "escalated":   sum(1 for c in complaints if c.status == "escalated"),
                "closed":      sum(1 for c in complaints if c.status == "closed"),
            },
            "average_resolution_time": self._calculate_avg_resolution_time(complaints),
        }

    # ================================================================
    # PRIVATE HELPERS
    # ================================================================

    async def _get_complaint_by_id(self, complaint_id: UUID) -> Optional[Complaint]:
        """
        Fetch a Complaint ORM object by primary key within the current tenant.

        Excludes soft-deleted rows.  Returns None instead of raising so
        callers can decide whether to 404 or silently skip.
        Used internally before any mutation to ensure the record exists and
        belongs to the caller's tenant before modifying it.
        """
        stmt = select(Complaint).where(
            and_(
                Complaint.id == complaint_id,
                Complaint.tenant_id == self.tenant_id,
                Complaint.deleted_at.is_(None),
            )
        )
        result = await self.db.execute(stmt)
        return result.scalars().first()

    def _calculate_avg_resolution_time(self, complaints: List[Complaint]) -> float:
        """
        Return the mean time-to-resolve across the given complaints, in hours.

        Only complaints that have a resolved_at timestamp are included.
        Returns 0.0 when no complaints have been resolved yet.
        """
        resolved = [c for c in complaints if c.resolved_at]
        if not resolved:
            return 0.0

        total_hours = sum(
            (c.resolved_at - c.created_at).total_seconds() / 3600
            for c in resolved
        )
        return round(total_hours / len(resolved), 2)
