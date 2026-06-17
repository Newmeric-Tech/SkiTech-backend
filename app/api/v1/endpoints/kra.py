"""
KRA Router - Key Result Areas Management

Endpoints for daily, weekly, monthly, and quarterly KRA tracking.
"""

from datetime import date as dt_date
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db as get_db_session
from app.api.dependencies import get_current_user
from app.schemas.common import PaginatedResponse
from app.schemas.kra import (
    KRAComplianceResponse,
    DailyKRACreate, DailyKRAListResponse, DailyKRAResponse, DailyKRAUpdate,
    WeeklyKRACreate, WeeklyKRAListResponse, WeeklyKRAResponse, WeeklyKRAUpdate,
    MonthlyKRACreate, MonthlyKRAListResponse, MonthlyKRAResponse, MonthlyKRAUpdate,
    QuarterlyKRACreate, QuarterlyKRAListResponse, QuarterlyKRAResponse, QuarterlyKRAUpdate,
)
from app.services.kra_service import (
    DailyKRAService, WeeklyKRAService, MonthlyKRAService, QuarterlyKRAService,
)
from app.utils.exceptions import NotFoundError

router = APIRouter(prefix="/kra", tags=["KRA"])


async def get_current_user_context(user: dict = Depends(get_current_user)):
    """Extract user context from JWT for KRA endpoints."""
    return {
        "tenant_id": UUID(user["tenant_id"]),
        "user_id": UUID(user["user_id"]),
        "role": user.get("role", "staff"),
    }


def resolve_pagination(skip: int, limit: int, page: Optional[int], page_size: Optional[int]) -> tuple[int, int]:
    if page is not None or page_size is not None:
        resolved_page = page or 1
        resolved_page_size = page_size or limit
        return (resolved_page - 1) * resolved_page_size, resolved_page_size
    return skip, limit


# ==================== COMPLIANCE ====================

@router.get("/compliance", response_model=KRAComplianceResponse)
async def get_kra_compliance(
    start_date: dt_date = Query(...),
    end_date: dt_date = Query(...),
    employee_id: Optional[int] = Query(None),
    property_id: Optional[int] = Query(None),
    db: AsyncSession = Depends(get_db_session),
    user_context: dict = Depends(get_current_user_context),
) -> KRAComplianceResponse:
    if end_date < start_date:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="end_date must be >= start_date")
    service = DailyKRAService(db)
    result = await service.calculate_compliance(
        tenant_id=user_context["tenant_id"], start_date=start_date, end_date=end_date,
        employee_id=employee_id, property_id=property_id,
    )
    return KRAComplianceResponse(**result)


# ==================== DAILY KRAs ====================

@router.get("/daily", response_model=PaginatedResponse[DailyKRAListResponse])
async def list_daily_kras(
    skip: int = Query(0, ge=0), limit: int = Query(20, ge=1, le=100),
    page: Optional[int] = Query(None, ge=1), page_size: Optional[int] = Query(None, ge=1, le=100),
    user_id: Optional[int] = Query(None),
    db: AsyncSession = Depends(get_db_session),
    user_context: dict = Depends(get_current_user_context),
):
    service = DailyKRAService(db)
    resolved_skip, resolved_limit = resolve_pagination(skip, limit, page, page_size)
    kras, total = await service.list_daily_kras(
        tenant_id=user_context["tenant_id"], user_id=user_id, skip=resolved_skip, limit=resolved_limit
    )
    return PaginatedResponse(total=total, skip=resolved_skip, limit=resolved_limit,
                             items=[DailyKRAListResponse.from_orm(k) for k in kras])


@router.post("/daily", response_model=DailyKRAResponse, status_code=status.HTTP_201_CREATED)
async def create_daily_kra(
    kra_data: DailyKRACreate,
    db: AsyncSession = Depends(get_db_session),
    user_context: dict = Depends(get_current_user_context),
):
    service = DailyKRAService(db)
    existing = await service.get_daily_kra_by_date(
        tenant_id=user_context["tenant_id"], user_id=user_context["user_id"], kra_date=kra_data.date
    )
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Daily KRA already exists for {kra_data.date}")
    kra = await service.create_daily_kra(
        tenant_id=user_context["tenant_id"], user_id=user_context["user_id"], kra_data=kra_data
    )
    await db.commit()
    await db.refresh(kra)
    return DailyKRAResponse.from_orm(kra)


