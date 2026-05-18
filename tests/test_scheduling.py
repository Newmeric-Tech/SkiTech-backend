"""
Tests for Employee Scheduling Service - tests/test_scheduling.py
"""

import pytest
from datetime import datetime, timedelta
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession
from app.models.models import (
    Tenant, Property, Employee, Department, User, Role,
    EmployeeAvailability, WeeklySchedule, ShiftAssignment,
    ReplacementRequest
)
from app.schemas.scheduling import (
    EmployeeAvailabilityCreate, WeeklyScheduleCreate, ShiftAssignmentCreate,
    ReplacementRequestCreate, AvailabilityStatus, ScheduleStatus, ShiftStatus,
    RequestPriority, ReplacementRequestType
)
from app.services.scheduling_service import SchedulingService


@pytest.fixture
async def setup_test_data(db: AsyncSession):
    """Setup test data for scheduling tests"""
    # Create tenant
    tenant = Tenant(
        business_name="Test Hotel",
        business_type="hotel",
        subscription_status="active"
    )
    db.add(tenant)
    await db.flush()

    # Create property
    property = Property(
        tenant_id=tenant.id,
        name="Main Property",
        is_active=True
    )
    db.add(property)
    await db.flush()

    # Create department
    department = Department(
        tenant_id=tenant.id,
        property_id=property.id,
        name="Front Desk"
    )
    db.add(department)
    await db.flush()

    # Create role
    role = Role(
        name="employee",
        role_level=1
    )
    db.add(role)
    await db.flush()

    # Create user (manager)
    user = User(
        email="manager@test.com",
        password_hash="hash",
        tenant_id=tenant.id,
        property_id=property.id,
        role_id=role.id
    )
    db.add(user)
    await db.flush()

    # Create employees
    employees = []
    for i in range(5):
        emp = Employee(
            tenant_id=tenant.id,
            property_id=property.id,
            role_id=role.id,
            department_id=department.id,
            first_name=f"Employee{i}",
            last_name=f"Test{i}",
            email=f"emp{i}@test.com",
            position="Associate",
            is_active=True
        )
        db.add(emp)
        employees.append(emp)
    
    await db.flush()
    await db.commit()

    return {
        "tenant": tenant,
        "property": property,
        "department": department,
        "user": user,
        "employees": employees
    }


@pytest.mark.asyncio
class TestAvailabilityManagement:
    
    async def test_create_availability(self, db: AsyncSession, setup_test_data):
        """Test creating employee availability"""
        data = setup_test_data
        service = SchedulingService(db, data["tenant"].id, data["property"].id, data["user"].id)
        
        availability_data = EmployeeAvailabilityCreate(
            availability_date=datetime.now(),
            status=AvailabilityStatus.OFF,
            reason="Personal Leave"
        )
        
        availability = await service.create_availability(data["employees"][0].id, availability_data)
        
        assert availability.status == "off"
        assert availability.reason == "Personal Leave"
        assert availability.employee_id == data["employees"][0].id

    async def test_bulk_create_availability(self, db: AsyncSession, setup_test_data):
        """Test bulk creating availability for date range"""
        data = setup_test_data
        service = SchedulingService(db, data["tenant"].id, data["property"].id, data["user"].id)
        
        start_date = datetime.now()
        end_date = start_date + timedelta(days=3)
        
        availabilities = await service.bulk_create_availability(
            data["employees"][0].id,
            start_date,
            end_date,
            "leave",
            "Vacation"
        )
        
        assert len(availabilities) == 4  # 4 days inclusive
        assert all(a.status == "leave" for a in availabilities)


