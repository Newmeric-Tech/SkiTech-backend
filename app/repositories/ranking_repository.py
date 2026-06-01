"""
Ranking System Repository - app/repositories/ranking_repository.py

Data access layer for ranking system.
"""

from datetime import datetime
from typing import List, Optional, Tuple
from uuid import UUID

from sqlalchemy import and_, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ranking_models import (
    EmployeeRanking, EmployeeRankingScore, RankingCriteriaConfig,
    RankingAuditLog, RankingInsight
)
from app.models.models import Employee


# ===========================================================
# RANKING CRITERIA REPOSITORY
# ===========================================================

class RankingCriteriaRepository:
    """Repository for ranking criteria configuration"""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_criteria(
        self,
        tenant_id: UUID,
        property_id: UUID,
        criterion_name: str,
        weightage: float,
        max_points: float = 100.0,
        deduction_rules: Optional[dict] = None,
        description: Optional[str] = None,
        details: Optional[dict] = None
    ) -> RankingCriteriaConfig:
        """Create new ranking criterion"""
        criteria = RankingCriteriaConfig(
            tenant_id=tenant_id,
            property_id=property_id,
            criterion_name=criterion_name,
            weightage=weightage,
            max_points=max_points,
            deduction_rules=deduction_rules,
            description=description,
            details=details
        )
        self.session.add(criteria)
        await self.session.flush()
        return criteria

    async def get_criteria_by_property(
        self,
        property_id: UUID,
        active_only: bool = True
    ) -> List[RankingCriteriaConfig]:
        """Get all criteria for property"""
        query = select(RankingCriteriaConfig).where(
            RankingCriteriaConfig.property_id == property_id
        )
        if active_only:
            query = query.where(RankingCriteriaConfig.is_active == True)
        
        result = await self.session.execute(query)
        return result.scalars().all()

    async def get_criteria_by_name(
        self,
        property_id: UUID,
        criterion_name: str
    ) -> Optional[RankingCriteriaConfig]:
        """Get specific criterion"""
        result = await self.session.execute(
            select(RankingCriteriaConfig).where(
                and_(
                    RankingCriteriaConfig.property_id == property_id,
                    RankingCriteriaConfig.criterion_name == criterion_name
                )
            )
        )
        return result.scalar_one_or_none()

    async def update_criteria(
        self,
        criteria_id: UUID,
        **kwargs
    ) -> RankingCriteriaConfig:
        """Update criterion"""
        criteria = await self.session.get(RankingCriteriaConfig, criteria_id)
        if criteria:
            for key, value in kwargs.items():
                if hasattr(criteria, key):
                    setattr(criteria, key, value)
            await self.session.flush()
        return criteria


# ===========================================================
# EMPLOYEE SCORES REPOSITORY
# ===========================================================

class EmployeeScoresRepository:
    """Repository for employee scores"""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_score(
        self,
        tenant_id: UUID,
        property_id: UUID,
        employee_id: UUID,
        criterion_name: str,
        weightage: float,
        raw_points: float,
        deductions: float = 0.0,
        max_points: float = 100.0,
        period_start: datetime = None,
        period_end: datetime = None,
        deduction_details: Optional[dict] = None,
        notes: Optional[str] = None,
        evidence: Optional[dict] = None
    ) -> EmployeeRankingScore:
        """Create new employee score"""
        final_points = max(0, raw_points - deductions)
        
        score = EmployeeRankingScore(
            tenant_id=tenant_id,
            property_id=property_id,
            employee_id=employee_id,
            criterion_name=criterion_name,
            weightage=weightage,
            raw_points=raw_points,
            deductions=deductions,
            final_points=final_points,
            max_points=max_points,
            period_start=period_start,
            period_end=period_end,
            deduction_details=deduction_details,
            notes=notes,
            evidence=evidence
        )
        self.session.add(score)
        await self.session.flush()
        return score

    async def get_employee_scores(
        self,
        employee_id: UUID,
        period_start: Optional[datetime] = None,
        period_end: Optional[datetime] = None
    ) -> List[EmployeeRankingScore]:
        """Get all scores for employee in period"""
        query = select(EmployeeRankingScore).where(
            EmployeeRankingScore.employee_id == employee_id
        )
        if period_start and period_end:
            query = query.where(
                and_(
                    EmployeeRankingScore.period_start >= period_start,
                    EmployeeRankingScore.period_end <= period_end
                )
            )
        result = await self.session.execute(query)
        return result.scalars().all()

    async def get_score_by_criterion_period(
        self,
        employee_id: UUID,
        criterion_name: str,
        period_start: datetime,
        period_end: datetime
    ) -> Optional[EmployeeRankingScore]:
        """Get specific score"""
        result = await self.session.execute(
            select(EmployeeRankingScore).where(
                and_(
                    EmployeeRankingScore.employee_id == employee_id,
                    EmployeeRankingScore.criterion_name == criterion_name,
                    EmployeeRankingScore.period_start == period_start,
                    EmployeeRankingScore.period_end == period_end
                )
            )
        )
        return result.scalar_one_or_none()

    async def update_score(
        self,
        score_id: UUID,
        **kwargs
    ) -> EmployeeRankingScore:
        """Update employee score"""
        score = await self.session.get(EmployeeRankingScore, score_id)
        if score:
            for key, value in kwargs.items():
                if hasattr(score, key):
                    setattr(score, key, value)
            await self.session.flush()
        return score


