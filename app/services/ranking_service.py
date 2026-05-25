"""
Ranking System Service - app/services/ranking_service.py

Business logic for employee ranking calculation.

Implements 7-category ranking system:
- Attendance & Functionality: 20%
- Task Completion: 25%
- Task Quality & Cleanliness: 20%
- Standby / Emergency Support: 10%
- Overtime Contribution: 10%
- Manager Review & Behaviour: 10%
- Customer Feedback / Complaints: 5%
"""

from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from uuid import UUID
import statistics

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ranking_models import EmployeeRanking, PerformanceStatus
from app.models.models import Employee, User, Property
from app.repositories.ranking_repository import (
    RankingCriteriaRepository, EmployeeScoresRepository,
    EmployeeRankingRepository, RankingAuditRepository, RankingInsightRepository
)
from app.schemas.ranking_schemas import (
    EmployeeRankingResponse, EmployeeRankingScoreBreakdown, RankingListItem,
    PerformanceMetric, EmployeePerformancePortal, EmployeeBadge
)
from app.utils.exceptions import NotFound, ValidationError


# ===========================================================
# DEFAULT RANKING CRITERIA
# ===========================================================

DEFAULT_CRITERIA = [
    {
        "name": "attendance",
        "criterion_name": "Attendance & Functionality",
        "weightage": 20.0,
        "max_points": 100.0,
        "description": "Reliability and consistency in attendance"
    },
    {
        "name": "task_completion",
        "criterion_name": "Task Completion",
        "weightage": 25.0,
        "max_points": 100.0,
        "description": "Timeliness and completion rate of assigned tasks"
    },
    {
        "name": "task_quality",
        "criterion_name": "Task Quality & Cleanliness",
        "weightage": 20.0,
        "max_points": 100.0,
        "description": "Quality and standards adherence in work"
    },
    {
        "name": "standby_support",
        "criterion_name": "Standby / Emergency Support",
        "weightage": 10.0,
        "max_points": 100.0,
        "description": "Availability for standby and emergency shifts"
    },
    {
        "name": "overtime",
        "criterion_name": "Overtime Contribution",
        "weightage": 10.0,
        "max_points": 100.0,
        "description": "Extra hours and dedication"
    },
    {
        "name": "manager_review",
        "criterion_name": "Manager Review & Behaviour",
        "weightage": 10.0,
        "max_points": 100.0,
        "description": "Professionalism and conduct at work"
    },
    {
        "name": "feedback",
        "criterion_name": "Customer Feedback / Complaints",
        "weightage": 5.0,
        "max_points": 100.0,
        "description": "Guest satisfaction and complaint handling"
    }
]


# ===========================================================
# RANKING SERVICE
# ===========================================================

