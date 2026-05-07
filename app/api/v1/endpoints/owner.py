"""
Owner Router

Owner/Property Owner management endpoints: CRUD operations for property owners.
"""

from typing import Optional
from fastapi import APIRouter, Query

router = APIRouter(prefix="/owners", tags=["Owners"])


@router.get("/")
async def list_owners(skip: int = Query(0), limit: int = Query(100)):
    return {"message": "Owners endpoint - to be implemented", "owners": []}


@router.get("/{owner_id}")
async def get_owner(owner_id: int):
    return {"owner_id": owner_id, "message": "Owner details - to be implemented"}


@router.post("/")
async def create_owner(data: dict):
    return {"message": "Owner created - endpoint to be implemented", "data": data}


@router.put("/{owner_id}")
async def update_owner(owner_id: int, data: dict):
    return {"owner_id": owner_id, "message": "Owner updated - endpoint to be implemented", "data": data}


@router.delete("/{owner_id}")
async def delete_owner(owner_id: int):
    return {"owner_id": owner_id, "message": "Owner deleted - endpoint to be implemented"}