# ===========================================================
# EMPLOYEE RANKING REPOSITORY
# ===========================================================

class EmployeeRankingRepository:
    """Repository for employee rankings"""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_ranking(
        self,
        tenant_id: UUID,
        property_id: UUID,
        employee_id: UUID,
        user_id: Optional[UUID],
        period_start: datetime,
        period_end: datetime,
        ranking_type: str,
        overall_score: float,
        rank: int,
        total_active_employees: int,
        scores_breakdown: dict,
        performance_status: str = "consistent",
        previous_overall_score: Optional[float] = None,
        score_change: Optional[float] = None
    ) -> EmployeeRanking:
        """Create new ranking"""
        ranking = EmployeeRanking(
            tenant_id=tenant_id,
            property_id=property_id,
            employee_id=employee_id,
            user_id=user_id,
            period_start=period_start,
            period_end=period_end,
            ranking_type=ranking_type,
            overall_score=overall_score,
            rank=rank,
            total_active_employees=total_active_employees,
            scores_breakdown=scores_breakdown,
            performance_status=performance_status,
            previous_overall_score=previous_overall_score,
            score_change=score_change
        )
        self.session.add(ranking)
        await self.session.flush()
        return ranking

    async def get_current_rankings(
        self,
        property_id: UUID,
        ranking_type: str = "weekly",
        period_start: Optional[datetime] = None,
        period_end: Optional[datetime] = None,
        skip: int = 0,
        limit: int = 50
    ) -> Tuple[List[EmployeeRanking], int]:
        """Get rankings for property, most recent"""
        query = select(EmployeeRanking).where(
            and_(
                EmployeeRanking.property_id == property_id,
                EmployeeRanking.ranking_type == ranking_type
            )
        )
        
        if period_start and period_end:
            query = query.where(
                and_(
                    EmployeeRanking.period_start >= period_start,
                    EmployeeRanking.period_end <= period_end
                )
            )
        
        # Count total
        count_result = await self.session.execute(
            select(func.count()).select_from(query.alias())
        )
        total = count_result.scalar()
        
        # Get paginated results, ordered by rank
        query = query.order_by(EmployeeRanking.rank).offset(skip).limit(limit)
        result = await self.session.execute(query)
        rankings = result.scalars().all()
        
        return rankings, total

    async def get_employee_ranking(
        self,
        employee_id: UUID,
        ranking_type: str = "weekly",
        period_start: Optional[datetime] = None,
        period_end: Optional[datetime] = None
    ) -> Optional[EmployeeRanking]:
        """Get specific employee ranking"""
        query = select(EmployeeRanking).where(
            and_(
                EmployeeRanking.employee_id == employee_id,
                EmployeeRanking.ranking_type == ranking_type
            )
        )
        
        if period_start and period_end:
            query = query.where(
                and_(
                    EmployeeRanking.period_start >= period_start,
                    EmployeeRanking.period_end <= period_end
                )
            )
        
        result = await self.session.execute(query.order_by(desc(EmployeeRanking.created_at)).limit(1))
        return result.scalar_one_or_none()

    async def get_top_performers(
        self,
        property_id: UUID,
        limit: int = 5
    ) -> List[EmployeeRanking]:
        """Get top performers"""
        result = await self.session.execute(
            select(EmployeeRanking)
            .where(EmployeeRanking.property_id == property_id)
            .order_by(EmployeeRanking.rank)
            .limit(limit)
        )
        return result.scalars().all()

    async def update_ranking(
        self,
        ranking_id: UUID,
        **kwargs
    ) -> EmployeeRanking:
        """Update ranking"""
        ranking = await self.session.get(EmployeeRanking, ranking_id)
        if ranking:
            for key, value in kwargs.items():
                if hasattr(ranking, key):
                    setattr(ranking, key, value)
            await self.session.flush()
        return ranking

    async def get_ranking_statistics(
        self,
        property_id: UUID,
        ranking_type: str = "weekly"
    ) -> dict:
        """Get ranking statistics for property"""
        result = await self.session.execute(
            select(
                func.count().label("total_employees"),
                func.avg(EmployeeRanking.overall_score).label("avg_score"),
                func.max(EmployeeRanking.overall_score).label("max_score"),
                func.min(EmployeeRanking.overall_score).label("min_score")
            ).where(
                and_(
                    EmployeeRanking.property_id == property_id,
                    EmployeeRanking.ranking_type == ranking_type
                )
            )
        )
        row = result.one()
        return {
            "total_employees": row.total_employees or 0,
            "avg_score": float(row.avg_score) if row.avg_score else 0,
            "max_score": float(row.max_score) if row.max_score else 0,
            "min_score": float(row.min_score) if row.min_score else 0
        }


