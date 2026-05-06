"""
KRA Router - Key Result Areas Management

KRA (Key Result Areas) endpoints for managing performance metrics
across different timeframes: daily, weekly, monthly, and quarterly.

Endpoints:
- GET /kra/daily - List all daily KRAs
- POST /kra/daily - Create new daily KRA
- GET /kra/daily/{kra_id} - Get specific daily KRA
- PUT /kra/daily/{kra_id} - Update daily KRA
- DELETE /kra/daily/{kra_id} - Delete daily KRA
- GET /kra/weekly - List all weekly KRAs
- POST /kra/weekly - Create new weekly KRA
- GET /kra/weekly/{kra_id} - Get specific weekly KRA
- PUT /kra/weekly/{kra_id} - Update weekly KRA
- DELETE /kra/weekly/{kra_id} - Delete weekly KRA
- GET /kra/monthly - List all monthly KRAs
- POST /kra/monthly - Create new monthly KRA (with S3 file upload)
- GET /kra/monthly/{kra_id} - Get specific monthly KRA
- PUT /kra/monthly/{kra_id} - Update monthly KRA
- DELETE /kra/monthly/{kra_id} - Delete monthly KRA
- GET /kra/quarterly - List all quarterly KRAs
- POST /kra/quarterly - Create new quarterly KRA (with S3 file upload)
- GET /kra/quarterly/{kra_id} - Get specific quarterly KRA
- PUT /kra/quarterly/{kra_id} - Update quarterly KRA
- DELETE /kra/quarterly/{kra_id} - Delete quarterly KRA

Features:
- Tenant-level filtering (only show KRAs for user's tenant)
- Proper pagination support
- Input validation via Pydantic schemas
- S3 file upload support for revenue reports (monthly & quarterly)
"""

from datetime import date as dt_date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from ....core.database import get_db_session
from ....schemas.common import PaginatedResponse
from ....schemas.kra import (
    KRAComplianceResponse,
    DailyKRACreate,
    DailyKRAListResponse,
    DailyKRAResponse,
    DailyKRAUpdate,
    WeeklyKRACreate,
    WeeklyKRAListResponse,
    WeeklyKRAResponse,
    WeeklyKRAUpdate,
    MonthlyKRACreate,
    MonthlyKRAListResponse,
    MonthlyKRAResponse,
    MonthlyKRAUpdate,
    QuarterlyKRACreate,
    QuarterlyKRAListResponse,
    QuarterlyKRAResponse,
    QuarterlyKRAUpdate,
)
from ....services.kra_service import (
    DailyKRAService,
    WeeklyKRAService,
    MonthlyKRAService,
    QuarterlyKRAService,
)
from ....utils.exceptions import NotFoundError

router = APIRouter(
    prefix="/kra",
    tags=["KRA"],
    responses={
        401: {"description": "Unauthorized"},
        403: {"description": "Forbidden - Insufficient permissions"},
        404: {"description": "KRA not found"},
    },
)


# ==================== DEPENDENCIES ====================

async def get_current_user_context():
    """
    Get current user context
    
    TODO: Implement proper JWT token validation to extract:
    - tenant_id
    - user_id
    - user_role
    - permissions
    
    For now, this is a placeholder. In production, extract from JWT token.
    """
    # This would be replaced with actual JWT token validation
    # For now returning mock context for testing
    return {
        "tenant_id": 1,  # Would come from JWT token
        "user_id": 1,    # Would come from JWT token
        "role": "staff",
    }


# ==================== DAILY KRAs ====================

def resolve_pagination(
    skip: int,
    limit: int,
    page: Optional[int],
    page_size: Optional[int],
) -> tuple[int, int]:
    """Resolve offset pagination from either skip/limit or page/page_size."""
    if page is not None or page_size is not None:
        resolved_page = page or 1
        resolved_page_size = page_size or limit
        return (resolved_page - 1) * resolved_page_size, resolved_page_size
    return skip, limit


