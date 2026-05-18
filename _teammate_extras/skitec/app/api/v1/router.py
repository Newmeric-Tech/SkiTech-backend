"""
API v1 Router - Aggregates all v1 endpoints

Combines all API routers for version 1 of the API.
Maintains separation of concerns while providing unified routing.
"""

from fastapi import APIRouter

from .endpoints import (
    auth, governance, properties, reports, users, workforce,
    department, employee, inventory, owner, sop, vendor, kra, attendance
)
from . import vendor_owner_department_routes

# Create main v1 router
router = APIRouter(prefix="/v1")

# Include all endpoint routers
router.include_router(auth.router)
router.include_router(users.router)
router.include_router(properties.router)
router.include_router(workforce.router)
router.include_router(governance.router)
router.include_router(reports.router)
router.include_router(department.router)
router.include_router(employee.router)
router.include_router(inventory.router)
router.include_router(owner.router)
router.include_router(sop.router)
router.include_router(vendor.router)
router.include_router(kra.router)
router.include_router(attendance.router)
router.include_router(vendor_owner_department_routes.router)

__all__ = ["router"]
