"""
Missed punch-out correction routes - app/api/v1/endpoints/attendance_corrections.py

POST /attendance/correction-requests                -> claim a punch-out time for your auto_closed shift
GET  /attendance/correction-requests?status=&mine=  -> your requests, plus those you may review
POST /attendance/correction-requests/{id}/approve   -> completes the shift with the approved time
POST /attendance/correction-requests/{id}/reject
POST /attendance/correction-requests/{id}/cancel    -> the requester, while pending

See app/services/attendance_correction_service.py for the rules.
"""
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Body, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user
from app.core.database import get_db
from app.schemas.attendance import (
    AttendanceCorrectionCreate, AttendanceCorrectionResponse, AttendanceCorrectionReview,
)
from app.services import attendance_correction_service as corrections
from app.services.attendance_correction_service import hours_between
from app.services.geofence_request_service import RequestConflict, RequestForbidden, RequestNotFound

router = APIRouter(prefix="/attendance", tags=["Attendance & Geolocation"])

STATUSES = ("pending", "approved", "rejected", "cancelled")


async def _respond(db: AsyncSession, items) -> List[AttendanceCorrectionResponse]:
    users, props, punch_ins = await corrections.details_for(db, items)
    out = []
    for r in items:
        resp = AttendanceCorrectionResponse.model_validate(r)
        resp.property_name = props.get(r.property_id)
        resp.requested_by_name = users.get(r.requested_by)
        resp.reviewed_by_name = users.get(r.reviewed_by)
        punch_in = punch_ins.get(r.attendance_id)
        resp.punch_in_time = punch_in
        resp.claimed_hours = hours_between(punch_in, r.claimed_punch_out_time) if punch_in else None
        out.append(resp)
    return out


def _http(err: Exception) -> HTTPException:
    if isinstance(err, RequestNotFound):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    if isinstance(err, RequestConflict):
        return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(err))
    if isinstance(err, RequestForbidden):
        return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(err))
    # ValueError messages are written by the service for the user
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(err))


_KNOWN = (RequestNotFound, RequestConflict, RequestForbidden, ValueError)


@router.post("/correction-requests", response_model=AttendanceCorrectionResponse,
             status_code=status.HTTP_201_CREATED)
async def create_correction_request(
    data: AttendanceCorrectionCreate,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    try:
        request = await corrections.create_correction(db, user, data)
    except _KNOWN as err:
        raise _http(err)
    return (await _respond(db, [request]))[0]


@router.get("/correction-requests", response_model=List[AttendanceCorrectionResponse])
async def list_correction_requests(
    status_filter: Optional[str] = Query(None, alias="status"),
    mine: bool = Query(False, description="Only your own requests"),
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    if status_filter and status_filter not in STATUSES:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                            detail=f"status must be one of {', '.join(STATUSES)}")
    items = await corrections.list_corrections(db, user, status_filter, mine_only=mine)
    return await _respond(db, items)


@router.post("/correction-requests/{request_id}/approve", response_model=AttendanceCorrectionResponse)
async def approve_correction_request(
    request_id: UUID,
    review: Optional[AttendanceCorrectionReview] = Body(None),
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    try:
        request, _ = await corrections.approve_correction(
            db, user, request_id, review.review_note if review else None)
    except _KNOWN as err:
        raise _http(err)
    return (await _respond(db, [request]))[0]


@router.post("/correction-requests/{request_id}/reject", response_model=AttendanceCorrectionResponse)
async def reject_correction_request(
    request_id: UUID,
    review: Optional[AttendanceCorrectionReview] = Body(None),
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    try:
        request = await corrections.reject_correction(
            db, user, request_id, review.review_note if review else None)
    except _KNOWN as err:
        raise _http(err)
    return (await _respond(db, [request]))[0]


@router.post("/correction-requests/{request_id}/cancel", response_model=AttendanceCorrectionResponse)
async def cancel_correction_request(
    request_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    try:
        request = await corrections.cancel_correction(db, user, request_id)
    except _KNOWN as err:
        raise _http(err)
    return (await _respond(db, [request]))[0]