# ===========================================================
# AUDIT LOG REPOSITORY
# ===========================================================

class RankingAuditRepository:
    """Repository for audit logs"""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def log_action(
        self,
        tenant_id: UUID,
        property_id: UUID,
        action: str,
        employee_id: Optional[UUID] = None,
        criterion_name: Optional[str] = None,
        old_value: Optional[dict] = None,
        new_value: Optional[dict] = None,
        changed_by: Optional[UUID] = None,
        notes: Optional[str] = None
    ) -> RankingAuditLog:
        """Log action"""
        log = RankingAuditLog(
            tenant_id=tenant_id,
            property_id=property_id,
            employee_id=employee_id,
            action=action,
            criterion_name=criterion_name,
            old_value=old_value,
            new_value=new_value,
            changed_by=changed_by,
            notes=notes
        )
        self.session.add(log)
        await self.session.flush()
        return log


# ===========================================================
# INSIGHTS REPOSITORY
# ===========================================================

class RankingInsightRepository:
    """Repository for insights"""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_insight(
        self,
        tenant_id: UUID,
        property_id: UUID,
        employee_id: UUID,
        period_start: datetime,
        period_end: datetime,
        insight_type: str,
        title: str,
        description: str,
        metric_name: Optional[str] = None,
        metric_value: Optional[float] = None,
        priority: int = 0,
        is_positive: bool = True
    ) -> RankingInsight:
        """Create insight"""
        insight = RankingInsight(
            tenant_id=tenant_id,
            property_id=property_id,
            employee_id=employee_id,
            period_start=period_start,
            period_end=period_end,
            insight_type=insight_type,
            title=title,
            description=description,
            metric_name=metric_name,
            metric_value=metric_value,
            priority=priority,
            is_positive=is_positive
        )
        self.session.add(insight)
        await self.session.flush()
        return insight

    async def get_insights_for_property(
        self,
        property_id: UUID,
        limit: int = 10
    ) -> List[RankingInsight]:
        """Get insights for property"""
        result = await self.session.execute(
            select(RankingInsight)
            .where(RankingInsight.property_id == property_id)
            .order_by(desc(RankingInsight.priority), desc(RankingInsight.created_at))
            .limit(limit)
        )
        return result.scalars().all()

    async def get_insights_for_employee(
        self,
        employee_id: UUID,
        limit: int = 5
    ) -> List[RankingInsight]:
        """Get insights for specific employee"""
        result = await self.session.execute(
            select(RankingInsight)
            .where(RankingInsight.employee_id == employee_id)
            .order_by(desc(RankingInsight.priority), desc(RankingInsight.created_at))
            .limit(limit)
        )
        return result.scalars().all()
