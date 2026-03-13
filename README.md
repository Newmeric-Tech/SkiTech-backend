# SciTech - Enterprise Hospitality Platform

SciTech is a robust, enterprise-grade backend platform designed for the hospitality industry. It features a scalable, multi-tenant architecture built on FastAPI and PostgreSQL, providing strict data isolation and a clean service-repository pattern.

## 🚀 Key Features

- **Multi-Tenancy**: Shared database with strict row-level isolation using `tenant_id`.
- **Clean Architecture**: Multi-layered structure (API, Repository, CRUD, Models) for maximum maintainability.
- **Workforce Management**: Comprehensive Employee module with advanced filtering and relational integrity.
- **Enterprise Security**: JWT-based authentication with RBAC (Role-Based Access Control) and global exception handling.
- **Relational Integrity**: Migrated from NoSQL to PostgreSQL for strict ACID compliance and relational constraints.

## 🛠 Tech Stack

- **Framework**: FastAPI (Python 3.10+)
- **Database**: PostgreSQL with SQLAlchemy ORM
- **Migrations**: Alembic
- **Security**: JWT (python-jose), Password Hashing (passlib/bcrypt)
- **Validation**: Pydantic v2

## 📦 Project Structure

```text
SciTech/
├── api/            # API Layer (v1 routers)
├── core/           # Core configurations and security
├── crud/           # Generic CRUD operations
├── models/         # SQLAlchemy ORM models
├── repositories/   # Business logic and tenant filtering
├── middleware/     # Custom middlewares (Exception Handling, etc.)
├── config.py       # Pydantic Settings management
├── main.py         # Application entry point
└── requirements.txt # Project dependencies
```

## ⚙️ Setup & Installation

### 1. Clone the Repository
```bash
git clone https://github.com/your-repo/SciTech.git
cd SciTech
```

### 2. Create Virtual Environment
```bash
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
```

### 3. Install Dependencies
```bash
pip install -r requirements.txt
```

### 4. Environment Configuration
Copy the example environment file and update your credentials:
```bash
cp .env.example .env
```

### 5. Running the Application
```bash
python main.py
```
Or using uvicorn:
```bash
uvicorn main:app --reload
```
The API will be available at `http://127.0.0.1:8000`.

## 📖 API Documentation

Once the server is running, you can access the interactive API docs:
- **Swagger UI**: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)
- **ReDoc**: [http://127.0.0.1:8000/redoc](http://127.0.0.1:8000/redoc)

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
