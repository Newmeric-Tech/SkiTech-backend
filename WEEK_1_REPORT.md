# Week 1 Project Report
## Phase: Architecture Skeleton and Environment Setup

### 1. What Was Done
During the first week, the primary objective was establishing a robust, scalable foundation tailored specifically for an enterprise-grade FastAPI application.

* **Project Folder Structure Setup**: We broke away from flat script patterns and implemented a layered architecture:
  * `api/`: Holds routing endpoints, dependency injections (`get_db`, `get_current_user`), and grouped API versions (`v1`).
  * `core/`: Configured for global security operations and JWT utility functions.
  * `crud/`: Reserved for database manipulation classes decoupling SQL logic from networking logic.
  * `models/`: Database ORM models mapping strictly to PostgreSQL.
  * `repositories/`: Custom business logic abstractions.
  * `middleware/`: Reserved for intercepting request/response lifecycles.
* **Virtual Environment**: Initialized a Python virtual environment (`.venv`) to strictly isolate the project's dependencies from system-wide Python packages, ensuring the setup is reproducible inside Docker containers or other machines.
* **Requirements Setup**: Defined the project dependencies in `requirements.txt`. Key libraries included:
  * `fastapi` and `uvicorn` (ASGI Server).
  * `sqlalchemy` (Database ORM) and `psycopg2-binary` (PostgreSQL adapter).
  * `pydantic` and `pydantic-settings` (Data validation and environment config mapping).
  * `python-jose` and `passlib` (Security and JWT tokens).
* **Git Repository Initialization**: Configured `.git` and established a stringent `.gitignore` to prevent committing the `.env`, `.venv`, and `__pycache__` directories.
* **Documentation**: Laid out baseline README and architectural outlines mapping out how future features would hook into the skeleton.

### 2. Problems Faced
* **Dependency Conflicts**: Transitioning between Pydantic v1 vs Pydantic v2 caused initial serialization hiccups since v2 requires `model_config = {"from_attributes": True}` instead of the older `orm_mode = True`.
* **Architecture Decision Paralysis**: Deciding how granular the separation of concerns should be. Breaking down `crud/` versus `repositories/` took some planning to ensure that the controllers (API endpoints) remain incredibly lightweight without writing duplicate database logic.

### 3. Other Information
* The current skeleton successfully starts locally via `uvicorn main:app --reload` and defaults to serving the automated Swagger UI at `/docs`.
* By completing the folder structure this way, any team member can easily identify where networking logic starts (in `api/`) versus where the database logic happens (in `crud/`).
