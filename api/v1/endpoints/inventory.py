from typing import Any, List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from app.permission_checker import require_permission
from api import dependencies
from crud.inventory import inventory_item
from crud.inventory import (
    InventoryItemCreate, InventoryItemUpdate, InventoryItemInDB
)
from db_connection import get_db
from models.user import User

router = APIRouter()


@router.post("/items", response_model=InventoryItemInDB, status_code=status.HTTP_201_CREATED)
def create_item(
    *,
    db: Session = Depends(get_db),
    obj_in: InventoryItemCreate,
    current_user: User = Depends(dependencies.get_current_user),
    user=Depends(require_permission("manage_inventory"))  # ADDED
) -> Any:
    """
    Create a new inventory item.
    Only Tenant Admin and Super Admin can create inventory items.
    """
    return inventory_item.create(
        db,
        obj_in=obj_in,
        tenant_id=current_user.tenant_id,
        property_id=current_user.property_id
    )


@router.get("/items", response_model=List[InventoryItemInDB])
def list_items(
    db: Session = Depends(get_db),
    skip: int = Query(0, description="Skip the first N items"),
    limit: int = Query(100, description="Limit the number of results"),
    property_id: Optional[str] = Query(None, description="Filter items by a specific property ID"),
    current_user: User = Depends(dependencies.get_current_user),
    user=Depends(require_permission("view_inventory"))    # ADDED
) -> Any:
    """
    Retrieve inventory items. Optionally filter by property ID.
    All roles can view inventory.
    """
    return inventory_item.get_multi_by_property(
        db,
        tenant_id=current_user.tenant_id,
        property_id=property_id,
        skip=skip,
        limit=limit
    )


@router.patch("/items/{id}", response_model=InventoryItemInDB)
def update_item(
    *,
    db: Session = Depends(get_db),
    id: int,
    obj_in: InventoryItemUpdate,
    current_user: User = Depends(dependencies.get_current_user),
    user=Depends(require_permission("manage_inventory"))  # ADDED
) -> Any:
    """
    Update an inventory item.
    Only Tenant Admin and Super Admin can update inventory items.
    """
    db_obj = inventory_item.get(db, id=id, tenant_id=current_user.tenant_id)
    if not db_obj:
        raise HTTPException(status_code=404, detail="Inventory Item not found")
    return inventory_item.update(db, db_obj=db_obj, obj_in=obj_in)