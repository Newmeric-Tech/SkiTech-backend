"""Reporting and analytics endpoints."""

from datetime import date as dt_date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from ....core.database import get_db_session
from ....schemas.kra import DailyReportResponse
from ....services.kra_service import DailyKRAService

router = APIRouter(
    prefix="/reports",
    tags=["Reports"],
)


async def get_current_user_context() -> dict:
    """Temporary user context dependency until auth extraction is wired."""
    return {
        "tenant_id": 1,
        "user_id": 1,
        "role": "staff",
    }


@router.get("/daily", response_model=DailyReportResponse)
async def get_daily_report(
    date: Optional[dt_date] = Query(None, description="Single day report"),
    start_date: Optional[dt_date] = Query(None, description="Start date (inclusive)"),
    end_date: Optional[dt_date] = Query(None, description="End date (inclusive)"),
    employee_id: Optional[int] = Query(None, description="Filter by employee/user ID"),
    property_id: Optional[int] = Query(None, description="Filter by property ID"),
    db: AsyncSession = Depends(get_db_session),
    user_context: dict = Depends(get_current_user_context),
) -> DailyReportResponse:
    """Aggregate daily KRA metrics such as check-ins, check-outs, and complaints."""
    if date and (start_date or end_date):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Use either date or start_date/end_date, not both",
        )

    if date is not None:
        resolved_start_date = date
        resolved_end_date = date
    elif start_date is None and end_date is None:
        resolved_start_date = dt_date.today()
        resolved_end_date = dt_date.today()
    elif start_date is None or end_date is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Both start_date and end_date are required for a date range",
        )
    else:
        resolved_start_date = start_date
        resolved_end_date = end_date

    if resolved_end_date < resolved_start_date:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="end_date must be greater than or equal to start_date",
        )

    service = DailyKRAService(db)
    report = await service.aggregate_daily_data(
        tenant_id=user_context["tenant_id"],
        start_date=resolved_start_date,
        end_date=resolved_end_date,
        employee_id=employee_id,
        property_id=property_id,
    )
    return DailyReportResponse(**report)


@router.get("/occupancy")
async def get_occupancy_report():
    """
    Get occupancy rates report
    
    Returns:
        Occupancy statistics
    """
    return {
        "message": "Occupancy report - to be implemented",
        "data": {}
    }


@router.get("/workforce")
async def get_workforce_report():
    """
    Get workforce analytics report
    
    Returns:
        Workforce statistics
    """
    return {
        "message": "Workforce report - to be implemented",
        "data": {}
    }


@router.get("/governance")
async def get_governance_report():
    """
    Get workflow statistics report
    
    Returns:
        Governance statistics
    """
    return {
        "message": "Governance report - to be implemented",
        "data": {}
    }


@router.get("/audit")
async def get_audit_report():
    """
    Get audit trail report
    
    Returns:
        Audit records
    """
    return {
        "message": "Audit report - to be implemented",
        "data": {}
    }
