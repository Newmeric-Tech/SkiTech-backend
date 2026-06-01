"""
Ranking System API Endpoints - app/api/v1/endpoints/ranking.py

REST API endpoints for Employee Ranking System.
"""

from datetime import datetime, timedelta
from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db as get_async_session
from app.api.dependencies import get_current_user_obj as get_current_user
from app.models.models import User, Employee
from app.repositories.ranking_repository import (
    RankingCriteriaRepository, EmployeeScoresRepository, EmployeeRankingRepository
)
from app.schemas.ranking_schemas import (
    RankingCriteriaRequest, RankingCriteriaResponse,
    EmployeeScoreDetailRequest, EmployeeScoreResponse,
    RankingListItem, RankingsListResponse, EmployeeRankingResponse,
    DashboardStats, RecalculateRankingRequest, RecalculationResult,
    RankingType
)
from app.services.ranking_service import RankingService
from app.utils.exceptions import AccessDenied, NotFound, ValidationError


router = APIRouter(prefix="/rankings", tags=["rankings"])


# ===========================================================
# CURRENT STAFF MEMBER — OWN RANKING
# ===========================================================

@router.get(
    "/me",
    response_model=EmployeeRankingResponse,
    summary="Get current staff member's own ranking"
)
async def get_my_ranking(
    ranking_type: str = Query("weekly"),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session)
):
    """
    Returns the ranking for the currently authenticated staff member.
    Looks up the Employee record linked to this user, then fetches their ranking.
    """
    try:
        from sqlalchemy import select
        result = await session.execute(
            select(Employee).where(Employee.user_id == current_user.id)
        )
        employee = result.scalar_one_or_none()
        if not employee:
            raise NotFound("No employee record linked to your account")

        service = RankingService(session)
        ranking = await service.get_employee_ranking_detail(
            employee_id=employee.id,
            ranking_type=ranking_type
        )
        if not ranking:
            raise NotFound("No ranking found for the current period")

        return ranking
    except NotFound as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


# ===========================================================
# INITIALIZATION & SETUP
# ===========================================================

@router.post(
    "/initialize",
    status_code=status.HTTP_200_OK,
    summary="Initialize default ranking criteria"
)
async def initialize_ranking_criteria(
    tenant_id: UUID = Query(..., description="Tenant ID"),
    property_id: UUID = Query(..., description="Property ID"),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session)
):
    """
    Initialize default ranking criteria for a property.
    
    Creates 7 default criteria with standard weightages:
    - Attendance & Functionality: 20%
    - Task Completion: 25%
    - Task Quality & Cleanliness: 20%
    - Standby / Emergency Support: 10%
    - Overtime Contribution: 10%
    - Manager Review & Behaviour: 10%
    - Customer Feedback / Complaints: 5%
    """
    try:
        # Verify tenant access
        if current_user.tenant_id != tenant_id:
            raise AccessDenied("Not authorized to access this tenant")
        
        service = RankingService(session)
        criteria_list = await service.initialize_criteria(tenant_id, property_id)
        
        return {
            "success": True,
            "message": f"Initialized {len(criteria_list)} criteria",
            "criteria_count": len(criteria_list)
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


# ===========================================================
# RANKING CRITERIA MANAGEMENT
# ===========================================================

@router.post(
    "/criteria",
    response_model=RankingCriteriaResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create or update ranking criterion"
)
async def create_ranking_criterion(
    tenant_id: UUID = Query(...),
    property_id: UUID = Query(...),
    request: RankingCriteriaRequest = None,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session)
):
    """Create new ranking criterion"""
    try:
        if current_user.tenant_id != tenant_id:
            raise AccessDenied("Not authorized")
        
        repo = RankingCriteriaRepository(session)
        criteria = await repo.create_criteria(
            tenant_id=tenant_id,
            property_id=property_id,
            criterion_name=request.criterion_name,
            weightage=request.weightage,
            max_points=request.max_points,
            deduction_rules=[r.dict() for r in request.deduction_rules] if request.deduction_rules else None,
            description=request.description,
            details=request.details.dict() if request.details else None
        )
        
        await session.commit()
        return criteria
    except Exception as e:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.get(
    "/criteria",
    response_model=List[RankingCriteriaResponse],
    summary="List ranking criteria"
)
async def list_ranking_criteria(
    tenant_id: UUID = Query(...),
    property_id: UUID = Query(...),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session)
):
    """Get all ranking criteria for property"""
    try:
        if current_user.tenant_id != tenant_id:
            raise AccessDenied("Not authorized")
        
        repo = RankingCriteriaRepository(session)
        criteria_list = await repo.get_criteria_by_property(property_id)
        
        return criteria_list
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


# ===========================================================
# EMPLOYEE SCORES
# ===========================================================

