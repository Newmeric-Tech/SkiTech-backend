"""
SOP Routes - app/api/v1/endpoints/sop.py

Full CRUD for SOP Categories, Items, Versions.
Role-based visibility enforced (Staff sees only their department's SOPs).
"""

from typing import List
from uuid import UUID

import boto3
from botocore.exceptions import ClientError
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import require_permission
from app.core.config import settings
from app.core.database import get_db
from app.models.models import SOPCategory, SOPItem, SOPVersion
from app.schemas.schemas import (
    SOPCategoryCreate, SOPCategoryResponse,
    SOPCreate, SOPResponse, SOPUpdate,
    SOPVersionCreate, SOPVersionResponse,
    SOPExecutionResponse,
)

router = APIRouter(prefix="/sop", tags=["SOP"])


def _apply_sop_visibility(q, user: dict):
    """Apply role-based filter to SOP queries."""
    role = user.get("role", "")
    tenant_id = UUID(user["tenant_id"])
    q = q.where(SOPItem.tenant_id == tenant_id)

    if role == "Staff":
        dept_id = user.get("department_id")
        if dept_id:
            q = q.where(SOPItem.department_id == UUID(dept_id))
    elif role == "Manager":
        prop_id = user.get("property_id")
        if prop_id:
            q = q.where(SOPItem.property_id == UUID(prop_id))
    # Admin / Tenant Admin / Super Admin see all

    return q


# ── Categories ────────────────────────────────────────────

@router.post("/categories", response_model=SOPCategoryResponse, status_code=201)
async def create_category(
    property_id: UUID,
    data: SOPCategoryCreate,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_permission("create_sop")),
):
    cat = SOPCategory(
        tenant_id=UUID(user["tenant_id"]),
        property_id=property_id,
        **data.model_dump(),
    )
    db.add(cat)
    await db.commit()
    await db.refresh(cat)
    return cat


@router.get("/categories/{property_id}", response_model=List[SOPCategoryResponse])
async def list_categories(
    property_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_permission("view_sop")),
):
    result = await db.execute(
        select(SOPCategory).where(
            SOPCategory.property_id == property_id,
            SOPCategory.tenant_id == UUID(user["tenant_id"]),
            SOPCategory.deleted_at == None,
        )
    )
    return result.scalars().all()


# ── SOP Items ─────────────────────────────────────────────

@router.post("/items", response_model=SOPResponse, status_code=201)
async def create_sop(
    property_id: UUID,
    data: SOPCreate,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_permission("create_sop")),
):
    sop = SOPItem(
        tenant_id=UUID(user["tenant_id"]),
        property_id=property_id,
        **data.model_dump(),
    )
    db.add(sop)
    await db.flush()

    if sop.assigned_employee_id:
        employee = await db.get(Employee, sop.assigned_employee_id)
        if employee and employee.user_id:
            execution = SOPExecution(
                sop_id=sop.id,
                user_id=employee.user_id,
                property_id=sop.property_id,
                tenant_id=sop.tenant_id,
                status="pending"
            )
            db.add(execution)

    await db.commit()
    await db.refresh(sop)
    return sop


@router.get("/items/{property_id}", response_model=List[SOPResponse])
async def list_sops(
    property_id: UUID,
    category_id: UUID = None,
    department_id: UUID = None,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_permission("view_sop")),
):
    q = select(SOPItem).where(
        SOPItem.property_id == property_id,
        SOPItem.deleted_at == None,
    )
    q = _apply_sop_visibility(q, user)
    if category_id:
        q = q.where(SOPItem.category_id == category_id)
    if department_id:
        q = q.where(SOPItem.department_id == department_id)
    result = await db.execute(q)
    return result.scalars().all()


@router.get("/items/detail/{sop_id}", response_model=SOPResponse)
async def get_sop(
    sop_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_permission("view_sop")),
):
    result = await db.execute(
        select(SOPItem).where(
            SOPItem.id == sop_id,
            SOPItem.tenant_id == UUID(user["tenant_id"]),
        )
    )
    sop = result.scalar_one_or_none()
    if not sop:
        raise HTTPException(status_code=404, detail="SOP not found")
    return sop


