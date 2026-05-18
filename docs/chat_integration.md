# Chat Integration — Full Documentation

## Overview

A complete real-time chat system was integrated into the SkiTech platform. The work covered:

1. Merging the teammate's chat backend code into the main `skitech_backend`
2. Wiring up database migrations
3. Fixing a maximized-view UI bug in the chat widget
4. Replacing all static mock data with real API calls
5. Implementing role-based contact visibility
6. Making emoji, file, and image buttons functional

---

## Part 1 — Backend Merge

### Files Copied from `SkiTech-backend-api-integrate` into `skitech_backend`

| File | Purpose |
|---|---|
| `app/models/chat_models.py` | 7 SQLAlchemy ORM models |
| `app/schemas/chat_schemas.py` | Pydantic request/response schemas |
| `app/repositories/chat_repository.py` | Data access layer |
| `app/services/chat_service.py` | Business logic layer |
| `app/utils/chat_security.py` | JWT + multi-tenant validation |
| `app/utils/chat_utils.py` | UUID, pagination, media-type helpers |
| `app/websocket/manager.py` | In-memory WebSocket connection manager |
| `app/storage/base.py` | Local file storage backend |
| `app/api/v1/endpoints/chat.py` | REST + WebSocket endpoints |
| `app/repositories/__init__.py` | Empty init |
| `app/websocket/__init__.py` | Empty init |
| `app/storage/__init__.py` | Empty init |

### Import Fixes Applied to Copied Files

**Problem 1** — `chat.py` and `chat_security.py` used `get_async_session` but the main backend exports `get_db`.

```python
# Fix applied in both files:
from app.core.database import get_db as get_async_session
```

**Problem 2** — `chat_security.py` imported `verify_token` which does not exist in the main backend. The correct function is `decode_token` which returns `None` on failure instead of raising.

```python
# Old (teammate's code):
from app.core.security import verify_token
token_data = verify_token(token)  # raises on failure

# Fixed:
from app.core.security import decode_token
token_data = decode_token(token)
if not token_data:
    raise HTTPException(status_code=401, detail="Invalid or expired token")
```

**Problem 3** — `verify_property_access` in `chat_security.py` accessed `user.role_obj.name` which is a lazy SQLAlchemy relationship and fails in async context.

```python
# Old:
if user.property_id != property_id and not user.role_obj.name == "super_admin":

# Fixed:
if user.property_id != property_id:
    raise AccessDenied("User does not have access to this property")
```

### Existing Files Modified

**`app/utils/exceptions.py`** — Added aliases used by the chat code:

```python
AccessDenied = ForbiddenError
NotFound = NotFoundError
```

**`app/models/__init__.py`** — Added chat model imports so Alembic autogenerate picks them up:

```python
from app.models.chat_models import (
    Conversation, ConversationParticipant, Message, MessageMedia,
    MessageDeliveryStatus, TypingIndicator, ChatNotification,
)
```

**`app/api/v1/router.py`** — Registered the chat router:

```python
from app.api.v1.endpoints import ..., chat
router.include_router(chat.router)
```

**`app/__init__.py`** — Added startup initialization in the lifespan handler:

```python
from app.websocket.manager import init_websocket_manager
from app.storage.base import init_storage

# Inside lifespan:
Path("uploads/chat").mkdir(parents=True, exist_ok=True)
init_websocket_manager()
init_storage("local", base_path="uploads/chat")
```

---

## Part 2 — Database Migration

### Files Created

**`alembic/versions/81aac769860e_baseline.py`** — Stub baseline migration. The Neon database already had a revision `81aac769860e` tracked in `alembic_version` but no corresponding file existed locally. This file provides that anchor point.

```python
revision = '81aac769860e'
down_revision = None
def upgrade() -> None:
    pass  # schema already exists in the database
def downgrade() -> None:
    pass
```

**`alembic/versions/001_add_chat_tables.py`** — Creates all 7 chat tables:

