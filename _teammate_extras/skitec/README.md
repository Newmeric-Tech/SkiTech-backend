# Skitec Backend - Production-Ready FastAPI Application

## Overview

Skitec is an enterprise-grade hospitality governance platform backend built with FastAPI. It supports:

- **Multi-property hotel management** - Manage multiple properties across different locations
- **Role-based access control (RBAC)** - Fine-grained permissions and role management
- **Workforce management** - Track employees, scheduling, and workforce analytics
- **Approval workflows & governance** - Customizable approval processes for operational changes
- **Audit logging** - Complete audit trail for compliance and security
- **Reporting & analytics** - Business intelligence and reporting capabilities
- **AI-ready architecture** - Prepared for future anomaly detection and ML integrations

## Project Structure

```
skitec/
├── app/
│   ├── api/                    # API Layer
│   │   └── v1/               # API v1 endpoints
│   │       ├── endpoints/    # Individual route modules
│   │       │   ├── auth.py
│   │       │   ├── users.py
│   │       │   ├── properties.py
│   │       │   ├── workforce.py
│   │       │   ├── governance.py
│   │       │   └── reports.py
│   │       └── router.py     # v1 router aggregation
│   │
│   ├── core/                   # Core Configuration
│   │   ├── config.py          # Environment & app settings
│   │   ├── database.py        # SQLAlchemy setup & session management
│   │   ├── security.py        # JWT, password hashing, RBAC
│   │   └── constants.py       # Application constants
│   │
│   ├── models/                 # SQLAlchemy ORM Models
│   │   ├── base.py            # Base model and mixins
│   │   ├── user.py            # User entity
│   │   ├── property.py        # Property entity
│   │   ├── workforce.py       # Workforce/Employee entity
│   │   ├── governance.py      # Workflow & approval entities
│   │   └── audit.py           # Audit log entity
│   │
│   ├── schemas/                # Pydantic Request/Response Models
│   │   ├── common.py          # Shared schemas (pagination, etc)
│   │   ├── user.py            # User schemas
│   │   ├── property.py        # Property schemas
│   │   ├── workforce.py       # Workforce schemas
│   │   └── governance.py      # Governance schemas
│   │
│   ├── services/               # Business Logic Layer
│   │   ├── auth_service.py    # Authentication logic
│   │   ├── user_service.py    # User management
│   │   ├── property_service.py # Property management
│   │   ├── workforce_service.py # Workforce management
│   │   ├── governance_service.py # Workflow management
│   │   └── audit_service.py   # Audit logging
│   │
│   ├── middleware/             # HTTP Middleware
│   │   ├── logging.py         # Request/response logging
│   │   ├── audit.py           # Audit trail middleware
│   │   └── error_handler.py   # Centralized error handling
│   │
│   ├── utils/                  # Utilities
│   │   ├── exceptions.py      # Custom exception classes
│   │   ├── validators.py      # Input validators
│   │   └── helpers.py         # Helper functions
│   │
│   ├── __init__.py            # App factory
│   └── main.py                # Entry point
│
├── tests/                      # Test Suite
│   ├── conftest.py            # pytest configuration
│   ├── test_auth.py
│   ├── test_users.py
│   └── fixtures/              # Test fixtures
│
├── migrations/                 # Alembic database migrations
│   ├── env.py
│   ├── script.py.mako
│   └── versions/
│
├── .env.example               # Environment template
├── .gitignore
├── requirements.txt           # Python dependencies
├── pyproject.toml            # Project config
└── README.md

```

## Architecture Principles

### Layered Architecture
- **API Layer**: FastAPI routers handle HTTP requests/responses
- **Service Layer**: Business logic separated from HTTP layer
- **Data Layer**: SQLAlchemy ORM with async support
- **Schema Layer**: Pydantic for validation and serialization

### SOLID Principles
- **Single Responsibility**: Each module has one clear purpose
- **Dependency Injection**: Loose coupling via FastAPI dependencies
- **Service Abstraction**: Services handle business logic, not routers
- **Configuration Management**: Environment-based config, not hardcoded values

### Enterprise Patterns
- **RBAC Ready**: Role permissions system in `core/security.py`
- **Audit Trail**: `AuditService` logs all significant actions
- **Soft Deletes**: Records marked deleted, not permanently removed
- **Pagination**: Standard offset/limit pagination with counts
- **Error Handling**: Custom exceptions with proper HTTP status codes
- **Timestamps**: All entities track creation and modification times

### Scalability
- **Async/Await**: All I/O operations are async-ready
- **Connection Pooling**: Configured for production database loads
- **Modular Routers**: Easy to split into microservices
- **Database Agnostic**: SQLAlchemy supports PostgreSQL, MySQL, etc.
- **Future ML Integration**: Audit logs and data models ready for ML pipelines

## Getting Started

### Prerequisites
- Python 3.9+
- PostgreSQL 12+
- Virtual environment (venv, conda, etc.)

### Installation

1. Clone repository and navigate to project:
```bash
cd skitec
```

2. Create virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Create `.env` file from template:
```bash
cp .env.example .env
```

5. Update `.env` with your configuration (database URL, secret key, etc.)