@router.get("/daily/{kra_id}", response_model=DailyKRAResponse)
async def get_daily_kra(kra_id: UUID, db: AsyncSession = Depends(get_db_session),
                         user_context: dict = Depends(get_current_user_context)):
    kra = await DailyKRAService(db).get_daily_kra_by_id(kra_id=kra_id, tenant_id=user_context["tenant_id"])
    if not kra:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Daily KRA not found")
    return DailyKRAResponse.from_orm(kra)


@router.put("/daily/{kra_id}", response_model=DailyKRAResponse)
async def update_daily_kra(kra_id: UUID, update_data: DailyKRAUpdate,
                            db: AsyncSession = Depends(get_db_session),
                            user_context: dict = Depends(get_current_user_context)):
    service = DailyKRAService(db)
    kra = await service.get_daily_kra_by_id(kra_id=kra_id, tenant_id=user_context["tenant_id"])
    if not kra:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Daily KRA not found")
    kra = await service.update_daily_kra(kra, update_data)
    await db.commit()
    await db.refresh(kra)
    return DailyKRAResponse.from_orm(kra)


@router.delete("/daily/{kra_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_daily_kra(kra_id: UUID, db: AsyncSession = Depends(get_db_session),
                            user_context: dict = Depends(get_current_user_context)):
    service = DailyKRAService(db)
    kra = await service.get_daily_kra_by_id(kra_id=kra_id, tenant_id=user_context["tenant_id"])
    if not kra:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Daily KRA not found")
    await service.delete_daily_kra(kra)
    await db.commit()


# ==================== WEEKLY KRAs ====================

@router.get("/weekly", response_model=PaginatedResponse[WeeklyKRAListResponse])
async def list_weekly_kras(
    skip: int = Query(0, ge=0), limit: int = Query(20, ge=1, le=100),
    page: Optional[int] = Query(None, ge=1), page_size: Optional[int] = Query(None, ge=1, le=100),
    user_id: Optional[int] = Query(None),
    db: AsyncSession = Depends(get_db_session),
    user_context: dict = Depends(get_current_user_context),
):
    service = WeeklyKRAService(db)
    resolved_skip, resolved_limit = resolve_pagination(skip, limit, page, page_size)
    kras, total = await service.list_weekly_kras(
        tenant_id=user_context["tenant_id"], user_id=user_id, skip=resolved_skip, limit=resolved_limit
    )
    return PaginatedResponse(total=total, skip=resolved_skip, limit=resolved_limit,
                             items=[WeeklyKRAListResponse.from_orm(k) for k in kras])


@router.post("/weekly", response_model=WeeklyKRAResponse, status_code=status.HTTP_201_CREATED)
async def create_weekly_kra(kra_data: WeeklyKRACreate, db: AsyncSession = Depends(get_db_session),
                             user_context: dict = Depends(get_current_user_context)):
    service = WeeklyKRAService(db)
    existing = await service.get_weekly_kra_by_week(
        tenant_id=user_context["tenant_id"], user_id=user_context["user_id"],
        year=kra_data.year, week_number=kra_data.week_number
    )
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                            detail=f"Weekly KRA already exists for week {kra_data.week_number}/{kra_data.year}")
    kra = await service.create_weekly_kra(
        tenant_id=user_context["tenant_id"], user_id=user_context["user_id"], kra_data=kra_data
    )
    await db.commit()
    await db.refresh(kra)
    return WeeklyKRAResponse.from_orm(kra)


@router.get("/weekly/{kra_id}", response_model=WeeklyKRAResponse)
async def get_weekly_kra(kra_id: UUID, db: AsyncSession = Depends(get_db_session),
                          user_context: dict = Depends(get_current_user_context)):
    kra = await WeeklyKRAService(db).get_weekly_kra_by_id(kra_id=kra_id, tenant_id=user_context["tenant_id"])
    if not kra:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Weekly KRA not found")
    return WeeklyKRAResponse.from_orm(kra)


