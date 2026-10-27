"""
Geofence change request routes - app/api/v1/endpoints/geofence_requests.py

POST /attendance/geofence-requests                 -> propose a punch location (Manager+)
GET  /attendance/geofence-requests?status=         -> Manager: own requests; admins: tenant (Co Admin: own property)
POST /attendance/geofence-requests/{id}/approve    -> apply to the live geofence (Super Admin / Tenant Admin / Co Admin)
POST /attendance/geofence-requests/{id}/reject     -> (Super Admin / Tenant Admin / Co Admin)
POST /attendance/geofence-requests/{id}/cancel     -> the requester, while pending

See app/services/geofence_request_service.py for the rules.
"""
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Body, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user, require_roles
from app.core.database import get_db
from app.schemas.attendance import (
    GeofenceChangeRequestCreate, GeofenceChangeRequestResponse, GeofenceChangeRequestReview,
)
from app.services import geofence_request_service as requests_service
from app.services.geofence_request_service import (
    REQUEST_ROLES, RequestConflict, RequestForbidden, RequestNotFound,
)
from app.services.geofence_scope import GEOFENCE_ADMIN_ROLES, PropertyNotInScope

router = APIRouter(prefix="/attendance", tags=["Attendance & Geolocation"])

REQUEST_STATUSES = ("pending", "approved", "rejected", "cancelled")


async def _respond(db: AsyncSession, items) -> List[GeofenceChangeRequestResponse]:
    users, props = await requests_service.names_for(db, items)
    out = []
    for r in items:
        resp = GeofenceChangeRequestResponse.model_validate(r)
        resp.property_name = props.get(r.property_id)
        resp.requested_by_name = users.get(r.requested_by)
        resp.reviewed_by_name = users.get(r.reviewed_by)
        out.append(resp)
    return out


def _http(err: Exception) -> HTTPException:
    if isinstance(err, (RequestNotFound,)):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Request not found")
    if isinstance(err, PropertyNotInScope):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Property not found")
    if isinstance(err, RequestConflict):
        return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(err))
    if isinstance(err, RequestForbidden):
        return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(err))
    return HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error processing request")


_KNOWN = (RequestNotFound, PropertyNotInScope, RequestConflict, RequestForbidden)


@router.post("/geofence-requests", response_model=GeofenceChangeRequestResponse,
             status_code=status.HTTP_201_CREATED)
async def create_geofence_request(
    data: GeofenceChangeRequestCreate,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_roles(list(REQUEST_ROLES))),
):
    try:
        request = await requests_service.create_request(db, user, data)
    except _KNOWN as err:
        raise _http(err)
    return (await _respond(db, [request]))[0]


@router.get("/geofence-requests", response_model=List[GeofenceChangeRequestResponse])
async def list_geofence_requests(
    status_filter: Optional[str] = Query(None, alias="status"),
    property_id: Optional[UUID] = Query(None),
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_roles(list(REQUEST_ROLES))),
):
    if status_filter and status_filter not in REQUEST_STATUSES:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                            detail=f"status must be one of {', '.join(REQUEST_STATUSES)}")
    items = await requests_service.list_requests(db, user, status_filter, property_id)
    return await _respond(db, items)


@router.post("/geofence-requests/{request_id}/approve", response_model=GeofenceChangeRequestResponse)
async def approve_geofence_request(
    request_id: UUID,
    review: Optional[GeofenceChangeRequestReview] = Body(None),
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_roles(list(GEOFENCE_ADMIN_ROLES))),
):
    try:
        request, _ = await requests_service.approve_request(
            db, user, request_id, review.review_note if review else None)
    except _KNOWN as err:
        raise _http(err)
    return (await _respond(db, [request]))[0]


@router.post("/geofence-requests/{request_id}/reject", response_model=GeofenceChangeRequestResponse)
async def reject_geofence_request(
    request_id: UUID,
    review: Optional[GeofenceChangeRequestReview] = Body(None),
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_roles(list(GEOFENCE_ADMIN_ROLES))),
):
    try:
        request = await requests_service.reject_request(
            db, user, request_id, review.review_note if review else None)
    except _KNOWN as err:
        raise _http(err)
    return (await _respond(db, [request]))[0]


@router.post("/geofence-requests/{request_id}/cancel", response_model=GeofenceChangeRequestResponse)
async def cancel_geofence_request(
    request_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_roles(list(REQUEST_ROLES))),
):
    try:
        request = await requests_service.cancel_request(db, user, request_id)
    except _KNOWN as err:
        raise _http(err)
    return (await _respond(db, [request]))[0]
