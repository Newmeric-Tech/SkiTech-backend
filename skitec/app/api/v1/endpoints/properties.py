"""
Properties Router - Placeholder

Property management endpoints: CRUD operations for hotel properties.
Follow the pattern established in users.py for other modules.

Endpoints to implement:
- GET /properties - List properties
- GET /properties/{id} - Get property details
- POST /properties - Create property
- PUT /properties/{id} - Update property
- DELETE /properties/{id} - Delete property
"""

from fastapi import APIRouter

router = APIRouter(
    prefix="/properties",
    tags=["Properties"],
)


# TODO: Implement property endpoints following UserService pattern
