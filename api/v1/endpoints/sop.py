import boto3
from typing import Any, List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query

from sqlalchemy.orm import Session
from app.core.permissions import require_permission
from api import dependencies
from crud.sop import sop_category, sop_item
from crud.sop import (
    SOPCategoryCreate, SOPCategoryUpdate, SOPCategoryInDB,
    SOPItemCreate, SOPItemUpdate, SOPItemInDB,
    sop_version, sop_audit, SOPVersionCreate, SOPVersionInDB, SOPAuditCreate, SOPAuditInDB
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
    from crud.department import department
    
    # Validate category exists
    category = sop_category.get(db, id=obj_in.category_id, tenant_id=current_user.tenant_id)
    if not category:
        raise HTTPException(status_code=404, detail="SOP Category not found")
    
    # Validate department exists
    dept = department.get(db, id=obj_in.department_id, tenant_id=current_user.tenant_id)
    if not dept:
        raise HTTPException(status_code=404, detail="Department not found")

    return sop_item.create(
        db,
        obj_in=obj_in,
        tenant_id=current_user.tenant_id,
        property_id=current_user.property_id
    )


@router.get("/items", response_model=List[SOPItemInDB])
def list_items(
    db: Session = Depends(get_db),
    skip: int = Query(0),
    limit: int = Query(100),
    department_id: Optional[int] = Query(None),
    current_user: User = Depends(dependencies.get_current_user),
    user=Depends(require_permission("view_sop"))     # ADDED
) -> Any:
    """
    Retrieve SOP items. Optionally filter by department.
    All roles can view SOP items.
    """
    return sop_item.get_multi_by_department(
        db,
        tenant_id=current_user.tenant_id,
        department_id=department_id,
        skip=skip,
        limit=limit
    )

@router.get("/items/{id}", response_model=SOPItemInDB)
def get_item(
    *,
    db: Session = Depends(get_db),
    id: int,
    current_user: User = Depends(dependencies.get_current_user),
    user=Depends(require_permission("view_sop"))
) -> Any:
    """
    Retrieve a single SOP item by ID.
    """
    db_obj = sop_item.get(db, id=id, tenant_id=current_user.tenant_id)
    if not db_obj:
        raise HTTPException(status_code=404, detail="SOP Item not found")
    return db_obj

@router.delete("/items/{id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_item(
    *,
    db: Session = Depends(get_db),
    id: int,
    current_user: User = Depends(dependencies.get_current_user),
    user=Depends(require_permission("create_sop"))
) -> Any:
    """
    Delete a SOP item and all its versions/audit logs.
    Only Managers and above can delete SOP items.
    """
    db_obj = sop_item.get(db, id=id, tenant_id=current_user.tenant_id)
    if not db_obj:
        raise HTTPException(status_code=404, detail="SOP Item not found")
    sop_item.remove(db, id=id)
    return None

# --- S3 Pre-signed URL Endpoint ---
s3_client = boto3.client('s3', region_name='us-east-1')
S3_BUCKET_NAME = "your-sop-bucket-name"

@router.post("/upload/presigned-url")
def get_presigned_url(
    filename: str,
    file_type: str,
    current_user: User = Depends(dependencies.get_current_user),
    user=Depends(require_permission("create_sop"))
) -> Any:
    """
    Generate a pre-signed URL to upload SOP documents directly to S3.
    """
    try:
        object_key = f"{current_user.tenant_id}/sops/{filename}"
        presigned_url = s3_client.generate_presigned_url(
            'put_object',
            Params={'Bucket': S3_BUCKET_NAME, 'Key': object_key, 'ContentType': file_type},
            ExpiresIn=3600
        )
        return {"upload_url": presigned_url, "file_key": object_key}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# --- SOP Versioning Endpoints ---
@router.post("/items/{id}/versions", response_model=SOPVersionInDB, status_code=status.HTTP_201_CREATED)
def create_sop_version(
    *,
    db: Session = Depends(get_db),
    id: int,
    obj_in: SOPVersionCreate,
    current_user: User = Depends(dependencies.get_current_user),
    user=Depends(require_permission("create_sop"))
) -> Any:
    """
    Create a new version for an SOP document.
    """
    item = sop_item.get(db, id=id, tenant_id=current_user.tenant_id)
    if not item:
        raise HTTPException(status_code=404, detail="SOP Item not found")
        
    obj_in.sop_item_id = id
    obj_in.created_by_user = current_user.email
    
    version = sop_version.create(
        db,
        obj_in=obj_in,
        tenant_id=current_user.tenant_id,
        property_id=item.property_id
    )
    
    audit_in = SOPAuditCreate(
        sop_item_id=id,
        action="VERSION_ADDED",
        performed_by=current_user.email,
        details=f"Added version {version.version_number}"
    )
    sop_audit.create(db, obj_in=audit_in, tenant_id=current_user.tenant_id, property_id=item.property_id)
    
    return version

@router.get("/items/{id}/versions", response_model=List[SOPVersionInDB])
def list_sop_versions(
    *,
    db: Session = Depends(get_db),
    id: int,
    current_user: User = Depends(dependencies.get_current_user),
    user=Depends(require_permission("view_sop"))
) -> Any:
    """
    List history of versions for an SOP document.
    """
    return sop_version.get_by_item(db, sop_item_id=id, tenant_id=current_user.tenant_id)

@router.get("/items/{id}/versions/{version_id}", response_model=SOPVersionInDB)
def get_sop_version(
    *,
    db: Session = Depends(get_db),
    id: int,
    version_id: int,
    current_user: User = Depends(dependencies.get_current_user),
    user=Depends(require_permission("view_sop"))
) -> Any:
    """
    Fetch a specific SOP version.
    """
    version = sop_version.get(db, id=version_id, tenant_id=current_user.tenant_id)
    if not version or version.sop_item_id != id:
        raise HTTPException(status_code=404, detail="Version not found")
    return version

# --- SOP Audit Trail Endpoint ---
@router.get("/items/{id}/audit", response_model=List[SOPAuditInDB])
def get_sop_audit_trail(
    *,
    db: Session = Depends(get_db),
    id: int,
    current_user: User = Depends(dependencies.get_current_user),
    user=Depends(require_permission("view_sop"))
) -> Any:
    """
    Fetch the audit trail for a specific SOP item.
    """
    return sop_audit.get_by_item(db, sop_item_id=id, tenant_id=current_user.tenant_id)