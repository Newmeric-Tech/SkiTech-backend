"""
Stats Routes - app/api/v1/endpoints/stats.py

GET /stats/owner               → Owner dashboard stats
GET /stats/manager/{property_id} → Manager dashboard stats
GET /stats/staff/me            → Staff dashboard stats
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user, require_roles
from app.core.database import get_db
from app.schemas.schemas import (
    ManagerStatsResponse, OwnerStatsResponse, StaffStatsResponse,
)
from app.services.stats_service import (
    get_manager_stats, get_owner_stats, get_staff_stats,
)

router = APIRouter(prefix="/stats", tags=["Stats"])


@router.get("/owner", response_model=OwnerStatsResponse)
async def owner_stats(
    property_id: UUID = None,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_roles(["Super Admin", "Tenant Admin"])),
):
    """
    Owner dashboard stats.
    Optional property_id filter — if not given, aggregates across all properties.
    """
    tenant_id_str = user.get("tenant_id") or ""
    if not tenant_id_str:
        raise HTTPException(status_code=400, detail="No tenant assigned to this account")
    return await get_owner_stats(
        db=db,
        tenant_id=UUID(tenant_id_str),
        property_id=property_id,
    )


@router.get("/manager/{property_id}", response_model=ManagerStatsResponse)
async def manager_stats(
    property_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_roles(["Super Admin", "Tenant Admin", "Manager"])),
):
    """Manager dashboard stats — scoped to a specific property."""
    tenant_id_str = user.get("tenant_id") or ""
    if not tenant_id_str:
        raise HTTPException(status_code=400, detail="No tenant assigned to this account")
    return await get_manager_stats(
        db=db,
        tenant_id=UUID(tenant_id_str),
        property_id=property_id,
    )


@router.get("/staff/me", response_model=StaffStatsResponse)
async def staff_stats(
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """Staff dashboard stats — scoped to the logged-in user only."""
    tenant_id_str = user.get("tenant_id") or ""
    if not tenant_id_str:
        raise HTTPException(status_code=400, detail="No tenant assigned to this account")
    return await get_staff_stats(
        db=db,
        tenant_id=UUID(tenant_id_str),
        user_id=UUID(user["user_id"]),
    )