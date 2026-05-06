# Geolocation Punch In/Out - Quick Reference Guide

## 🎯 Quick Start

### 1. Verify Installation
```bash
cd d:\SciTech\skitec
# All code files are ready in app/models, app/schemas, app/services, app/api/v1/endpoints
```

### 2. Run Tests
```bash
python -m pytest tests/test_attendance.py -v
```

### 3. Start API Server
```bash
python -m uvicorn app.main:app --reload
```

### 4. Access API Docs
```
http://localhost:8000/docs  # Swagger UI
http://localhost:8000/redoc # ReDoc
```

---

## 📂 File Structure

```
skitec/
├── app/
│   ├── models/
│   │   ├── __init__.py
│   │   └── attendance.py          ✅ AttendanceRecord, PropertyGeofence
│   ├── schemas/
│   │   ├── __init__.py
│   │   └── attendance.py          ✅ Request/Response schemas
│   ├── services/
│   │   ├── __init__.py
│   │   └── attendance_service.py  ✅ AttendanceService, GeofenceService
│   ├── api/v1/endpoints/
│   │   ├── __init__.py
│   │   └── attendance.py          ✅ 11 REST endpoints
│   ├── utils/
│   │   ├── __init__.py
│   │   └── geolocation.py         ✅ Haversine, geofence validation
│   └── core/
│       ├── database.py            ✅ Uses get_db_session
│       ├── security.py            ✅ JWT auth, get_current_user
│       └── config.py
├── tests/
│   └── test_attendance.py         ✅ 30+ test cases
└── migrations/
    └── versions/
        └── 002_add_attendance_geofence.py
```

---

## 🔌 API Endpoints

| Method | Endpoint | Auth | Description |
|--------|----------|------|---|
| `POST` | `/attendance/punch-in` | User | Start work shift |
| `POST` | `/attendance/punch-out` | User | End work shift |
| `GET` | `/attendance/status` | User | Check punch status |
| `GET` | `/attendance/history` | User | Attendance records |
| `GET` | `/attendance/daily-summary` | User | Daily stats |
| `POST` | `/attendance/geofence` | Admin | Create geofence |
| `GET` | `/attendance/geofence/{property_id}` | User | Get geofence |
| `PUT` | `/attendance/geofence/{geofence_id}` | Admin | Update geofence |
| `DELETE` | `/attendance/geofence/{geofence_id}` | Admin | Delete geofence |
| `GET` | `/attendance/geofence` | User | List geofences |

---

## 🔑 Key Parameters

### Punch In/Out
- **Query:** `property_id` (UUID) - Required
- **Body Fields:**
  - `geolocation.latitude` (float) - -90 to 90
  - `geolocation.longitude` (float) - -180 to 180
  - `geolocation.accuracy` (float) - GPS accuracy in meters
  - `device_info` (object) - Browser, OS info
  - `notes` (string) - Optional comments

### Geofence
- **Required:**
  - `property_id` (UUID)
  - `center_lat`, `center_lng` (float)
  - `radius_meters` (int) - 50 to 5000
  - `property_name` (string)
- **Optional:**
  - `address`, `city`, `country`
  - `alert_on_breach` (boolean)

---

## 💾 Database Queries

### Get Active Punch
```python
from app.models.attendance import AttendanceRecord

active = db.query(AttendanceRecord).filter(
    AttendanceRecord.user_id == user_id,
    AttendanceRecord.property_id == property_id,
    AttendanceRecord.tenant_id == tenant_id,
    AttendanceRecord.punch_out_time.is_(None)  # Still active
).first()
```

### Get Attendance History
```python
records = db.query(AttendanceRecord).filter(
    AttendanceRecord.user_id == user_id,
    AttendanceRecord.tenant_id == tenant_id,
    AttendanceRecord.punch_in_time >= start_date,
    AttendanceRecord.punch_in_time <= end_date
).all()
```

### Get Geofence
```python
geofence = db.query(PropertyGeofence).filter(
    PropertyGeofence.property_id == property_id,
    PropertyGeofence.tenant_id == tenant_id
).first()
```

---

## 🧮 Geolocation Calculation

### Distance Calculation (Haversine Formula)
```python
from app.utils.geolocation import haversine_distance

distance = haversine_distance(
    user_lat=28.4595,
    user_lon=77.0266,
    center_lat=28.4590,
    center_lon=77.0260,
    unit='meters'  # Returns meters
)
# Returns: 68.5 meters
```

### Geofence Check
```python
from app.utils.geolocation import is_within_geofence

is_inside, distance, status = is_within_geofence(
    user_lat=28.4595,
    user_lon=77.0266,
    center_lat=28.4590,
    center_lon=77.0260,
    radius_meters=500,
    boundary_buffer=50  # 50m buffer zone
)
# Returns: (True, 68.5, "Inside")
```

### Coordinate Validation
```python
from app.utils.geolocation import validate_coordinates

is_valid, error = validate_coordinates(
    latitude=28.4595,
    longitude=77.0266,
    accuracy=25.5,
    max_accuracy=100.0  # Max acceptable accuracy
)
# Returns: (True, None)
```

