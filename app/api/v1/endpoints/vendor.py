"""
Vendor Router

Vendor management endpoints: CRUD operations for vendors/suppliers.
"""

from typing import Optional
from fastapi import APIRouter, Query

router = APIRouter(prefix="/vendors", tags=["Vendors"])


@router.get("/")
async def list_vendors(
    skip: int = Query(0),
    limit: int = Query(100),
    property_id: Optional[str] = Query(None),
):
    return {"message": "Vendors endpoint - to be implemented", "filters": {"property_id": property_id}, "vendors": []}


@router.get("/{vendor_id}")
async def get_vendor(vendor_id: int):
    return {"vendor_id": vendor_id, "message": "Vendor details - to be implemented"}


@router.post("/")
async def create_vendor(data: dict):
    return {"message": "Vendor created - endpoint to be implemented", "data": data}


@router.put("/{vendor_id}")
async def update_vendor(vendor_id: int, data: dict):
    return {"vendor_id": vendor_id, "message": "Vendor updated - endpoint to be implemented", "data": data}


@router.delete("/{vendor_id}")
async def delete_vendor(vendor_id: int):
    return {"vendor_id": vendor_id, "message": "Vendor deleted - endpoint to be implemented"}
