# SkiTech Backend

Enterprise hospitality governance platform — **fully merged FastAPI backend**.

Merged from 4 source projects:
- **Project-ansh** — basic FastAPI scaffold, logging, middleware
- **SkiTech-Nupur** — JWT auth, OTP email, RBAC, property/owner CRUD, audit + tenant isolation middleware
- **SciTech-amardeep** — async SQLAlchemy architecture, governance workflows, service layer pattern
- **skitech-Rishiiii** — full database schema: Alembic migrations, inventory movements, SOP versions + role visibility, departments, vendors, hotel rooms/bookings, restaurant tables/orders

---

## Project Structure

```
skitech_backend/
├── main.py                         # Entry point (uvicorn main:app)
├── requirements.txt
├── .env                            # Copy and fill in your values
├── alembic.ini
├── alembic/
│   ├── env.py
│   └── versions/                   # Add migration files here
├── app/
│   ├── __init__.py                 # FastAPI app factory (app object lives here)
│   ├── core/
│   │   ├── config.py               # Settings from env vars
│   │   ├── database.py             # Async SQLAlchemy engine + get_db dependency
│   │   ├── security.py             # JWT, password hashing, RBAC permission map
│   │   └── constants.py
│   ├── models/
│   │   ├── base.py                 # UUIDMixin, IdMixin, TimestampMixin, SoftDeleteMixin, Base
│   │   ├── models.py               # Core ORM models (RBAC, tenants, users, properties, etc.)
│   │   ├── kra.py                  # KRA models (DailyKRA, WeeklyKRA, MonthlyKRA, QuarterlyKRA)
│   │   ├── attendance.py           # AttendanceRecord, PropertyGeofence
│   │   ├── workforce_entry.py      # WorkforceEntry (for KRA compliance)
│   │   └── __init__.py
│   ├── schemas/
│   │   ├── schemas.py              # All Pydantic request/response schemas
│   │   ├── common.py               # PaginatedResponse, ErrorResponse
│   │   ├── kra.py                  # KRA schemas
│   │   └── attendance.py           # Attendance schemas
│   ├── services/
│   │   ├── kra_service.py          # KRA business logic
│   │   └── attendance_service.py   # Attendance + geofence logic
│   ├── api/
│   │   └── v1/
│   │       ├── router.py           # Aggregates all endpoint routers
│   │       ├── vendor_owner_department_routes.py
│   │       └── endpoints/
│   │           ├── auth.py
│   │           ├── properties.py
│   │           ├── workforce.py
│   │           ├── inventory.py
│   │           ├── sop.py
│   │           ├── governance.py
│   │           ├── kra.py          # KRA CRUD endpoints
│   │           ├── attendance.py   # Punch in/out + geofence endpoints
│   │           ├── department.py
│   │           ├── employee.py
│   │           ├── vendor.py
│   │           └── owner.py
│   ├── middleware/
│   └── utils/
│       ├── exceptions.py
│       ├── geolocation.py          # Haversine distance, geofence check
│       ├── permission_checker.py
│       └── otp.py
└── tests/
```

---

## Setup & Run

### 1. Install dependencies
```bash
pip install -r requirements.txt
```

### 2. Configure environment
```bash
cp .env.example .env   # edit to add your database URL, secret key, SMTP creds
```

Key variables:
```env
DATABASE_URL=postgresql+asyncpg://user:password@host:5432/dbname
SECRET_KEY=your-32-char-minimum-secret-key
SMTP_EMAIL=your@gmail.com
SMTP_PASSWORD=your-app-password
```

### 3. Run database migrations
```bash
alembic upgrade head
```

### 4. Start the server
```bash
# Development
uvicorn main:app --reload

# Production
uvicorn main:app --host 0.0.0.0 --port 8000 --workers 4
```

Open **http://localhost:8000/docs** for the interactive Swagger UI.
