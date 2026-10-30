"""
Ranking System Service - app/services/ranking_service.py

Business logic for employee ranking calculation.

Implements 8-category ranking system:
- Attendance & Functionality: 20%
- Task Completion: 15%
- KRA Completion: 10% (calculated from KRA tasks; the others are entered manually)
- Task Quality & Cleanliness: 20%
- Standby / Emergency Support: 10%
- Overtime Contribution: 10%
- Manager Review & Behaviour: 10%
- Customer Feedback / Complaints: 5%
"""

from datetime import datetime, timedelta, timezone
import logging
from typing import Dict, List, Optional, Tuple
from uuid import UUID
import statistics

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.kra_tasks import KraDefinition, KraOccurrence
from app.models.ranking_models import EmployeeRanking, PerformanceStatus, RankingCriteriaConfig
from app.models.models import Employee, User, Property
from app.repositories.ranking_repository import (
    RankingCriteriaRepository, EmployeeScoresRepository,
    EmployeeRankingRepository, RankingAuditRepository, RankingInsightRepository
)
from app.schemas.ranking_schemas import (
    EmployeeRankingResponse, EmployeeRankingScoreBreakdown, RankingListItem,
    PerformanceMetric, EmployeePerformancePortal, EmployeeBadge
)
from app.services.kra_task_service import ensure_occurrences
from app.utils.exceptions import NotFound, ValidationError
from app.utils.safe_errors import log_safe_exception

