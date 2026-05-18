"""
Test suite for Complaint & Error Log API

Tests all complaint management features:
- Create, read, update, resolve complaints
- Assign to staff
- Add comments
- Dashboard data
- Filtering and search
"""

import pytest
from datetime import datetime, timedelta
from uuid import uuid4
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import (
    Tenant, Property, Department, Role, RolePermission, Permission, User,
    Complaint, ComplaintComment, ComplaintAssignment
)
from app.schemas.complaints import (
    ComplaintCreate, ComplaintUpdate, ComplaintResolve, ComplaintCommentCreate,
    ComplaintAssignmentCreate, ComplaintPriority, ComplaintStatus,
    ComplaintType, ComplaintCategory
)
from app.services.complaint_service import ComplaintService


@pytest.fixture
async def setup_complaint_test_data(db: AsyncSession):
    """Set up test data for complaint tests"""
    # Create tenant
    tenant = Tenant(
        id=uuid4(),
        business_name="Test Hotel",
        business_type="hotel",
        owner_name="Owner",
        contact_email="owner@test.com"
    )
    db.add(tenant)
    
    # Create property
    property = Property(
        id=uuid4(),
        tenant_id=tenant.id,
        property_name="Test Property",
        property_type="hotel",
        address="123 Main St"
    )
    db.add(property)
    
    # Create department
    department = Department(
        id=uuid4(),
        tenant_id=tenant.id,
        property_id=property.id,
        department_name="Maintenance",
        description="Maintenance Department"
    )
    db.add(department)
    
    # Create roles
    staff_role = Role(
        id=uuid4(),
        name="staff",
        role_level=5,
        description="Staff role"
    )
    manager_role = Role(
        id=uuid4(),
        name="manager",
        role_level=3,
        description="Manager role"
    )
    owner_role = Role(
        id=uuid4(),
        name="owner",
        role_level=1,
        description="Owner role"
    )
    db.add_all([staff_role, manager_role, owner_role])
    
    # Create users
    staff_user = User(
        id=uuid4(),
        tenant_id=tenant.id,
        property_id=property.id,
        email="staff@test.com",
        username="staff",
        hashed_password="hashed",
        role_id=staff_role.id
    )
    manager_user = User(
        id=uuid4(),
        tenant_id=tenant.id,
        property_id=property.id,
        email="manager@test.com",
        username="manager",
        hashed_password="hashed",
        role_id=manager_role.id
    )
    owner_user = User(
        id=uuid4(),
        tenant_id=tenant.id,
        property_id=property.id,
        email="owner@test.com",
        username="owner",
        hashed_password="hashed",
        role_id=owner_role.id
    )
    db.add_all([staff_user, manager_user, owner_user])
    
    await db.flush()
    
    return {
        "tenant": tenant,
        "property": property,
        "department": department,
        "staff_user": staff_user,
        "manager_user": manager_user,
        "owner_user": owner_user,
        "db": db
    }


class TestComplaintCreation:
    """Test complaint creation"""
    
    async def test_create_complaint_by_staff(self, setup_complaint_test_data):
        """Test staff creating a complaint"""
        data = setup_complaint_test_data
        service = ComplaintService(
            db=data["db"],
            tenant_id=data["tenant"].id,
            property_id=data["property"].id,
            user_id=data["staff_user"].id,
            user_role="staff"
        )
        
        complaint_data = ComplaintCreate(
            title="AC Not Cooling",
            description="Room 305 - AC is not working properly",
            category=ComplaintCategory.MAINTENANCE,
            complaint_type=ComplaintType.COMPLAINT,
            priority=ComplaintPriority.HIGH,
            room_number="305",
            location="Building A"
        )
        
        result = await service.create_complaint(complaint_data)
        
        assert result.id is not None
        assert result.title == "AC Not Cooling"
        assert result.status == "open"
        assert result.priority == "high"
        assert result.created_by == data["staff_user"].id
    
    async def test_create_different_complaint_types(self, setup_complaint_test_data):
        """Test creating different types of complaints"""
        data = setup_complaint_test_data
        service = ComplaintService(
            db=data["db"],
            tenant_id=data["tenant"].id,
            property_id=data["property"].id,
            user_id=data["staff_user"].id,
            user_role="staff"
        )
        
        # Create error type
        error_data = ComplaintCreate(
            title="System Error",
            description="Payment system error",
            category=ComplaintCategory.TECHNICAL,
            complaint_type=ComplaintType.ERROR,
            priority=ComplaintPriority.CRITICAL
        )
        error = await service.create_complaint(error_data)
        assert error.complaint_type == "error"
        
        # Create handover type
        handover_data = ComplaintCreate(
            title="Shift Handover Issue",
            description="Missing inventory handover",
            category=ComplaintCategory.OPERATIONAL,
            complaint_type=ComplaintType.HANDOVER,
            priority=ComplaintPriority.MEDIUM
        )
        handover = await service.create_complaint(handover_data)
        assert handover.complaint_type == "handover"


