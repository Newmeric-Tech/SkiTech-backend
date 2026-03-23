from fastapi import APIRouter
from api.v1.endpoints import employee, sop, inventory

api_router = APIRouter()
api_router.include_router(employee.router, prefix="/employees", tags=["employees"])
api_router.include_router(sop.router, prefix="/sop", tags=["sop"])
api_router.include_router(inventory.router, prefix="/inventory", tags=["inventory"])
