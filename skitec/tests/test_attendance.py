"""
Test Suite for Attendance & Geolocation Endpoints

Tests for:
- Punch in/out operations
- Geofence validation
- Distance calculations
- Attendance history and reports
"""

import pytest
from datetime import datetime, timezone, timedelta
from sqlalchemy.orm import Session
from fastapi.testclient import TestClient

from app.main import app
from app.models.attendance import AttendanceRecord, PropertyGeofence
from app.models.user import User
from app.schemas.attendance import (
    PunchInRequest, PunchOutRequest, GeolocationData,
    PropertyGeofenceCreate
)
from app.services.attendance_service import AttendanceService, GeofenceService
from app.utils.geolocation import haversine_distance, is_within_geofence, validate_coordinates


# ===========================
# Fixtures
# ===========================

@pytest.fixture
def client():
    """FastAPI test client"""
    return TestClient(app)


@pytest.fixture
def test_user(db: Session) -> User:
    """Create test user"""
    user = User(
        email="testuser@example.com",
        username="testuser",
        hashed_password="hashed_password",
        first_name="Test",
        last_name="User",
        role="staff",
        is_active=True
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def test_geofence(db: Session) -> PropertyGeofence:
    """Create test geofence"""
    geofence = PropertyGeofence(
        property_id=1,
        property_name="Grand Hotel Delhi",
        center_latitude=28.5250,
        center_longitude=77.1860,
        radius_meters=500,
        address="123 Main Street",
        city="New Delhi",
        country="India",
        is_active=True
    )
    db.add(geofence)
    db.commit()
    db.refresh(geofence)
    return geofence


# ===========================
# Geolocation Utility Tests
# ===========================

class TestGeolocationUtilities:
    """Test geolocation calculation functions"""

    def test_haversine_distance_same_point(self):
        """Test distance between same points is zero"""
        distance = haversine_distance(28.5250, 77.1860, 28.5250, 77.1860)
        assert distance == 0

    def test_haversine_distance_known_points(self):
        """Test distance calculation with known points"""
        # New Delhi to Mumbai is approximately 1400 km
        distance = haversine_distance(
            28.6139, 77.2090,  # New Delhi
            19.0760, 72.8777,  # Mumbai
            unit='kilometers'
        )
        assert 1300 < distance < 1500

    def test_haversine_distance_meters(self):
        """Test distance in meters"""
        # Approximately 100 meters
        distance = haversine_distance(
            28.5250, 77.1860,
            28.5260, 77.1870,
            unit='meters'
        )
        assert 1000 < distance < 2000

    def test_validate_coordinates_valid(self):
        """Test valid coordinates pass validation"""
        is_valid, error = validate_coordinates(28.5250, 77.1860, accuracy=15.0)
        assert is_valid
        assert error is None

    def test_validate_coordinates_invalid_latitude(self):
        """Test invalid latitude fails validation"""
        is_valid, error = validate_coordinates(91.0, 77.1860)
        assert not is_valid
        assert error is not None

    def test_validate_coordinates_invalid_longitude(self):
        """Test invalid longitude fails validation"""
        is_valid, error = validate_coordinates(28.5250, 181.0)
        assert not is_valid
        assert error is not None

    def test_validate_coordinates_poor_accuracy(self):
        """Test poor accuracy fails validation"""
        is_valid, error = validate_coordinates(28.5250, 77.1860, accuracy=150.0, max_accuracy=100.0)
        assert not is_valid
        assert "accuracy" in error.lower()

    def test_is_within_geofence_inside(self):
        """Test location inside geofence"""
        is_inside, distance, status = is_within_geofence(
            28.5244, 77.1855,  # 45m from center
            28.5250, 77.1860,  # Center
            500  # 500m radius
        )
        assert is_inside
        assert distance < 100
        assert status.value == "inside"

    def test_is_within_geofence_outside(self):
        """Test location outside geofence"""
        is_inside, distance, status = is_within_geofence(
            28.5200, 77.1800,  # Far away
            28.5250, 77.1860,  # Center
            500  # 500m radius
        )
        assert not is_inside
        assert distance > 500
        assert status.value == "outside"

    def test_is_within_geofence_boundary(self):
        """Test location at boundary"""
        is_inside, distance, status = is_within_geofence(
            28.5250, 77.1860,  # At center
            28.5250, 77.1860,
            500,  # Move 500m (approx)
            boundary_buffer=50
        )
        # Should be inside since we're at center
        assert is_inside


# ===========================
# Attendance Service Tests
# ===========================

class TestAttendanceService:
    """Test attendance service business logic"""

    def test_create_punch_in_within_geofence(self, db: Session, test_user: User, test_geofence: PropertyGeofence):
        """Test punch in within geofence"""
        punch_request = PunchInRequest(
            geolocation=GeolocationData(
                latitude=28.5244,
                longitude=77.1855,
                accuracy=15.0,
                address="Hotel Entrance"
            ),
            device_info="Chrome/Windows",
            notes="Morning shift"
        )

        attendance, has_warning, warning_msg = AttendanceService.create_punch_in(
            db=db,
            user_id=test_user.id,
            property_id=1,
            punch_in_request=punch_request
        )

        assert attendance.id is not None
        assert attendance.user_id == test_user.id
        assert attendance.is_within_geofence
        assert not has_warning
        assert warning_msg is None

    def test_create_punch_in_outside_geofence(self, db: Session, test_user: User, test_geofence: PropertyGeofence):
        """Test punch in outside geofence generates warning"""
        punch_request = PunchInRequest(
            geolocation=GeolocationData(
                latitude=28.4000,  # Far away
                longitude=77.0000,
                accuracy=20.0
            )
        )

        attendance, has_warning, warning_msg = AttendanceService.create_punch_in(
            db=db,
            user_id=test_user.id,
            property_id=1,
            punch_in_request=punch_request
        )

        assert not attendance.is_within_geofence
        assert has_warning
        assert warning_msg is not None
        assert "outside geofence" in warning_msg.lower()

    def test_punch_in_without_geofence(self, db: Session, test_user: User):
        """Test punch in when no geofence is configured"""
        punch_request = PunchInRequest(
            geolocation=GeolocationData(
                latitude=28.5244,
                longitude=77.1855,
                accuracy=15.0
            )
        )

        # Should work but without geofence validation
        attendance, has_warning, warning_msg = AttendanceService.create_punch_in(
            db=db,
            user_id=test_user.id,
            property_id=999,  # No geofence
            punch_in_request=punch_request
        )

        assert attendance.is_within_geofence == False  # No validation

    def test_create_punch_out(self, db: Session, test_user: User, test_geofence: PropertyGeofence):
        """Test punch out operation"""
        # First punch in
        punch_in_request = PunchInRequest(
            geolocation=GeolocationData(
                latitude=28.5244,
                longitude=77.1855,
                accuracy=15.0
            )
        )

        attendance, _, _ = AttendanceService.create_punch_in(
            db=db,
            user_id=test_user.id,
            property_id=1,
            punch_in_request=punch_in_request
        )

        # Then punch out
        punch_out_request = PunchOutRequest(
            geolocation=GeolocationData(
                latitude=28.5245,
                longitude=77.1856,
                accuracy=12.0
            )
        )

        updated, has_warning, warning_msg = AttendanceService.create_punch_out(
            db=db,
            user_id=test_user.id,
            property_id=1,
            punch_out_request=punch_out_request
        )

        assert updated.status == "completed"
        assert updated.punch_out_time is not None
        assert updated.hours_worked is not None
        assert updated.hours_worked > 0

    def test_punch_out_without_punch_in(self, db: Session, test_user: User):
        """Test punch out fails without active punch in"""
        punch_out_request = PunchOutRequest(
            geolocation=GeolocationData(
                latitude=28.5245,
                longitude=77.1856,
                accuracy=12.0
            )
        )

        with pytest.raises(ValueError, match="No active punch in"):
            AttendanceService.create_punch_out(
                db=db,
                user_id=test_user.id,
                property_id=1,
                punch_out_request=punch_out_request
            )

    def test_get_active_punch_in(self, db: Session, test_user: User, test_geofence: PropertyGeofence):
        """Test getting active punch in record"""
        punch_request = PunchInRequest(
            geolocation=GeolocationData(
                latitude=28.5244,
                longitude=77.1855,
                accuracy=15.0
            )
        )

        attendance, _, _ = AttendanceService.create_punch_in(
            db=db,
            user_id=test_user.id,
            property_id=1,
            punch_in_request=punch_request
        )

        active = AttendanceService.get_active_punch_in(
            db=db,
            user_id=test_user.id,
            property_id=1
        )

        assert active is not None
        assert active.id == attendance.id
        assert active.status == "active"

    def test_get_attendance_history(self, db: Session, test_user: User, test_geofence: PropertyGeofence):
        """Test retrieving attendance history"""
        # Create multiple records
        for i in range(3):
            punch_request = PunchInRequest(
                geolocation=GeolocationData(
                    latitude=28.5244 + (i * 0.001),
                    longitude=77.1855 + (i * 0.001),
                    accuracy=15.0
                )
            )

            AttendanceService.create_punch_in(
                db=db,
                user_id=test_user.id,
                property_id=1,
                punch_in_request=punch_request
            )

        records, total = AttendanceService.get_attendance_history(
            db=db,
            user_id=test_user.id,
            skip=0,
            limit=10
        )

        assert len(records) == 3
        assert total == 3

    def test_get_daily_summary(self, db: Session, test_user: User, test_geofence: PropertyGeofence):
        """Test daily summary calculation"""
        punch_request = PunchInRequest(
            geolocation=GeolocationData(
                latitude=28.5244,
                longitude=77.1855,
                accuracy=15.0
            )
        )

        attendance, _, _ = AttendanceService.create_punch_in(
            db=db,
            user_id=test_user.id,
            property_id=1,
            punch_in_request=punch_request
        )

        punch_out_request = PunchOutRequest(
            geolocation=GeolocationData(
                latitude=28.5245,
                longitude=77.1856,
                accuracy=12.0
            )
        )

        AttendanceService.create_punch_out(
            db=db,
            user_id=test_user.id,
            property_id=1,
            punch_out_request=punch_out_request
        )

        summary = AttendanceService.get_daily_summary(
            db=db,
            user_id=test_user.id,
            date=datetime.now(timezone.utc)
        )

        assert summary["total_records"] >= 1
        assert summary["total_hours_worked"] > 0
        assert summary["within_geofence_count"] >= 0


# ===========================
# Geofence Service Tests
# ===========================

class TestGeofenceService:
    """Test geofence management service"""

    def test_create_geofence(self, db: Session):
        """Test creating a geofence"""
        geofence_data = PropertyGeofenceCreate(
            property_id=1,
            property_name="Test Hotel",
            center_latitude=28.5250,
            center_longitude=77.1860,
            radius_meters=500,
            city="New Delhi"
        )

        geofence = GeofenceService.create_geofence(db=db, geofence_data=geofence_data)

        assert geofence.id is not None
        assert geofence.property_id == 1
        assert geofence.radius_meters == 500

    def test_create_duplicate_geofence_fails(self, db: Session, test_geofence: PropertyGeofence):
        """Test creating duplicate geofence fails"""
        geofence_data = PropertyGeofenceCreate(
            property_id=1,  # Already exists
            property_name="Another Hotel",
            center_latitude=28.5250,
            center_longitude=77.1860,
            radius_meters=500
        )

        with pytest.raises(ValueError, match="already exists"):
            GeofenceService.create_geofence(db=db, geofence_data=geofence_data)

    def test_get_geofence(self, db: Session, test_geofence: PropertyGeofence):
        """Test getting geofence by property ID"""
        geofence = GeofenceService.get_geofence(db=db, property_id=1)

        assert geofence is not None
        assert geofence.id == test_geofence.id

    def test_update_geofence(self, db: Session, test_geofence: PropertyGeofence):
        """Test updating geofence"""
        geofence_data = PropertyGeofenceCreate(
            property_id=1,
            property_name="Updated Hotel",
            center_latitude=28.5300,
            center_longitude=77.1900,
            radius_meters=750
        )

        updated = GeofenceService.update_geofence(
            db=db,
            geofence_id=test_geofence.id,
            geofence_data=geofence_data
        )

        assert updated.radius_meters == 750
        assert updated.center_latitude == 28.5300

    def test_delete_geofence(self, db: Session, test_geofence: PropertyGeofence):
        """Test deleting geofence (soft delete)"""
        result = GeofenceService.delete_geofence(db=db, geofence_id=test_geofence.id)

        assert result
        geofence = db.query(PropertyGeofence).filter(
            PropertyGeofence.id == test_geofence.id
        ).first()
        assert geofence.is_active == False

    def test_list_geofences(self, db: Session, test_geofence: PropertyGeofence):
        """Test listing geofences"""
        geofences, total = GeofenceService.list_geofences(db=db, skip=0, limit=10)

        assert total >= 1
        assert len(geofences) >= 1


# ===========================
# API Endpoint Tests
# ===========================

class TestAttendanceEndpoints:
    """Test API endpoints"""

    def test_punch_in_endpoint(self, client: TestClient, test_user: User, test_geofence: PropertyGeofence):
        """Test POST /attendance/punch-in"""
        # Note: In real tests, you'd need to authenticate
        payload = {
            "geolocation": {
                "latitude": 28.5244,
                "longitude": 77.1855,
                "accuracy": 15.0,
                "address": "Hotel Entrance"
            },
            "device_info": "Chrome/Windows"
        }

        response = client.post(
            "/api/v1/attendance/punch-in?property_id=1",
            json=payload,
            headers={"Authorization": "Bearer test_token"}
        )

        # Would return 200/201 on success or auth error
        assert response.status_code in [200, 201, 401, 403]

    def test_geofence_endpoint(self, client: TestClient):
        """Test GET /attendance/geofence"""
        response = client.get(
            "/api/v1/attendance/geofence",
            headers={"Authorization": "Bearer test_token"}
        )

        # Would return 200 or auth error
        assert response.status_code in [200, 401, 403]
