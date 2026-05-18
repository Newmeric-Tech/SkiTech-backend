"""
Governance Routes - app/api/v1/endpoints/governance.py

Approval workflows: templates + instances.
"""

from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user, require_roles
from app.core.database import get_db
from app.models.models import GovernanceWorkflow, WorkflowInstance
from app.schemas.schemas import (
    WorkflowCreate, WorkflowInstanceCreate,
    WorkflowInstanceResponse, WorkflowRejectRequest, WorkflowResponse,
)

router = APIRouter(prefix="/governance", tags=["Governance"])


@router.post("/workflows", response_model=WorkflowResponse, status_code=201)
async def create_workflow(
    data: WorkflowCreate,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_roles(["Super Admin", "Tenant Admin"])),
):
    wf = GovernanceWorkflow(**data.model_dump())
    db.add(wf)
    await db.commit()
    await db.refresh(wf)
    return wf


@router.get("/workflows", response_model=List[WorkflowResponse])
async def list_workflows(
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    result = await db.execute(
        select(GovernanceWorkflow).where(GovernanceWorkflow.deleted_at == None)
    )
    return result.scalars().all()


@router.post("/instances", response_model=WorkflowInstanceResponse, status_code=201)
async def create_instance(
    data: WorkflowInstanceCreate,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    instance = WorkflowInstance(
        **data.model_dump(),
        requested_by_id=UUID(user["user_id"]),
    )
    db.add(instance)
    await db.commit()
    await db.refresh(instance)
    return instance


@router.get("/instances", response_model=List[WorkflowInstanceResponse])
async def list_instances(
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    result = await db.execute(
        select(WorkflowInstance).where(WorkflowInstance.deleted_at == None)
    )
    return result.scalars().all()


@router.put("/instances/{instance_id}/approve", response_model=WorkflowInstanceResponse)
async def approve_instance(
    instance_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_roles(["Super Admin", "Tenant Admin", "Manager"])),
):
    result = await db.execute(
        select(WorkflowInstance).where(WorkflowInstance.id == instance_id)
    )
    instance = result.scalar_one_or_none()
    if not instance:
        raise HTTPException(status_code=404, detail="Workflow instance not found")
    if instance.status != "pending":
        raise HTTPException(status_code=400, detail=f"Cannot approve a '{instance.status}' instance")

    instance.status = "approved"
    instance.current_approver_id = UUID(user["user_id"])
    await db.commit()
    await db.refresh(instance)
    return instance


@router.put("/instances/{instance_id}/reject", response_model=WorkflowInstanceResponse)
async def reject_instance(
    instance_id: UUID,
    data: WorkflowRejectRequest,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_roles(["Super Admin", "Tenant Admin", "Manager"])),
):
    result = await db.execute(
        select(WorkflowInstance).where(WorkflowInstance.id == instance_id)
    )
    instance = result.scalar_one_or_none()
    if not instance:
        raise HTTPException(status_code=404, detail="Workflow instance not found")
    if instance.status != "pending":
        raise HTTPException(status_code=400, detail=f"Cannot reject a '{instance.status}' instance")

    instance.status = "rejected"
    instance.rejection_reason = data.reason
    instance.current_approver_id = UUID(user["user_id"])
    await db.commit()
    await db.refresh(instance)
    return instance
