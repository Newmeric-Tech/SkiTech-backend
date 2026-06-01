"""
Ranking System Schemas - app/schemas/ranking_schemas.py

Request/Response models for Employee Ranking System.
"""

from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field, validator


# ===========================================================
# ENUMS
# ===========================================================

class RankingType(str, Enum):
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    YEARLY = "yearly"


class PerformanceStatus(str, Enum):
    PROMOTION_READY = "promotion_ready"
    HIGH_PERFORMER = "high_performer"
    CONSISTENT = "consistent"
    NEEDS_IMPROVEMENT = "needs_improvement"
    SMART_RANKING = "smart_ranking"
    MOST_IMPROVED = "most_improved"


# ===========================================================
# CRITERIA CONFIGURATION
# ===========================================================

class DeductionRule(BaseModel):
    """Deduction rule for a criterion"""
    issue: str = Field(..., description="Issue name")
    points: float = Field(..., description="Points to deduct (negative value)")
    description: Optional[str] = None


class RankingCriteriaDetailRequest(BaseModel):
    """Criterion-specific details"""
    min_attendance_percent: Optional[float] = Field(None, ge=0, le=100)
    days_absence_deduction: Optional[float] = Field(None, ge=0)
    early_punch_in_deduction: Optional[float] = Field(None, ge=0)
    late_punch_in_deduction: Optional[float] = Field(None, ge=0)
    
    # Task completion details
    on_time_completion_target: Optional[float] = Field(None, ge=0, le=100)
    delayed_task_deduction: Optional[float] = Field(None, ge=0)
    
    # Quality details
    quality_inspection_passing_rate: Optional[float] = Field(None, ge=0, le=100)
    failed_inspection_deduction: Optional[float] = Field(None, ge=0)


class RankingCriteriaRequest(BaseModel):
    """Request to create/update ranking criteria"""
    criterion_name: str = Field(..., description="Name of criterion")
    weightage: float = Field(..., ge=0.1, le=100, description="Weightage in percentage")
    max_points: float = Field(100.0, ge=1, description="Maximum points possible")
    deduction_rules: Optional[List[DeductionRule]] = None
    description: Optional[str] = None
    details: Optional[RankingCriteriaDetailRequest] = None


class RankingCriteriaResponse(BaseModel):
    """Response for ranking criteria"""
    id: UUID
    criterion_name: str
    weightage: float
    max_points: float
    deduction_rules: Optional[List[DeductionRule]] = None
    description: Optional[str] = None
    details: Optional[Dict] = None
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True


# ===========================================================
# EMPLOYEE SCORES
# ===========================================================

class EmployeeScoreDetailRequest(BaseModel):
    """Request to record a score for an employee"""
    criterion_name: str = Field(..., description="Criterion name")
    raw_points: float = Field(..., ge=0, description="Raw points before deductions")
    deductions: float = Field(0, ge=0, description="Total deductions")
    deduction_details: Optional[Dict] = Field(None, description="Breakdown of deductions")
    notes: Optional[str] = None
    evidence: Optional[Dict] = None
    period_start: datetime
    period_end: datetime


class EmployeeScoreResponse(BaseModel):
    """Response for employee score"""
    id: UUID
    employee_id: UUID
    criterion_name: str
    weightage: float
    max_points: float
    raw_points: float
    deductions: float
    final_points: float
    deduction_details: Optional[Dict] = None
    period_start: datetime
    period_end: datetime
    calculated_at: datetime
    notes: Optional[str] = None

    class Config:
        from_attributes = True


# ===========================================================
# EMPLOYEE RANKING
# ===========================================================

class EmployeeRankingScoreBreakdown(BaseModel):
    """Score breakdown for a specific ranking"""
    criterion_name: str
    score: float
    weightage: float
    weighted_score: float


class EmployeeRankingResponse(BaseModel):
    """Response for employee ranking"""
    id: UUID
    employee_id: UUID
    employee_name: str
    department: Optional[str] = None
    rank: int
    overall_score: float
    performance_status: str
    period_start: datetime
    period_end: datetime
    ranking_type: str
    total_active_employees: int
    scores_breakdown: List[EmployeeRankingScoreBreakdown]
    previous_overall_score: Optional[float] = None
    score_change: Optional[float] = None
    score_change_percentage: Optional[float] = None

    class Config:
        from_attributes = True