@router.get("/compliance", response_model=KRAComplianceResponse)
async def get_kra_compliance(
    start_date: dt_date = Query(..., description="Start date (inclusive)"),
    end_date: dt_date = Query(..., description="End date (inclusive)"),
    employee_id: Optional[int] = Query(None, description="Filter by employee/user ID"),
    property_id: Optional[int] = Query(None, description="Filter by property ID"),
    db: AsyncSession = Depends(get_db_session),
    user_context: dict = Depends(get_current_user_context),
) -> KRAComplianceResponse:
    """Return KRA compliance percentage for employee/property/date range."""
    if end_date < start_date:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="end_date must be greater than or equal to start_date",
        )

    service = DailyKRAService(db)
    result = await service.calculate_compliance(
        tenant_id=user_context["tenant_id"],
        start_date=start_date,
        end_date=end_date,
        employee_id=employee_id,
        property_id=property_id,
    )
    return KRAComplianceResponse(**result)

@router.get("/daily", response_model=PaginatedResponse[DailyKRAListResponse])
async def list_daily_kras(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    page: Optional[int] = Query(None, ge=1, description="Page number (alternative to skip)"),
    page_size: Optional[int] = Query(
        None,
        ge=1,
        le=100,
        description="Page size (alternative to limit)",
    ),
    user_id: Optional[int] = Query(None, description="Filter by specific user"),
    db: AsyncSession = Depends(get_db_session),
    user_context: dict = Depends(get_current_user_context),
) -> PaginatedResponse[DailyKRAListResponse]:
    """
    List all daily KRAs for current tenant
    
    Supports filtering by user_id and pagination.
    Only returns KRAs belonging to the current user's tenant.
    
    Args:
        skip: Number of records to skip (pagination)
        limit: Number of records to return (pagination)
        user_id: Optional filter by specific user
        db: Database session
        user_context: Current user context (tenant_id, user_id, role)
        
    Returns:
        PaginatedResponse with list of daily KRAs
    """
    service = DailyKRAService(db)
    resolved_skip, resolved_limit = resolve_pagination(skip, limit, page, page_size)
    kras, total = await service.list_daily_kras(
        tenant_id=user_context["tenant_id"],
        user_id=user_id,
        skip=resolved_skip,
        limit=resolved_limit,
    )

    return PaginatedResponse(
        total=total,
        skip=resolved_skip,
        limit=resolved_limit,
        items=[DailyKRAListResponse.from_orm(kra) for kra in kras],
    )


@router.post(
    "/daily",
    response_model=DailyKRAResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_daily_kra(
    kra_data: DailyKRACreate,
    db: AsyncSession = Depends(get_db_session),
    user_context: dict = Depends(get_current_user_context),
) -> DailyKRAResponse:
    """
    Create new daily KRA
    
    Args:
        kra_data: Daily KRA creation data
        db: Database session
        user_context: Current user context (tenant_id, user_id, role)
        
    Returns:
        Created DailyKRAResponse
        
    Raises:
        HTTPException: If validation fails
    """
    service = DailyKRAService(db)
    
    # Check if KRA already exists for this date
    existing_kra = await service.get_daily_kra_by_date(
        tenant_id=user_context["tenant_id"],
        user_id=user_context["user_id"],
        kra_date=kra_data.date,
    )
    
    if existing_kra:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Daily KRA already exists for {kra_data.date}",
        )
    
    # Create KRA
    kra = await service.create_daily_kra(
        tenant_id=user_context["tenant_id"],
        user_id=user_context["user_id"],
        kra_data=kra_data,
    )
    
    await db.commit()
    await db.refresh(kra)
    
    return DailyKRAResponse.from_orm(kra)


@router.get("/daily/{kra_id}", response_model=DailyKRAResponse)
async def get_daily_kra(
    kra_id: int,
    db: AsyncSession = Depends(get_db_session),
    user_context: dict = Depends(get_current_user_context),
) -> DailyKRAResponse:
    """
    Get specific daily KRA by ID
    
    Args:
        kra_id: Daily KRA ID to retrieve
        db: Database session
        user_context: Current user context (tenant_id, user_id, role)
        
    Returns:
        DailyKRAResponse
        
    Raises:
        HTTPException: 404 if KRA not found or doesn't belong to tenant
    """
    service = DailyKRAService(db)
    kra = await service.get_daily_kra_by_id(
        kra_id=kra_id,
        tenant_id=user_context["tenant_id"],
    )
    
    if not kra:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Daily KRA not found",
        )
    
    return DailyKRAResponse.from_orm(kra)