logger = logging.getLogger("skitech")


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
        "weightage": 15.0,
        "max_points": 100.0,
        "description": "Timeliness and completion rate of assigned tasks"
    },
    {
        "name": "kra_completion",
        "criterion_name": "KRA Completion",
        "weightage": 10.0,
        "max_points": 100.0,
        "description": "Share of assigned KRA tasks completed, with half credit when completed after a delay"
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
# KRA COMPLETION SCORE
# ===========================================================

KRA_CRITERION = "KRA Completion"
# completed_at is UTC while periods are local dates, so a day's grace.
KRA_LATE_ALLOWANCE = timedelta(days=1)


def _naive_utc(value: datetime) -> datetime:
    """The period columns have no time zone, and asyncpg rejects aware values.
    The frontend sends toISOString() dates, with a Z."""
    return value.astimezone(timezone.utc).replace(tzinfo=None) if value.tzinfo else value


def kra_credit(status: str, was_delayed: bool, completed_at: Optional[datetime], period_end) -> Tuple[float, str]:
    """(credit, category) for one task period."""
    if status != "completed":
        return 0.0, "not_completed"
    if was_delayed:
        return 0.5, "completed_after_delay"
    if completed_at is None or completed_at.date() > period_end + KRA_LATE_ALLOWANCE:
        return 0.5, "late_without_mark"
    return 1.0, "on_time"


def score_kra_occurrences(occurrences) -> Optional[dict]:
    """raw_points (0-100) and evidence counts, or None if nothing counts.

    Takes rows with definition_id, assignee_id, period_start, period_end,
    status, was_delayed, completed_at and frequency. A task ended and reassigned
    in the same period has two rows: it counts once, with the better credit.
    """
    best: Dict[tuple, Tuple[float, str, str]] = {}
    for row in occurrences:
        key = (row.definition_id, row.assignee_id, row.period_start)
        credit, category = kra_credit(row.status, row.was_delayed, row.completed_at, row.period_end)
        if key not in best or credit > best[key][0]:
            best[key] = (credit, category, row.frequency)
    if not best:
        return None

    evidence = {"counted": len(best), "on_time": 0, "completed_after_delay": 0,
                "late_without_mark": 0, "not_completed": 0, "by_frequency": {}}
    for _, category, frequency in best.values():
        evidence[category] += 1
        evidence["by_frequency"][frequency] = evidence["by_frequency"].get(frequency, 0) + 1
    raw_points = sum(credit for credit, _, _ in best.values()) / len(best) * 100
    return {"raw_points": raw_points, "evidence": evidence}


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
    # TENANT SCOPING
    # ===========================================================
    # tenant_id always comes from the authenticated user. Another tenant's
    # property or employee raises the same NotFound as a missing one.

    async def require_property(self, tenant_id: UUID, property_id: UUID) -> Property:
        prop = await self.session.get(Property, property_id)
        if not prop or prop.tenant_id != tenant_id:
            raise NotFound(f"Property {property_id} not found")
        return prop

    async def require_employee(self, tenant_id: UUID, employee_id: UUID) -> Employee:
        employee = await self.session.get(Employee, employee_id)
        if not employee or employee.tenant_id != tenant_id:
            raise NotFound(f"Employee {employee_id} not found")
        return employee

    # ===========================================================
    # INITIALIZATION
    # ===========================================================

    async def initialize_criteria(
        self,
        tenant_id: UUID,
        property_id: UUID
    ) -> List:
        """Initialize default criteria for property"""
        await self.require_property(tenant_id, property_id)
        criteria_list = []

        for criterion in DEFAULT_CRITERIA:
            existing = await self.criteria_repo.get_criteria_by_name(
                tenant_id, property_id, criterion["criterion_name"]
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
    # KRA COMPLETION
    # ===========================================================

    async def store_kra_score(
        self,
        tenant_id: UUID,
        employee: Employee,
        criterion: RankingCriteriaConfig,
        period_start: datetime,
        period_end: datetime
    ) -> bool:
        """Calculate and save the employee's KRA Completion score for the period,
        replacing any earlier one. False when the criterion doesn't apply to them
        (no linked user, or no task period counted), and then no row is left.
        The caller commits.
        """
        result = None
        if employee.user_id is not None:
            result = await self._kra_result(tenant_id, employee, period_start.date(), period_end.date())

        existing = await self.scores_repo.get_score_by_criterion_period(
            tenant_id=tenant_id,
            employee_id=employee.id,
            criterion_name=KRA_CRITERION,
            period_start=period_start,
            period_end=period_end
        )
        if result is None:
            if existing:
                await self.session.delete(existing)
                await self.session.flush()
            return False

        if existing:
            await self.scores_repo.update_score(
                tenant_id,
                existing.id,
                property_id=employee.property_id,
                weightage=criterion.weightage,
                max_points=criterion.max_points,
                raw_points=result["raw_points"],
                deductions=0.0,
                final_points=result["raw_points"],
                deduction_details=None,
                notes=None,
                evidence=result["evidence"],
                calculated_at=datetime.utcnow(),
                deleted_at=None
            )
        else:
            await self.scores_repo.create_score(
                tenant_id=tenant_id,
                property_id=employee.property_id,
                employee_id=employee.id,
                criterion_name=KRA_CRITERION,
                weightage=criterion.weightage,
                raw_points=result["raw_points"],
                max_points=criterion.max_points,
                period_start=period_start,
                period_end=period_end,
                evidence=result["evidence"]
            )
        return True

    async def _kra_result(self, tenant_id: UUID, employee: Employee, window_start, window_end) -> Optional[dict]:
        # Tasks nobody opened must exist to count as missed.
        today = datetime.utcnow().date()
        await ensure_occurrences(
            self.session, tenant_id, assignee_id=employee.user_id, property_id=employee.property_id,
            up_to_date=min(window_end, today)
        )
        rows = (await self.session.execute(
            select(
                KraOccurrence.definition_id, KraOccurrence.assignee_id, KraOccurrence.period_start,
                KraOccurrence.period_end, KraOccurrence.status, KraOccurrence.was_delayed,
                KraOccurrence.completed_at, KraDefinition.frequency
            )
            .join(KraDefinition, KraDefinition.id == KraOccurrence.definition_id)
            .where(
                KraOccurrence.tenant_id == tenant_id,
                KraOccurrence.assignee_id == employee.user_id,
                KraOccurrence.property_id == employee.property_id,
                KraOccurrence.period_end >= window_start,
                KraOccurrence.period_end <= window_end,
                KraOccurrence.period_end < today  # a period ending today is still running
            )
        )).all()
        return score_kra_occurrences(rows)

    # ===========================================================
    # CALCULATION ENGINE
    # ===========================================================

    async def calculate_employee_ranking(
        self,
        tenant_id: UUID,
        employee_id: UUID,
        property_id: UUID,
        period_start: datetime,
        period_end: datetime,
        ranking_type: str = "weekly"
    ) -> Optional[EmployeeRanking]:
        """Calculate ranking for single employee"""
        period_start, period_end = _naive_utc(period_start), _naive_utc(period_end)
        
        # Get employee
        employee = await self.session.get(Employee, employee_id)
        if not employee or not employee.is_active or employee.tenant_id != tenant_id:
            raise NotFound(f"Active employee {employee_id} not found")

        # Get all criteria for property
        criteria_list = await self.criteria_repo.get_criteria_by_property(tenant_id, employee.property_id)

        # KRA Completion is calculated, unlike the manually entered criteria
        kra_applies = True
        kra_criterion = next((c for c in criteria_list if c.criterion_name == KRA_CRITERION), None)
        if kra_criterion:
            kra_applies = await self.store_kra_score(tenant_id, employee, kra_criterion, period_start, period_end)

        # Fetch scores for each criterion
        scores_breakdown = {}
        total_weighted_score = 0.0
        total_weightage = 0.0

        for criterion in criteria_list:
            if criterion.criterion_name == KRA_CRITERION and not kra_applies:
                # Not a zero: left out, and the other weights scale up
                continue

            score = await self.scores_repo.get_score_by_criterion_period(
                tenant_id=tenant_id,
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
        
        # Final overall score, out of 100 whatever weight the applicable criteria total
        overall_score = total_weighted_score / total_weightage * 100 if total_weightage else 0.0
        overall_score = max(0, min(100, overall_score))

        # Get previous score for trend (not this period's own row when re-running)
        previous_ranking = await self.ranking_repo.get_previous_ranking(
            tenant_id=tenant_id,
            employee_id=employee_id,
            ranking_type=ranking_type,
            period_start=period_start,
            period_end=period_end
        )
        
        previous_score = previous_ranking.overall_score if previous_ranking else None
        score_change = None
        if previous_score is not None:
            score_change = overall_score - previous_score
        
        # Determine performance status
        performance_status = self._determine_performance_status(
            overall_score, score_change, previous_ranking
        )
        
        # Update this period's ranking when re-running (uq_employee_period_ranking), else create it
        existing_ranking = await self.ranking_repo.get_ranking_for_period(
            tenant_id=tenant_id,
            employee_id=employee_id,
            ranking_type=ranking_type,
            period_start=period_start,
            period_end=period_end
        )
        if existing_ranking:
            ranking = await self.ranking_repo.update_ranking(
                tenant_id,
                existing_ranking.id,
                property_id=employee.property_id,
                user_id=employee.user_id,
                overall_score=overall_score,
                scores_breakdown=scores_breakdown,
                performance_status=performance_status,
                previous_overall_score=previous_score,
                score_change=score_change,
                recalculated_at=datetime.utcnow()
            )
        else:
            ranking = await self.ranking_repo.create_ranking(
                tenant_id=employee.tenant_id,
                property_id=employee.property_id,
                employee_id=employee_id,
                user_id=employee.user_id,
                period_start=period_start,
                period_end=period_end,
                ranking_type=ranking_type,
                overall_score=overall_score,
                rank=1,  # Provisional (check_rank requires rank >= 1); recalculate_property_rankings sets the real rank
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
        tenant_id: UUID,
        property_id: UUID,
        period_start: datetime,
        period_end: datetime,
        ranking_type: str = "weekly"
    ) -> Dict:
        """Recalculate all rankings for property in period"""
        period_start, period_end = _naive_utc(period_start), _naive_utc(period_end)
        
        # Get all active employees
        result = await self.session.execute(
            select(Employee).where(
                and_(
                    Employee.tenant_id == tenant_id,
                    Employee.property_id == property_id,
                    Employee.is_active == True
                )
            )
        )
        employee_ids = [employee.id for employee in result.scalars().all()]

        if not employee_ids:
            raise NotFound(f"No active employees in property {property_id}")

        # Calculate for each employee. The savepoint keeps one employee's database
        # error from aborting the transaction the others share.
        rankings = []
        for employee_id in employee_ids:
            try:
                async with self.session.begin_nested():
                    ranking = await self.calculate_employee_ranking(
                        tenant_id=tenant_id,
                        employee_id=employee_id,
                        property_id=property_id,
                        period_start=period_start,
                        period_end=period_end,
                        ranking_type=ranking_type
                    )
                rankings.append(ranking)
            except Exception as e:
                # Continue with next employee
                log_safe_exception(logger, f"[RANKING] calculation failed for employee {employee_id}", e)
        
        # Sort by overall_score descending and assign ranks
        rankings.sort(key=lambda r: r.overall_score, reverse=True)
        for idx, ranking in enumerate(rankings, 1):
            await self.ranking_repo.update_ranking(
                tenant_id,
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
        tenant_id: UUID,
        property_id: UUID,
        ranking_type: str = "weekly",
        skip: int = 0,
        limit: int = 50
    ) -> Tuple[List[RankingListItem], int]:
        """Get formatted ranking list"""
        
        rankings, total = await self.ranking_repo.get_current_rankings(
            tenant_id=tenant_id,
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
        tenant_id: UUID,
        employee_id: UUID,
        ranking_type: str = "weekly"
    ) -> Optional[EmployeeRankingResponse]:
        """Get detailed ranking for employee"""
        
        ranking = await self.ranking_repo.get_employee_ranking(
            tenant_id=tenant_id,
            employee_id=employee_id,
            ranking_type=ranking_type
        )
        
        if not ranking:
            return None
        
        employee = await self.session.get(Employee, employee_id)
        
        # Build score breakdown
        score_breakdown = []
        criteria_list = await self.criteria_repo.get_criteria_by_property(tenant_id, ranking.property_id)
        
        for criterion in criteria_list:
            if criterion.criterion_name == KRA_CRITERION and KRA_CRITERION not in ranking.scores_breakdown:
                continue  # not applicable to this employee, which is not a zero

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
        tenant_id: UUID,
        employee_id: UUID
    ) -> Optional[EmployeePerformancePortal]:
        """Build employee performance portal"""
        
        employee = await self.require_employee(tenant_id, employee_id)

        ranking = await self.ranking_repo.get_employee_ranking(
            tenant_id=tenant_id,
            employee_id=employee_id,
            ranking_type="weekly"
        )
        
        if not ranking:
            raise NotFound(f"No ranking found for employee {employee_id}")
        
        # Get insights
        insights = await self.insight_repo.get_insights_for_employee(tenant_id, employee_id, limit=5)
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
        tenant_id: UUID,
        property_id: UUID
    ) -> Dict:
        """Get dashboard statistics"""
        
        # Get property
        await self.require_property(tenant_id, property_id)
        
        # Get top performers
        top_5 = await self.ranking_repo.get_top_performers(tenant_id, property_id, limit=5)
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
        stats = await self.ranking_repo.get_ranking_statistics(tenant_id, property_id)
        
        # Count by performance status
        promotion_ready = 0
        high_performer = 0
        consistent = 0
        needs_improvement = 0
        
        result = await self.session.execute(
            select(EmployeeRanking.performance_status, func.count()).where(
                EmployeeRanking.tenant_id == tenant_id,
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
        property_insights = await self.insight_repo.get_insights_for_property(tenant_id, property_id, limit=3)
        
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