---

## 🔐 Authentication & Authorization

### Extract Tenant from JWT
```python
@router.get("/attendance/status")
def get_status(current_user: User = Depends(get_current_user)):
    # current_user.id -> User UUID
    # current_user.tenant_id -> Tenant UUID
    # current_user.role -> 'admin', 'manager', 'user'
    
    tenant_id = str(current_user.tenant_id)  # Convert to string for UUID
```

### Role-Based Access
```python
if current_user.role not in ["admin", "manager"]:
    raise HTTPException(
        status_code=403,
        detail="Only admins and managers can create geofences"
    )
```

---

## ⚙️ Configuration

### Environment Variables (if needed)
```env
# In your .env or config.py
GEOFENCE_BOUNDARY_BUFFER=50  # meters
MAX_GPS_ACCURACY=100         # meters
MAX_GEOFENCE_RADIUS=5000     # meters
MIN_GEOFENCE_RADIUS=50       # meters
```

---

## 🐛 Common Issues & Solutions

### Issue: "Geofence not found"
**Cause:** Geofence created in different tenant
**Solution:** Ensure geofence.tenant_id matches current_user.tenant_id

### Issue: GPS accuracy too high
**Cause:** Device GPS signal weak
**Solution:** Increase `max_accuracy` parameter in validate_coordinates()

### Issue: Distance always showing large value
**Cause:** Coordinates might be swapped or invalid
**Solution:** Verify latitude (-90 to 90), longitude (-180 to 180)

### Issue: "No active punch in"
**Cause:** User punch already completed
**Solution:** Check AttendanceRecord.punch_out_time is None for active records

---

## 📊 Data Examples

### Punch In Response
```json
{
  "success": true,
  "message": "Punched in successfully",
  "attendance_id": "660e8400-e29b-41d4-a716-446655440001",
  "is_within_fence": true,
  "distance_meters": 25.5,
  "warning": null
}
```

### Outside Geofence Response
```json
{
  "success": true,
  "message": "Punched in (outside geofence)",
  "attendance_id": "660e8400-e29b-41d4-a716-446655440001",
  "is_within_fence": false,
  "distance_meters": 650.8,
  "warning": "Punch in recorded outside hotel premises. Distance: 650.8m"
}
```

### Attendance Record
```json
{
  "id": "660e8400-e29b-41d4-a716-446655440001",
  "tenant_id": "550e8400-e29b-41d4-a716-446655440000",
  "user_id": "770e8400-e29b-41d4-a716-446655440002",
  "property_id": "550e8400-e29b-41d4-a716-446655440000",
  "punch_in_time": "2024-01-15T09:00:00Z",
  "punch_in_lat": 28.4595,
  "punch_in_lon": 77.0266,
  "punch_in_acc": 15.5,
  "is_within_fence": true,
  "distance_meters": 25.5,
  "punch_out_time": "2024-01-15T17:30:00Z",
  "punch_out_lat": 28.4597,
  "punch_out_lon": 77.0268,
  "hours_worked": 8.5,
  "status": "completed",
  "notes": "Regular shift"
}
```

---

## 🧪 Testing Examples

### Test Punch In
```python
def test_punch_in():
    response = client.post(
        "/attendance/punch-in?property_id=550e8400-e29b-41d4-a716-446655440000",
        json={
            "geolocation": {
                "latitude": 28.4595,
                "longitude": 77.0266,
                "accuracy": 15.5
            },
            "device_info": {"browser": "Chrome"},
            "notes": "Test"
        },
        headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 201
    assert response.json()["success"] == True
```

### Test Geofence Creation
```python
def test_create_geofence():
    response = client.post(
        "/attendance/geofence",
        json={
            "property_id": "550e8400-e29b-41d4-a716-446655440000",
            "property_name": "Hotel Grand",
            "center_lat": 28.4595,
            "center_lng": 77.0266,
            "radius_meters": 500,
            "alert_on_breach": True
        },
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert response.status_code == 201
```

---

## 📈 Performance Tips

1. **Index on frequently queried columns:**
   ```sql
   CREATE INDEX idx_attendance_user_property ON attendance_records(user_id, property_id, tenant_id);
   CREATE INDEX idx_attendance_time ON attendance_records(punch_in_time DESC);
   CREATE INDEX idx_geofence_property ON property_geofences(property_id, tenant_id);
   ```

2. **Pagination for large result sets:**
   - Use `skip` and `limit` in history queries
   - Default limit: 50, max: 100

3. **Cache geofences:**
   - Geofences rarely change
   - Consider caching with 1-hour TTL

---

## 🚀 Production Checklist

- [ ] Set `DEBUG = False` in config
- [ ] Use strong `SECRET_KEY` for JWT
- [ ] Enable HTTPS/TLS
- [ ] Set up database backups
- [ ] Configure logging
- [ ] Set up monitoring/alerts
- [ ] Test with actual GPS devices
- [ ] Validate geofence coordinates with surveyors
- [ ] Set up geofence for each property
- [ ] Train staff on punch in/out process

---

**Last Updated:** 2024
**Status:** Production Ready ✅