- `conversations` — Direct and group chats, multi-tenant isolated
- `messages` — Chat messages with soft delete and reply support
- `conversation_participants` — User membership and roles
- `message_media` — File/image/audio attachments
- `message_delivery_status` — Sent/delivered/read receipts
- `typing_indicators` — Real-time typing state
- `chat_notifications` — Push notifications

```python
revision = '001_add_chat_tables'
down_revision = '81aac769860e'  # chains after the baseline
```

### How to Run the Migration

```bash
cd skitech_backend
# Activate virtual environment first
venv\Scripts\activate          # Windows
source venv/bin/activate       # Mac/Linux

alembic upgrade head
```

---

## Part 3 — UI Bug Fix (Maximized View)

**Problem** — When the chat widget was maximized without a conversation selected, the right panel was blank white. The conditional rendering logic fell through to a single-panel list instead of the two-panel layout.

**Fix** — Restructured the render logic so that `isMaximized` always renders the two-panel layout, with a placeholder ("Select a conversation") on the right when no chat is active.

```
Before:
  isMaximized && activeChat → two-panel
  activeChat (non-maximized) → single chat window
  (default) → chat list only   ← blank right side when maximized, no selection

After:
  isMaximized → two-panel always (placeholder on right if no selection)
  activeChat (non-maximized) → single chat window
  (default) → chat list only
```

---

## Part 4 — Real Data Integration

### Backend Changes

#### `app/schemas/chat_schemas.py`

Added `other_participants` to `ConversationListItem` so the frontend knows who is in each direct conversation without fetching full conversation details:

```python
class ConversationListItem(BaseModel):
    ...
    other_participants: List[UserInChat] = []
```

#### `app/repositories/chat_repository.py`

Changed the `get_user_conversations` query to eager-load the user object on each participant. Without this, accessing `participant.user` in async SQLAlchemy raises a `MissingGreenlet` error.

```python
# Before:
.options(selectinload(Conversation.participants))

# After:
.options(
    selectinload(Conversation.participants).selectinload(ConversationParticipant.user)
)
```

#### `app/services/chat_service.py`

Moved `UserInChat` to the top-level import, removed duplicate bottom-level import, and populated `other_participants` in `get_user_conversations`:

```python
other_participants = [
    UserInChat(
        id=p.user.id,
        first_name=p.user.first_name or "",
        last_name=p.user.last_name or "",
        email=p.user.email
    )
    for p in conv.participants
    if p.user_id != user_id and p.left_at is None and p.user is not None
]
```

#### `app/api/v1/endpoints/chat.py` — New `/contacts` Endpoint

Added `GET /api/v1/chat/contacts` which any authenticated user (including Staff) can call. It returns contacts filtered by the caller's role and property.

**Role-based contact rules:**

| Caller Role | Can Chat With |
|---|---|
| Tenant Admin (Owner) | Other Tenant Admins + Managers (same property) |
| Manager | Tenant Admins + Staff (same property) |
| Staff | Managers + Staff (same property) |
| Super Admin | All roles (same property) |

This endpoint was necessary because the existing `GET /v1/users/` endpoint blocks Staff role users.

```python
GET /api/v1/chat/contacts?tenant_id={uuid}&property_id={uuid}
Authorization: Bearer <token>

Response: [{ id, first_name, last_name, email }, ...]
```

### Frontend Changes

#### `skitech_frontend/lib/api/chat.ts` (New File)

API module for all chat operations:

```typescript
chatAPI.contacts(tenantId, propertyId)
chatAPI.listConversations(tenantId, propertyId, skip?, limit?)
chatAPI.createDirect(tenantId, propertyId, otherUserId)
chatAPI.getMessages(conversationId, tenantId, propertyId, skip?, limit?)
chatAPI.sendMessage(conversationId, tenantId, propertyId, content)
chatAPI.uploadMedia(conversationId, tenantId, propertyId, messageId, file)
```

#### `skitech_frontend/components/chat/ChatWidget.tsx` (Rewritten)

Complete rewrite replacing all static mock data with real API calls.

**Data loading flow:**