@router.put("/daily/{kra_id}", response_model=DailyKRAResponse)
async def update_daily_kra(
    kra_id: int,
    update_data: DailyKRAUpdate,
    db: AsyncSession = Depends(get_db_session),
    user_context: dict = Depends(get_current_user_context),
) -> DailyKRAResponse:
    """
    Update daily KRA
    
    Args:
        kra_id: Daily KRA ID to update
        update_data: Partial update data
        db: Database session
        user_context: Current user context (tenant_id, user_id, role)
        
    Returns:
        Updated DailyKRAResponse
        
    Raises:
        HTTPException: 404 if KRA not found
    """
    service = DailyKRAService(db)
    kra = await service.get_daily_kra_by_id(
        kra_id=kra_id,
        tenant_id=user_context["tenant_id"],
    )
    
    if not kra:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Daily KRA not found",
        )
    
    # Update KRA
    kra = await service.update_daily_kra(kra, update_data)
    await db.commit()
    await db.refresh(kra)
    
    return DailyKRAResponse.from_orm(kra)


@router.delete("/daily/{kra_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_daily_kra(
    kra_id: int,
    db: AsyncSession = Depends(get_db_session),
    user_context: dict = Depends(get_current_user_context),
) -> None:
    """
    Delete daily KRA (soft delete)
    
    Args:
        kra_id: Daily KRA ID to delete
        db: Database session
        user_context: Current user context (tenant_id, user_id, role)
        
    Raises:
        HTTPException: 404 if KRA not found
    """
    service = DailyKRAService(db)
    kra = await service.get_daily_kra_by_id(
        kra_id=kra_id,
        tenant_id=user_context["tenant_id"],
    )
    
    if not kra:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Daily KRA not found",
        )
    
    # Soft delete KRA
    await service.delete_daily_kra(kra)
    await db.commit()


# ==================== WEEKLY KRAs ====================

@router.get("/weekly", response_model=PaginatedResponse[WeeklyKRAListResponse])
async def list_weekly_kras(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    page: Optional[int] = Query(None, ge=1, description="Page number (alternative to skip)"),
    page_size: Optional[int] = Query(
        None,
        ge=1,
        le=100,
        description="Page size (alternative to limit)",
    ),
    user_id: Optional[int] = Query(None, description="Filter by specific user"),
    db: AsyncSession = Depends(get_db_session),
    user_context: dict = Depends(get_current_user_context),
) -> PaginatedResponse[WeeklyKRAListResponse]:
    """
    List all weekly KRAs for current tenant
    
    Supports filtering by user_id and pagination.
    Only returns KRAs belonging to the current user's tenant.
    
    Args:
        skip: Number of records to skip (pagination)
        limit: Number of records to return (pagination)
        user_id: Optional filter by specific user
        db: Database session
        user_context: Current user context (tenant_id, user_id, role)
        
    Returns:
        PaginatedResponse with list of weekly KRAs
    """
    service = WeeklyKRAService(db)
    resolved_skip, resolved_limit = resolve_pagination(skip, limit, page, page_size)
    kras, total = await service.list_weekly_kras(
        tenant_id=user_context["tenant_id"],
        user_id=user_id,
        skip=resolved_skip,
        limit=resolved_limit,
    )

    return PaginatedResponse(
        total=total,
        skip=resolved_skip,
        limit=resolved_limit,
        items=[WeeklyKRAListResponse.from_orm(kra) for kra in kras],
    )


