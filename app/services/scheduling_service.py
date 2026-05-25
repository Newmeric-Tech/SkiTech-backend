"""
Employee Scheduling Service - app/services/scheduling_service.py
"""

from datetime import datetime, timedelta
from typing import List, Optional, Tuple
from uuid import UUID

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.models import (
    Employee, EmployeeAvailability, WeeklySchedule, ShiftAssignment,
    ReplacementRequest, ShiftResponse, EmployeeSkill, Department, User
)
from app.schemas.scheduling import (
    EmployeeAvailabilityCreate, WeeklyScheduleCreate, ShiftAssignmentCreate,
    ReplacementRequestCreate, ShiftResponseCreate, CriticalActionItem,
    ConflictDetectionResult, RecommendedEmployeeScore, AIRecommendationResponse,
    ManagerDashboardData, StaffDashboardData
)


class SchedulingService:
    """Service for managing employee scheduling, shifts, and replacements"""

    def __init__(self, db: AsyncSession, tenant_id: UUID, property_id: Optional[UUID], user_id: UUID):
        self.db = db
        self.tenant_id = tenant_id
        self.property_id = property_id  # None → tenant-wide (owner/admin)
        self.user_id = user_id

    # ─────────────────────────────────────────────────────────────
    # Employee Availability Management
    # ─────────────────────────────────────────────────────────────

    async def create_availability(self, employee_id: UUID, data: EmployeeAvailabilityCreate):
        """Create employee availability record"""
        availability = EmployeeAvailability(
            tenant_id=self.tenant_id,
            property_id=self.property_id,
            employee_id=employee_id,
            availability_date=data.availability_date,
            status=data.status,
            reason=data.reason,
            notes=data.notes
        )
        self.db.add(availability)
        await self.db.flush()
        return availability

    async def bulk_create_availability(self, employee_id: UUID, start_date: datetime, 
                                       end_date: datetime, status: str, reason: Optional[str] = None):
        """Bulk create availability for date range"""
        current_date = start_date
        availabilities = []
        
        while current_date <= end_date:
            availability = EmployeeAvailability(
                tenant_id=self.tenant_id,
                property_id=self.property_id,
                employee_id=employee_id,
                availability_date=current_date,
                status=status,
                reason=reason
            )
            availabilities.append(availability)
            current_date += timedelta(days=1)
        
        self.db.add_all(availabilities)
        await self.db.flush()
        return availabilities

    async def get_employee_availability(self, employee_id: UUID, date: datetime) -> Optional[EmployeeAvailability]:
        """Get employee availability for specific date"""
        stmt = select(EmployeeAvailability).where(
            and_(
                EmployeeAvailability.employee_id == employee_id,
                EmployeeAvailability.availability_date == date
            )
        )
        result = await self.db.execute(stmt)
        return result.scalars().first()

    # ─────────────────────────────────────────────────────────────
    # Weekly Schedule Management
    # ─────────────────────────────────────────────────────────────

    async def create_weekly_schedule(self, employee_id: UUID, data: WeeklyScheduleCreate):
        """Create weekly schedule for employee"""
        schedule = WeeklySchedule(
            tenant_id=self.tenant_id,
            property_id=self.property_id,
            employee_id=employee_id,
            week_start_date=data.week_start_date,
            week_end_date=data.week_end_date,
            department_id=data.department_id,
            status=data.status,
            assigned_by=self.user_id
        )
        self.db.add(schedule)
        await self.db.flush()
        return schedule

    async def bulk_create_weekly_schedules(self, employee_ids: List[UUID], 
                                          week_start: datetime, week_end: datetime, 
                                          department_id: Optional[UUID] = None):
        """Bulk create weekly schedules for multiple employees"""
        schedules = []
        for emp_id in employee_ids:
            schedule = WeeklySchedule(
                tenant_id=self.tenant_id,
                property_id=self.property_id,
                employee_id=emp_id,
                week_start_date=week_start,
                week_end_date=week_end,
                department_id=department_id,
                status="draft",
                assigned_by=self.user_id,
                assigned_at=datetime.utcnow()
            )
            schedules.append(schedule)
        
        self.db.add_all(schedules)
        await self.db.flush()
        return schedules

    async def get_weekly_schedule(self, schedule_id: UUID) -> Optional[WeeklySchedule]:
        """Get weekly schedule with shift assignments"""
        stmt = select(WeeklySchedule).where(
            WeeklySchedule.id == schedule_id
        ).options(
            selectinload(WeeklySchedule.shift_assignments)
        )
        result = await self.db.execute(stmt)
        return result.scalars().first()

    async def publish_schedule(self, schedule_id: UUID):
        """Publish weekly schedule"""
        schedule = await self.get_weekly_schedule(schedule_id)
        if schedule:
            schedule.status = "published"
            schedule.published_at = datetime.utcnow()
            await self.db.flush()
        return schedule

    # ─────────────────────────────────────────────────────────────
    # Shift Assignment Management
    # ─────────────────────────────────────────────────────────────

    async def create_shift_assignment(self, schedule_id: UUID, employee_id: UUID, 
                                     data: ShiftAssignmentCreate):
        """Create shift assignment"""
        shift = ShiftAssignment(
            tenant_id=self.tenant_id,
            property_id=self.property_id,
            schedule_id=schedule_id,
            employee_id=employee_id,
            shift_date=data.shift_date,
            shift_start_time=data.shift_start_time,
            shift_end_time=data.shift_end_time,
            shift_type=data.shift_type,
            status=data.status
        )
        self.db.add(shift)
        await self.db.flush()
        return shift

    async def get_shift_assignment(self, shift_id: UUID) -> Optional[ShiftAssignment]:
        """Get shift assignment"""
        stmt = select(ShiftAssignment).where(ShiftAssignment.id == shift_id)
        result = await self.db.execute(stmt)
        return result.scalars().first()

    # ─────────────────────────────────────────────────────────────
    # Conflict Detection
    # ─────────────────────────────────────────────────────────────

    async def detect_schedule_conflicts(self, schedule_id: UUID) -> ConflictDetectionResult:
        """Detect conflicts in schedule (employee off on assigned shift day)"""
        schedule = await self.get_weekly_schedule(schedule_id)
        if not schedule:
            return ConflictDetectionResult(has_conflicts=False, conflict_count=0)

        conflicts = []
        stmt = select(ShiftAssignment).where(
            ShiftAssignment.schedule_id == schedule_id
        )
        result = await self.db.execute(stmt)
        shift_assignments = result.scalars().all()

        for shift in shift_assignments:
            # Check if employee is off on this date
            availability = await self.get_employee_availability(
                shift.employee_id, shift.shift_date
            )
            
            if availability and availability.status in ["off", "leave", "sick", "holiday"]:
                conflicts.append(CriticalActionItem(
                    shift_assignment_id=str(shift.id),
                    employee_id=str(shift.employee_id),
                    employee_name=f"{shift.employee.first_name} {shift.employee.last_name}",
                    department=shift.employee.department.name if shift.employee.department else "",
                    shift_date=shift.shift_date,
                    shift_start_time=shift.shift_start_time,
                    shift_end_time=shift.shift_end_time,
                    reason_off=availability.reason or availability.status,
                    urgency="immediate"
                ))

        # Count pending replacement requests
        stmt = select(ReplacementRequest).where(
            and_(
                ReplacementRequest.shift_assignment_id.in_([str(s.id) for s in shift_assignments]),
                ReplacementRequest.status == "pending"
            )
        )
        result = await self.db.execute(stmt)
        pending_requests = result.scalars().all()
        pending_count = len(pending_requests)
        urgent_count = sum(1 for r in pending_requests if r.priority == "urgent")

        return ConflictDetectionResult(
            has_conflicts=len(conflicts) > 0,
            conflict_count=len(conflicts),
            conflicts=conflicts,
            replacement_requests_pending=pending_count,
            replacement_requests_urgent=urgent_count
        )

    # ─────────────────────────────────────────────────────────────
    # Replacement Request Management
    # ─────────────────────────────────────────────────────────────

    async def create_replacement_request(self, shift_assignment_id: UUID, 
                                        original_employee_id: UUID,
                                        replacement_employee_id: Optional[UUID],
                                        data: ReplacementRequestCreate):
        """Create replacement request"""
        request = ReplacementRequest(
            tenant_id=self.tenant_id,
            property_id=self.property_id,
            shift_assignment_id=shift_assignment_id,
            original_employee_id=original_employee_id,
            replacement_employee_id=replacement_employee_id,
            request_date=datetime.utcnow(),
            shift_date=data.shift_date,
            shift_start_time=data.shift_start_time,
            shift_end_time=data.shift_end_time,
            reason=data.reason,
            priority=data.priority,
            request_type=data.request_type,
            status="pending",
            created_by=self.user_id
        )
        self.db.add(request)
        await self.db.flush()
        return request

    async def get_replacement_request(self, request_id: UUID) -> Optional[ReplacementRequest]:
        """Get replacement request with related data"""
        stmt = select(ReplacementRequest).where(
            ReplacementRequest.id == request_id
        ).options(
            selectinload(ReplacementRequest.original_employee),
            selectinload(ReplacementRequest.replacement_employee),
            selectinload(ReplacementRequest.shift_assignment)
        )
        result = await self.db.execute(stmt)
        return result.scalars().first()

    async def accept_replacement_request(self, request_id: UUID, employee_id: UUID):
        """Accept replacement request"""
        request = await self.get_replacement_request(request_id)
        if request:
            request.status = "accepted"
            request.replacement_employee_id = employee_id
            request.responded_by = employee_id
            request.responded_at = datetime.utcnow()
            
            # Update shift assignment status
            shift = await self.get_shift_assignment(request.shift_assignment_id)
            if shift:
                shift.status = "covered"
            
            await self.db.flush()
        return request

    async def reject_replacement_request(self, request_id: UUID, employee_id: UUID, 
                                        reason: Optional[str] = None):
        """Reject replacement request"""
        request = await self.get_replacement_request(request_id)
        if request:
            request.status = "rejected"
            request.responded_by = employee_id
            request.responded_at = datetime.utcnow()
            request.response_reason = reason
            await self.db.flush()
        return request

    async def direct_assign_replacement(self, request_id: UUID, replacement_employee_id: UUID):
        """Directly assign replacement employee"""
        request = await self.get_replacement_request(request_id)
        if request:
            request.replacement_employee_id = replacement_employee_id
            request.status = "assigned"
            
            # Update shift assignment
            shift = await self.get_shift_assignment(request.shift_assignment_id)
            if shift:
                shift.employee_id = replacement_employee_id
                shift.status = "covered"
            
            await self.db.flush()
        return request

    # ─────────────────────────────────────────────────────────────
    # AI Recommendations
    # ─────────────────────────────────────────────────────────────

    async def get_available_employees(self, shift_date: datetime,
                                      start_time: str, end_time: str,
                                      department_id: Optional[UUID] = None) -> List[Employee]:
        """Get employees available for a shift"""
        # Build query for available employees
        conditions = [
            Employee.tenant_id == self.tenant_id,
            Employee.is_active == True,
        ]
        if self.property_id is not None:
            conditions.append(Employee.property_id == self.property_id)
        stmt = select(Employee).where(and_(*conditions))
        
        if department_id:
            stmt = stmt.where(Employee.department_id == department_id)
        
        result = await self.db.execute(stmt)
        employees = result.scalars().all()
        
        # Filter by availability
        available_employees = []
        for emp in employees:
            availability = await self.get_employee_availability(emp.id, shift_date)
            if not availability or availability.status == "available":
                available_employees.append(emp)
        
        return available_employees

    async def calculate_compatibility_score(self, employee: Employee, 
                                           original_employee: Employee) -> float:
        """Calculate compatibility score for recommendation"""
        score = 50.0  # Base score
        
        # Same department bonus
        if employee.department_id == original_employee.department_id:
            score += 20
        
        # Position match bonus
        if employee.position == original_employee.position:
            score += 15
        
        # Skills match bonus
        stmt = select(EmployeeSkill).where(
            EmployeeSkill.employee_id == employee.id
        )
        result = await self.db.execute(stmt)
        skills = result.scalars().all()
        if skills:
            score += 10
        
        return min(score, 100.0)

    async def get_ai_recommendations(self, shift_date: datetime, start_time: str, 
                                    end_time: str, original_employee_id: UUID,
                                    department_id: Optional[UUID] = None,
                                    max_recommendations: int = 5) -> AIRecommendationResponse:
        """Get AI-recommended employees for shift replacement"""
        original_employee = await self.db.get(Employee, original_employee_id)
        available_employees = await self.get_available_employees(
            shift_date, start_time, end_time, department_id
        )
        
        recommendations = []
        for emp in available_employees:
            if emp.id != original_employee_id:
                score = await self.calculate_compatibility_score(emp, original_employee)
                recommendations.append(RecommendedEmployeeScore(
                    employee_id=str(emp.id),
                    employee_name=f"{emp.first_name} {emp.last_name}",
                    department=emp.department.name if emp.department else "N/A",
                    position=emp.position or "N/A",
                    compatibility_score=score,
                    reason=self._get_compatibility_reason(emp, original_employee),
                    available=True
                ))
        
        # Sort by score descending
        recommendations.sort(key=lambda x: x.compatibility_score, reverse=True)
        recommendations = recommendations[:max_recommendations]
        
        return AIRecommendationResponse(
            recommendations=recommendations,
            total_available=len(available_employees),
            timestamp=datetime.utcnow()
        )

    def _get_compatibility_reason(self, employee: Employee, original: Employee) -> str:
        """Generate compatibility reason"""
        reasons = []
        
        if employee.department_id == original.department_id:
            reasons.append("Same department")
        
        if employee.position == original.position:
            reasons.append("Same position")
        
        if not reasons:
            reasons.append("Available for shift")
        
        return ", ".join(reasons)

    # ─────────────────────────────────────────────────────────────
    # Dashboard Data
    # ─────────────────────────────────────────────────────────────

    async def get_manager_dashboard_data(self, week_start: datetime, 
                                        week_end: datetime) -> ManagerDashboardData:
        """Get manager dashboard summary"""
        # Get all employees — owner (no property_id) sees whole tenant
        emp_conditions = [
            Employee.tenant_id == self.tenant_id,
            Employee.is_active == True,
        ]
        if self.property_id is not None:
            emp_conditions.append(Employee.property_id == self.property_id)
        stmt = select(Employee).where(and_(*emp_conditions))
        result = await self.db.execute(stmt)
        all_employees = result.scalars().all()
        employee_count = len(all_employees)

        # Get scheduled employees for week
        sched_conditions = [
            WeeklySchedule.week_start_date >= week_start,
            WeeklySchedule.week_end_date <= week_end,
            WeeklySchedule.status.in_(["assigned", "published"]),
        ]
        if self.property_id is not None:
            sched_conditions.append(WeeklySchedule.property_id == self.property_id)
        stmt = select(WeeklySchedule).where(and_(*sched_conditions))
        result = await self.db.execute(stmt)
        schedules = result.scalars().all()
        scheduled_count = len(set(s.employee_id for s in schedules))
        unscheduled_count = employee_count - scheduled_count

        # Get critical actions
        critical_actions = []
        for schedule in schedules:
            conflicts = await self.detect_schedule_conflicts(schedule.id)
            critical_actions.extend(conflicts.conflicts)

        # Get pending replacements
        repl_conditions = [ReplacementRequest.status.in_(["pending", "accepted"])]
        if self.property_id is not None:
            repl_conditions.append(ReplacementRequest.property_id == self.property_id)
        stmt = select(ReplacementRequest).where(and_(*repl_conditions))
        result = await self.db.execute(stmt)
        pending_requests = result.scalars().all()
        
        scheduling_progress = (scheduled_count / employee_count * 100) if employee_count > 0 else 0
        
        return ManagerDashboardData(
            scheduling_progress=scheduling_progress,
            employee_count=employee_count,
            scheduled_count=scheduled_count,
            unscheduled_count=unscheduled_count,
            critical_actions=critical_actions,
            pending_responses=pending_requests,
            weekly_schedule_count=len(schedules)
        )

    async def get_staff_dashboard_data(self, employee_id: UUID) -> StaffDashboardData:
        """Get staff dashboard data"""
        # Get pending shift requests
        stmt = select(ReplacementRequest).where(
            and_(
                ReplacementRequest.original_employee_id == employee_id,
                ReplacementRequest.status == "pending"
            )
        ).options(
            selectinload(ReplacementRequest.shift_assignment)
        )
        result = await self.db.execute(stmt)
        pending_requests = result.scalars().all()
        
        # Get current week schedule
        today = datetime.utcnow()
        week_start = today - timedelta(days=today.weekday())
        week_end = week_start + timedelta(days=6)
        
        stmt = select(WeeklySchedule).where(
            and_(
                WeeklySchedule.employee_id == employee_id,
                WeeklySchedule.week_start_date >= week_start,
                WeeklySchedule.week_end_date <= week_end
            )
        ).options(
            selectinload(WeeklySchedule.shift_assignments)
        )
        result = await self.db.execute(stmt)
        current_schedule = result.scalars().first()
        
        # Count responses
        stmt = select(ReplacementRequest).where(
            ReplacementRequest.original_employee_id == employee_id
        )
        result = await self.db.execute(stmt)
        all_requests = result.scalars().all()
        accepted_count = sum(1 for r in all_requests if r.status == "accepted")
        rejected_count = sum(1 for r in all_requests if r.status == "rejected")
        
        return StaffDashboardData(
            emergency_shift_requests=pending_requests,
            pending_requests_count=len(pending_requests),
            accepted_requests_count=accepted_count,
            rejected_requests_count=rejected_count,
            current_week_schedule=current_schedule
        )