class RankingListItem(BaseModel):
    """Compact ranking item for lists"""
    rank: int
    employee_id: UUID
    employee_name: str
    department: Optional[str] = None
    overall_score: float
    performance_status: str
    score_change: Optional[float] = None
    attendance_percent: Optional[float] = None
    task_completion_percent: Optional[float] = None
    task_quality_percent: Optional[float] = None


class RankingsListResponse(BaseModel):
    """Paginated list of rankings"""
    total: int
    skip: int
    limit: int
    items: List[RankingListItem]
    ranking_type: str
    period_start: datetime
    period_end: datetime
    property_name: Optional[str] = None


# ===========================================================
# EMPLOYEE PERFORMANCE PORTAL
# ===========================================================

class EmployeeBadge(BaseModel):
    """Achievement badge for employee"""
    badge_name: str
    display_name: str
    icon: Optional[str] = None
    description: Optional[str] = None


class PerformanceMetric(BaseModel):
    """Individual performance metric"""
    metric_name: str
    label: str
    value: float
    unit: str  # "%", "pts", "days", etc.
    status: Optional[str] = None  # "good", "warning", "critical"


class EmployeePerformancePortal(BaseModel):
    """Employee's personal performance page"""
    employee_id: UUID
    employee_name: str
    employee_avatar: Optional[str] = None
    department: str
    position: str
    
    # Current period ranking
    current_rank: int
    current_overall_score: float
    performance_status: str
    
    # Score breakdown
    score_breakdown: Dict[str, float]  # {criterion: score}
    
    # Key metrics
    metrics: List[PerformanceMetric]
    
    # Position in leaderboard
    leaderboard_position: int
    total_employees: int
    
    # Trends
    score_history: List[Dict]  # [{period, score}, ...]
    badges_earned: List[EmployeeBadge]
    
    # Today's tasks
    todays_tasks: List[Dict]
    
    created_at: datetime


# ===========================================================
# INSIGHTS & ANALYTICS
# ===========================================================

class RankingInsightResponse(BaseModel):
    """AI-generated insight about performance"""
    id: UUID
    insight_type: str
    title: str
    description: str
    metric_name: Optional[str] = None
    metric_value: Optional[float] = None
    is_positive: bool
    priority: int

    class Config:
        from_attributes = True


class PropertyRankingStats(BaseModel):
    """Property-level ranking statistics"""
    total_active_employees: int
    average_score: float
    highest_score: float
    lowest_score: float
    score_std_dev: float
    
    # Distribution
    promotion_ready_count: int  # 90-100
    high_performer_count: int   # 80-89
    consistent_count: int       # 70-79
    needs_improvement_count: int  # <70


class DashboardStats(BaseModel):
    """Dashboard statistics"""
    overall_workforce_score: float
    active_staff: int
    attendance_percent: float
    overtime_hours: int
    standby_on_call: int
    total_hours: int
    staff_count: int
    
    top_5_employees: List[RankingListItem]
    property_stats: PropertyRankingStats
    insights: List[RankingInsightResponse]


# ===========================================================
# RECALCULATION REQUESTS
# ===========================================================

class RecalculateRankingRequest(BaseModel):
    """Request to recalculate rankings"""
    ranking_type: RankingType
    period_start: datetime
    period_end: datetime
    recalculate_all: bool = Field(False, description="Recalculate all employees or just active ones")


class RecalculationResult(BaseModel):
    """Result of ranking recalculation"""
    success: bool
    message: str
    employees_processed: int
    new_rankings_created: int
    existing_rankings_updated: int
    errors: Optional[List[str]] = None


# ===========================================================
# EXPORT & REPORTING
# ===========================================================

class RankingReportRequest(BaseModel):
    """Request to generate ranking report"""
    ranking_type: RankingType
    period_start: datetime
    period_end: datetime
    include_insights: bool = True
    include_history: bool = True


class EmployeeDetailedRankingReport(BaseModel):
    """Detailed report for an employee"""
    employee_id: UUID
    employee_name: str
    period: str
    overall_score: float
    rank: int
    
    scores_by_criterion: Dict[str, float]
    deductions_by_criterion: Dict[str, float]
    
    performance_status: str
    previous_score: Optional[float]
    score_improvement: Optional[float]
    
    insights: List[str]
    recommendations: List[str]
