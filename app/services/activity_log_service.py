"""
Activity Log Service

Handles business logic for retrieving and analyzing activity logs.
Filters logs based on owner's properties for role-based access.
"""

from datetime import datetime, timedelta
from typing import Optional, List, Dict, Tuple
from uuid import UUID

from sqlalchemy import select, and_, desc, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import AuditLog, Property, OwnerDetails, User


class ActivityLogService:
    """Service for managing activity logs with owner-based filtering."""

    @staticmethod
    async def get_owner_properties(
        db: AsyncSession,
        tenant_id: UUID,
        user_id: Optional[UUID] = None,
    ) -> List[UUID]:
        """
        Get all property IDs that the owner has access to.
        For owner role: returns only their assigned properties.
        For super admin: returns all tenant properties.
        """
        # Check if user is owner - get properties assigned to owner user
        if user_id:
            user_result = await db.execute(
                select(User).where(
                    User.id == user_id,
                    User.tenant_id == tenant_id,
                )
            )
            user = user_result.scalar_one_or_none()
            
            if user and user.property_id:
                # Owner has a specific property assigned
                return [user.property_id]
            
            # Check if user has multiple properties via OwnerDetails
            owner_details_result = await db.execute(
                select(OwnerDetails.property_id).where(
                    OwnerDetails.tenant_id == tenant_id,
                )
            )
            property_ids = owner_details_result.scalars().all()
            if property_ids:
                return property_ids

        # Fallback: return all tenant properties (for super admin or full access)
        properties_result = await db.execute(
            select(Property.id).where(Property.tenant_id == tenant_id)
        )
        return properties_result.scalars().all()

    @staticmethod
    async def get_activity_logs(
        db: AsyncSession,
        tenant_id: UUID,
        user_id: Optional[UUID] = None,
        property_ids: Optional[List[UUID]] = None,
        skip: int = 0,
        limit: int = 50,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        action_type: Optional[str] = None,
        severity: Optional[str] = None,
        resource_type: Optional[str] = None,
    ) -> Tuple[List[AuditLog], int]:
        """
        Retrieve activity logs with filtering.
        
        Args:
            db: Database session
            tenant_id: Tenant ID
            user_id: Current user ID (for owner property filtering)
            property_ids: Specific property IDs to filter (if None, gets owner's properties)
            skip: Pagination skip
            limit: Pagination limit
            start_date: Filter from date
            end_date: Filter to date
            action_type: Filter by action type
            severity: Filter by severity level
            resource_type: Filter by resource type
            
        Returns:
            Tuple of (logs, total_count)
        """
        # Get properties to filter by
        if property_ids is None:
            property_ids = await ActivityLogService.get_owner_properties(
                db, tenant_id, user_id
            )
        
        if not property_ids:
            return [], 0

        # Build base query
        filters = [
            AuditLog.tenant_id == tenant_id,
            AuditLog.property_id.in_(property_ids),
        ]

        # Add optional filters
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

        # Get total count
        count_query = select(func.count(AuditLog.id)).where(and_(*filters))
        count_result = await db.execute(count_query)
        total = count_result.scalar()

        # Get paginated logs
        query = (
            select(AuditLog)
            .where(and_(*filters))
            .order_by(desc(AuditLog.created_at))
            .offset(skip)
            .limit(limit)
        )
        
        result = await db.execute(query)
        logs = result.scalars().all()

        return logs, total

    @staticmethod
    async def get_property_activity_logs(
        db: AsyncSession,
        tenant_id: UUID,
        property_id: UUID,
        user_id: Optional[UUID] = None,
        skip: int = 0,
        limit: int = 50,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        action_type: Optional[str] = None,
        severity: Optional[str] = None,
    ) -> Tuple[List[AuditLog], int]:
        """
        Get activity logs for a specific property.
        Ensures user has access to this property.
        """
        # Verify user has access to this property
        owner_properties = await ActivityLogService.get_owner_properties(
            db, tenant_id, user_id
        )
        
        if property_id not in owner_properties:
            raise PermissionError(f"Access denied to property {property_id}")

        return await ActivityLogService.get_activity_logs(
            db=db,
            tenant_id=tenant_id,
            user_id=user_id,
            property_ids=[property_id],
            skip=skip,
            limit=limit,
            start_date=start_date,
            end_date=end_date,
            action_type=action_type,
            severity=severity,
        )

    @staticmethod
    async def get_activity_summary(
        db: AsyncSession,
        tenant_id: UUID,
        user_id: Optional[UUID] = None,
        property_ids: Optional[List[UUID]] = None,
        days: int = 7,
    ) -> Dict:
        """
        Get activity summary statistics.
        
        Returns:
            Dictionary with summary data:
            - total_events: Total number of events
            - warnings: Count of warning severity
            - critical: Count of critical severity
            - by_action: Count of events grouped by action
            - by_resource: Count of events grouped by resource type
            - by_severity: Count of events grouped by severity
        """
        # Get properties to filter by
        if property_ids is None:
            property_ids = await ActivityLogService.get_owner_properties(
                db, tenant_id, user_id
            )
        
        if not property_ids:
            return {
                "total_events": 0,
                "warnings": 0,
                "critical": 0,
                "by_action": [],
                "by_resource": [],
                "by_severity": [],
                "log_size_gb": 0.0,
            }

        # Calculate date range
        end_date = datetime.utcnow()
        start_date = end_date - timedelta(days=days)

        filters = [
            AuditLog.tenant_id == tenant_id,
            AuditLog.property_id.in_(property_ids),
            AuditLog.created_at >= start_date,
            AuditLog.created_at <= end_date,
        ]

        # Total events
        total_query = select(func.count(AuditLog.id)).where(and_(*filters))
        total_result = await db.execute(total_query)
        total_events = total_result.scalar()

        # Events by severity
        severity_query = (
            select(AuditLog.severity, func.count(AuditLog.id))
            .where(and_(*filters))
            .group_by(AuditLog.severity)
        )
        severity_result = await db.execute(severity_query)
        severity_counts = {row[0]: row[1] for row in severity_result.all()}

        # Events by action
        action_query = (
            select(AuditLog.action, func.count(AuditLog.id))
            .where(and_(*filters))
            .group_by(AuditLog.action)
            .order_by(desc(func.count(AuditLog.id)))
            .limit(10)
        )
        action_result = await db.execute(action_query)
        by_action = [
            {"action": row[0], "count": row[1]}
            for row in action_result.all()
        ]

        # Events by resource type
        resource_query = (
            select(AuditLog.resource_type, func.count(AuditLog.id))
            .where(and_(*filters))
            .group_by(AuditLog.resource_type)
            .order_by(desc(func.count(AuditLog.id)))
            .limit(10)
        )
        resource_result = await db.execute(resource_query)
        by_resource = [
            {"resource_type": row[0], "count": row[1]}
            for row in resource_result.all()
        ]

        return {
            "total_events": total_events,
            "warnings": severity_counts.get("warning", 0),
            "critical": severity_counts.get("critical", 0),
            "by_action": by_action,
            "by_resource": by_resource,
            "by_severity": [
                {"severity": k, "count": v}
                for k, v in severity_counts.items()
            ],
            "log_size_gb": round(total_events * 0.001, 2),  # Estimate
        }

    @staticmethod
    async def get_critical_events(
        db: AsyncSession,
        tenant_id: UUID,
        user_id: Optional[UUID] = None,
        property_ids: Optional[List[UUID]] = None,
        limit: int = 10,
    ) -> List[AuditLog]:
        """
        Get recent critical events.
        """
        if property_ids is None:
            property_ids = await ActivityLogService.get_owner_properties(
                db, tenant_id, user_id
            )
        
        if not property_ids:
            return []

        query = (
            select(AuditLog)
            .where(
                and_(
                    AuditLog.tenant_id == tenant_id,
                    AuditLog.property_id.in_(property_ids),
                    AuditLog.severity == "critical",
                )
            )
            .order_by(desc(AuditLog.created_at))
            .limit(limit)
        )
        
        result = await db.execute(query)
        return result.scalars().all()

    @staticmethod
    async def filter_logs_by_date_range(
        db: AsyncSession,
        tenant_id: UUID,
        property_ids: List[UUID],
        days_back: int = 7,
    ) -> List[AuditLog]:
        """
        Get logs from the last N days.
        """
        end_date = datetime.utcnow()
        start_date = end_date - timedelta(days=days_back)

        query = (
            select(AuditLog)
            .where(
                and_(
                    AuditLog.tenant_id == tenant_id,
                    AuditLog.property_id.in_(property_ids),
                    AuditLog.created_at >= start_date,
                    AuditLog.created_at <= end_date,
                )
            )
            .order_by(desc(AuditLog.created_at))
        )
        
        result = await db.execute(query)
        return result.scalars().all()
