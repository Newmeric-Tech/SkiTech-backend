"""
Governance Service

Handles approval workflows and governance processes.
Manages workflow instances and approval state transitions.
"""

from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.models.governance import GovernanceWorkflow, WorkflowInstance
from app.schemas.governance import (
    GovernanceWorkflowCreate,
    WorkflowInstanceCreate,
)


class GovernanceService:
    """Service for governance and workflow operations"""

    def __init__(self, db: AsyncSession):
        """
        Initialize governance service with database session

        Args:
            db: SQLAlchemy async session
        """
        self.db = db

    # Workflow Template Operations

    async def get_workflow_template(self, workflow_id: int) -> Optional[GovernanceWorkflow]:
        """
        Get workflow template by ID

        Args:
            workflow_id: Workflow template ID

        Returns:
            GovernanceWorkflow if found, None otherwise
        """
        result = await self.db.execute(
            select(GovernanceWorkflow).where(GovernanceWorkflow.id == workflow_id)
        )
        return result.scalar_one_or_none()

    async def create_workflow_template(
        self, workflow_data: GovernanceWorkflowCreate
    ) -> GovernanceWorkflow:
        """
        Create new workflow template

        Args:
            workflow_data: GovernanceWorkflowCreate schema

        Returns:
            Created GovernanceWorkflow
        """
        workflow = GovernanceWorkflow(**workflow_data.dict())
        self.db.add(workflow)
        await self.db.commit()
        await self.db.refresh(workflow)
        return workflow

    # Workflow Instance Operations

    async def get_workflow_instance(
        self, instance_id: int
    ) -> Optional[WorkflowInstance]:
        """
        Get workflow instance by ID

        Args:
            instance_id: Workflow instance ID

        Returns:
            WorkflowInstance if found, None otherwise
        """
        result = await self.db.execute(
            select(WorkflowInstance).where(WorkflowInstance.id == instance_id)
        )
        return result.scalar_one_or_none()

    async def create_workflow_instance(
        self, instance_data: WorkflowInstanceCreate
    ) -> WorkflowInstance:
        """
        Create new workflow instance (initiate approval process)

        Args:
            instance_data: WorkflowInstanceCreate schema

        Returns:
            Created WorkflowInstance
        """
        instance = WorkflowInstance(**instance_data.dict())
        self.db.add(instance)
        await self.db.commit()
        await self.db.refresh(instance)
        return instance

    async def approve_instance(
        self, instance: WorkflowInstance
    ) -> WorkflowInstance:
        """
        Approve workflow instance

        Args:
            instance: WorkflowInstance to approve

        Returns:
            Updated WorkflowInstance
        """
        instance.status = "approved"
        instance.current_step += 1
        await self.db.commit()
        await self.db.refresh(instance)
        return instance

    async def reject_instance(
        self, instance: WorkflowInstance, reason: str
    ) -> WorkflowInstance:
        """
        Reject workflow instance

        Args:
            instance: WorkflowInstance to reject
            reason: Reason for rejection

        Returns:
            Updated WorkflowInstance
        """
        instance.status = "rejected"
        instance.rejection_reason = reason
        await self.db.commit()
        await self.db.refresh(instance)
        return instance

    async def list_pending_workflows(
        self, approver_id: int, skip: int = 0, limit: int = 20
    ) -> tuple[list[WorkflowInstance], int]:
        """
        List pending workflows for a specific approver

        Args:
            approver_id: Approver user ID
            skip: Number to skip
            limit: Number to return

        Returns:
            Tuple of (list[WorkflowInstance], total_count)
        """
        query = select(WorkflowInstance).where(
            WorkflowInstance.current_approver_id == approver_id
        ).where(
            WorkflowInstance.status == "pending"
        )

        count_result = await self.db.execute(query.count())
        total = count_result.scalar()

        result = await self.db.execute(query.offset(skip).limit(limit))
        instances = result.scalars().all()
        return instances, total

    async def list_user_requests(
        self, user_id: int, skip: int = 0, limit: int = 20
    ) -> tuple[list[WorkflowInstance], int]:
        """
        List workflow instances created by a user

        Args:
            user_id: User ID who created the requests
            skip: Number to skip
            limit: Number to return

        Returns:
            Tuple of (list[WorkflowInstance], total_count)
        """
        query = select(WorkflowInstance).where(
            WorkflowInstance.requested_by_id == user_id
        )

        count_result = await self.db.execute(query.count())
        total = count_result.scalar()

        result = await self.db.execute(query.offset(skip).limit(limit))
        instances = result.scalars().all()
        return instances, total