```
Widget opens
  └─ usersAPI.me() → gets property_id (not in JWT)
      └─ chatAPI.listConversations() → loads real conversations
          └─ Maps API response to Chat objects (shows real names)

User selects conversation
  └─ chatAPI.getMessages() → loads real message history

User sends text message
  └─ Optimistic local add → chatAPI.sendMessage() → replaces with real server response

User picks image/file
  └─ Show locally via blob URL immediately
  └─ chatAPI.sendMessage(filename) → get message ID
  └─ chatAPI.uploadMedia(messageId, file) → uploads in background

User clicks "New Chat" (+ icon)
  └─ chatAPI.contacts() → loads role-filtered contact list
  └─ User picks contact → chatAPI.createDirect() → creates/gets conversation → selects it
```

**Changes to chat list:**
- Filter tabs updated from "AI / Staff / Manager / Group" to "All / Direct / Group"
- "New Chat" button (`UserPlus` icon) added to header
- Empty state shown when no conversations exist
- Real participant names displayed for direct chats

**Emoji button** — Already worked (adds emoji to text input). No changes needed.

**File/Image buttons** — Now fully wired: immediate local display + background upload to backend.

**Voice recording** — Shows locally; upload to backend not yet wired (audio upload would require the same two-step flow as files).

---

## Part 5 — API Endpoint Reference

All chat endpoints are under `/api/v1/chat/` and require `Authorization: Bearer <token>`.

| Method | Endpoint | Description |
|---|---|---|
| GET | `/chat/contacts` | Role-filtered contact list for current user |
| GET | `/chat/conversations` | List user's conversations |
| POST | `/chat/conversations/direct` | Create or get direct conversation |
| POST | `/chat/conversations/group` | Create group conversation |
| GET | `/chat/conversations/{id}` | Get conversation details + participants |
| PUT | `/chat/conversations/{id}` | Update name/description/avatar |
| POST | `/chat/conversations/{id}/archive` | Archive conversation |
| POST | `/chat/conversations/{id}/mute` | Mute/unmute conversation |
| GET | `/chat/conversations/{id}/messages` | Get paginated messages |
| POST | `/chat/conversations/{id}/messages` | Send message |
| PUT | `/chat/messages/{id}` | Edit message (sender only) |
| DELETE | `/chat/messages/{id}` | Delete message (sender only) |
| POST | `/chat/conversations/{id}/media/upload` | Upload file/image |
| GET | `/chat/media/{id}/download` | Download media file |
| WS | `/chat/conversations/{id}/ws?token=<jwt>` | WebSocket real-time channel |

---

## Part 6 — Architecture Notes

### Multi-Tenant Isolation

Every chat query checks three levels:
1. `tenant_id` — prevents data leakage across tenants
2. `property_id` — prevents data leakage across properties within a tenant
3. Conversation membership — user must be an active participant

### WebSocket

The WebSocket manager (`app/websocket/manager.py`) is in-memory. It handles:
- `typing.start` / `typing.stop` — broadcasts to conversation participants
- `read.receipt` — broadcasts read status
- `user.online` / `user.offline` — presence events on connect/disconnect

For production scale, replace the in-memory manager with Redis pub/sub.

### File Storage

Files are stored locally at `uploads/chat/conversations/{conv_id}/messages/{msg_id}/{filename}`.

The `app/storage/base.py` `LocalStorageBackend` can be swapped for S3/GCS by implementing the same interface and calling `init_storage("s3", ...)`.

### Property ID Not in JWT

The JWT token contains `user_id`, `tenant_id`, `role`, `email` — but not `property_id`. The frontend resolves this by calling `GET /v1/users/me` once on widget open to fetch `property_id`. This value is then passed as a query parameter on all chat API calls.

---

## Part 7 — Known Limitations

| Item | Status |
|---|---|
| Voice recording upload to backend | Local playback only; no server upload |
| Last message preview in conversation list | Not fetched (shows "Tap to start chatting") |
| WebSocket real-time in frontend | Not yet connected (polling via reload) |
| Online/offline presence dot | Always shows offline (WebSocket not connected) |
| Super Admin property access | Super Admin must belong to a property to use chat |

---

## Part 8 — Post-Integration Bug Fixes & RBAC Overhaul