@router.post(
    "/weekly",
    response_model=WeeklyKRAResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_weekly_kra(
    kra_data: WeeklyKRACreate,
    db: AsyncSession = Depends(get_db_session),
    user_context: dict = Depends(get_current_user_context),
) -> WeeklyKRAResponse:
    """
    Create new weekly KRA
    
    Args:
        kra_data: Weekly KRA creation data
        db: Database session
        user_context: Current user context (tenant_id, user_id, role)
        
    Returns:
        Created WeeklyKRAResponse
        
    Raises:
        HTTPException: If validation fails
    """
    service = WeeklyKRAService(db)
    
    # Check if KRA already exists for this week
    existing_kra = await service.get_weekly_kra_by_week(
        tenant_id=user_context["tenant_id"],
        user_id=user_context["user_id"],
        year=kra_data.year,
        week_number=kra_data.week_number,
    )
    
    if existing_kra:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Weekly KRA already exists for week {kra_data.week_number}/{kra_data.year}",
        )
    
    # Create KRA
    kra = await service.create_weekly_kra(
        tenant_id=user_context["tenant_id"],
        user_id=user_context["user_id"],
        kra_data=kra_data,
    )
    
    await db.commit()
    await db.refresh(kra)
    
    return WeeklyKRAResponse.from_orm(kra)


@router.get("/weekly/{kra_id}", response_model=WeeklyKRAResponse)
async def get_weekly_kra(
    kra_id: int,
    db: AsyncSession = Depends(get_db_session),
    user_context: dict = Depends(get_current_user_context),
) -> WeeklyKRAResponse:
    """
    Get specific weekly KRA by ID
    
    Args:
        kra_id: Weekly KRA ID to retrieve
        db: Database session
        user_context: Current user context (tenant_id, user_id, role)
        
    Returns:
        WeeklyKRAResponse
        
    Raises:
        HTTPException: 404 if KRA not found or doesn't belong to tenant
    """
    service = WeeklyKRAService(db)
    kra = await service.get_weekly_kra_by_id(
        kra_id=kra_id,
        tenant_id=user_context["tenant_id"],
    )
    
    if not kra:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Weekly KRA not found",
        )
    
    return WeeklyKRAResponse.from_orm(kra)


@router.put("/weekly/{kra_id}", response_model=WeeklyKRAResponse)
async def update_weekly_kra(
    kra_id: int,
    update_data: WeeklyKRAUpdate,
    db: AsyncSession = Depends(get_db_session),
    user_context: dict = Depends(get_current_user_context),
) -> WeeklyKRAResponse:
    """
    Update weekly KRA
    
    Args:
        kra_id: Weekly KRA ID to update
        update_data: Partial update data
        db: Database session
        user_context: Current user context (tenant_id, user_id, role)
        
    Returns:
        Updated WeeklyKRAResponse
        
    Raises:
        HTTPException: 404 if KRA not found
    """
    service = WeeklyKRAService(db)
    kra = await service.get_weekly_kra_by_id(
        kra_id=kra_id,
        tenant_id=user_context["tenant_id"],
    )
    
    if not kra:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Weekly KRA not found",
        )
    
    # Update KRA
    kra = await service.update_weekly_kra(kra, update_data)
    await db.commit()
    await db.refresh(kra)
    
    return WeeklyKRAResponse.from_orm(kra)


@router.delete("/weekly/{kra_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_weekly_kra(
    kra_id: int,
    db: AsyncSession = Depends(get_db_session),
    user_context: dict = Depends(get_current_user_context),
) -> None:
    """
    Delete weekly KRA (soft delete)
    
    Args:
        kra_id: Weekly KRA ID to delete
        db: Database session
        user_context: Current user context (tenant_id, user_id, role)
        
    Raises:
        HTTPException: 404 if KRA not found
    """
    service = WeeklyKRAService(db)
    kra = await service.get_weekly_kra_by_id(
        kra_id=kra_id,
        tenant_id=user_context["tenant_id"],
    )
    
    if not kra:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Weekly KRA not found",
        )
    
    # Soft delete KRA
    await service.delete_weekly_kra(kra)
    await db.commit()


# ==================== MONTHLY KRAs ====================

