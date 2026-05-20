"""
Activity Log Repository - app/repositories/activity_log_repository.py

Data access layer for activity logs with tenant and property isolation.
"""

from datetime import datetime
from typing import List, Optional, Tuple
from uuid import UUID

from sqlalchemy import and_, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import AuditLog, Property, OwnerDetails


class ActivityLogRepository:
    """Data access layer for activity logs with strict isolation."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_logs_for_owner(
        self,
        tenant_id: UUID,
        user_id: Optional[UUID] = None,
        skip: int = 0,
        limit: int = 50,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        action_type: Optional[str] = None,
        severity: Optional[str] = None,
        resource_type: Optional[str] = None,
    ) -> Tuple[List[AuditLog], int]:
        """
        Get activity logs visible to owner.
        Filters by tenant and owner's accessible properties.
        """
        # Get properties owned by this user
        owner_properties = await self._get_user_properties(tenant_id, user_id)
        
        if not owner_properties:
            return [], 0

        filters = [
            AuditLog.tenant_id == tenant_id,
            AuditLog.property_id.in_(owner_properties),
        ]

        if start_date:
            filters.append(AuditLog.created_at >= start_date)
        if end_date:
            filters.append(AuditLog.created_at <= end_date)
        if action_type:
            filters.append(AuditLog.action == action_type)
        if severity:
            filters.append(AuditLog.severity == severity)
        if resource_type:
            filters.append(AuditLog.resource_type == resource_type)

        # Count total
        count_stmt = select(func.count(AuditLog.id)).where(and_(*filters))
        count_result = await self.session.execute(count_stmt)
        total = count_result.scalar()

        # Get paginated logs
        stmt = (
            select(AuditLog)
            .where(and_(*filters))
            .order_by(desc(AuditLog.created_at))
            .offset(skip)
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        logs = result.scalars().all()

        return logs, total

    async def get_property_logs(
        self,
        tenant_id: UUID,
        property_id: UUID,
        user_id: Optional[UUID] = None,
        skip: int = 0,
        limit: int = 50,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> Tuple[List[AuditLog], int]:
        """
        Get logs for specific property.
        Verifies user has access to the property.
        """
        # Verify access
        owner_properties = await self._get_user_properties(tenant_id, user_id)
        if property_id not in owner_properties:
            raise PermissionError(f"Access denied to property {property_id}")

        filters = [
            AuditLog.tenant_id == tenant_id,
            AuditLog.property_id == property_id,
        ]

        if start_date:
            filters.append(AuditLog.created_at >= start_date)
        if end_date:
            filters.append(AuditLog.created_at <= end_date)

        # Count total
        count_stmt = select(func.count(AuditLog.id)).where(and_(*filters))
        count_result = await self.session.execute(count_stmt)
        total = count_result.scalar()

        # Get paginated logs
        stmt = (
            select(AuditLog)
            .where(and_(*filters))
            .order_by(desc(AuditLog.created_at))
            .offset(skip)
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        logs = result.scalars().all()

        return logs, total

    async def get_critical_logs(
        self,
        tenant_id: UUID,
        user_id: Optional[UUID] = None,
        limit: int = 10,
    ) -> List[AuditLog]:
        """Get recent critical severity logs."""
        owner_properties = await self._get_user_properties(tenant_id, user_id)
        
        if not owner_properties:
            return []

        stmt = (
            select(AuditLog)
            .where(
                and_(
                    AuditLog.tenant_id == tenant_id,
                    AuditLog.property_id.in_(owner_properties),
                    AuditLog.severity == "critical",
                )
            )
            .order_by(desc(AuditLog.created_at))
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def get_action_summary(
        self,
        tenant_id: UUID,
        user_id: Optional[UUID] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> List[Tuple[str, int]]:
        """Get count of actions grouped by action type."""
        owner_properties = await self._get_user_properties(tenant_id, user_id)
        
        if not owner_properties:
            return []

        filters = [
            AuditLog.tenant_id == tenant_id,
            AuditLog.property_id.in_(owner_properties),
        ]

        if start_date:
            filters.append(AuditLog.created_at >= start_date)
        if end_date:
            filters.append(AuditLog.created_at <= end_date)

        stmt = (
            select(AuditLog.action, func.count(AuditLog.id))
            .where(and_(*filters))
            .group_by(AuditLog.action)
            .order_by(desc(func.count(AuditLog.id)))
        )
        result = await self.session.execute(stmt)
        return result.all()

    async def get_severity_summary(
        self,
        tenant_id: UUID,
        user_id: Optional[UUID] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> dict:
        """Get count of events by severity level."""
        owner_properties = await self._get_user_properties(tenant_id, user_id)
        
        if not owner_properties:
            return {"low": 0, "medium": 0, "warning": 0, "critical": 0}

        filters = [
            AuditLog.tenant_id == tenant_id,
            AuditLog.property_id.in_(owner_properties),
        ]

        if start_date:
            filters.append(AuditLog.created_at >= start_date)
        if end_date:
            filters.append(AuditLog.created_at <= end_date)

        stmt = (
            select(AuditLog.severity, func.count(AuditLog.id))
            .where(and_(*filters))
            .group_by(AuditLog.severity)
        )
        result = await self.session.execute(stmt)
        return {row[0]: row[1] for row in result.all()}

    async def _get_user_properties(
        self,
        tenant_id: UUID,
        user_id: Optional[UUID] = None,
    ) -> List[UUID]:
        """
        Get property IDs accessible to user.
        Returns owner's properties from OwnerDetails.
        """
        if not user_id:
            # Get all tenant properties (for super admin access)
            stmt = select(Property.id).where(Property.tenant_id == tenant_id)
            result = await self.session.execute(stmt)
            return result.scalars().all()

        # Get properties where user is owner
        from app.models.models import User
        
        user_stmt = select(User).where(
            User.id == user_id,
            User.tenant_id == tenant_id,
        )
        user_result = await self.session.execute(user_stmt)
        user = user_result.scalar_one_or_none()

        # If user has direct property assignment
        if user and user.property_id:
            return [user.property_id]

        # Get via OwnerDetails
        owner_stmt = (
            select(OwnerDetails.property_id)
            .where(OwnerDetails.tenant_id == tenant_id)
        )
        owner_result = await self.session.execute(owner_stmt)
        property_ids = owner_result.scalars().all()

        return property_ids if property_ids else []

    async def count_events_by_resource(
        self,
        tenant_id: UUID,
        user_id: Optional[UUID] = None,
    ) -> List[Tuple[str, int]]:
        """Get count of events grouped by resource type."""
        owner_properties = await self._get_user_properties(tenant_id, user_id)
        
        if not owner_properties:
            return []

        stmt = (
            select(AuditLog.resource_type, func.count(AuditLog.id))
            .where(
                and_(
                    AuditLog.tenant_id == tenant_id,
                    AuditLog.property_id.in_(owner_properties),
                )
            )
            .group_by(AuditLog.resource_type)
            .order_by(desc(func.count(AuditLog.id)))
        )
        result = await self.session.execute(stmt)
        return result.all()