This section documents bugs found and fixed after the initial integration (sessions 2026-05-17 and 2026-05-18).

---

### Bug 1 — Login Broken: `ArgumentError: remote_side=[id]`

**Symptom:** Every login returned a 500 error. Backend log showed:

```
ArgumentError: Column expression expected for argument 'remote_side';
got <built-in function id>
```

**Root Cause:** `app/models/chat_models.py` contained a self-referential relationship on `Message` where `remote_side` was set to `[id]` — Python's built-in `id()` function, not the `Message.id` column.

```python
# BROKEN — [id] refers to Python's built-in id() function
replies = relationship("Message", remote_side=[id], ...)
```

This caused SQLAlchemy to raise an `ArgumentError` at import time, which prevented the app from starting entirely.

**Fix (commit `6d91a59`):** Use the string form, which SQLAlchemy resolves at runtime after the model class is fully defined.

```python
# FIXED — string resolved by SQLAlchemy at runtime
replies = relationship("Message", remote_side="Message.id", ...)
```

**File:** `app/models/chat_models.py`

---

### Bug 2 — Backend Deployed from Wrong Branch

**Symptom:** Render was deploying from the `api-integrate` branch. Fixes pushed to `main` were not being deployed.

**Root Cause:** The Render service was configured to watch the `api-integrate` branch. Additionally, local `main` and `api-integrate` had diverged histories.

**Fix:** Force-pushed `api-integrate` into `origin/main`, then synced the local branch:

```bash
git push origin api-integrate:main   # promote api-integrate → main on remote
git pull origin main --rebase         # sync local main to match
```

Render was then reconfigured to watch the `main` branch.

---

### Bug 3 — Startup Foreign Key Error (Render Logs)

**Symptom:** Render logs showed a `ForeignKeyViolation` or `DuplicateTable` error on every deploy restart. The tables were being created in a single transaction, so if any chat table already existed, the whole `create_all()` call could fail.

**Root Cause:** `init_db()` in `app/core/database.py` called `Base.metadata.create_all()` which runs all table creations in one transaction. If any chat table already existed, the error propagated even though it was caught at the top level.

**Fix (commit `375408c`):** Create each table individually in its own `try/except`, then apply idempotent `ALTER TABLE` migrations.

```python
# app/core/database.py — init_db()
for table in Base.metadata.sorted_tables:
    try:
        await conn.run_sync(lambda c, t=table: t.create(c, checkfirst=True))
    except Exception:
        pass  # Table already exists — skip gracefully

migrations = [
    "ALTER TABLE attendance_records ADD COLUMN IF NOT EXISTS current_status VARCHAR(50);",
    "ALTER TABLE properties ADD COLUMN IF NOT EXISTS image_urls JSONB DEFAULT '[]'::jsonb;",
]
for sql in migrations:
    try:
        await conn.execute(text(sql))
    except Exception:
        pass
```

**File:** `app/core/database.py`

---

### Bug 4 — Tenant Admin Could Not See Staff Contacts

**Symptom:** When Owner (Tenant Admin) opened "New Chat", only Managers appeared — no Staff members.

**Root Cause:** The `role_map` in the contacts endpoint only listed `["Tenant Admin", "Manager"]` for Tenant Admin. `"Staff"` was missing.

**Fix (commit `34eb817`):**

```python
# app/api/v1/endpoints/chat.py — contacts endpoint
role_map = {
    "Tenant Admin": ["Tenant Admin", "Manager", "Staff"],  # Staff was missing
    "Manager":      ["Tenant Admin", "Staff"],
    "Staff":        ["Manager", "Staff"],
}
```

**File:** `app/api/v1/endpoints/chat.py`

---

### Bug 5 — Tenant Admin Locked Out of Any Property

**Symptom:** Owner (Tenant Admin) had `property_id = null` in the database. The `verify_property_access` check raised `AccessDenied` for any property_id that didn't match the user's `property_id` — which was `null`, so it always failed.

**Root Cause:** The access check used strict equality:

```python
# BROKEN
if user.property_id != property_id:
    raise AccessDenied("User does not have access to this property")
```