class TestComplaintManagement:
    """Test complaint CRUD operations"""
    
    async def test_update_complaint(self, setup_complaint_test_data):
        """Test updating complaint details"""
        data = setup_complaint_test_data
        service = ComplaintService(
            db=data["db"],
            tenant_id=data["tenant"].id,
            property_id=data["property"].id,
            user_id=data["staff_user"].id,
            user_role="staff"
        )
        
        # Create complaint
        complaint_data = ComplaintCreate(
            title="Original Title",
            description="Original Description",
            category=ComplaintCategory.MAINTENANCE,
            complaint_type=ComplaintType.COMPLAINT,
            priority=ComplaintPriority.LOW
        )
        complaint = await service.create_complaint(complaint_data)
        
        # Update complaint
        update_data = ComplaintUpdate(
            title="Updated Title",
            priority=ComplaintPriority.HIGH
        )
        updated = await service.update_complaint(complaint.id, update_data)
        
        assert updated.title == "Updated Title"
        assert updated.priority == "high"
    
    async def test_resolve_complaint(self, setup_complaint_test_data):
        """Test resolving a complaint"""
        data = setup_complaint_test_data
        service = ComplaintService(
            db=data["db"],
            tenant_id=data["tenant"].id,
            property_id=data["property"].id,
            user_id=data["manager_user"].id,
            user_role="manager"
        )
        
        # Create complaint
        complaint_data = ComplaintCreate(
            title="Issue to Resolve",
            description="This needs to be resolved",
            category=ComplaintCategory.MAINTENANCE,
            complaint_type=ComplaintType.COMPLAINT,
            priority=ComplaintPriority.HIGH
        )
        complaint = await service.create_complaint(complaint_data)
        
        # Resolve complaint
        resolve_data = ComplaintResolve(
            status=ComplaintStatus.RESOLVED,
            resolution_notes="Fixed the AC unit"
        )
        resolved = await service.resolve_complaint(complaint.id, resolve_data)
        
        assert resolved.status == "resolved"
        assert resolved.resolution_notes == "Fixed the AC unit"
        assert resolved.resolved_at is not None