@router.get("/monthly", response_model=PaginatedResponse[MonthlyKRAListResponse])
async def list_monthly_kras(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    page: Optional[int] = Query(None, ge=1, description="Page number (alternative to skip)"),
    page_size: Optional[int] = Query(
        None,
        ge=1,
        le=100,
        description="Page size (alternative to limit)",
    ),
    user_id: Optional[int] = Query(None, description="Filter by specific user"),
    db: AsyncSession = Depends(get_db_session),
    user_context: dict = Depends(get_current_user_context),
) -> PaginatedResponse[MonthlyKRAListResponse]:
    """
    List all monthly KRAs for current tenant
    
    Supports filtering by user_id and pagination.
    Only returns KRAs belonging to the current user's tenant.
    
    Args:
        skip: Number of records to skip (pagination)
        limit: Number of records to return (pagination)
        user_id: Optional filter by specific user
        db: Database session
        user_context: Current user context (tenant_id, user_id, role)
        
    Returns:
        PaginatedResponse with list of monthly KRAs
    """
    service = MonthlyKRAService(db)
    resolved_skip, resolved_limit = resolve_pagination(skip, limit, page, page_size)
    kras, total = await service.list_monthly_kras(
        tenant_id=user_context["tenant_id"],
        user_id=user_id,
        skip=resolved_skip,
        limit=resolved_limit,
    )

    return PaginatedResponse(
        total=total,
        skip=resolved_skip,
        limit=resolved_limit,
        items=[MonthlyKRAListResponse.from_orm(kra) for kra in kras],
    )


@router.post(
    "/monthly",
    response_model=MonthlyKRAResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_monthly_kra(
    kra_data: MonthlyKRACreate,
    db: AsyncSession = Depends(get_db_session),
    user_context: dict = Depends(get_current_user_context),
) -> MonthlyKRAResponse:
    """
    Create new monthly KRA with revenue report submission
    
    Accepts S3 file URL for revenue report. The file should be uploaded to S3 separately
    and the URL provided in the revenue_report_url field.
    
    Args:
        kra_data: Monthly KRA creation data (includes revenue_report_url)
        db: Database session
        user_context: Current user context (tenant_id, user_id, role)
        
    Returns:
        Created MonthlyKRAResponse
        
    Raises:
        HTTPException: If validation fails or KRA already exists
    """
    service = MonthlyKRAService(db)
    
    # Check if KRA already exists for this month
    existing_kra = await service.get_monthly_kra_by_month(
        tenant_id=user_context["tenant_id"],
        user_id=user_context["user_id"],
        month=kra_data.month,
        year=kra_data.year,
    )
    
    if existing_kra:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Monthly KRA already exists for {kra_data.month}/{kra_data.year}",
        )
    
    # Create KRA
    kra = await service.create_monthly_kra(
        tenant_id=user_context["tenant_id"],
        user_id=user_context["user_id"],
        kra_data=kra_data,
    )
    
    await db.commit()
    await db.refresh(kra)
    
    return MonthlyKRAResponse.from_orm(kra)


@router.get("/monthly/{kra_id}", response_model=MonthlyKRAResponse)
async def get_monthly_kra(
    kra_id: int,
    db: AsyncSession = Depends(get_db_session),
    user_context: dict = Depends(get_current_user_context),
) -> MonthlyKRAResponse:
    """
    Get specific monthly KRA by ID
    
    Args:
        kra_id: Monthly KRA ID to retrieve
        db: Database session
        user_context: Current user context (tenant_id, user_id, role)
        
    Returns:
        MonthlyKRAResponse
        
    Raises:
        HTTPException: 404 if KRA not found or doesn't belong to tenant
    """
    service = MonthlyKRAService(db)
    kra = await service.get_monthly_kra_by_id(
        kra_id=kra_id,
        tenant_id=user_context["tenant_id"],
    )
    
    if not kra:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Monthly KRA not found",
        )
    
    return MonthlyKRAResponse.from_orm(kra)


