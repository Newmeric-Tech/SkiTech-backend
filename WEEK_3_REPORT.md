# Week 3 Project Report
## Phase: SOPs, Inventory Module APIs, and Route Finalization

### 1. What Was Done
The goal for the third week was finalizing the multi-tenant architecture for specialized platform modules—specifically the Inventory APIs and the Standard Operating Procedures (SOP) APIs. 

* **Inventory API Implementation**: 
  * Designed the `InventoryItem` SQL model featuring properties like `name`, `sku`, `price`, and `quantity`.
  * Plumbed up the routes via `api/v1/endpoints/inventory.py`.
  * Bootstrapped full Create, Update, and List logic utilizing the `CRUDBase` inheritance pattern established in Week 2.
  * Advanced the `GET /inventory/items` API to dynamically handle massive payload requests using custom pagination (`skip=0`, `limit=100`).
  * Attached dynamic filtering parameters allowing clients to directly query inventory per location (`?property_id=XYZ`).
* **SOP (Standard Operating Procedures) APIs**:
  * Implemented parallel APIs targeting `SOP Categories` and `SOP Items`.
  * Scaffolded Pydantic schemas validating nested relations (e.g., ensuring an SOP Item mapped securely to a valid SOP Category). 
* **Route Re-Structuring**: 
  * Cleaned up the `main.py` entry point. Unified the Employee, SOP, and Inventory networking layers into a central router mapped dynamically inside `api/v1/router.py`. 
* **Finalizing Code Quality**: 
  * Ran local sanity checks via the `/docs` UI.
  * Verified that all newly added modules booted cleanly together and that there were no conflicting router endpoint aliases.

### 2. Problems Faced
* **Foreign Key and Relationship Verification**: Building the Inventory and SOP models presented a problem regarding foreign key integrity. If a user tries to attach an `InventoryItem` to a `property_id` they do not own, the system shouldn't just rely on the database crashing with a Constraint Error. We had to build intermediate logic ensuring that the `current_user` explicitly owned the target entity before resolving the `session.commit()`.
* **Managing Deeply Nested Routing Trees**: As the application expanded from one module to three, organizing imports between endpoints, schemas, CRUD logic, and models invited cyclic "Circular Import" errors. Resolving this required strict adherence to single-direction imports (Routers -> CRUD -> Models).

### 3. Other Information
* The system is now heavily standardized. Testing the backend via Swagger UI confirms that latency per standard list query handles exceedingly well locally.
* The API correctly categorizes its interactive documentation using specific FastAPI router `tags=["inventory", "employees", "sop"]` for ease of communication with frontend clients.