class TestComplaintAssignment:
    """Test complaint assignment to staff"""
    
    async def test_assign_complaint_to_staff(self, setup_complaint_test_data):
        """Test assigning complaint to staff"""
        data = setup_complaint_test_data
        service = ComplaintService(
            db=data["db"],
            tenant_id=data["tenant"].id,
            property_id=data["property"].id,
            user_id=data["manager_user"].id,
            user_role="manager"
        )
        
        # Create complaint
        complaint_data = ComplaintCreate(
            title="Assign Me",
            description="Please assign to staff",
            category=ComplaintCategory.MAINTENANCE,
            complaint_type=ComplaintType.COMPLAINT,
            priority=ComplaintPriority.HIGH
        )
        complaint = await service.create_complaint(complaint_data)
        
        # Assign to staff
        assign_data = ComplaintAssignmentCreate(
            assigned_to=data["staff_user"].id,
            notes="Please resolve ASAP"
        )
        assigned = await service.assign_complaint(complaint.id, assign_data)
        
        assert assigned.assigned_to == data["staff_user"].id
        assert assigned.status == "in_progress"
    
    async def test_reassign_complaint(self, setup_complaint_test_data):
        """Test reassigning complaint to different staff"""
        data = setup_complaint_test_data
        
        # Create second staff user
        staff_user_2 = User(
            id=uuid4(),
            tenant_id=data["tenant"].id,
            property_id=data["property"].id,
            email="staff2@test.com",
            username="staff2",
            hashed_password="hashed",
            role_id=data["manager_user"].role_id
        )
        data["db"].add(staff_user_2)
        await data["db"].flush()
        
        service = ComplaintService(
            db=data["db"],
            tenant_id=data["tenant"].id,
            property_id=data["property"].id,
            user_id=data["manager_user"].id,
            user_role="manager"
        )
        
        # Create and assign complaint
        complaint_data = ComplaintCreate(
            title="Reassign Me",
            description="Will be reassigned",
            category=ComplaintCategory.MAINTENANCE,
            complaint_type=ComplaintType.COMPLAINT,
            priority=ComplaintPriority.MEDIUM
        )
        complaint = await service.create_complaint(complaint_data)
        
        assign_data = ComplaintAssignmentCreate(assigned_to=data["staff_user"].id)
        await service.assign_complaint(complaint.id, assign_data)
        
        # Reassign to different staff
        reassign_data = ComplaintAssignmentCreate(
            assigned_to=staff_user_2.id,
            notes="Reassigning to more experienced staff"
        )
        reassigned = await service.reassign_complaint(
            complaint.id,
            staff_user_2.id,
            "Reassigning to more experienced staff"
        )
        
        assert reassigned.assigned_to == staff_user_2.id


class TestComplaintComments:
    """Test comments on complaints"""
    
    async def test_add_comment(self, setup_complaint_test_data):
        """Test adding comment to complaint"""
        data = setup_complaint_test_data
        service = ComplaintService(
            db=data["db"],
            tenant_id=data["tenant"].id,
            property_id=data["property"].id,
            user_id=data["staff_user"].id,
            user_role="staff"
        )
        
        # Create complaint
        complaint_data = ComplaintCreate(
            title="Issue with Comment",
            description="Add comment to this",
            category=ComplaintCategory.MAINTENANCE,
            complaint_type=ComplaintType.COMPLAINT,
            priority=ComplaintPriority.MEDIUM
        )
        complaint = await service.create_complaint(complaint_data)
        
        # Add comment
        comment_data = ComplaintCommentCreate(
            comment="Working on this issue",
            is_internal=False
        )
        comment = await service.add_comment(complaint.id, comment_data)
        
        assert comment.comment == "Working on this issue"
        assert comment.is_internal is False
    
    async def test_add_internal_comment(self, setup_complaint_test_data):
        """Test adding internal notes to complaint"""
        data = setup_complaint_test_data
        service = ComplaintService(
            db=data["db"],
            tenant_id=data["tenant"].id,
            property_id=data["property"].id,
            user_id=data["manager_user"].id,
            user_role="manager"
        )
        
        # Create complaint
        complaint_data = ComplaintCreate(
            title="Issue with Internal Note",
            description="Add internal note",
            category=ComplaintCategory.MAINTENANCE,
            complaint_type=ComplaintType.COMPLAINT,
            priority=ComplaintPriority.HIGH
        )
        complaint = await service.create_complaint(complaint_data)
        
        # Add internal comment
        internal_comment = ComplaintCommentCreate(
            comment="Internal note: Staff needs training on this",
            is_internal=True
        )
        comment = await service.add_comment(complaint.id, internal_comment)
        
        assert comment.is_internal is True


class TestComplaintFiltering:
    """Test filtering and searching complaints"""
    
    async def test_list_complaints_by_status(self, setup_complaint_test_data):
        """Test listing complaints filtered by status"""
        data = setup_complaint_test_data
        service = ComplaintService(
            db=data["db"],
            tenant_id=data["tenant"].id,
            property_id=data["property"].id,
            user_id=data["manager_user"].id,
            user_role="manager"
        )
        
        # Create complaints with different statuses
        for i in range(3):
            complaint_data = ComplaintCreate(
                title=f"Complaint {i}",
                description=f"Issue {i}",
                category=ComplaintCategory.MAINTENANCE,
                complaint_type=ComplaintType.COMPLAINT,
                priority=ComplaintPriority.MEDIUM
            )
            await service.create_complaint(complaint_data)
        
        # List open complaints
        from app.schemas.complaints import ComplaintFilterParams
        filters = ComplaintFilterParams(status=ComplaintStatus.OPEN)
        complaints, total = await service.list_complaints(filters)
        
        assert total >= 3