@router.post(
    "/employees/{employee_id}/scores",
    response_model=EmployeeScoreResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Record employee score for criterion"
)
async def record_employee_score(
    employee_id: UUID,
    tenant_id: UUID = Query(...),
    property_id: UUID = Query(...),
    request: EmployeeScoreDetailRequest = None,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session)
):
    """
    Record a score for an employee on a specific criterion.
    
    Supports recording historical scores for recalculation.
    """
    try:
        if current_user.tenant_id != tenant_id:
            raise AccessDenied("Not authorized")
        
        repo = EmployeeScoresRepository(session)
        
        # Get criterion to get weightage
        criteria_repo = RankingCriteriaRepository(session)
        criterion = await criteria_repo.get_criteria_by_name(property_id, request.criterion_name)
        
        if not criterion:
            raise NotFound(f"Criterion {request.criterion_name} not found")
        
        score = await repo.create_score(
            tenant_id=tenant_id,
            property_id=property_id,
            employee_id=employee_id,
            criterion_name=request.criterion_name,
            weightage=criterion.weightage,
            raw_points=request.raw_points,
            deductions=request.deductions,
            max_points=criterion.max_points,
            period_start=request.period_start,
            period_end=request.period_end,
            deduction_details=request.deduction_details,
            notes=request.notes,
            evidence=request.evidence
        )
        
        await session.commit()
        return score
    except Exception as e:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.get(
    "/employees/{employee_id}/scores",
    response_model=List[EmployeeScoreResponse],
    summary="Get employee scores"
)
async def get_employee_scores(
    employee_id: UUID,
    tenant_id: UUID = Query(...),
    property_id: UUID = Query(...),
    period_start: datetime = Query(None),
    period_end: datetime = Query(None),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session)
):
    """Get all scores for an employee"""
    try:
        if current_user.tenant_id != tenant_id:
            raise AccessDenied("Not authorized")
        
        repo = EmployeeScoresRepository(session)
        scores = await repo.get_employee_scores(
            employee_id=employee_id,
            period_start=period_start,
            period_end=period_end
        )
        
        return scores
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


# ===========================================================
# RANKINGS
# ===========================================================

@router.get(
    "/properties/{property_id}/rankings",
    response_model=RankingsListResponse,
    summary="Get employee rankings for property"
)
async def get_property_rankings(
    property_id: UUID,
    tenant_id: UUID = Query(...),
    ranking_type: str = Query("weekly", description="weekly, monthly, yearly"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session)
):
    """
    Get current rankings for all employees in property.
    
    Shows:
    - Rank and overall score
    - Performance status badge
    - Score breakdown by criterion
    - Comparison to previous period
    """
    try:
        if current_user.tenant_id != tenant_id:
            raise AccessDenied("Not authorized")
        
        service = RankingService(session)
        items, total = await service.get_rankings_for_property(
            property_id=property_id,
            ranking_type=ranking_type,
            skip=skip,
            limit=limit
        )
        
        return RankingsListResponse(
            total=total,
            skip=skip,
            limit=limit,
            items=items,
            ranking_type=ranking_type,
            period_start=datetime.now(),  # TODO: Get actual period
            period_end=datetime.now(),
            property_name="Property"  # TODO: Get property name
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.get(
    "/employees/{employee_id}/ranking",
    response_model=EmployeeRankingResponse,
    summary="Get employee ranking details"
)
async def get_employee_ranking(
    employee_id: UUID,
    tenant_id: UUID = Query(...),
    ranking_type: str = Query("weekly"),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session)
):
    """Get detailed ranking for specific employee"""
    try:
        if current_user.tenant_id != tenant_id:
            raise AccessDenied("Not authorized")
        
        service = RankingService(session)
        ranking = await service.get_employee_ranking_detail(
            employee_id=employee_id,
            ranking_type=ranking_type
        )
        
        if not ranking:
            raise NotFound("No ranking found for employee")
        
        return ranking
    except NotFound as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.get(
    "/employees/{employee_id}/performance-portal",
    response_model=dict,
    summary="Get employee performance portal"
)
async def get_performance_portal(
    employee_id: UUID,
    tenant_id: UUID = Query(...),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session)
):
    """
    Get employee's personal performance page.
    
    Shows:
    - Current ranking and score
    - Score breakdown
    - Performance trends
    - Achievements and badges
    - Leaderboard position
    - Today's tasks
    """
    try:
        # Allow employees to view their own portal or allow managers
        if current_user.tenant_id != tenant_id:
            raise AccessDenied("Not authorized")
        
        service = RankingService(session)
        portal = await service.get_performance_portal(employee_id)
        
        if not portal:
            raise NotFound("Performance data not available")
        
        return portal.dict()
    except NotFound as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


# ===========================================================
# DASHBOARD
# ===========================================================

@router.get(
    "/properties/{property_id}/dashboard",
    response_model=dict,
    summary="Get ranking dashboard stats"
)
async def get_dashboard_stats(
    property_id: UUID,
    tenant_id: UUID = Query(...),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session)
):
    """
    Get dashboard overview statistics.
    
    Shows:
    - Overall workforce score
    - Top 5 employees
    - Performance distribution
    - Key insights
    - Attendance and overtime metrics
    """
    try:
        if current_user.tenant_id != tenant_id:
            raise AccessDenied("Not authorized")
        
        service = RankingService(session)
        stats = await service.get_dashboard_stats(property_id)
        
        return stats
    except NotFound as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


# ===========================================================
# RECALCULATION
# ===========================================================

@router.post(
    "/properties/{property_id}/recalculate",
    response_model=RecalculationResult,
    summary="Recalculate all rankings"
)
async def recalculate_rankings(
    property_id: UUID,
    tenant_id: UUID = Query(...),
    request: RecalculateRankingRequest = None,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session)
):
    """
    Trigger recalculation of all rankings.
    
    Recalculates employee scores, assigns ranks, and generates insights.
    """
    try:
        if current_user.tenant_id != tenant_id:
            raise AccessDenied("Not authorized")
        
        service = RankingService(session)
        result = await service.recalculate_property_rankings(
            property_id=property_id,
            period_start=request.period_start,
            period_end=request.period_end,
            ranking_type=request.ranking_type
        )
        
        return RecalculationResult(
            success=result["success"],
            message=f"Calculated rankings for {result['total_calculated']} employees",
            employees_processed=result["total_calculated"],
            new_rankings_created=result["total_calculated"],
            existing_rankings_updated=0
        )
    except NotFound as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
