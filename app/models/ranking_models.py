"""
Employee Ranking System Models - app/models/ranking_models.py

Implements the 7-category ranking system with weightages:
- Attendance & Functionality: 20%
- Task Completion: 25%
- Task Quality & Cleanliness: 20%
- Standby / Emergency Support: 10%
- Overtime Contribution: 10%
- Manager Review & Behaviour: 10%
- Customer Feedback / Complaints: 5%
"""

import uuid
from datetime import datetime
from enum import Enum
from typing import Optional

from sqlalchemy import (
    Boolean, CheckConstraint, Column, DateTime, Enum as SQLEnum, Float, ForeignKey,
    Index, Integer, String, Text, UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.models.base import Base, UUIDMixin, TimestampMixin, SoftDeleteMixin


# ===========================================================
# ENUMS
# ===========================================================

class RankingStatus(str, Enum):
    """Ranking calculation status"""
    ACTIVE = "active"
    INACTIVE = "inactive"
    ARCHIVED = "archived"


class PerformanceStatus(str, Enum):
    """Employee performance status badge"""
    PROMOTION_READY = "promotion_ready"
    HIGH_PERFORMER = "high_performer"
    CONSISTENT = "consistent"
    NEEDS_IMPROVEMENT = "needs_improvement"
    SMART_RANKING = "smart_ranking"
    MOST_IMPROVED = "most_improved"


# ===========================================================
# RANKING CRITERIA CONFIGURATION
# ===========================================================

class RankingCriteriaConfig(Base, UUIDMixin, TimestampMixin):
    """
    Configuration for ranking criteria.
    
    Stores the weightages and point deduction rules for each category.
    Per property to allow customization.
    """
    __tablename__ = "ranking_criteria_config"

    tenant_id: UUID = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    property_id: UUID = Column(UUID(as_uuid=True), ForeignKey("properties.id", ondelete="CASCADE"), nullable=False, index=True)
    
    # Criterion name (attendance, task_completion, etc.)
    criterion_name: str = Column(String(100), nullable=False)
    
    # Weightage percentage
    weightage: float = Column(Float, nullable=False)  # e.g., 20.0 for 20%
    
    # Maximum points possible
    max_points: float = Column(Float, nullable=False, default=100.0)
    
    # Deduction rules as JSON: [{"issue": "name", "points": -x}, ...]
    deduction_rules: dict = Column(JSONB, nullable=True)
    
    # Description and criteria details
    description: Optional[str] = Column(Text, nullable=True)
    details: Optional[dict] = Column(JSONB, nullable=True)  # Stores criterion-specific details
    
    # Is this criterion active
    is_active: bool = Column(Boolean, nullable=False, default=True)

    __table_args__ = (
        UniqueConstraint("property_id", "criterion_name", name="uq_property_criterion"),
        CheckConstraint("weightage > 0 AND weightage <= 100", name="check_weightage"),
        Index("idx_criteria_tenant_id", "tenant_id"),
        Index("idx_criteria_property_id", "property_id"),
    )

    property = relationship("Property")


# ===========================================================
# EMPLOYEE SCORES (Per Criterion)
# ===========================================================

class EmployeeRankingScore(Base, UUIDMixin, TimestampMixin, SoftDeleteMixin):
    """
    Individual score for an employee on a specific criterion.
    
    Stores:
    - Raw points scored
    - Deductions applied
    - Final score
    - Evidence/notes for audit trail
    
    Recalculated periodically (weekly/monthly).
    """
    __tablename__ = "employee_ranking_scores"

    # Identifiers
    tenant_id: UUID = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    property_id: UUID = Column(UUID(as_uuid=True), ForeignKey("properties.id", ondelete="CASCADE"), nullable=False, index=True)
    employee_id: UUID = Column(UUID(as_uuid=True), ForeignKey("employees.id", ondelete="CASCADE"), nullable=False, index=True)
    
    # Criterion being scored
    criterion_name: str = Column(String(100), nullable=False)  # e.g., "attendance", "task_completion"
    weightage: float = Column(Float, nullable=False)  # Criterion weightage
    
    # Scoring
    max_points: float = Column(Float, nullable=False, default=100.0)
    raw_points: float = Column(Float, nullable=False)  # Before deductions
    deductions: float = Column(Float, nullable=False, default=0.0)  # Total deductions
    final_points: float = Column(Float, nullable=False)  # After deductions: raw_points - deductions
    
    # Deduction details
    deduction_details: Optional[dict] = Column(JSONB, nullable=True)  # List of deductions applied
    
    # Period
    period_start: datetime = Column(DateTime, nullable=False)
    period_end: datetime = Column(DateTime, nullable=False)
    
    # Calculated as
    calculated_at: datetime = Column(DateTime, nullable=False, server_default=func.now())
    
    # Evidence and notes
    notes: Optional[str] = Column(Text, nullable=True)
    evidence: Optional[dict] = Column(JSONB, nullable=True)  # Supporting data

    __table_args__ = (
        UniqueConstraint("employee_id", "criterion_name", "period_start", "period_end", name="uq_employee_criterion_period"),
        CheckConstraint("raw_points >= 0 AND raw_points <= max_points", name="check_raw_points"),
        CheckConstraint("final_points >= 0", name="check_final_points"),
        Index("idx_scores_employee_id", "employee_id"),
        Index("idx_scores_property_id", "property_id"),
        Index("idx_scores_criterion", "criterion_name"),
        Index("idx_scores_period", "period_start", "period_end"),
    )

    employee = relationship("Employee")
    property = relationship("Property")


# ===========================================================
# EMPLOYEE FINAL RANKING
# ===========================================================

class EmployeeRanking(Base, UUIDMixin, TimestampMixin, SoftDeleteMixin):
    """
    Final ranking for an employee.
    
    Aggregates all criterion scores into:
    - Overall score (0-100)
    - Rank (1, 2, 3, ...)
    - Performance status badge
    - Ranking tier
    
    Recalculated weekly/monthly.
    """
    __tablename__ = "employee_rankings"

    tenant_id: UUID = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    property_id: UUID = Column(UUID(as_uuid=True), ForeignKey("properties.id", ondelete="CASCADE"), nullable=False, index=True)
    employee_id: UUID = Column(UUID(as_uuid=True), ForeignKey("employees.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id: Optional[UUID] = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    
    # Ranking period
    period_start: datetime = Column(DateTime, nullable=False)
    period_end: datetime = Column(DateTime, nullable=False)
    ranking_type: str = Column(String(50), nullable=False)  # "weekly", "monthly", "yearly"
    
    # Overall score calculation
    overall_score: float = Column(Float, nullable=False)  # 0-100
    rank: int = Column(Integer, nullable=False)  # 1, 2, 3, ...
    total_active_employees: int = Column(Integer, nullable=False)  # For context
    
    # Performance status
    performance_status: str = Column(
        SQLEnum(PerformanceStatus),
        nullable=False,
        default=PerformanceStatus.CONSISTENT
    )
    
    # Individual criterion scores breakdown (denormalized for performance)
    scores_breakdown: dict = Column(JSONB, nullable=False)  # {criterion_name: score_value, ...}
    
    # Previous period for trend
    previous_overall_score: Optional[float] = Column(Float, nullable=True)
    score_change: Optional[float] = Column(Float, nullable=True)  # Positive = improvement
    
    # Status
    status: str = Column(
        SQLEnum(RankingStatus),
        nullable=False,
        default=RankingStatus.ACTIVE
    )
    
    # Recalculation info
    calculated_at: datetime = Column(DateTime, nullable=False, server_default=func.now())
    recalculated_at: Optional[datetime] = Column(DateTime, nullable=True)

    __table_args__ = (
        UniqueConstraint("employee_id", "period_start", "period_end", "ranking_type", name="uq_employee_period_ranking"),
        CheckConstraint("overall_score >= 0 AND overall_score <= 100", name="check_overall_score"),
        CheckConstraint("rank >= 1", name="check_rank"),
        Index("idx_ranking_employee_id", "employee_id"),
        Index("idx_ranking_property_id", "property_id"),
        Index("idx_ranking_overall_score", "overall_score"),
        Index("idx_ranking_rank", "rank"),
        Index("idx_ranking_period", "period_start", "period_end"),
        Index("idx_ranking_performance_status", "performance_status"),
    )

    employee = relationship("Employee")
    user = relationship("User")
    property = relationship("Property")


# ===========================================================
# RANKING HISTORY & AUDIT TRAIL
# ===========================================================

class RankingAuditLog(Base, UUIDMixin, TimestampMixin):
    """
    Audit trail for ranking calculations.
    
    Tracks every score change and recalculation for compliance and debugging.
    """
    __tablename__ = "ranking_audit_logs"

    tenant_id: UUID = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    property_id: UUID = Column(UUID(as_uuid=True), ForeignKey("properties.id", ondelete="CASCADE"), nullable=False, index=True)
    employee_id: UUID = Column(UUID(as_uuid=True), ForeignKey("employees.id", ondelete="SET NULL"), nullable=True)
    
    # What changed
    action: str = Column(String(50), nullable=False)  # "score_updated", "ranking_calculated", etc.
    criterion_name: Optional[str] = Column(String(100), nullable=True)
    
    # Old vs new values
    old_value: Optional[dict] = Column(JSONB, nullable=True)
    new_value: Optional[dict] = Column(JSONB, nullable=True)
    
    # Who made the change
    changed_by: Optional[UUID] = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    
    # Notes
    notes: Optional[str] = Column(Text, nullable=True)

    __table_args__ = (
        Index("idx_audit_employee_id", "employee_id"),
        Index("idx_audit_property_id", "property_id"),
        Index("idx_audit_action", "action"),
        Index("idx_audit_created_at", "created_at"),
    )

    employee = relationship("Employee")
    changed_by_user = relationship("User", foreign_keys=[changed_by])


# ===========================================================
# RANKING INSIGHTS & ANALYTICS
# ===========================================================

class RankingInsight(Base, UUIDMixin, TimestampMixin):
    """
    AI-generated insights about employee performance.
    
    Stores automated observations like:
    - "Most Improved" - biggest score improvement
    - "Attendance Champion" - perfect attendance
    - "Needs Attention" - low performance areas
    - etc.
    """
    __tablename__ = "ranking_insights"

    tenant_id: UUID = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    property_id: UUID = Column(UUID(as_uuid=True), ForeignKey("properties.id", ondelete="CASCADE"), nullable=False, index=True)
    employee_id: UUID = Column(UUID(as_uuid=True), ForeignKey("employees.id", ondelete="CASCADE"), nullable=False, index=True)
    
    # Period
    period_start: datetime = Column(DateTime, nullable=False)
    period_end: datetime = Column(DateTime, nullable=False)
    
    # Insight details
    insight_type: str = Column(String(100), nullable=False)  # "most_improved", "attendance_champion", etc.
    title: str = Column(String(255), nullable=False)
    description: str = Column(Text, nullable=False)
    
    # Metric
    metric_name: str = Column(String(100), nullable=True)  # e.g., "attendance_rate", "score_improvement"
    metric_value: float = Column(Float, nullable=True)
    
    # Priority for display
    priority: int = Column(Integer, nullable=False, default=0)
    is_positive: bool = Column(Boolean, nullable=False, default=True)

    __table_args__ = (
        Index("idx_insight_employee_id", "employee_id"),
        Index("idx_insight_property_id", "property_id"),
        Index("idx_insight_type", "insight_type"),
        Index("idx_insight_priority", "priority"),
    )

    employee = relationship("Employee")
    property = relationship("Property")
