"""
Audit Service

Handles audit logging for compliance and tracking.
Records all significant system actions.
"""

from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.core.constants import AUDIT_ACTION_CREATE
from app.models.audit import AuditLog


class AuditService:
    """Service for audit logging operations"""

    def __init__(self, db: AsyncSession):
        """
        Initialize audit service with database session

        Args:
            db: SQLAlchemy async session
        """
        self.db = db

    async def log_action(
        self,
        action: str,
        resource_type: str,
        resource_id: Optional[int] = None,
        user_id: Optional[int] = None,
        username: Optional[str] = None,
        details: Optional[str] = None,
        property_id: Optional[int] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        status: str = "success",
        error_message: Optional[str] = None,
    ) -> AuditLog:
        """
        Log an action to audit trail

        Args:
            action: Type of action (CREATE, READ, UPDATE, DELETE, etc.)
            resource_type: Type of resource affected
            resource_id: ID of affected resource
            user_id: ID of user performing action
            username: Username of user performing action
            details: Additional details (JSON string recommended)
            property_id: Property ID if applicable
            ip_address: Client IP address
            user_agent: Client user agent string
            status: Action status (success, failure)
            error_message: Error message if action failed

        Returns:
            Created AuditLog entry
        """
        log = AuditLog(
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            user_id=user_id,
            username=username,
            details=details,
            property_id=property_id,
            ip_address=ip_address,
            user_agent=user_agent,
            status=status,
            error_message=error_message,
        )
        self.db.add(log)
        await self.db.commit()
        await self.db.refresh(log)
        return log

    async def get_audit_log(self, log_id: int) -> Optional[AuditLog]:
        """
        Retrieve audit log entry by ID

        Args:
            log_id: Audit log ID

        Returns:
            AuditLog if found, None otherwise
        """
        result = await self.db.execute(
            select(AuditLog).where(AuditLog.id == log_id)
        )
        return result.scalar_one_or_none()

    async def list_logs_for_resource(
        self,
        resource_type: str,
        resource_id: int,
        skip: int = 0,
        limit: int = 50,
    ) -> tuple[list[AuditLog], int]:
        """
        List all audit logs for a specific resource

        Args:
            resource_type: Type of resource
            resource_id: ID of resource
            skip: Number to skip
            limit: Number to return

        Returns:
            Tuple of (list[AuditLog], total_count)
        """
        query = select(AuditLog).where(
            AuditLog.resource_type == resource_type
        ).where(
            AuditLog.resource_id == resource_id
        ).order_by(
            AuditLog.created_at.desc()
        )

        count_result = await self.db.execute(query.count())
        total = count_result.scalar()

        result = await self.db.execute(query.offset(skip).limit(limit))
        logs = result.scalars().all()
        return logs, total

    async def list_logs_for_user(
        self,
        user_id: int,
        skip: int = 0,
        limit: int = 50,
    ) -> tuple[list[AuditLog], int]:
        """
        List all audit logs for a specific user

        Args:
            user_id: User ID
            skip: Number to skip
            limit: Number to return

        Returns:
            Tuple of (list[AuditLog], total_count)
        """
        query = select(AuditLog).where(
            AuditLog.user_id == user_id
        ).order_by(
            AuditLog.created_at.desc()
        )

        count_result = await self.db.execute(query.count())
        total = count_result.scalar()

        result = await self.db.execute(query.offset(skip).limit(limit))
        logs = result.scalars().all()
        return logs, total

    async def list_logs_for_property(
        self,
        property_id: int,
        skip: int = 0,
        limit: int = 50,
    ) -> tuple[list[AuditLog], int]:
        """
        List all audit logs for a specific property

        Args:
            property_id: Property ID
            skip: Number to skip
            limit: Number to return

        Returns:
            Tuple of (list[AuditLog], total_count)
        """
        query = select(AuditLog).where(
            AuditLog.property_id == property_id
        ).order_by(
            AuditLog.created_at.desc()
        )

        count_result = await self.db.execute(query.count())
        total = count_result.scalar()

        result = await self.db.execute(query.offset(skip).limit(limit))
        logs = result.scalars().all()
        return logs, total
