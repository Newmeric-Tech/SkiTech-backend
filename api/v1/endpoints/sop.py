from typing import Any, List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.permission_checker import require_permission
from api import dependencies
from crud.sop import sop_category, sop_item
from crud.sop import (
    SOPCategoryCreate, SOPCategoryUpdate, SOPCategoryInDB,
    SOPItemCreate, SOPItemUpdate, SOPItemInDB
)
from db_connection import get_db
from models.user import User

router = APIRouter()


# --- SOP Category Endpoints ---

@router.post("/category", response_model=SOPCategoryInDB, status_code=status.HTTP_201_CREATED)
def create_category(
    *,
    db: Session = Depends(get_db),
    obj_in: SOPCategoryCreate,
    current_user: User = Depends(dependencies.get_current_user),
    user=Depends(require_permission("create_sop"))   # ADDED
) -> Any:
    """
    Create a new SOP category.
    Only Managers and above can create SOPs.
    """
    return sop_category.create(
        db,
        obj_in=obj_in,
        tenant_id=current_user.tenant_id,
        property_id=current_user.property_id
    )


@router.get("/category", response_model=List[SOPCategoryInDB])
def list_categories(
    db: Session = Depends(get_db),
    skip: int = 0,
    limit: int = 100,
    current_user: User = Depends(dependencies.get_current_user),
    user=Depends(require_permission("view_sop"))     # ADDED
) -> Any:
    """
    Retrieve SOP categories.
    All roles can view SOPs.
    """
    return sop_category.get_multi(
        db,
        tenant_id=current_user.tenant_id,
        skip=skip,
        limit=limit
    )


@router.patch("/category/{id}", response_model=SOPCategoryInDB)
def update_category(
    *,
    db: Session = Depends(get_db),
    id: int,
    obj_in: SOPCategoryUpdate,
    current_user: User = Depends(dependencies.get_current_user),
    user=Depends(require_permission("update_sop"))   # ADDED
) -> Any:
    """
    Update an SOP category.
    Only Managers and above can update SOPs.
    """
    db_obj = sop_category.get(db, id=id, tenant_id=current_user.tenant_id)
    if not db_obj:
        raise HTTPException(status_code=404, detail="SOP Category not found")
    return sop_category.update(db, db_obj=db_obj, obj_in=obj_in)


# --- SOP Item Endpoints ---

@router.post("/items", response_model=SOPItemInDB, status_code=status.HTTP_201_CREATED)
def create_item(
    *,
    db: Session = Depends(get_db),
    obj_in: SOPItemCreate,
    current_user: User = Depends(dependencies.get_current_user),
    user=Depends(require_permission("create_sop"))   # ADDED
) -> Any:
    """
    Create a new SOP item.
    Only Managers and above can create SOP items.
    """
    category = sop_category.get(db, id=obj_in.category_id, tenant_id=current_user.tenant_id)
    if not category:
        raise HTTPException(status_code=404, detail="SOP Category not found")

    return sop_item.create(
        db,
        obj_in=obj_in,
        tenant_id=current_user.tenant_id,
        property_id=current_user.property_id
    )


@router.get("/items", response_model=List[SOPItemInDB])
def list_items(
    db: Session = Depends(get_db),
    skip: int = 0,
    limit: int = 100,
    current_user: User = Depends(dependencies.get_current_user),
    user=Depends(require_permission("view_sop"))     # ADDED
) -> Any:
    """
    Retrieve SOP items.
    All roles can view SOP items.
    """
    return sop_item.get_multi(
        db,
        tenant_id=current_user.tenant_id,
        skip=skip,
        limit=limit
    )