@router.put("/weekly/{kra_id}", response_model=WeeklyKRAResponse)
async def update_weekly_kra(kra_id: UUID, update_data: WeeklyKRAUpdate,
                             db: AsyncSession = Depends(get_db_session),
                             user_context: dict = Depends(get_current_user_context)):
    service = WeeklyKRAService(db)
    kra = await service.get_weekly_kra_by_id(kra_id=kra_id, tenant_id=user_context["tenant_id"])
    if not kra:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Weekly KRA not found")
    kra = await service.update_weekly_kra(kra, update_data)
    await db.commit()
    await db.refresh(kra)
    return WeeklyKRAResponse.from_orm(kra)


@router.delete("/weekly/{kra_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_weekly_kra(kra_id: UUID, db: AsyncSession = Depends(get_db_session),
                             user_context: dict = Depends(get_current_user_context)):
    service = WeeklyKRAService(db)
    kra = await service.get_weekly_kra_by_id(kra_id=kra_id, tenant_id=user_context["tenant_id"])
    if not kra:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Weekly KRA not found")
    await service.delete_weekly_kra(kra)
    await db.commit()


# ==================== MONTHLY KRAs ====================

@router.get("/monthly", response_model=PaginatedResponse[MonthlyKRAListResponse])
async def list_monthly_kras(
    skip: int = Query(0, ge=0), limit: int = Query(20, ge=1, le=100),
    page: Optional[int] = Query(None, ge=1), page_size: Optional[int] = Query(None, ge=1, le=100),
    user_id: Optional[int] = Query(None),
    db: AsyncSession = Depends(get_db_session),
    user_context: dict = Depends(get_current_user_context),
):
    service = MonthlyKRAService(db)
    resolved_skip, resolved_limit = resolve_pagination(skip, limit, page, page_size)
    kras, total = await service.list_monthly_kras(
        tenant_id=user_context["tenant_id"], user_id=user_id, skip=resolved_skip, limit=resolved_limit
    )
    return PaginatedResponse(total=total, skip=resolved_skip, limit=resolved_limit,
                             items=[MonthlyKRAListResponse.from_orm(k) for k in kras])


@router.post("/monthly", response_model=MonthlyKRAResponse, status_code=status.HTTP_201_CREATED)
async def create_monthly_kra(kra_data: MonthlyKRACreate, db: AsyncSession = Depends(get_db_session),
                              user_context: dict = Depends(get_current_user_context)):
    service = MonthlyKRAService(db)
    existing = await service.get_monthly_kra_by_month(
        tenant_id=user_context["tenant_id"], user_id=user_context["user_id"],
        month=kra_data.month, year=kra_data.year
    )
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                            detail=f"Monthly KRA already exists for {kra_data.month}/{kra_data.year}")
    kra = await service.create_monthly_kra(
        tenant_id=user_context["tenant_id"], user_id=user_context["user_id"], kra_data=kra_data
    )
    await db.commit()
    await db.refresh(kra)
    return MonthlyKRAResponse.from_orm(kra)


@router.get("/monthly/{kra_id}", response_model=MonthlyKRAResponse)
async def get_monthly_kra(kra_id: UUID, db: AsyncSession = Depends(get_db_session),
                           user_context: dict = Depends(get_current_user_context)):
    kra = await MonthlyKRAService(db).get_monthly_kra_by_id(kra_id=kra_id, tenant_id=user_context["tenant_id"])
    if not kra:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Monthly KRA not found")
    return MonthlyKRAResponse.from_orm(kra)


@router.put("/monthly/{kra_id}", response_model=MonthlyKRAResponse)
async def update_monthly_kra(kra_id: UUID, update_data: MonthlyKRAUpdate,
                              db: AsyncSession = Depends(get_db_session),
                              user_context: dict = Depends(get_current_user_context)):
    service = MonthlyKRAService(db)
    kra = await service.get_monthly_kra_by_id(kra_id=kra_id, tenant_id=user_context["tenant_id"])
    if not kra:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Monthly KRA not found")
    kra = await service.update_monthly_kra(kra, update_data)
    await db.commit()
    await db.refresh(kra)
    return MonthlyKRAResponse.from_orm(kra)