@router.put("/items/{sop_id}", response_model=SOPResponse)
async def update_sop(
    sop_id: UUID,
    data: SOPUpdate,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_permission("update_sop")),
):
    result = await db.execute(
        select(SOPItem).where(
            SOPItem.id == sop_id,
            SOPItem.tenant_id == UUID(user["tenant_id"]),
        )
    )
    sop = result.scalar_one_or_none()
    if not sop:
        raise HTTPException(status_code=404, detail="SOP not found")
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(sop, k, v)
    await db.commit()
    await db.refresh(sop)
    return sop


@router.delete("/items/{sop_id}")
async def delete_sop(
    sop_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_permission("delete_sop")),
):
    from datetime import datetime
    result = await db.execute(
        select(SOPItem).where(
            SOPItem.id == sop_id,
            SOPItem.tenant_id == UUID(user["tenant_id"]),
        )
    )
    sop = result.scalar_one_or_none()
    if not sop:
        raise HTTPException(status_code=404, detail="SOP not found")
    sop.deleted_at = datetime.utcnow()
    await db.commit()
    return {"message": "SOP deleted"}


# ── Versions ──────────────────────────────────────────────

@router.post("/items/{sop_id}/versions", response_model=SOPVersionResponse, status_code=201)
async def create_version(
    sop_id: UUID,
    data: SOPVersionCreate,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_permission("update_sop")),
):
    result = await db.execute(
        select(SOPItem).where(SOPItem.id == sop_id, SOPItem.tenant_id == UUID(user["tenant_id"]))
    )
    sop = result.scalar_one_or_none()
    if not sop:
        raise HTTPException(status_code=404, detail="SOP not found")

    version = SOPVersion(
        sop_item_id=sop_id,
        tenant_id=sop.tenant_id,
        property_id=sop.property_id,
        version_number=data.version_number,
        content=data.content,
        created_by=UUID(user["user_id"]) if user.get("user_id") else None,
    )
    db.add(version)
    await db.commit()
    await db.refresh(version)
    return version


@router.get("/items/{sop_id}/versions", response_model=List[SOPVersionResponse])
async def list_versions(
    sop_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_permission("view_sop")),
):
    result = await db.execute(
        select(SOPVersion).where(SOPVersion.sop_item_id == sop_id)
    )
    return result.scalars().all()

@router.post("/complete/{execution_id}")
async def complete_sop(
    execution_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_permission("view_sop")),
):
    from datetime import datetime

    result = await db.execute(
        select(SOPExecution).where(
            SOPExecution.id == execution_id,
            SOPExecution.user_id == UUID(user["user_id"])
        )
    )

    exec_obj = result.scalar_one_or_none()

    if not exec_obj:
        raise HTTPException(status_code=404, detail="Task not found")

    exec_obj.status = "completed"
    exec_obj.completed_at = datetime.utcnow()

    await db.commit()

    return {"message": "SOP completed successfully"}

@router.get("/my-tasks", response_model=List[SOPExecutionResponse])
async def my_sops(
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_permission("view_sop")),
):
    result = await db.execute(
        select(SOPExecution).where(
            SOPExecution.user_id == UUID(user["user_id"])
        )
    )

    return result.scalars().all()


# ── S3 Upload ─────────────────────────────────────────────

@router.post("/upload/presigned-url")
def get_sop_upload_url(
    filename: str = Query(..., description="Name of the file to upload"),
    file_type: str = Query(..., description="MIME type of the file (e.g. application/pdf)"),
    user: dict = Depends(require_permission("create_sop")),
):
    """
    Generate a pre-signed S3 URL to upload a SOP document directly from the client.
    The file is scoped under the tenant's folder: {tenant_id}/sops/{filename}
    """
    if not settings.AWS_ACCESS_KEY_ID or not settings.AWS_SECRET_ACCESS_KEY:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="S3 upload is not configured on this server"
        )

    tenant_id = user.get("tenant_id", "unknown")
    object_key = f"{tenant_id}/sops/{filename}"

    try:
        s3 = boto3.client(
            "s3",
            region_name=settings.AWS_REGION,
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
        )
        presigned_url = s3.generate_presigned_url(
            "put_object",
            Params={
                "Bucket": settings.S3_SOP_BUCKET,
                "Key": object_key,
                "ContentType": file_type,
            },
            ExpiresIn=3600,
        )
        return {"upload_url": presigned_url, "file_key": object_key}
    except ClientError as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))