@router.put("/monthly/{kra_id}", response_model=MonthlyKRAResponse)
async def update_monthly_kra(
    kra_id: int,
    update_data: MonthlyKRAUpdate,
    db: AsyncSession = Depends(get_db_session),
    user_context: dict = Depends(get_current_user_context),
) -> MonthlyKRAResponse:
    """
    Update monthly KRA
    
    Can be used to update the revenue_report_url with a new S3 file URL.
    
    Args:
        kra_id: Monthly KRA ID to update
        update_data: Partial update data
        db: Database session
        user_context: Current user context (tenant_id, user_id, role)
        
    Returns:
        Updated MonthlyKRAResponse
        
    Raises:
        HTTPException: 404 if KRA not found
    """
    service = MonthlyKRAService(db)
    kra = await service.get_monthly_kra_by_id(
        kra_id=kra_id,
        tenant_id=user_context["tenant_id"],
    )
    
    if not kra:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Monthly KRA not found",
        )
    
    # Update KRA
    kra = await service.update_monthly_kra(kra, update_data)
    await db.commit()
    await db.refresh(kra)
    
    return MonthlyKRAResponse.from_orm(kra)


@router.delete("/monthly/{kra_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_monthly_kra(
    kra_id: int,
    db: AsyncSession = Depends(get_db_session),
    user_context: dict = Depends(get_current_user_context),
) -> None:
    """
    Delete monthly KRA (soft delete)
    
    Args:
        kra_id: Monthly KRA ID to delete
        db: Database session
        user_context: Current user context (tenant_id, user_id, role)
        
    Raises:
        HTTPException: 404 if KRA not found
    """
    service = MonthlyKRAService(db)
    kra = await service.get_monthly_kra_by_id(
        kra_id=kra_id,
        tenant_id=user_context["tenant_id"],
    )
    
    if not kra:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Monthly KRA not found",
        )
    
    # Soft delete KRA
    await service.delete_monthly_kra(kra)
    await db.commit()


# ==================== QUARTERLY KRAs ====================

@router.get("/quarterly", response_model=PaginatedResponse[QuarterlyKRAListResponse])
async def list_quarterly_kras(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    page: Optional[int] = Query(None, ge=1, description="Page number (alternative to skip)"),
    page_size: Optional[int] = Query(
        None,
        ge=1,
        le=100,
        description="Page size (alternative to limit)",
    ),
    user_id: Optional[int] = Query(None, description="Filter by specific user"),
    db: AsyncSession = Depends(get_db_session),
    user_context: dict = Depends(get_current_user_context),
) -> PaginatedResponse[QuarterlyKRAListResponse]:
    """
    List all quarterly KRAs for current tenant
    
    Supports filtering by user_id and pagination.
    Only returns KRAs belonging to the current user's tenant.
    
    Args:
        skip: Number of records to skip (pagination)
        limit: Number of records to return (pagination)
        user_id: Optional filter by specific user
        db: Database session
        user_context: Current user context (tenant_id, user_id, role)
        
    Returns:
        PaginatedResponse with list of quarterly KRAs
    """
    service = QuarterlyKRAService(db)
    resolved_skip, resolved_limit = resolve_pagination(skip, limit, page, page_size)
    kras, total = await service.list_quarterly_kras(
        tenant_id=user_context["tenant_id"],
        user_id=user_id,
        skip=resolved_skip,
        limit=resolved_limit,
    )

    return PaginatedResponse(
        total=total,
        skip=resolved_skip,
        limit=resolved_limit,
        items=[QuarterlyKRAListResponse.from_orm(kra) for kra in kras],
    )


