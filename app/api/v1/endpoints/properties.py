"""
Properties Routes - app/api/v1/endpoints/properties.py

Full CRUD for Properties + nested OwnerDetails.
Tenant isolation enforced via JWT tenant_id.
"""

from datetime import datetime
from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user, require_permission
from app.core.database import get_db
from app.models.models import OwnerDetails, Property
from app.schemas.schemas import (
    OwnerDetailsCreate, OwnerDetailsResponse, OwnerDetailsUpdate,
    PropertyCreate, PropertyResponse, PropertyUpdate,
)

router = APIRouter(prefix="/properties", tags=["Properties"])


# ── Helpers ──────────────────────────────────────────────

async def _get_property_or_404(db: AsyncSession, property_id: UUID, tenant_id: UUID) -> Property:
    result = await db.execute(
        select(Property).where(
            Property.id == property_id,
            Property.tenant_id == tenant_id,
            Property.deleted_at == None,
        )
    )
    prop = result.scalar_one_or_none()
    if not prop:
        raise HTTPException(status_code=404, detail="Property not found")
    return prop


# ── Property CRUD ─────────────────────────────────────────

@router.post("/", response_model=PropertyResponse, status_code=status.HTTP_201_CREATED)
async def create_property(
    data: PropertyCreate,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_permission("manage_property")),
):
    tenant_id = UUID(user["tenant_id"])

    # Check duplicate name within tenant
    dup = await db.execute(
        select(Property).where(
            Property.tenant_id == tenant_id,
            Property.name == data.name,
            Property.deleted_at == None,
        )
    )
    if dup.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="A property with this name already exists")

    prop = Property(
        tenant_id=tenant_id,
        **data.model_dump(),
    )
    db.add(prop)
    await db.commit()
    await db.refresh(prop)
    return prop


@router.get("/", response_model=List[PropertyResponse])
async def list_properties(
    skip: int = 0,
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_permission("manage_property")),
):
    tenant_id = UUID(user["tenant_id"])
    result = await db.execute(
        select(Property)
        .where(Property.tenant_id == tenant_id, Property.deleted_at == None)
        .offset(skip)
        .limit(limit)
    )
    return result.scalars().all()


@router.get("/{property_id}", response_model=PropertyResponse)
async def get_property(
    property_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_permission("manage_property")),
):
    return await _get_property_or_404(db, property_id, UUID(user["tenant_id"]))


@router.put("/{property_id}", response_model=PropertyResponse)
async def update_property(
    property_id: UUID,
    data: PropertyUpdate,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_permission("manage_property")),
):
    prop = await _get_property_or_404(db, property_id, UUID(user["tenant_id"]))
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(prop, k, v)
    await db.commit()
    await db.refresh(prop)
    return prop


@router.delete("/{property_id}", status_code=status.HTTP_200_OK)
async def delete_property(
    property_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_permission("manage_property")),
):
    prop = await _get_property_or_404(db, property_id, UUID(user["tenant_id"]))
    prop.deleted_at = datetime.utcnow()
    await db.commit()
    return {"message": "Property deleted successfully"}


# ── Owner Details ─────────────────────────────────────────

@router.post("/{property_id}/owner", response_model=OwnerDetailsResponse, status_code=201)
async def create_owner(
    property_id: UUID,
    data: OwnerDetailsCreate,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_permission("manage_owner")),
):
    tenant_id = UUID(user["tenant_id"])
    await _get_property_or_404(db, property_id, tenant_id)

    owner = OwnerDetails(tenant_id=tenant_id, property_id=property_id, **data.model_dump())
    db.add(owner)
    await db.commit()
    await db.refresh(owner)
    return owner


@router.get("/{property_id}/owner", response_model=List[OwnerDetailsResponse])
async def list_owners(
    property_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_permission("view_owner")),
):
    tenant_id = UUID(user["tenant_id"])
    await _get_property_or_404(db, property_id, tenant_id)
    result = await db.execute(
        select(OwnerDetails).where(
            OwnerDetails.property_id == property_id,
            OwnerDetails.tenant_id == tenant_id,
        )
    )
    return result.scalars().all()


@router.put("/{property_id}/owner/{owner_id}", response_model=OwnerDetailsResponse)
async def update_owner(
    property_id: UUID,
    owner_id: UUID,
    data: OwnerDetailsUpdate,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_permission("manage_owner")),
):
    result = await db.execute(
        select(OwnerDetails).where(
            OwnerDetails.id == owner_id,
            OwnerDetails.property_id == property_id,
            OwnerDetails.tenant_id == UUID(user["tenant_id"]),
        )
    )
    owner = result.scalar_one_or_none()
    if not owner:
        raise HTTPException(status_code=404, detail="Owner not found")

    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(owner, k, v)
    await db.commit()
    await db.refresh(owner)
    return owner