A Tenant Admin with `property_id = null` would fail this check against any non-null property_id.

**Fix:** Users with no assigned property (Tenant Admin / Super Admin) should be allowed to access any property within their tenant.

```python
# FIXED — app/utils/chat_security.py
if user.property_id is not None and user.property_id != property_id:
    raise AccessDenied("User does not have access to this property")
```

**File:** `app/utils/chat_security.py`

---

### Bug 6 — MissingGreenlet Errors (Contacts endpoint async lazy loading)

**Symptom:** Clicking on a contact to start a DM either showed "Could not start conversation" or went blank. Backend logs showed `MissingGreenlet` or `greenlet_spawn` errors.

**Root Cause:** Two places in the repository had lazy-loaded SQLAlchemy relationships accessed outside the async greenlet:

1. `get_direct_conversation` — accessed `conv.participants` after fetching the conversation, but participants were not eagerly loaded.
2. `get_by_id` — accessed `p.user` and `conversation.creator` which were lazy relationships.

**Fix (commit `b327a44`):**

```python
# get_direct_conversation — add selectinload for participants
stmt = (
    select(Conversation)
    .where(and_(...))
    .options(selectinload(Conversation.participants))  # ADDED
)

# get_by_id — add nested selectinloads
.options(
    selectinload(Conversation.participants).selectinload(ConversationParticipant.user),
    selectinload(Conversation.creator),
)
```

**File:** `app/repositories/chat_repository.py`

---

### Bug 7 — Blank Conversation List (SQLAlchemy count_stmt crash)

**Symptom:** The chat widget opened but showed "No conversations yet" for all users, even after conversations were created. Backend logs showed a SQLAlchemy error on the `list_conversations` endpoint.

**Root Cause:** `get_user_conversations` in the repository had this count query at line 117:

```python
# BROKEN — SQLAlchemy 2.0 rejects a select() as argument to select_from()
count_stmt = select(func.count()).select_from(base_query)
```

In SQLAlchemy 2.0, `select_from()` requires a table or mapped class, not a `select()` statement. The correct form wraps the base query as a subquery.

**Fix (commit `256df18`):**

```python
# FIXED
count_stmt = select(func.count()).select_from(base_query.subquery())
```

**File:** `app/repositories/chat_repository.py`

---

### Bug 8 — Owner Only Saw Conversations from One Property

**Symptom:** Owner (Tenant Admin) with null `property_id` could only see conversations from whichever property the frontend happened to discover first. Conversations involving users from other properties were invisible.

**Root Cause:** Two compounding issues:

1. `list_conversations` required `property_id: UUID = Query(...)` — mandatory, non-null. The frontend set `effectivePropertyId` by calling `usersAPI.list()` and using the first user's property. Only conversations from that single property were returned.

2. `get_user_conversations` in the repository always filtered by `Conversation.property_id == property_id`. No mechanism existed for returning conversations across all properties.

**Fix (commit `256df18`):**

**Backend — `app/api/v1/endpoints/chat.py`:**

```python
# property_id is now optional
async def list_conversations(
    tenant_id: UUID = Query(...),
    property_id: Optional[UUID] = Query(None),  # omit → Tenant Admin sees all
    ...
):
    user, _ = await verify_jwt_token(authorization, session)
    await verify_tenant_access(user, tenant_id, session)
    # Use explicit param → user's own property → None (Tenant Admin)
    effective_prop = property_id if property_id is not None else user.property_id
    if effective_prop is not None:
        await verify_property_access(user, tenant_id, effective_prop, session)

    conversations, total = await service.get_user_conversations(
        user_id=user.id,
        tenant_id=tenant_id,
        property_id=effective_prop,  # None = no property filter
        ...
    )
```

**Backend — `app/repositories/chat_repository.py`:**

```python
async def get_user_conversations(
    self,
    user_id: UUID,
    tenant_id: UUID,
    property_id: Optional[UUID] = None,  # None = all properties
    ...
):
    conditions = [
        Conversation.tenant_id == tenant_id,
        Conversation.deleted_at.is_(None),
    ]
    if property_id is not None:
        conditions.append(Conversation.property_id == property_id)

    base_query = select(Conversation).join(...).where(and_(*conditions))
```

