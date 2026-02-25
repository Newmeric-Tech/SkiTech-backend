"""
Governance Model - SQLAlchemy ORM Definition

Represents governance and approval workflows in the system.
Tracks workflow definitions, instances, and approval states.
"""

from typing import Optional

from sqlalchemy import String, Text, Boolean
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, IdMixin, SoftDeleteMixin, TimestampMixin


class GovernanceWorkflow(Base, IdMixin, TimestampMixin, SoftDeleteMixin):
    """
    Governance Workflow Model

    Represents a workflow template for approvals and governance processes.
    Can be instantiated for specific requests.
    """

    __tablename__ = "governance_workflows"

    # Workflow Definition
    name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    code: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)

    # Configuration
    # Define as JSON in production (using JSONB for PostgreSQL)
    # steps: Mapped[str] = mapped_column(Text, nullable=False)  # JSON string
    # approvers: Mapped[str] = mapped_column(Text, nullable=False)  # JSON string

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    def __repr__(self) -> str:
        return f"<GovernanceWorkflow (id={self.id}, name={self.name}, code={self.code})>"


class WorkflowInstance(Base, IdMixin, TimestampMixin, SoftDeleteMixin):
    """
    Workflow Instance Model

    Represents an instance of a workflow for a specific request or action.
    Tracks current approval status and history.
    """

    __tablename__ = "workflow_instances"

    # Reference to workflow template
    workflow_id: Mapped[int] = mapped_column(nullable=False, index=True)

    # Request Information
    request_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    request_id: Mapped[int] = mapped_column(nullable=False, index=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Approvals
    requested_by_id: Mapped[int] = mapped_column(nullable=False, index=True)
    current_approver_id: Mapped[Optional[int]] = mapped_column(nullable=True, index=True)

    # Status
    status: Mapped[str] = mapped_column(
        String(50),
        default="pending",
        nullable=False,
        index=True,
    )  # pending, approved, rejected

    # State tracking
    current_step: Mapped[int] = mapped_column(default=0, nullable=False)
    rejection_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    def __repr__(self) -> str:
        return (
            f"<WorkflowInstance (id={self.id}, workflow_id={self.workflow_id}, "
            f"status={self.status})>"
        )
