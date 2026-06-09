"""
Complaint & Error Log Service - Business Logic Layer

Handles all complaint management operations:
- Create, update, resolve complaints
- Assign to staff
- Comment and activity tracking
- Dashboard data aggregation
- Export functionality
"""

from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any
from uuid import UUID

from sqlalchemy import and_, desc, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.models import (
    Complaint, ComplaintAssignment, ComplaintComment, ComplaintAttachment,
    ComplaintCommentAttachment, Property, User, Department, Employee
)
from app.schemas.complaints import (
    ComplaintCreate, ComplaintUpdate, ComplaintResolve, ComplaintResponse,
    ComplaintDetailResponse, ComplaintListResponse, ComplaintFilterParams,
    ManagerDashboardData, OwnerDashboardData, StaffDashboardData,
    ComplaintDashboardStats, ComplaintDashboardNeedAttention, ComplaintDashboardEvent,
    ComplaintCommentCreate, ComplaintCommentResponse, ComplaintAssignmentCreate
)


class ComplaintService:
    """Service for managing complaints and errors"""
    
    def __init__(
        self,
        db: AsyncSession,
        tenant_id: UUID,
        property_id: UUID,
        user_id: UUID,
        user_role: str = "staff"  # staff, manager, owner
    ):
        """Initialize service with database context"""
        self.db = db
        self.tenant_id = tenant_id
        self.property_id = property_id
        self.user_id = user_id
        self.user_role = user_role

    # ===========================================================
    # COMPLAINT CREATION & MANAGEMENT
    # ===========================================================

    async def create_complaint(self, data: ComplaintCreate) -> ComplaintResponse:
        """Create a new complaint"""
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
            status="open"
        )
        self.db.add(complaint)
        await self.db.commit()
        await self.db.refresh(complaint)

        return ComplaintResponse.from_orm(complaint)

    async def get_complaint(self, complaint_id: UUID) -> Optional[ComplaintDetailResponse]:
        """Get complaint with all details"""
        stmt = (
            select(Complaint)
            .where(
                and_(
                    Complaint.id == complaint_id,
                    Complaint.tenant_id == self.tenant_id,
                    Complaint.deleted_at.is_(None)
                )
            )
            .options(
                selectinload(Complaint.comments),
                selectinload(Complaint.assignments),
                selectinload(Complaint.attachments)
            )
        )
        result = await self.db.execute(stmt)
        complaint = result.scalars().first()
        
        if not complaint:
            return None
        
        return ComplaintDetailResponse.from_orm(complaint)

    async def update_complaint(self, complaint_id: UUID, data: ComplaintUpdate) -> ComplaintResponse:
        """Update complaint details"""
        complaint = await self._get_complaint_by_id(complaint_id)
        if not complaint:
            return None
        
        # Update allowed fields
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
    ) -> ComplaintResponse:
        """Resolve or close a complaint"""
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

    async def escalate_complaint(self, complaint_id: UUID, reason: str) -> ComplaintResponse:
        """Escalate complaint to higher authority"""
        complaint = await self._get_complaint_by_id(complaint_id)
        if not complaint:
            return None
        
        complaint.status = "escalated"
        complaint.resolution_notes = f"Escalated: {reason}"
        
        # Add internal comment
        await self.add_comment(
            complaint_id,
            ComplaintCommentCreate(
                comment=f"Escalated by {self.user_role}: {reason}",
                is_internal=True
            )
        )
        
        await self.db.commit()
        await self.db.refresh(complaint)
        return ComplaintResponse.from_orm(complaint)

    # ===========================================================
    # COMPLAINT LISTING & FILTERING
    # ===========================================================

    async def list_complaints(
        self,
        filters: Optional[ComplaintFilterParams] = None,
        skip: int = 0,
        limit: int = 50
    ) -> tuple[List[ComplaintListResponse], int]:
        """List complaints with optional filters"""
        # Base query
        stmt = select(Complaint).where(
            and_(
                Complaint.tenant_id == self.tenant_id,
                Complaint.deleted_at.is_(None)
            )
        )
        
        # Apply property filter for non-owner roles
        if self.user_role != "owner":
            stmt = stmt.where(Complaint.property_id == self.property_id)
        
        # Apply filters
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
                search_term = f"%{filters.search}%"
                stmt = stmt.where(
                    or_(
                        Complaint.title.ilike(search_term),
                        Complaint.description.ilike(search_term),
                        Complaint.room_number == filters.search
                    )
                )
        
        # Get total count
        count_stmt = select(func.count()).select_from(
            stmt.distinct().subquery()
        )
        total_result = await self.db.execute(count_stmt)
        total = total_result.scalar() or 0
        
        # Get paginated results
        stmt = stmt.order_by(desc(Complaint.created_at)).offset(skip).limit(limit)
        result = await self.db.execute(stmt)
        complaints = result.scalars().all()
        
        return [ComplaintListResponse.from_orm(c) for c in complaints], total

    async def list_staff_complaints(
        self,
        skip: int = 0,
        limit: int = 50
    ) -> tuple[List[ComplaintListResponse], int]:
        """List complaints created by current staff member"""
        filters = ComplaintFilterParams(created_by=self.user_id)
        return await self.list_complaints(filters, skip, limit)

    async def list_assigned_complaints(
        self,
        skip: int = 0,
        limit: int = 50
    ) -> tuple[List[ComplaintListResponse], int]:
        """List complaints assigned to current user"""
        filters = ComplaintFilterParams(assigned_to=self.user_id)
        return await self.list_complaints(filters, skip, limit)

    # ===========================================================
    # ASSIGNMENT MANAGEMENT
    # ===========================================================

    async def assign_complaint(
        self, complaint_id: UUID, data: ComplaintAssignmentCreate
    ) -> ComplaintResponse:
        """Assign complaint to a staff member"""
        complaint = await self._get_complaint_by_id(complaint_id)
        if not complaint:
            return None
        
        # Check if already assigned to this user
        stmt = select(ComplaintAssignment).where(
            and_(
                ComplaintAssignment.complaint_id == complaint_id,
                ComplaintAssignment.assigned_to == data.assigned_to
            )
        )
        existing = await self.db.execute(stmt)
        if existing.scalars().first():
            # Update existing assignment
            assignment = existing.scalars().first()
            if data.notes:
                assignment.notes = data.notes
        else:
            # Create new assignment
            assignment = ComplaintAssignment(
                tenant_id=self.tenant_id,
                complaint_id=complaint_id,
                assigned_to=data.assigned_to,
                assigned_by=self.user_id,
                notes=data.notes
            )
            self.db.add(assignment)
        
        # Update main complaint
        complaint.assigned_to = data.assigned_to
        complaint.assigned_by = self.user_id
        complaint.assigned_at = datetime.utcnow()
        complaint.status = "in_progress"

        await self.db.commit()
        await self.db.refresh(complaint)

        # Add activity comment
        await self.add_comment(
            complaint_id,
            ComplaintCommentCreate(
                comment=f"Assigned to user {data.assigned_to}. {data.notes or ''}",
                is_internal=True
            )
        )
        
        return ComplaintResponse.from_orm(complaint)

    async def reassign_complaint(
        self, complaint_id: UUID, new_assigned_to: UUID, notes: str = None
    ) -> ComplaintResponse:
        """Reassign complaint to another staff"""
        return await self.assign_complaint(
            complaint_id,
            ComplaintAssignmentCreate(assigned_to=new_assigned_to, notes=notes)
        )

    # ===========================================================
    # COMMENTS & ACTIVITY
    # ===========================================================

    async def add_comment(
        self, complaint_id: UUID, data: ComplaintCommentCreate
    ) -> ComplaintCommentResponse:
        """Add comment to complaint"""
        complaint = await self._get_complaint_by_id(complaint_id)
        if not complaint:
            return None
        
        comment = ComplaintComment(
            tenant_id=self.tenant_id,
            complaint_id=complaint_id,
            user_id=self.user_id,
            comment=data.comment,
            is_internal=data.is_internal
        )
        self.db.add(comment)
        
        # Increment comment count
        complaint.comment_count = (complaint.comment_count or 0) + 1

        await self.db.commit()
        await self.db.refresh(comment)
        return ComplaintCommentResponse.from_orm(comment)

    async def get_comments(self, complaint_id: UUID) -> List[ComplaintCommentResponse]:
        """Get all comments for a complaint"""
        stmt = (
            select(ComplaintComment)
            .where(
                and_(
                    ComplaintComment.complaint_id == complaint_id,
                    ComplaintComment.tenant_id == self.tenant_id
                )
            )
            .order_by(ComplaintComment.created_at)
        )
        result = await self.db.execute(stmt)
        comments = result.scalars().all()
        
        return [ComplaintCommentResponse.from_orm(c) for c in comments]

    # ===========================================================
    # DASHBOARD DATA
    # ===========================================================

    async def get_manager_dashboard(self) -> ManagerDashboardData:
        """Get manager dashboard with all statistics"""
        # Base query for property
        base_query = select(Complaint).where(
            and_(
                Complaint.property_id == self.property_id,
                Complaint.tenant_id == self.tenant_id,
                Complaint.deleted_at.is_(None)
            )
        )
        
        result = await self.db.execute(base_query)
        all_complaints = result.scalars().all()
        
        # Calculate statistics
        total = len(all_complaints)
        open_count = len([c for c in all_complaints if c.status == "open"])
        in_progress = len([c for c in all_complaints if c.status == "in_progress"])
        resolved_today = len([
            c for c in all_complaints 
            if c.resolved_at and c.resolved_at.date() == datetime.utcnow().date()
        ])
        escalated = len([c for c in all_complaints if c.status == "escalated"])
        
        # Group by priority, status, category, type
        by_priority = {}
        by_status = {}
        by_category = {}
        by_type = {}
        
        for complaint in all_complaints:
            # By priority
            by_priority[complaint.priority] = by_priority.get(complaint.priority, 0) + 1
            # By status
            by_status[complaint.status] = by_status.get(complaint.status, 0) + 1
            # By category
            by_category[complaint.category] = by_category.get(complaint.category, 0) + 1
            # By type
            by_type[complaint.complaint_type] = by_type.get(complaint.complaint_type, 0) + 1
        
        # Get recent complaints
        recent = sorted(all_complaints, key=lambda x: x.created_at, reverse=True)[:10]
        recent_complaints = [ComplaintListResponse.from_orm(c) for c in recent]
        
        # Get complaints needing attention (high priority, unresolved)
        need_attention_list = []
        for c in all_complaints:
            if c.priority in ["high", "critical"] and c.status != "resolved":
                days_open = (datetime.utcnow() - c.created_at).days
                need_attention_list.append(
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
                        days_open=days_open
                    )
                )
        
        # Daily events (today's complaints)
        daily_events = []
        today_complaints = [
            c for c in all_complaints 
            if c.created_at.date() == datetime.utcnow().date()
        ]
        for c in today_complaints[:20]:
            daily_events.append(
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
                    assigned_to=c.assigned_to
                )
            )
        
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
            need_attention=need_attention_list,
            daily_events=daily_events
        )

    async def get_owner_dashboard(self) -> OwnerDashboardData:
        """Get owner dashboard - all properties"""
        # Query all complaints for tenant
        stmt = select(Complaint).where(
            and_(
                Complaint.tenant_id == self.tenant_id,
                Complaint.deleted_at.is_(None)
            )
        )
        result = await self.db.execute(stmt)
        all_complaints = result.scalars().all()
        
        total = len(all_complaints)
        critical = len([c for c in all_complaints if c.priority == "critical"])
        high = len([c for c in all_complaints if c.priority == "high"])
        resolved = len([c for c in all_complaints if c.status == "resolved"])
        
        resolution_rate = (resolved / total * 100) if total > 0 else 0
        
        # Group by property and category
        by_property = {}
        by_category = {}
        by_status = {}
        critical_complaints = []
        
        for complaint in all_complaints:
            # By property
            prop_id_str = str(complaint.property_id)
            by_property[prop_id_str] = by_property.get(prop_id_str, 0) + 1
            # By category
            by_category[complaint.category] = by_category.get(complaint.category, 0) + 1
            # By status
            by_status[complaint.status] = by_status.get(complaint.status, 0) + 1
            # Critical complaints
            if complaint.priority == "critical":
                critical_complaints.append(ComplaintListResponse.from_orm(complaint))
        
        return OwnerDashboardData(
            total_complaints=total,
            total_critical=critical,
            total_high=high,
            total_resolved=resolved,
            resolution_rate=resolution_rate,
            by_property=by_property,
            by_category=by_category,
            by_status=by_status,
            critical_complaints=critical_complaints[:20]
        )

    async def get_staff_dashboard(self) -> StaffDashboardData:
        """Get staff dashboard - personal view"""
        # My complaints
        my_complaints_stmt = select(Complaint).where(
            and_(
                Complaint.created_by == self.user_id,
                Complaint.tenant_id == self.tenant_id,
                Complaint.deleted_at.is_(None)
            )
        )
        my_result = await self.db.execute(my_complaints_stmt)
        my_complaints = my_result.scalars().all()
        
        # Assigned to me
        assigned_stmt = select(Complaint).where(
            and_(
                Complaint.assigned_to == self.user_id,
                Complaint.tenant_id == self.tenant_id,
                Complaint.deleted_at.is_(None)
            )
        )
        assigned_result = await self.db.execute(assigned_stmt)
        assigned_complaints = assigned_result.scalars().all()
        
        my_complaints_count = len(my_complaints)
        pending = len([c for c in my_complaints if c.status != "resolved"])
        resolved_by_me = len([c for c in my_complaints if c.resolved_by == self.user_id])
        assigned_to_me = len(assigned_complaints)
        
        return StaffDashboardData(
            my_complaints_count=my_complaints_count,
            pending_resolution=pending,
            resolved_by_me=resolved_by_me,
            assigned_to_me=assigned_to_me,
            my_complaints=[ComplaintListResponse.from_orm(c) for c in my_complaints[:10]],
            complaints_assigned_to_me=[ComplaintListResponse.from_orm(c) for c in assigned_complaints[:10]]
        )

    # ===========================================================
    # HELPER METHODS
    # ===========================================================

    async def _get_complaint_by_id(self, complaint_id: UUID) -> Optional[Complaint]:
        """Get complaint by ID with tenant check"""
        stmt = select(Complaint).where(
            and_(
                Complaint.id == complaint_id,
                Complaint.tenant_id == self.tenant_id,
                Complaint.deleted_at.is_(None)
            )
        )
        result = await self.db.execute(stmt)
        return result.scalars().first()

    async def get_statistics(self, filters: Optional[ComplaintFilterParams] = None) -> Dict[str, Any]:
        """Get complaint statistics"""
        stmt = select(Complaint).where(
            and_(
                Complaint.tenant_id == self.tenant_id,
                Complaint.deleted_at.is_(None)
            )
        )
        
        if self.user_role != "owner":
            stmt = stmt.where(Complaint.property_id == self.property_id)
        
        # Apply filters
        if filters and filters.status:
            stmt = stmt.where(Complaint.status == filters.status.value)
        
        result = await self.db.execute(stmt)
        complaints = result.scalars().all()
        
        return {
            "total": len(complaints),
            "by_priority": {
                "critical": len([c for c in complaints if c.priority == "critical"]),
                "high": len([c for c in complaints if c.priority == "high"]),
                "medium": len([c for c in complaints if c.priority == "medium"]),
                "low": len([c for c in complaints if c.priority == "low"]),
            },
            "by_status": {
                "open": len([c for c in complaints if c.status == "open"]),
                "in_progress": len([c for c in complaints if c.status == "in_progress"]),
                "resolved": len([c for c in complaints if c.status == "resolved"]),
                "escalated": len([c for c in complaints if c.status == "escalated"]),
                "closed": len([c for c in complaints if c.status == "closed"]),
            },
            "average_resolution_time": self._calculate_avg_resolution_time(complaints)
        }

    def _calculate_avg_resolution_time(self, complaints: List[Complaint]) -> float:
        """Calculate average time to resolve in hours"""
        resolved = [c for c in complaints if c.resolved_at]
        if not resolved:
            return 0
        
        total_hours = 0
        for complaint in resolved:
            time_diff = complaint.resolved_at - complaint.created_at
            hours = time_diff.total_seconds() / 3600
            total_hours += hours
        
        return round(total_hours / len(resolved), 2)