6. Initialize database:
```bash
alembic upgrade head
```

### Running the Application

Development:
```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Production (with gunicorn):
```bash
gunicorn -w 4 -k uvicorn.workers.UvicornWorker app.main:app
```

API Documentation:
- Swagger UI: http://localhost:8000/api/docs
- ReDoc: http://localhost:8000/api/redoc
- OpenAPI JSON: http://localhost:8000/api/openapi.json

## API Endpoints

### Authentication
- `POST /api/v1/auth/login` - Login and get tokens
- `POST /api/v1/auth/refresh` - Refresh access token
- `POST /api/v1/auth/logout` - Logout

### Users
- `GET /api/v1/users` - List users (paginated)
- `GET /api/v1/users/{id}` - Get user details
- `POST /api/v1/users` - Create user
- `PUT /api/v1/users/{id}` - Update user
- `DELETE /api/v1/users/{id}` - Delete user (soft delete)

### Properties
- `GET /api/v1/properties` - List properties
- `GET /api/v1/properties/{id}` - Get property
- `POST /api/v1/properties` - Create property
- `PUT /api/v1/properties/{id}` - Update property
- `DELETE /api/v1/properties/{id}` - Delete property

### Workforce
- `GET /api/v1/workforce` - List workforce entries
- `GET /api/v1/workforce/{id}` - Get workforce member
- `POST /api/v1/workforce` - Create workforce entry
- `PUT /api/v1/workforce/{id}` - Update workforce member
- `DELETE /api/v1/workforce/{id}` - Delete workforce member

### Governance & Workflows
- `GET /api/v1/governance/workflows` - List workflow templates
- `POST /api/v1/governance/workflows` - Create workflow
- `GET /api/v1/governance/instances` - List workflow instances
- `POST /api/v1/governance/instances` - Create workflow request
- `PUT /api/v1/governance/instances/{id}/approve` - Approve request
- `PUT /api/v1/governance/instances/{id}/reject` - Reject request

### Reporting
- `GET /api/v1/reports/occupancy` - Occupancy analytics
- `GET /api/v1/reports/workforce` - Workforce analytics
- `GET /api/v1/reports/governance` - Workflow statistics
- `GET /api/v1/reports/audit` - Audit reports

## Database Models

### User
- Authentication and profile information
- Role-based access control
- Active status and verification tracking

### Property
- Hotel property details
- Location and contact information
- Operational configuration

### WorkforceEntry
- Employee records
- Department and position assignment
- Schedule and employment status

### GovernanceWorkflow & WorkflowInstance
- Approval process templates
- Workflow instantiation and state tracking
- Multi-step approval workflows

### AuditLog
- Immutable action records
- User, resource, and action tracking
- Compliance and security audit trail

## Configuration

Environment variables (see `.env.example`):

```
# Application
APP_NAME=Skitec
ENVIRONMENT=development
DEBUG=True

# Database (PostgreSQL)
DATABASE_URL=postgresql://user:password@localhost:5432/skitec_db

# JWT & Security
SECRET_KEY=your-secret-key-min-32-chars
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30

# CORS
ALLOWED_ORIGINS=http://localhost:3000,http://localhost:8080

# Logging
LOG_LEVEL=INFO

# Redis (for caching, optional)
REDIS_URL=redis://localhost:6379/0
```

## Authentication & Authorization

JWT-based authentication with RBAC:

```python
# Role definitions in core/security.py
ROLES = {
    "super_admin": ["manage_users", "manage_properties", ...],
    "property_manager": ["manage_property", "manage_workforce", ...],
    "staff": ["view_schedule", "submit_time_entries", ...],
    "auditor": ["view_all_reports", "audit_logs", ...],
}
```

Token payload includes user ID and roles for authorization checks.

## Testing

Run tests:
```bash
pytest
```

With coverage:
```bash
pytest --cov=app tests/
```

## Development

Code formatting (Black):
```bash
black app/ tests/
```

Linting (pylint, flake8):
```bash
pylint app/
flake8 app/
```

Type checking (mypy):
```bash
mypy app/
```

## Deployment

### Docker
A `docker-compose.yml` should include:
- FastAPI application
- PostgreSQL database
- Redis (optional, for caching)

### Production Checklist
- [ ] Set `ENVIRONMENT=production`
- [ ] Set `DEBUG=False`
- [ ] Use strong `SECRET_KEY`
- [ ] Configure proper database
- [ ] Set up HTTPS/TLS
- [ ] Configure logging to centralized system
- [ ] Set up monitoring and alerting
- [ ] Configure backups
- [ ] Test error handling paths
- [ ] Load test the application

## Future Enhancements

- [ ] GraphQL API alongside REST
- [ ] AI anomaly detection for operations
- [ ] Real-time notifications with WebSockets
- [ ] Advanced reporting with Elasticsearch
- [ ] Message queue integration (RabbitMQ/Kafka)
- [ ] Multi-tenancy support
- [ ] Advanced caching with Redis
- [ ] Rate limiting and throttling

## License

Proprietary - Skitec

## Support

For issues and questions, contact: engineering@skitec.com