@pytest.mark.asyncio
class TestScheduleManagement:
    
    async def test_create_weekly_schedule(self, db: AsyncSession, setup_test_data):
        """Test creating weekly schedule"""
        data = setup_test_data
        service = SchedulingService(db, data["tenant"].id, data["property"].id, data["user"].id)
        
        week_start = datetime.now()
        week_end = week_start + timedelta(days=6)
        
        schedule_data = WeeklyScheduleCreate(
            employee_id=str(data["employees"][0].id),
            week_start_date=week_start,
            week_end_date=week_end,
            status=ScheduleStatus.DRAFT
        )
        
        schedule = await service.create_weekly_schedule(data["employees"][0].id, schedule_data)
        
        assert schedule.employee_id == data["employees"][0].id
        assert schedule.status == "draft"
        assert schedule.week_start_date == week_start

    async def test_bulk_create_schedules(self, db: AsyncSession, setup_test_data):
        """Test bulk creating schedules for multiple employees"""
        data = setup_test_data
        service = SchedulingService(db, data["tenant"].id, data["property"].id, data["user"].id)
        
        employee_ids = [emp.id for emp in data["employees"][:3]]
        week_start = datetime.now()
        week_end = week_start + timedelta(days=6)
        
        schedules = await service.bulk_create_weekly_schedules(
            employee_ids,
            week_start,
            week_end,
            data["department"].id
        )
        
        assert len(schedules) == 3
        assert all(s.status == "draft" for s in schedules)

    async def test_publish_schedule(self, db: AsyncSession, setup_test_data):
        """Test publishing a schedule"""
        data = setup_test_data
        service = SchedulingService(db, data["tenant"].id, data["property"].id, data["user"].id)
        
        # Create schedule
        schedule_data = WeeklyScheduleCreate(
            employee_id=str(data["employees"][0].id),
            week_start_date=datetime.now(),
            week_end_date=datetime.now() + timedelta(days=6),
            status=ScheduleStatus.DRAFT
        )
        schedule = await service.create_weekly_schedule(data["employees"][0].id, schedule_data)
        
        # Publish it
        published = await service.publish_schedule(schedule.id)
        
        assert published.status == "published"
        assert published.published_at is not None


@pytest.mark.asyncio
class TestShiftAssignment:
    
    async def test_create_shift_assignment(self, db: AsyncSession, setup_test_data):
        """Test creating shift assignment"""
        data = setup_test_data
        service = SchedulingService(db, data["tenant"].id, data["property"].id, data["user"].id)
        
        # Create schedule first
        schedule_data = WeeklyScheduleCreate(
            employee_id=str(data["employees"][0].id),
            week_start_date=datetime.now(),
            week_end_date=datetime.now() + timedelta(days=6),
            status=ScheduleStatus.DRAFT
        )
        schedule = await service.create_weekly_schedule(data["employees"][0].id, schedule_data)
        
        # Create shift
        shift_data = ShiftAssignmentCreate(
            shift_date=datetime.now(),
            shift_start_time="08:00",
            shift_end_time="17:00",
            shift_type="full-day",
            status=ShiftStatus.SCHEDULED
        )
        
        shift = await service.create_shift_assignment(schedule.id, data["employees"][0].id, shift_data)
        
        assert shift.shift_start_time == "08:00"
        assert shift.shift_end_time == "17:00"
        assert shift.status == "scheduled"


@pytest.mark.asyncio
class TestConflictDetection:
    
    async def test_detect_conflicts(self, db: AsyncSession, setup_test_data):
        """Test conflict detection when employee off on scheduled day"""
        data = setup_test_data
        service = SchedulingService(db, data["tenant"].id, data["property"].id, data["user"].id)
        
        employee = data["employees"][0]
        shift_date = datetime.now()
        
        # Create schedule
        schedule_data = WeeklyScheduleCreate(
            employee_id=str(employee.id),
            week_start_date=shift_date,
            week_end_date=shift_date + timedelta(days=6),
            status=ScheduleStatus.DRAFT
        )
        schedule = await service.create_weekly_schedule(employee.id, schedule_data)
        
        # Create shift on that date
        shift_data = ShiftAssignmentCreate(
            shift_date=shift_date,
            shift_start_time="12:00",
            shift_end_time="20:00",
            shift_type="afternoon",
            status=ShiftStatus.SCHEDULED
        )
        shift = await service.create_shift_assignment(schedule.id, employee.id, shift_data)
        
        # Mark employee as off on that date
        availability_data = EmployeeAvailabilityCreate(
            availability_date=shift_date,
            status=AvailabilityStatus.OFF,
            reason="Emergency"
        )
        await service.create_availability(employee.id, availability_data)
        
        # Detect conflicts
        conflicts = await service.detect_schedule_conflicts(schedule.id)
        
        assert conflicts.has_conflicts == True
        assert len(conflicts.conflicts) == 1
        assert conflicts.conflicts[0].employee_id == str(employee.id)

    async def test_no_conflicts(self, db: AsyncSession, setup_test_data):
        """Test no conflicts when employee is available"""
        data = setup_test_data
        service = SchedulingService(db, data["tenant"].id, data["property"].id, data["user"].id)
        
        employee = data["employees"][0]
        shift_date = datetime.now()
        
        # Create schedule
        schedule_data = WeeklyScheduleCreate(
            employee_id=str(employee.id),
            week_start_date=shift_date,
            week_end_date=shift_date + timedelta(days=6),
            status=ScheduleStatus.DRAFT
        )
        schedule = await service.create_weekly_schedule(employee.id, schedule_data)
        
        # Create shift
        shift_data = ShiftAssignmentCreate(
            shift_date=shift_date,
            shift_start_time="08:00",
            shift_end_time="17:00",
            shift_type="full-day",
            status=ShiftStatus.SCHEDULED
        )
        await service.create_shift_assignment(schedule.id, employee.id, shift_data)
        
        # Don't mark as off - employee is available
        
        # Detect conflicts
        conflicts = await service.detect_schedule_conflicts(schedule.id)
        
        assert conflicts.has_conflicts == False
        assert len(conflicts.conflicts) == 0


