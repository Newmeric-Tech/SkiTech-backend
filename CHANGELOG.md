# SkiTech Backend — Changelog

> See `../DEVELOPMENT_LOG.md` for full documentation covering both frontend and backend.

---

## [2026-05-25] — Document Auto-Approval for Owners

### Changed — `app/api/v1/endpoints/documents.py`
- After `create_document()` or upload, if the uploader's `role_obj.name` is `"Owner"`, `"Super Admin"`, `"owner"`, or `"super_admin"`, the document's `status` and `approval_status` are immediately set to `"approved"`. Owners do not need a review step.

---

## [2026-05-25] — Scheduling Fix for Owners (null property_id)

### Fixed — `app/services/scheduling_service.py`
- `property_id` changed from required `UUID` to `Optional[UUID]`.
- All SQL WHERE clauses are now conditional: if `property_id is None`, the property filter is skipped and the query returns results across all properties in the tenant.
- **Effect**: Owners (no property) see all employees tenant-wide; managers (with property) see only their property.

### Fixed — `app/api/v1/endpoints/scheduling.py`
- Removed hard guard: `if not current_user.property_id: raise HTTPException(400, "User must be assigned to a property")`. This blocked all owner-level users.

---

## [2026-05-24] — get_current_user_obj Dependency

### Added — `app/api/dependencies.py`

```python
async def get_current_user_obj(
    db: AsyncSession = Depends(get_db),
    token: str = Depends(oauth2_scheme),
    request: Request = None,
) -> User:
```

- Decodes JWT → queries User from DB → `selectinload(User.role_obj)` (not `role` — actual relationship name is `role_obj`)
- Sets `request.state.user`, `request.state.tenant_id`, `request.state.property_id`
- Raises HTTP 401 if user not found or not active
- Used by: `documents.py`, `scheduling.py`, `complaints.py`, `activity_log.py`
- The original `get_current_user` (returns JWT dict) is **unchanged** — ~20 existing endpoints still use it

---

## [2026-05-23] — New Module Endpoints

### Added — `/v1/` prefix fix
All four new endpoint files were missing the `/v1/` prefix in their router paths, causing `{"detail":"Not Found"}` on all calls. All paths now correctly start with `/v1/...`.

### Modules integrated:
| Endpoint file | Router prefix |
|---|---|
| `app/api/v1/endpoints/documents.py` | `/v1/documents` |
| `app/api/v1/endpoints/scheduling.py` | `/v1/scheduling` |
| `app/api/v1/endpoints/complaints.py` | `/v1/complaints` |
| `app/api/v1/endpoints/activity_log.py` | `/v1/activity-log` |

---

## [2026-05-22] — Chat System

### Added
- `app/api/v1/endpoints/chat.py` — conversations, messages, WebSocket delivery
- `message_media` table for media attachments
- `tenant_id` correctly persisted on messages
- `last_message` populated in conversation list response
- `last_message_at` updated on every new message send
- DB migration for new chat tables
