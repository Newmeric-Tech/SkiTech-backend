"""
Combined Router - Vendor, Owner, and Department Management

Handles vendor, owner, and department CRUD with permission-based access control.
"""

from fastapi import APIRouter, Depends
from app.utils.permission_checker import require_permission

router = APIRouter()


# ============================================================
# VENDOR ROUTES
# ============================================================

@router.get("/vendors")
def list_vendors(user=Depends(require_permission("view_vendor"))):
    return {"message": "Vendor list"}


@router.post("/vendors")
def create_vendor(user=Depends(require_permission("create_vendor"))):
    return {"message": "Vendor created"}


@router.put("/vendors/{vendor_id}")
def update_vendor(vendor_id: str, user=Depends(require_permission("update_vendor"))):
    return {"message": "Vendor updated"}


@router.delete("/vendors/{vendor_id}")
def delete_vendor(vendor_id: str, user=Depends(require_permission("delete_vendor"))):
    return {"message": "Vendor deleted"}


# ============================================================
# OWNER DETAILS ROUTES
# ============================================================

@router.get("/owners")
def list_owners(user=Depends(require_permission("view_owner"))):
    return {"message": "Owner list"}


@router.post("/owners")
def create_owner(user=Depends(require_permission("manage_owner"))):
    return {"message": "Owner created"}


@router.put("/owners/{owner_id}")
def update_owner(owner_id: str, user=Depends(require_permission("manage_owner"))):
    return {"message": "Owner updated"}


# ============================================================
# DEPARTMENT ROUTES
# ============================================================

@router.get("/departments")
def list_departments(user=Depends(require_permission("view_department"))):
    return {"message": "Department list"}


@router.post("/departments")
def create_department(user=Depends(require_permission("create_department"))):
    return {"message": "Department created"}


@router.put("/departments/{dept_id}")
def update_department(dept_id: str, user=Depends(require_permission("update_department"))):
    return {"message": "Department updated"}


@router.delete("/departments/{dept_id}")
def delete_department(dept_id: str, user=Depends(require_permission("delete_department"))):
    return {"message": "Department deleted"}
