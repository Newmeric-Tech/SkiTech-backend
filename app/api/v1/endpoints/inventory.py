"""
Inventory Routes - app/api/v1/endpoints/inventory.py

Full inventory CRUD + stock movements (add / remove / adjust).
"""

from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import require_permission
from app.core.database import get_db
from app.models.models import InventoryItem, InventoryMovement, LowStockAlert
from app.schemas.schemas import (
    AdjustStockRequest, InventoryCreate, InventoryResponse,
    InventoryUpdate, StockAdjustRequest,
)

router = APIRouter(prefix="/inventory", tags=["Inventory"])


async def _get_item(db: AsyncSession, item_id: UUID, tenant_id: UUID) -> InventoryItem:
    result = await db.execute(
        select(InventoryItem).where(
            InventoryItem.id == item_id,
            InventoryItem.tenant_id == tenant_id,
            InventoryItem.deleted_at == None,
        )
    )
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Inventory item not found")
    return item


@router.post("/{property_id}", response_model=InventoryResponse, status_code=201)
async def create_item(
    property_id: UUID,
    data: InventoryCreate,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_permission("manage_inventory")),
):
    item = InventoryItem(
        tenant_id=UUID(user["tenant_id"]),
        property_id=property_id,
        **data.model_dump(),
    )
    db.add(item)
    await db.commit()
    await db.refresh(item)
    return item


@router.get("/{property_id}", response_model=List[InventoryResponse])
async def list_items(
    property_id: UUID,
    department_id: UUID = None,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_permission("view_inventory")),
):
    q = select(InventoryItem).where(
        InventoryItem.property_id == property_id,
        InventoryItem.tenant_id == UUID(user["tenant_id"]),
        InventoryItem.deleted_at == None,
    )
    if department_id:
        q = q.where(InventoryItem.department_id == department_id)
    result = await db.execute(q)
    return result.scalars().all()


@router.get("/item/{item_id}", response_model=InventoryResponse)
async def get_item(
    item_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_permission("view_inventory")),
):
    return await _get_item(db, item_id, UUID(user["tenant_id"]))


@router.put("/item/{item_id}", response_model=InventoryResponse)
async def update_item(
    item_id: UUID,
    data: InventoryUpdate,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_permission("manage_inventory")),
):
    item = await _get_item(db, item_id, UUID(user["tenant_id"]))
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(item, k, v)
    await db.commit()
    await db.refresh(item)
    return item


@router.delete("/item/{item_id}")
async def delete_item(
    item_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_permission("manage_inventory")),
):
    from datetime import datetime
    item = await _get_item(db, item_id, UUID(user["tenant_id"]))
    item.deleted_at = datetime.utcnow()
    await db.commit()
    return {"message": "Inventory item deleted"}


# ── Stock Movements ───────────────────────────────────────

async def _record_movement(
    db: AsyncSession, item: InventoryItem, movement_type: str,
    quantity: int, user: dict, notes: str = None,
    vendor_id: UUID = None, department_id: UUID = None,
):
    movement = InventoryMovement(
        tenant_id=item.tenant_id,
        property_id=item.property_id,
        item_id=item.id,
        movement_type=movement_type,
        quantity=quantity,
        notes=notes,
        vendor_id=vendor_id,
        department_id=department_id,
        performed_by=UUID(user["user_id"]) if user.get("user_id") else None,
    )
    db.add(movement)

    # Check low stock alert
    if item.reorder_level and item.quantity <= item.reorder_level:
        alert = LowStockAlert(
            item_id=item.id,
            tenant_id=item.tenant_id,
            property_id=item.property_id,
            current_qty=item.quantity,
            threshold_qty=item.reorder_level,
        )
        db.add(alert)


@router.post("/item/{item_id}/add-stock", response_model=InventoryResponse)
async def add_stock(
    item_id: UUID,
    data: StockAdjustRequest,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_permission("manage_inventory")),
):
    item = await _get_item(db, item_id, UUID(user["tenant_id"]))
    item.quantity += data.quantity
    await _record_movement(db, item, "IN", data.quantity, user, data.notes, data.vendor_id, data.department_id)
    await db.commit()
    await db.refresh(item)
    return item


@router.post("/item/{item_id}/remove-stock", response_model=InventoryResponse)
async def remove_stock(
    item_id: UUID,
    data: StockAdjustRequest,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_permission("manage_inventory")),
):
    item = await _get_item(db, item_id, UUID(user["tenant_id"]))
    if item.quantity < data.quantity:
        raise HTTPException(status_code=400, detail="Not enough stock available")
    item.quantity -= data.quantity
    await _record_movement(db, item, "OUT", data.quantity, user, data.notes, department_id=data.department_id)
    await db.commit()
    await db.refresh(item)
    return item


@router.post("/item/{item_id}/adjust-stock", response_model=InventoryResponse)
async def adjust_stock(
    item_id: UUID,
    data: AdjustStockRequest,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_permission("manage_inventory")),
):
    item = await _get_item(db, item_id, UUID(user["tenant_id"]))
    diff = abs(data.new_quantity - item.quantity)
    item.quantity = data.new_quantity
    await _record_movement(db, item, "ADJUST", diff, user, data.notes)
    await db.commit()
    await db.refresh(item)
    return item
