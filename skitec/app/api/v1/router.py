"""
API v1 Router - Aggregates all v1 endpoints

Combines all API routers for version 1 of the API.
Maintains separation of concerns while providing unified routing.
"""

from fastapi import APIRouter

from app.api.v1.endpoints import auth, governance, properties, reports, users, workforce

# Create main v1 router
router = APIRouter(prefix="/v1")

# Include all endpoint routers
router.include_router(auth.router)
router.include_router(users.router)
router.include_router(properties.router)
router.include_router(workforce.router)
router.include_router(governance.router)
router.include_router(reports.router)

__all__ = ["router"]
