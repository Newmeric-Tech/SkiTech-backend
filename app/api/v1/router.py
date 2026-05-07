"""
API v1 Router - app/api/v1/router.py
"""

from fastapi import APIRouter

from app.api.v1.endpoints import (
    auth, governance, inventory,
    properties, sop, workforce, users, stats, reports, rooms,
    kra, attendance, department, employee, vendor, owner, superadmin, dashboard,
)
from app.api.v1 import vendor_owner_department_routes

router = APIRouter(prefix="/v1")

# Core
router.include_router(auth.router)
router.include_router(users.router)
router.include_router(dashboard.router)
router.include_router(stats.router)
router.include_router(reports.router)
router.include_router(rooms.router)
router.include_router(properties.router)

# Workforce (existing combined)
router.include_router(workforce.dept_router)
router.include_router(workforce.emp_router)
router.include_router(workforce.vendor_router)

# Workforce (new separate endpoints from teammate)
router.include_router(department.router)
router.include_router(employee.router)
router.include_router(vendor.router)
router.include_router(owner.router)

# Operations
router.include_router(inventory.router)
router.include_router(sop.router)
router.include_router(governance.router)

# New modules from teammate
router.include_router(kra.router)
router.include_router(attendance.router)
router.include_router(vendor_owner_department_routes.router)

# Superadmin
router.include_router(superadmin.router)