@router.post(
    "/quarterly",
    response_model=QuarterlyKRAResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_quarterly_kra(
    kra_data: QuarterlyKRACreate,
    db: AsyncSession = Depends(get_db_session),
    user_context: dict = Depends(get_current_user_context),
) -> QuarterlyKRAResponse:
    """
    Create new quarterly KRA with revenue report submission
    
    Accepts S3 file URL for revenue report. The file should be uploaded to S3 separately
    and the URL provided in the revenue_report_url field.
    
    Args:
        kra_data: Quarterly KRA creation data (includes revenue_report_url)
        db: Database session
        user_context: Current user context (tenant_id, user_id, role)
        
    Returns:
        Created QuarterlyKRAResponse
        
    Raises:
        HTTPException: If validation fails or KRA already exists
    """
    service = QuarterlyKRAService(db)
    
    # Check if KRA already exists for this quarter
    existing_kra = await service.get_quarterly_kra_by_quarter(
        tenant_id=user_context["tenant_id"],
        user_id=user_context["user_id"],
        quarter=kra_data.quarter,
        year=kra_data.year,
    )
    
    if existing_kra:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Quarterly KRA already exists for Q{kra_data.quarter}/{kra_data.year}",
        )
    
    # Create KRA
    kra = await service.create_quarterly_kra(
        tenant_id=user_context["tenant_id"],
        user_id=user_context["user_id"],
        kra_data=kra_data,
    )
    
    await db.commit()
    await db.refresh(kra)
    
    return QuarterlyKRAResponse.from_orm(kra)


@router.get("/quarterly/{kra_id}", response_model=QuarterlyKRAResponse)
async def get_quarterly_kra(
    kra_id: int,
    db: AsyncSession = Depends(get_db_session),
    user_context: dict = Depends(get_current_user_context),
) -> QuarterlyKRAResponse:
    """
    Get specific quarterly KRA by ID
    
    Args:
        kra_id: Quarterly KRA ID to retrieve
        db: Database session
        user_context: Current user context (tenant_id, user_id, role)
        
    Returns:
        QuarterlyKRAResponse
        
    Raises:
        HTTPException: 404 if KRA not found or doesn't belong to tenant
    """
    service = QuarterlyKRAService(db)
    kra = await service.get_quarterly_kra_by_id(
        kra_id=kra_id,
        tenant_id=user_context["tenant_id"],
    )
    
    if not kra:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Quarterly KRA not found",
        )
    
    return QuarterlyKRAResponse.from_orm(kra)


@router.put("/quarterly/{kra_id}", response_model=QuarterlyKRAResponse)
async def update_quarterly_kra(
    kra_id: int,
    update_data: QuarterlyKRAUpdate,
    db: AsyncSession = Depends(get_db_session),
    user_context: dict = Depends(get_current_user_context),
) -> QuarterlyKRAResponse:
    """
    Update quarterly KRA
    
    Can be used to update the revenue_report_url with a new S3 file URL.
    
    Args:
        kra_id: Quarterly KRA ID to update
        update_data: Partial update data
        db: Database session
        user_context: Current user context (tenant_id, user_id, role)
        
    Returns:
        Updated QuarterlyKRAResponse
        
    Raises:
        HTTPException: 404 if KRA not found
    """
    service = QuarterlyKRAService(db)
    kra = await service.get_quarterly_kra_by_id(
        kra_id=kra_id,
        tenant_id=user_context["tenant_id"],
    )
    
    if not kra:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Quarterly KRA not found",
        )
    
    # Update KRA
    kra = await service.update_quarterly_kra(kra, update_data)
    await db.commit()
    await db.refresh(kra)
    
    return QuarterlyKRAResponse.from_orm(kra)


@router.delete("/quarterly/{kra_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_quarterly_kra(
    kra_id: int,
    db: AsyncSession = Depends(get_db_session),
    user_context: dict = Depends(get_current_user_context),
) -> None:
    """
    Delete quarterly KRA (soft delete)
    
    Args:
        kra_id: Quarterly KRA ID to delete
        db: Database session
        user_context: Current user context (tenant_id, user_id, role)
        
    Raises:
        HTTPException: 404 if KRA not found
    """
    service = QuarterlyKRAService(db)
    kra = await service.get_quarterly_kra_by_id(
        kra_id=kra_id,
        tenant_id=user_context["tenant_id"],
    )
    
    if not kra:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Quarterly KRA not found",
        )
    
    # Soft delete KRA
    await service.delete_quarterly_kra(kra)
    await db.commit()