class RankingService:
    """Service for employee ranking calculations"""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.criteria_repo = RankingCriteriaRepository(session)
        self.scores_repo = EmployeeScoresRepository(session)
        self.ranking_repo = EmployeeRankingRepository(session)
        self.audit_repo = RankingAuditRepository(session)
        self.insight_repo = RankingInsightRepository(session)

    # ===========================================================
    # INITIALIZATION
    # ===========================================================

    async def initialize_criteria(
        self,
        tenant_id: UUID,
        property_id: UUID
    ) -> List:
        """Initialize default criteria for property"""
        criteria_list = []
        
        for criterion in DEFAULT_CRITERIA:
            existing = await self.criteria_repo.get_criteria_by_name(
                property_id, criterion["criterion_name"]
            )
            
            if not existing:
                new_criteria = await self.criteria_repo.create_criteria(
                    tenant_id=tenant_id,
                    property_id=property_id,
                    criterion_name=criterion["criterion_name"],
                    weightage=criterion["weightage"],
                    max_points=criterion["max_points"],
                    description=criterion["description"]
                )
                criteria_list.append(new_criteria)
        
        return criteria_list

    # ===========================================================
    # CALCULATION ENGINE
    # ===========================================================

    async def calculate_employee_ranking(
        self,
        employee_id: UUID,
        property_id: UUID,
        period_start: datetime,
        period_end: datetime,
        ranking_type: str = "weekly"
    ) -> Optional[EmployeeRanking]:
        """Calculate ranking for single employee"""
        
        # Get employee
        employee = await self.session.get(Employee, employee_id)
        if not employee or not employee.is_active:
            raise NotFound(f"Active employee {employee_id} not found")
        
        # Get all criteria for property
        criteria_list = await self.criteria_repo.get_criteria_by_property(employee.property_id)
        
        # Fetch scores for each criterion
        scores_breakdown = {}
        total_weighted_score = 0.0
        total_weightage = 0.0
        
        for criterion in criteria_list:
            score = await self.scores_repo.get_score_by_criterion_period(
                employee_id=employee_id,
                criterion_name=criterion.criterion_name,
                period_start=period_start,
                period_end=period_end
            )
            
            if score:
                # Normalize to 0-100 based on max_points
                normalized_score = (score.final_points / criterion.max_points) * 100
                scores_breakdown[criterion.criterion_name] = normalized_score
                
                # Calculate weighted score
                weighted_score = normalized_score * (criterion.weightage / 100)
                total_weighted_score += weighted_score
                total_weightage += criterion.weightage
            else:
                # Default to 0 if no score
                scores_breakdown[criterion.criterion_name] = 0.0
                total_weightage += criterion.weightage
        
        # Final overall score
        overall_score = total_weighted_score if total_weightage == 100 else total_weighted_score
        overall_score = max(0, min(100, overall_score))
        
        # Get previous score for trend
        previous_ranking = await self.ranking_repo.get_employee_ranking(
            employee_id=employee_id,
            ranking_type=ranking_type
        )
        
        previous_score = previous_ranking.overall_score if previous_ranking else None
        score_change = None
        if previous_score is not None:
            score_change = overall_score - previous_score
        
        # Determine performance status
        performance_status = self._determine_performance_status(
            overall_score, score_change, previous_ranking
        )
        
        # Create ranking record
        ranking = await self.ranking_repo.create_ranking(
            tenant_id=employee.tenant_id,
            property_id=employee.property_id,
            employee_id=employee_id,
            user_id=employee.user_id,
            period_start=period_start,
            period_end=period_end,
            ranking_type=ranking_type,
            overall_score=overall_score,
            rank=0,  # Will be updated after all rankings
            total_active_employees=0,  # Will be updated
            scores_breakdown=scores_breakdown,
            performance_status=performance_status,
            previous_overall_score=previous_score,
            score_change=score_change
        )
        
        # Log action
        await self.audit_repo.log_action(
            tenant_id=employee.tenant_id,
            property_id=employee.property_id,
            action="ranking_calculated",
            employee_id=employee_id,
            new_value={
                "overall_score": float(overall_score),
                "performance_status": performance_status
            }
        )
        
        return ranking

    def _determine_performance_status(
        self,
        overall_score: float,
        score_change: Optional[float],
        previous_ranking: Optional[EmployeeRanking]
    ) -> str:
        """Determine performance status badge"""
        
        if overall_score >= 90:
            return PerformanceStatus.PROMOTION_READY
        elif overall_score >= 80:
            return PerformanceStatus.HIGH_PERFORMER
        elif overall_score >= 70:
            # Check if improved significantly
            if score_change and score_change >= 5:
                return PerformanceStatus.MOST_IMPROVED
            return PerformanceStatus.CONSISTENT
        elif overall_score >= 60:
            return PerformanceStatus.NEEDS_IMPROVEMENT
        else:
            return PerformanceStatus.NEEDS_IMPROVEMENT

    async def recalculate_property_rankings(
        self,
        property_id: UUID,
        period_start: datetime,
        period_end: datetime,
        ranking_type: str = "weekly"
    ) -> Dict:
        """Recalculate all rankings for property in period"""
        
        # Get all active employees
        result = await self.session.execute(
            select(Employee).where(
                and_(
                    Employee.property_id == property_id,
                    Employee.is_active == True
                )
            )
        )
        employees = result.scalars().all()
        
        if not employees:
            raise NotFound(f"No active employees in property {property_id}")
        
        # Calculate for each employee
        rankings = []
        for employee in employees:
            try:
                ranking = await self.calculate_employee_ranking(
                    employee_id=employee.id,
                    property_id=property_id,
                    period_start=period_start,
                    period_end=period_end,
                    ranking_type=ranking_type
                )
                rankings.append(ranking)
            except Exception as e:
                # Continue with next employee
                pass
        
        # Sort by overall_score descending and assign ranks
        rankings.sort(key=lambda r: r.overall_score, reverse=True)
        for idx, ranking in enumerate(rankings, 1):
            await self.ranking_repo.update_ranking(
                ranking.id,
                rank=idx,
                total_active_employees=len(rankings)
            )
        
        await self.session.commit()
        
        # Generate insights
        await self._generate_insights(property_id, rankings, period_start, period_end)
        
        return {
            "success": True,
            "total_calculated": len(rankings),
            "period": f"{period_start.date()} to {period_end.date()}"
        }

    # ===========================================================
    # INSIGHTS GENERATION
    # ===========================================================

    async def _generate_insights(
        self,
        property_id: UUID,
        rankings: List[EmployeeRanking],
        period_start: datetime,
        period_end: datetime
    ):
        """Generate AI insights for rankings"""
        
        if not rankings:
            return
        
        tenant_id = rankings[0].tenant_id
        
        # Most Improved
        improved = [r for r in rankings if r.score_change and r.score_change >= 5]
        if improved:
            most_improved = max(improved, key=lambda r: r.score_change)
            await self.insight_repo.create_insight(
                tenant_id=tenant_id,
                property_id=property_id,
                employee_id=most_improved.employee_id,
                period_start=period_start,
                period_end=period_end,
                insight_type="most_improved",
                title="Most Improved",
                description=f"Significant improvement in this ranking period (+{most_improved.score_change:.1f}%)",
                metric_name="score_improvement",
                metric_value=float(most_improved.score_change),
                priority=10,
                is_positive=True
            )
        
        # Top Performer
        top = rankings[0]
        if top.overall_score >= 90:
            await self.insight_repo.create_insight(
                tenant_id=tenant_id,
                property_id=property_id,
                employee_id=top.employee_id,
                period_start=period_start,
                period_end=period_end,
                insight_type="top_performer",
                title="Top Performer",
                description="Outstanding performance and dedication!",
                metric_name="overall_score",
                metric_value=float(top.overall_score),
                priority=10,
                is_positive=True
            )
        
        # Needs Attention
        low_performers = [r for r in rankings if r.overall_score < 60]
        if low_performers:
            needs_attn = low_performers[0]
            await self.insight_repo.create_insight(
                tenant_id=tenant_id,
                property_id=property_id,
                employee_id=needs_attn.employee_id,
                period_start=period_start,
                period_end=period_end,
                insight_type="needs_attention",
                title="Performance Needs Attention",
                description="Additional support and guidance may help improve performance",
                metric_name="overall_score",
                metric_value=float(needs_attn.overall_score),
                priority=8,
                is_positive=False
            )

    # ===========================================================
    # RESPONSE BUILDING
    # ===========================================================

    async def get_rankings_for_property(
        self,
        property_id: UUID,
        ranking_type: str = "weekly",
        skip: int = 0,
        limit: int = 50
    ) -> Tuple[List[RankingListItem], int]:
        """Get formatted ranking list"""
        
        rankings, total = await self.ranking_repo.get_current_rankings(
            property_id=property_id,
            ranking_type=ranking_type,
            skip=skip,
            limit=limit
        )
        
        items = []
        for ranking in rankings:
            employee = await self.session.get(Employee, ranking.employee_id)
            
            item = RankingListItem(
                rank=ranking.rank,
                employee_id=ranking.employee_id,
                employee_name=f"{employee.first_name} {employee.last_name}" if employee else "Unknown",
                department=employee.department.name if employee and employee.department else None,
                overall_score=ranking.overall_score,
                performance_status=ranking.performance_status,
                score_change=ranking.score_change,
                attendance_percent=ranking.scores_breakdown.get("Attendance & Functionality"),
                task_completion_percent=ranking.scores_breakdown.get("Task Completion"),
                task_quality_percent=ranking.scores_breakdown.get("Task Quality & Cleanliness")
            )
            items.append(item)
        
        return items, total

    async def get_employee_ranking_detail(
        self,
        employee_id: UUID,
        ranking_type: str = "weekly"
    ) -> Optional[EmployeeRankingResponse]:
        """Get detailed ranking for employee"""
        
        ranking = await self.ranking_repo.get_employee_ranking(
            employee_id=employee_id,
            ranking_type=ranking_type
        )
        
        if not ranking:
            return None
        
        employee = await self.session.get(Employee, employee_id)
        
        # Build score breakdown
        score_breakdown = []
        criteria_list = await self.criteria_repo.get_criteria_by_property(ranking.property_id)
        
        for criterion in criteria_list:
            score = ranking.scores_breakdown.get(criterion.criterion_name, 0)
            weighted_score = score * (criterion.weightage / 100)
            
            score_breakdown.append(
                EmployeeRankingScoreBreakdown(
                    criterion_name=criterion.criterion_name,
                    score=score,
                    weightage=criterion.weightage,
                    weighted_score=weighted_score
                )
            )
        
        # Calculate change percentage
        score_change_pct = None
        if ranking.previous_overall_score and ranking.previous_overall_score > 0:
            score_change_pct = (ranking.score_change / ranking.previous_overall_score) * 100
        
        return EmployeeRankingResponse(
            id=ranking.id,
            employee_id=ranking.employee_id,
            employee_name=f"{employee.first_name} {employee.last_name}" if employee else "Unknown",
            department=employee.department.name if employee and employee.department else None,
            rank=ranking.rank,
            overall_score=ranking.overall_score,
            performance_status=ranking.performance_status,
            period_start=ranking.period_start,
            period_end=ranking.period_end,
            ranking_type=ranking.ranking_type,
            total_active_employees=ranking.total_active_employees,
            scores_breakdown=score_breakdown,
            previous_overall_score=ranking.previous_overall_score,
            score_change=ranking.score_change,
            score_change_percentage=score_change_pct
        )

    async def get_performance_portal(
        self,
        employee_id: UUID
    ) -> Optional[EmployeePerformancePortal]:
        """Build employee performance portal"""
        
        employee = await self.session.get(Employee, employee_id)
        if not employee:
            raise NotFound(f"Employee {employee_id} not found")
        
        ranking = await self.ranking_repo.get_employee_ranking(
            employee_id=employee_id,
            ranking_type="weekly"
        )
        
        if not ranking:
            raise NotFound(f"No ranking found for employee {employee_id}")
        
        # Get insights
        insights = await self.insight_repo.get_insights_for_employee(employee_id, limit=5)
        badges_earned = [
            EmployeeBadge(
                badge_name=insight.insight_type,
                display_name=insight.title
            )
            for insight in insights
        ]
        
        # Build performance metrics
        metrics = [
            PerformanceMetric(
                metric_name="attendance",
                label="Attendance Rate",
                value=ranking.scores_breakdown.get("Attendance & Functionality", 0),
                unit="%"
            ),
            PerformanceMetric(
                metric_name="task_completion",
                label="Task Completion",
                value=ranking.scores_breakdown.get("Task Completion", 0),
                unit="%"
            ),
            PerformanceMetric(
                metric_name="task_quality",
                label="Task Quality & Cleanliness",
                value=ranking.scores_breakdown.get("Task Quality & Cleanliness", 0),
                unit="%"
            ),
            PerformanceMetric(
                metric_name="guest_satisfaction",
                label="Guest Satisfaction",
                value=ranking.scores_breakdown.get("Customer Feedback / Complaints", 0),
                unit="%"
            ),
            PerformanceMetric(
                metric_name="punctuality",
                label="Punctuality Score",
                value=ranking.overall_score,
                unit="pts"
            )
        ]
        
        return EmployeePerformancePortal(
            employee_id=employee_id,
            employee_name=f"{employee.first_name} {employee.last_name}",
            department=employee.department.name if employee.department else "N/A",
            position=employee.position or "N/A",
            current_rank=ranking.rank,
            current_overall_score=ranking.overall_score,
            performance_status=ranking.performance_status,
            score_breakdown=ranking.scores_breakdown,
            metrics=metrics,
            leaderboard_position=ranking.rank,
            total_employees=ranking.total_active_employees,
            score_history=[],  # TODO: Fetch historical data
            badges_earned=badges_earned,
            todays_tasks=[],  # TODO: Fetch from task system
            created_at=ranking.created_at
        )

    async def get_dashboard_stats(
        self,
        property_id: UUID
    ) -> Dict:
        """Get dashboard statistics"""
        
        # Get property
        prop = await self.session.get(Property, property_id)
        if not prop:
            raise NotFound(f"Property {property_id} not found")
        
        # Get top performers
        top_5 = await self.ranking_repo.get_top_performers(property_id, limit=5)
        top_5_items = []
        for ranking in top_5:
            emp = await self.session.get(Employee, ranking.employee_id)
            top_5_items.append(
                RankingListItem(
                    rank=ranking.rank,
                    employee_id=ranking.employee_id,
                    employee_name=f"{emp.first_name} {emp.last_name}" if emp else "Unknown",
                    department=emp.department.name if emp and emp.department else None,
                    overall_score=ranking.overall_score,
                    performance_status=ranking.performance_status,
                    score_change=ranking.score_change
                )
            )
        
        # Get stats
        stats = await self.ranking_repo.get_ranking_statistics(property_id)
        
        # Count by performance status
        promotion_ready = 0
        high_performer = 0
        consistent = 0
        needs_improvement = 0
        
        result = await self.session.execute(
            select(EmployeeRanking.performance_status, func.count()).where(
                EmployeeRanking.property_id == property_id
            ).group_by(EmployeeRanking.performance_status)
        )
        
        for status, count in result:
            if status == PerformanceStatus.PROMOTION_READY:
                promotion_ready = count
            elif status == PerformanceStatus.HIGH_PERFORMER:
                high_performer = count
            elif status == PerformanceStatus.CONSISTENT:
                consistent = count
            else:
                needs_improvement = count
        
        # Get insights
        property_insights = await self.insight_repo.get_insights_for_property(property_id, limit=3)
        
        return {
            "overall_workforce_score": stats.get("avg_score", 0),
            "active_staff": stats.get("total_employees", 0),
            "top_5_employees": top_5_items,
            "performance_distribution": {
                "promotion_ready": promotion_ready,
                "high_performer": high_performer,
                "consistent": consistent,
                "needs_improvement": needs_improvement
            },
            "insights": [
                {
                    "title": insight.title,
                    "description": insight.description,
                    "type": insight.insight_type,
                    "priority": insight.priority
                }
                for insight in property_insights
            ]
        }