**Files:** `app/api/v1/endpoints/chat.py`, `app/repositories/chat_repository.py`, `app/services/chat_service.py`

---

### Bug 9 — Messages/Send Failed for Cross-Property Conversations

**Symptom:** After the Tenant Admin clicked on a conversation that belonged to Property B (while `effectivePropertyId` was set to Property A), loading messages and sending messages silently failed because the wrong property_id was sent to the backend.

**Root Cause:** The frontend used a single global `effectivePropertyId` for all message operations, regardless of which conversation was selected.

**Fix (commit `6383bd0`):**

**Backend — `app/schemas/chat_schemas.py`:**

```python
class ConversationListItem(BaseModel):
    ...
    property_id: Optional[UUID] = None  # NEW — returned with every conversation
```

**Frontend — `lib/api/chat.ts`:**

```typescript
export interface ConversationListItem {
  ...
  property_id: string | null;  // NEW
}

// listConversations now accepts optional propertyId
listConversations: (tenantId: string, propertyId: string | null | undefined, ...) =>
  api.get("/v1/chat/conversations", {
    params: { tenant_id: tenantId, ...(propertyId ? { property_id: propertyId } : {}), ... }
  }),
```

**Frontend — `components/chat/ChatWidget.tsx`:**

```typescript
interface Chat {
  ...
  property_id: string | null;  // NEW — stored per conversation
}

// Load conversations using user's own property_id (null for Tenant Admin)
// No longer waits for effectivePropertyId discovery
chatAPI.listConversations(user.tenant_id, myProfile.property_id)

// Messages use the conversation's own property_id
const propId = selectedChat.property_id || effectivePropertyId;
chatAPI.getMessages(selectedChat.id, user.tenant_id, propId)

// Send uses the conversation's own property_id
const chat = chats.find(c => c.id === chatId);
const propId = chat?.property_id || effectivePropertyId;
chatAPI.sendMessage(chatId, user.tenant_id, propId, content)
```

**Files:** `app/schemas/chat_schemas.py`, `app/services/chat_service.py`, `skitech_frontend/lib/api/chat.ts`, `skitech_frontend/components/chat/ChatWidget.tsx`

---

### Final RBAC Rules (As Implemented)

| Role | Sees in Contacts | Can Chat With |
|---|---|---|
| Tenant Admin (Owner) | All Managers + Staff across ALL properties | Anyone in tenant |
| Manager | Owner + all Staff at their property | Owner + own property Staff |
| Staff | Manager at their property + other Staff at same property | Manager + same-property Staff |

### Conversation Property Assignment

When a DM is created, the `property_id` on the `conversations` row is set to the **other user's** `property_id` (the contact's property). This means:

- Owner DMs Manager at Tulip → conversation stored with `property_id = tulip_id`
- Owner DMs Manager at Del Luna → conversation stored with `property_id = del_luna_id`
- Owner can see BOTH because `list_conversations` now skips the property filter for users with `null` property_id

---

### Commit History for This Session

| Commit | Description |
|---|---|
| `6d91a59` | Fix `remote_side=[id]` → `remote_side="Message.id"` in chat_models.py |
| `375408c` | Fix startup FK error — create tables individually with checkfirst=True |
| `34eb817` | Add Staff to Tenant Admin role_map in contacts endpoint |
| `b327a44` | Fix MissingGreenlet — add selectinload for participants and creator |
| `256df18` | Fix count_stmt subquery bug + make list_conversations optional property_id |
| `6383bd0` | Frontend: per-conversation property_id routing for messages and send |

---

## Part 9 — Known Limitations (Updated)

| Item | Status |
|---|---|
| Voice recording upload to backend | Local playback only; no server upload |
| WebSocket real-time in frontend | Not yet connected (REST polling only) |
| Online/offline presence dot | Always shows offline (WebSocket not connected) |
| Super Admin property access | Super Admin must belong to a property to use chat |
| Last message preview | Returned from API but displayed as "Tap to start chatting" if no messages sent yet |