@router.delete("/monthly/{kra_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_monthly_kra(kra_id: UUID, db: AsyncSession = Depends(get_db_session),
                              user_context: dict = Depends(get_current_user_context)):
    service = MonthlyKRAService(db)
    kra = await service.get_monthly_kra_by_id(kra_id=kra_id, tenant_id=user_context["tenant_id"])
    if not kra:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Monthly KRA not found")
    await service.delete_monthly_kra(kra)
    await db.commit()


# ==================== QUARTERLY KRAs ====================

@router.get("/quarterly", response_model=PaginatedResponse[QuarterlyKRAListResponse])
async def list_quarterly_kras(
    skip: int = Query(0, ge=0), limit: int = Query(20, ge=1, le=100),
    page: Optional[int] = Query(None, ge=1), page_size: Optional[int] = Query(None, ge=1, le=100),
    user_id: Optional[int] = Query(None),
    db: AsyncSession = Depends(get_db_session),
    user_context: dict = Depends(get_current_user_context),
):
    service = QuarterlyKRAService(db)
    resolved_skip, resolved_limit = resolve_pagination(skip, limit, page, page_size)
    kras, total = await service.list_quarterly_kras(
        tenant_id=user_context["tenant_id"], user_id=user_id, skip=resolved_skip, limit=resolved_limit
    )
    return PaginatedResponse(total=total, skip=resolved_skip, limit=resolved_limit,
                             items=[QuarterlyKRAListResponse.from_orm(k) for k in kras])


@router.post("/quarterly", response_model=QuarterlyKRAResponse, status_code=status.HTTP_201_CREATED)
async def create_quarterly_kra(kra_data: QuarterlyKRACreate, db: AsyncSession = Depends(get_db_session),
                                user_context: dict = Depends(get_current_user_context)):
    service = QuarterlyKRAService(db)
    existing = await service.get_quarterly_kra_by_quarter(
        tenant_id=user_context["tenant_id"], user_id=user_context["user_id"],
        quarter=kra_data.quarter, year=kra_data.year
    )
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                            detail=f"Quarterly KRA already exists for Q{kra_data.quarter}/{kra_data.year}")
    kra = await service.create_quarterly_kra(
        tenant_id=user_context["tenant_id"], user_id=user_context["user_id"], kra_data=kra_data
    )
    await db.commit()
    await db.refresh(kra)
    return QuarterlyKRAResponse.from_orm(kra)


@router.get("/quarterly/{kra_id}", response_model=QuarterlyKRAResponse)
async def get_quarterly_kra(kra_id: UUID, db: AsyncSession = Depends(get_db_session),
                             user_context: dict = Depends(get_current_user_context)):
    kra = await QuarterlyKRAService(db).get_quarterly_kra_by_id(kra_id=kra_id, tenant_id=user_context["tenant_id"])
    if not kra:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Quarterly KRA not found")
    return QuarterlyKRAResponse.from_orm(kra)


@router.put("/quarterly/{kra_id}", response_model=QuarterlyKRAResponse)
async def update_quarterly_kra(kra_id: UUID, update_data: QuarterlyKRAUpdate,
                                db: AsyncSession = Depends(get_db_session),
                                user_context: dict = Depends(get_current_user_context)):
    service = QuarterlyKRAService(db)
    kra = await service.get_quarterly_kra_by_id(kra_id=kra_id, tenant_id=user_context["tenant_id"])
    if not kra:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Quarterly KRA not found")
    kra = await service.update_quarterly_kra(kra, update_data)
    await db.commit()
    await db.refresh(kra)
    return QuarterlyKRAResponse.from_orm(kra)


@router.delete("/quarterly/{kra_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_quarterly_kra(kra_id: UUID, db: AsyncSession = Depends(get_db_session),
                                user_context: dict = Depends(get_current_user_context)):
    service = QuarterlyKRAService(db)
    kra = await service.get_quarterly_kra_by_id(kra_id=kra_id, tenant_id=user_context["tenant_id"])
    if not kra:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Quarterly KRA not found")
    await service.delete_quarterly_kra(kra)
    await db.commit()