@pytest.mark.asyncio
class TestReplacementRequests:
    
    async def test_create_replacement_request_send_type(self, db: AsyncSession, setup_test_data):
        """Test creating 'send_request' type replacement request"""
        data = setup_test_data
        service = SchedulingService(db, data["tenant"].id, data["property"].id, data["user"].id)
        
        # Create schedule and shift
        employee = data["employees"][0]
        shift_date = datetime.now()
        
        schedule_data = WeeklyScheduleCreate(
            employee_id=str(employee.id),
            week_start_date=shift_date,
            week_end_date=shift_date + timedelta(days=6),
            status=ScheduleStatus.DRAFT
        )
        schedule = await service.create_weekly_schedule(employee.id, schedule_data)
        
        shift_data = ShiftAssignmentCreate(
            shift_date=shift_date,
            shift_start_time="12:00",
            shift_end_time="20:00",
            shift_type="afternoon",
            status=ShiftStatus.SCHEDULED
        )
        shift = await service.create_shift_assignment(schedule.id, employee.id, shift_data)
        
        # Create replacement request
        request_data = ReplacementRequestCreate(
            original_employee_id=str(employee.id),
            shift_date=shift_date,
            shift_start_time="12:00",
            shift_end_time="20:00",
            reason="Employee on leave",
            priority=RequestPriority.HIGH,
            request_type=ReplacementRequestType.SEND_REQUEST
        )
        
        request = await service.create_replacement_request(shift.id, employee.id, None, request_data)
        
        assert request.status == "pending"
        assert request.request_type == "send_request"
        assert request.priority == "high"

    async def test_direct_assign_replacement(self, db: AsyncSession, setup_test_data):
        """Test direct assignment of replacement employee"""
        data = setup_test_data
        service = SchedulingService(db, data["tenant"].id, data["property"].id, data["user"].id)
        
        original_emp = data["employees"][0]
        replacement_emp = data["employees"][1]
        shift_date = datetime.now()
        
        # Create schedule and shift
        schedule_data = WeeklyScheduleCreate(
            employee_id=str(original_emp.id),
            week_start_date=shift_date,
            week_end_date=shift_date + timedelta(days=6),
            status=ScheduleStatus.DRAFT
        )
        schedule = await service.create_weekly_schedule(original_emp.id, schedule_data)
        
        shift_data = ShiftAssignmentCreate(
            shift_date=shift_date,
            shift_start_time="12:00",
            shift_end_time="20:00",
            shift_type="afternoon",
            status=ShiftStatus.SCHEDULED
        )
        shift = await service.create_shift_assignment(schedule.id, original_emp.id, shift_data)
        
        # Create replacement request with direct assignment
        request_data = ReplacementRequestCreate(
            original_employee_id=str(original_emp.id),
            replacement_employee_id=str(replacement_emp.id),
            shift_date=shift_date,
            shift_start_time="12:00",
            shift_end_time="20:00",
            reason="Direct assignment",
            priority=RequestPriority.URGENT,
            request_type=ReplacementRequestType.DIRECT_ASSIGNMENT
        )
        
        request = await service.create_replacement_request(
            shift.id, original_emp.id, replacement_emp.id, request_data
        )
        assigned = await service.direct_assign_replacement(request.id, replacement_emp.id)
        
        assert assigned.status == "assigned"
        assert assigned.replacement_employee_id == replacement_emp.id

    async def test_accept_replacement_request(self, db: AsyncSession, setup_test_data):
        """Test employee accepting replacement request"""
        data = setup_test_data
        service = SchedulingService(db, data["tenant"].id, data["property"].id, data["user"].id)
        
        original_emp = data["employees"][0]
        replacement_emp = data["employees"][1]
        shift_date = datetime.now()
        
        # Setup: Create schedule and shift
        schedule_data = WeeklyScheduleCreate(
            employee_id=str(original_emp.id),
            week_start_date=shift_date,
            week_end_date=shift_date + timedelta(days=6),
            status=ScheduleStatus.DRAFT
        )
        schedule = await service.create_weekly_schedule(original_emp.id, schedule_data)
        
        shift_data = ShiftAssignmentCreate(
            shift_date=shift_date,
            shift_start_time="12:00",
            shift_end_time="20:00",
            shift_type="afternoon",
            status=ShiftStatus.SCHEDULED
        )
        shift = await service.create_shift_assignment(schedule.id, original_emp.id, shift_data)
        
        # Create send_request type
        request_data = ReplacementRequestCreate(
            original_employee_id=str(original_emp.id),
            shift_date=shift_date,
            shift_start_time="12:00",
            shift_end_time="20:00",
            reason="Employee on leave",
            priority=RequestPriority.HIGH,
            request_type=ReplacementRequestType.SEND_REQUEST
        )
        request = await service.create_replacement_request(shift.id, original_emp.id, None, request_data)
        
        # Employee accepts
        accepted = await service.accept_replacement_request(request.id, replacement_emp.id)
        
        assert accepted.status == "accepted"
        assert accepted.replacement_employee_id == replacement_emp.id
        assert accepted.responded_by == replacement_emp.id


