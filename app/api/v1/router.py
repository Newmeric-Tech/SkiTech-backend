"""
API v1 Router - app/api/v1/router.py
"""

from fastapi import APIRouter, Depends

from app.api.dependencies import require_feature
from app.api.v1.endpoints import (
    auth, governance, inventory,
    properties, sop, workforce, users, stats, reports, rooms,
    kra, attendance, department, employee, vendor, owner, superadmin, dashboard,
    subscriptions, chat, scheduling, complaints, documents,
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
router.include_router(subscriptions.router)

# Workforce (existing combined)
router.include_router(workforce.dept_router)
router.include_router(workforce.emp_router)
router.include_router(workforce.vendor_router)

# Workforce (new separate endpoints from teammate)
router.include_router(department.router)
router.include_router(employee.router)
router.include_router(vendor.router)
router.include_router(owner.router)

# Operations — inventory is feature-gated by subscription plan
router.include_router(
    inventory.router,
    dependencies=[Depends(require_feature("inventory"))],
)
router.include_router(sop.router)
router.include_router(governance.router)

# New modules from teammate
router.include_router(kra.router)
router.include_router(attendance.router)
router.include_router(vendor_owner_department_routes.router)

# Employee Scheduling
router.include_router(scheduling.router)

# Error & Complaint Log
router.include_router(complaints.router)

# Document Management System
router.include_router(documents.router)

# Superadmin
router.include_router(superadmin.router)

# Chat & Messaging
router.include_router(chat.router)
