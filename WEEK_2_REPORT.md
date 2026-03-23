# Week 2 Project Report
## Phase: Database Integration, Exception Handling, and Employee Module

### 1. What Was Done
During the second week, the primary objective was connecting the FastAPI application to PostgreSQL, handling database lifecycles safely, and implementing the first major feature module: Employees.

* **PostgreSQL & SQLAlchemy Integration**: 
  * Created `config.py` using `pydantic_settings.BaseSettings` to dynamically load PostgreSQL variables from a local `.env` file.
  * Established `db_connection.py` containing the core SQLAlchemy Engine, declarative `Base`, and the `SessionLocal` maker.
* **Dependency Injection Lifecycle**: 
  * Wrote the `get_db` FastAPI dependency to seamlessly open a database session for every network request and automatically close it using `yield`. This ensures zero database connection leaks.
* **Base CRUD Utility**: 
  * Developed a highly reusable `CRUDBase` class using Python Generics (`TypeVar`). This allowed us to quickly scaffold logic for retrieving, creating, updating, and deleting records without rewriting boilerplate code for every new model.
* **Repository Generation**: 
  * Created the `User` repository and `Tenant` repository to handle tenant isolation patterns natively within the database queries.
* **Global Exception Handling Middleware**: 
  * Implemented a Starlette HTTP middleware `ExceptionHandlerMiddleware` to intercept unhandled application crashes (`500 Internal Server Errors`) and format them into clean, standardized JSON responses tailored for frontend consumption.
* **Employee Module Implementation**: 
  * Added the `Employee` ORM model mapped directly to properties and tenants.
  * Developed full CRUD APIs inside `api/v1/endpoints/employee.py`.
  * Configured Pydantic schemas (`EmployeeCreate`, `EmployeeUpdate`) to validate request payloads before hitting the database.
  * Built functional support for native pagination (`skip` and `limit`) and dynamic filtering parameters (like `property_id` and `role`).
* **Stability Review**: Extracted standard debug logs and ensured the backend was booting up entirely error-free before finalizing the stable branch.

### 2. Problems Faced
* **SQLAlchemy 2.0 Shift**: Ensuring the queries complied with SQLAlchemy 2.0-style statements (using `session.query().filter()`) rather than deprecated legacy logic in order to future-proof the application.
* **Multi-Tenant Data Leaks**: Designing the `Employee` endpoints required overriding basic CRUD operations. Native `.get()` functions expose data globally; we rigorously forced a `tenant_id` check alongside almost every database query to guarantee absolutely no cross-tenant data spillage.
* **Exception Handlers Overriding HTTPExceptions**: During middleware implementation, the global exception handler was inadvertently catching standard FastAPI user-errors (like `404 Not Found` or `422 Validation Error`). This required explicitly formatting traceback logic exclusively for severe developer-layer crashes.

### 3. Other Information
* The global exception handler prevents the server from returning unformatted raw HTML tracebacks, making the API behave professionally during severe edge cases.
* Setting up `CRUDBase` during Week 2 essentially accelerated Week 3's development velocity dramatically, as the core database logic approach was entirely solved.