@pytest.mark.asyncio
class TestAIRecommendations:
    
    async def test_get_available_employees(self, db: AsyncSession, setup_test_data):
        """Test getting available employees for shift"""
        data = setup_test_data
        service = SchedulingService(db, data["tenant"].id, data["property"].id, data["user"].id)
        
        shift_date = datetime.now()
        
        # Mark one employee as off
        availability_data = EmployeeAvailabilityCreate(
            availability_date=shift_date,
            status=AvailabilityStatus.OFF,
            reason="Off-day"
        )
        await service.create_availability(data["employees"][4].id, availability_data)
        
        # Get available employees
        available = await service.get_available_employees(
            shift_date, "08:00", "17:00", None
        )
        
        assert len(available) == 4  # 5 employees - 1 off
        assert data["employees"][4] not in available

    async def test_compatibility_score_same_department(self, db: AsyncSession, setup_test_data):
        """Test compatibility score calculation"""
        data = setup_test_data
        service = SchedulingService(db, data["tenant"].id, data["property"].id, data["user"].id)
        
        emp1 = data["employees"][0]
        emp2 = data["employees"][1]
        
        # Same department (already set in fixture)
        score = await service.calculate_compatibility_score(emp2, emp1)
        
        # Base 50 + 20 for same department = 70
        assert score >= 70

    async def test_get_ai_recommendations(self, db: AsyncSession, setup_test_data):
        """Test getting AI recommendations for replacement"""
        data = setup_test_data
        service = SchedulingService(db, data["tenant"].id, data["property"].id, data["user"].id)
        
        shift_date = datetime.now()
        original_emp = data["employees"][0]
        
        recommendations = await service.get_ai_recommendations(
            shift_date, "08:00", "17:00", original_emp.id, None, 3
        )
        
        assert len(recommendations.recommendations) <= 3
        assert recommendations.total_available > 0
        # Check scores are in valid range
        for rec in recommendations.recommendations:
            assert 0 <= rec.compatibility_score <= 100


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