class TestComplaintDashboards:
    """Test dashboard data generation"""
    
    async def test_manager_dashboard(self, setup_complaint_test_data):
        """Test manager dashboard data"""
        data = setup_complaint_test_data
        service = ComplaintService(
            db=data["db"],
            tenant_id=data["tenant"].id,
            property_id=data["property"].id,
            user_id=data["manager_user"].id,
            user_role="manager"
        )
        
        # Create some complaints
        for i in range(5):
            complaint_data = ComplaintCreate(
                title=f"Dashboard Issue {i}",
                description=f"Issue for dashboard {i}",
                category=ComplaintCategory.MAINTENANCE,
                complaint_type=ComplaintType.COMPLAINT,
                priority=ComplaintPriority.HIGH if i % 2 == 0 else ComplaintPriority.MEDIUM
            )
            await service.create_complaint(complaint_data)
        
        # Get dashboard
        dashboard = await service.get_manager_dashboard()
        
        assert dashboard.total_complaints >= 5
        assert dashboard.open_complaints >= 5
    
    async def test_staff_dashboard(self, setup_complaint_test_data):
        """Test staff dashboard data"""
        data = setup_complaint_test_data
        service = ComplaintService(
            db=data["db"],
            tenant_id=data["tenant"].id,
            property_id=data["property"].id,
            user_id=data["staff_user"].id,
            user_role="staff"
        )
        
        # Create complaint as staff
        complaint_data = ComplaintCreate(
            title="My Complaint",
            description="Complaint created by me",
            category=ComplaintCategory.MAINTENANCE,
            complaint_type=ComplaintType.COMPLAINT,
            priority=ComplaintPriority.MEDIUM
        )
        await service.create_complaint(complaint_data)
        
        # Get dashboard
        dashboard = await service.get_staff_dashboard()
        
        assert dashboard.my_complaints_count >= 1
    
    async def test_owner_dashboard(self, setup_complaint_test_data):
        """Test owner dashboard data"""
        data = setup_complaint_test_data
        service = ComplaintService(
            db=data["db"],
            tenant_id=data["tenant"].id,
            property_id=data["property"].id,
            user_id=data["owner_user"].id,
            user_role="owner"
        )
        
        # Create critical complaint
        complaint_data = ComplaintCreate(
            title="Critical Issue",
            description="This is critical",
            category=ComplaintCategory.SECURITY,
            complaint_type=ComplaintType.ERROR,
            priority=ComplaintPriority.CRITICAL
        )
        await service.create_complaint(complaint_data)
        
        # Get dashboard
        dashboard = await service.get_owner_dashboard()
        
        assert dashboard.total_complaints >= 1
        assert dashboard.total_critical >= 1


class TestComplaintEscalation:
    """Test complaint escalation"""
    
    async def test_escalate_complaint(self, setup_complaint_test_data):
        """Test escalating a complaint"""
        data = setup_complaint_test_data
        service = ComplaintService(
            db=data["db"],
            tenant_id=data["tenant"].id,
            property_id=data["property"].id,
            user_id=data["manager_user"].id,
            user_role="manager"
        )
        
        # Create complaint
        complaint_data = ComplaintCreate(
            title="To Escalate",
            description="This needs escalation",
            category=ComplaintCategory.MAINTENANCE,
            complaint_type=ComplaintType.COMPLAINT,
            priority=ComplaintPriority.HIGH
        )
        complaint = await service.create_complaint(complaint_data)
        
        # Escalate
        escalated = await service.escalate_complaint(
            complaint.id,
            "Requires management attention"
        )
        
        assert escalated.status == "escalated"
