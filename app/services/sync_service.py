from typing import Any, Dict, List, Optional, Tuple
import json
import logging
from datetime import datetime, timedelta
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import AsyncSessionLocal
from app.utils.crypto import decrypt
from app.services.adapters import get_adapter
from app.utils.safe_errors import log_safe_exception, safe_error_summary

logger = logging.getLogger(__name__)

# A run still 'syncing' after this long is treated as interrupted (e.g. the
# worker was restarted mid-sync and never wrote finished_at).
STALE_SYNC_MINUTES = 15

def add_days(date_str: str, days: int) -> str:
    date = datetime.strptime(date_str, "%Y-%m-%d")
    new_date = date + timedelta(days=days)
    return new_date.strftime("%Y-%m-%d")


async def create_sync_log(db: AsyncSession, integration_id: str) -> str:
    query = text("""
        INSERT INTO sync_logs (integration_id, started_at, status)
        VALUES (:integration_id, NOW(), 'syncing')
        RETURNING id
    """)
    res = await db.execute(query, {"integration_id": integration_id})
    await db.commit()
    # Fetch returned ID
    return str(res.scalar())


async def complete_sync_log(
    db: AsyncSession,
    log_id: str,
    status: str,
    records_synced: int,
    error_message: str = None
) -> None:
    query = text("""
        UPDATE sync_logs
        SET finished_at = NOW(), status = :status, records_synced = :records_synced, error_message = :error_message
        WHERE id = :id
    """)
    await db.execute(query, {
        "status": status,
        "records_synced": records_synced,
        "error_message": error_message,
        "id": log_id
    })
    await db.commit()


ROOM_NUMBER_MAX = 50   # rooms.room_number VARCHAR(50)
ROOM_TYPE_MAX = 100    # rooms.room_type VARCHAR(100)


def _norm(room_number: Optional[str]) -> str:
    return (room_number or "").strip().lower()


def plan_room_sync(
    existing: List[Dict[str, Any]],
    fetched: List[Dict[str, Any]],
    integration_id: str,
) -> Tuple[List[Dict[str, Any]], Optional[str]]:
    """
    Decide what the room import does for one property, without touching the DB.

    existing: every rooms row of the property, soft-deleted included (the
    uq_room_number constraint ignores deleted_at), each with id, room_number,
    deleted_at, integration_id, external_id and owner_active (its integration
    exists and is not disconnected).
    fetched: adapter.fetch_rooms() output.

    Rules:
    - One integration owns a property's rooms: if another live integration
      already owns any of them, nothing is done.
    - A room this integration imported earlier is matched by external_id and
      its number/type refreshed, unless it was soft-deleted (conflict).
    - Otherwise a room is adopted only when exactly one row of the property
      matches the trimmed, case-insensitive number and that row is live and
      unowned (or owned by a disconnected integration). No match -> insert.
      Anything else is a conflict and is left alone.
    - Status is never set here except 'available' on insert.

    Returns (actions, skip_reason). Each action has "action" in
    insert / adopt / update / conflict.
    """
    integration_id = str(integration_id)
    rows = [dict(r) for r in existing]
    for r in rows:
        if r.get("integration_id") is not None:
            r["integration_id"] = str(r["integration_id"])

    if any(r["integration_id"] and r["integration_id"] != integration_id and r.get("owner_active") for r in rows):
        return [], "rooms are owned by another active integration"

    by_external = {r["external_id"]: r for r in rows if r["integration_id"] == integration_id and r.get("external_id")}
    actions: List[Dict[str, Any]] = []

    for f in fetched:
        external_id = str(f["external_id"])
        number = (f.get("room_number") or "").strip()
        room_type = (f.get("room_type") or "").strip()[:ROOM_TYPE_MAX] or None

        if not number or len(number) > ROOM_NUMBER_MAX:
            actions.append({"action": "conflict", "external_id": external_id, "room_number": number,
                            "reason": "room name is empty or longer than 50 characters"})
            continue

        row = by_external.get(external_id)
        if row is not None:
            # A synced room the owner soft-deleted is never refreshed or restored.
            if row["deleted_at"] is not None:
                actions.append({"action": "conflict", "external_id": external_id, "room_number": number,
                                "reason": "matches a deleted room"})
                continue
            if _norm(row["room_number"]) != _norm(number):
                if any(r is not row and _norm(r["room_number"]) == _norm(number) for r in rows):
                    actions.append({"action": "conflict", "external_id": external_id, "room_number": number,
                                    "reason": f"renamed from {row['room_number']!r} but the new number is already used"})
                    continue
                row["room_number"] = number
            actions.append({"action": "update", "id": row["id"], "external_id": external_id,
                            "room_number": row["room_number"], "room_type": room_type})
            continue

        matches = [r for r in rows if _norm(r["room_number"]) == _norm(number)]
        if not matches:
            rows.append({"id": None, "room_number": number, "deleted_at": None,
                         "integration_id": integration_id, "external_id": external_id, "owner_active": True})
            by_external[external_id] = rows[-1]
            actions.append({"action": "insert", "external_id": external_id,
                            "room_number": number, "room_type": room_type})
            continue

        candidate = matches[0]
        adoptable = (
            len(matches) == 1
            and candidate["deleted_at"] is None
            and (candidate["integration_id"] is None or not candidate.get("owner_active"))
        )
        if adoptable:
            candidate["integration_id"] = integration_id
            candidate["external_id"] = external_id
            by_external[external_id] = candidate
            actions.append({"action": "adopt", "id": candidate["id"], "external_id": external_id,
                            "room_number": candidate["room_number"], "room_type": room_type})
            continue

        if len(matches) > 1:
            reason = f"{len(matches)} existing rooms match this number"
        elif candidate["deleted_at"] is not None:
            reason = "matches a deleted room"
        else:
            reason = "matches a room already linked to this integration under another id"
        actions.append({"action": "conflict", "external_id": external_id, "room_number": number, "reason": reason})

    return actions, None


async def sync_rooms(db: AsyncSession, integration: Any, fetched: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Apply plan_room_sync for one integration. Caller owns the transaction.

    Returns the run's summary for sync_logs.rooms_summary: the counts per
    action, each conflict as {room_number, reason}, and "skipped" with the
    reason when nothing was done. Room numbers only, never guest data.
    """
    existing = (await db.execute(text("""
        SELECT r.id, r.room_number, r.deleted_at, r.integration_id, r.external_id,
               (i.id IS NOT NULL AND i.connection_status != 'disconnected') AS owner_active
        FROM rooms r
        LEFT JOIN integrations i ON i.id = r.integration_id
        WHERE r.property_id = :property_id
    """), {"property_id": integration.property_id})).mappings().all()

    actions, skip_reason = plan_room_sync(existing, fetched, str(integration.id))
    counts = {"insert": 0, "adopt": 0, "update": 0, "conflict": 0}
    conflicts: List[Dict[str, str]] = []
    if skip_reason:
        print(f"Integration {integration.id}: room sync skipped: {skip_reason}.")
        return {**counts, "conflicts": conflicts, "skipped": skip_reason}

    for a in actions:
        counts[a["action"]] += 1
        if a["action"] == "insert":
            await db.execute(text("""
                INSERT INTO rooms (id, tenant_id, property_id, room_number, room_type, status, is_demo,
                                   integration_id, external_id, synced_at, created_at, updated_at)
                VALUES (gen_random_uuid(), :tenant_id, :property_id, :room_number, :room_type, 'available', FALSE,
                        :integration_id, :external_id, NOW(), NOW(), NOW())
            """), {
                "tenant_id": integration.tenant_id, "property_id": integration.property_id,
                "room_number": a["room_number"], "room_type": a["room_type"],
                "integration_id": integration.id, "external_id": a["external_id"],
            })
        elif a["action"] in ("adopt", "update"):
            await db.execute(text("""
                UPDATE rooms
                SET room_number = :room_number, room_type = COALESCE(:room_type, room_type),
                    integration_id = :integration_id, external_id = :external_id,
                    synced_at = NOW(), updated_at = NOW()
                WHERE id = :id
            """), {
                "id": a["id"], "room_number": a["room_number"], "room_type": a["room_type"],
                "integration_id": integration.id, "external_id": a["external_id"],
            })
            if a["action"] == "adopt":
                print(f"Integration {integration.id}: adopted existing room {a['room_number']!r}.")
        else:
            conflicts.append({"room_number": a["room_number"], "reason": a["reason"]})
            print(f"Integration {integration.id}: room {a['room_number']!r} not imported: {a['reason']}.")

    logger.info(
        "Integration %s: rooms imported=%d adopted=%d updated=%d conflicts=%d",
        integration.id, counts["insert"], counts["adopt"], counts["update"], counts["conflict"],
    )
    return {**counts, "conflicts": conflicts}


async def save_rooms_summary(db: AsyncSession, log_id: str, summary: Dict[str, Any]) -> None:
    """
    Store a run's room-sync summary on its sync_logs row. Never raises: if the
    write fails (e.g. migration 026 not applied, so the column is missing) only
    the savepoint is rolled back and the sync carries on without it.
    """
    try:
        async with db.begin_nested():
            await db.execute(
                text("UPDATE sync_logs SET rooms_summary = CAST(:summary AS JSONB) WHERE id = :id"),
                {"summary": json.dumps(summary), "id": log_id},
            )
    except Exception as err:
        log_safe_exception(logger, f"Sync log {log_id}: could not store rooms_summary", err, logging.WARNING)


async def _run_single_integration_sync(db: AsyncSession, integration: Any) -> None:
    log_id = await create_sync_log(db, str(integration.id))
    print(f"Starting sync for integration {integration.id} ({integration.provider_name})")

    try:
        # 1. Decrypt credentials
        credentials_raw = decrypt(integration.credentials_json)
        credentials = json.loads(credentials_raw)

        # 2. Get correct adapter
        adapter = get_adapter(integration.provider_name)

        # 2b. Import rooms (non-blocking). Runs in a savepoint so a failed room
        # statement rolls back only the room changes, not the reservation sync.
        if getattr(adapter, "supports_room_sync", False):
            try:
                fetched_rooms = await adapter.fetch_rooms(credentials)
                async with db.begin_nested():
                    rooms_summary = await sync_rooms(db, integration, fetched_rooms)
            except Exception as room_err:
                rooms_summary = {"error": safe_error_summary(room_err)}
                print(f"Non-blocking warning: Failed to sync rooms for {integration.provider_name}: {rooms_summary['error']}")
            await save_rooms_summary(db, log_id, rooms_summary)

        # 3. Calculate 90 days date range
        today_str = datetime.now().strftime("%Y-%m-%d")
        ninety_days_str = (datetime.now() + timedelta(days=90)).strftime("%Y-%m-%d")

        # 4. Fetch reservations
        reservations = await adapter.fetch_reservations(
            credentials,
            str(integration.property_id),
            today_str,
            ninety_days_str
        )

        print(f"Integration {integration.id}: Fetched {len(reservations)} reservations. Upserting...")

        # 5. Upsert reservations
        for res in reservations:
            query = text("""
                INSERT INTO reservations (
                    tenant_id, property_id, integration_id, external_id,
                    status, guest_name, guest_email, guest_phone,
                    room_number, room_type, check_in_date, check_out_date,
                    num_nights, num_adults, num_children,
                    total_amount, currency, booking_source, special_requests,
                    booked_at, synced_at
                ) VALUES (
                    :tenant_id, :property_id, :integration_id, :external_id,
                    :status, :guest_name, :guest_email, :guest_phone,
                    :room_number, :room_type, :check_in_date, :check_out_date,
                    :num_nights, :num_adults, :num_children,
                    :total_amount, :currency, :booking_source, :special_requests,
                    :booked_at, NOW()
                )
                ON CONFLICT (integration_id, external_id)
                DO UPDATE SET
                    status = EXCLUDED.status,
                    room_number = EXCLUDED.room_number,
                    check_in_date = EXCLUDED.check_in_date,
                    check_out_date = EXCLUDED.check_out_date,
                    total_amount = EXCLUDED.total_amount,
                    synced_at = NOW()
            """)
            await db.execute(query, {
                "tenant_id": integration.tenant_id,
                "property_id": integration.property_id,
                "integration_id": integration.id,
                "external_id": res["external_id"],
                "status": res["status"],
                "guest_name": res["guest_name"],
                "guest_email": res.get("guest_email"),
                "guest_phone": res.get("guest_phone"),
                "room_number": res.get("room_number"),
                "room_type": res.get("room_type"),
                "check_in_date": res["check_in_date"],
                "check_out_date": res["check_out_date"],
                "num_nights": res["num_nights"],
                "num_adults": res.get("num_adults", 1),
                "num_children": res.get("num_children", 0),
                "total_amount": res["total_amount"],
                "currency": res["currency"],
                "booking_source": res.get("booking_source"),
                "special_requests": res.get("special_requests"),
                "booked_at": res.get("booked_at")
            })

        # 6. Try fetching availability (non-blocking)
        try:
            availability = await adapter.fetch_availability(
                credentials,
                str(integration.property_id),
                today_str,
                ninety_days_str
            )
            print(f"Integration {integration.id}: Fetched {len(availability)} availability rows.")
        except Exception as avail_err:
            print(f"Non-blocking warning: Failed to sync availability for {integration.provider_name}: {safe_error_summary(avail_err)}")

        # 7. Update integration success status
        update_query = text("""
            UPDATE integrations
            SET last_sync_at = NOW(), connection_status = 'active', error_message = NULL
            WHERE id = :id
        """)
        await db.execute(update_query, {"id": integration.id})

        await complete_sync_log(db, log_id, "success", len(reservations))
        print(f"Integration {integration.id} sync completed successfully.")

    except Exception as err:
        # str(err) of a DB error carries the bound parameters (guest name,
        # email, phone); store and print only the sanitized summary.
        safe_message = safe_error_summary(err)
        print(f"Sync error for integration {integration.id}: {safe_message}")
        # A failed upsert leaves the Postgres transaction aborted; roll back so
        # the error bookkeeping below can run. The sync_logs row survives
        # because create_sync_log already committed it.
        await db.rollback()
        # 8. Mark integration as error
        error_query = text("""
            UPDATE integrations
            SET connection_status = 'error', error_message = :error_message
            WHERE id = :id
        """)
        await db.execute(error_query, {"error_message": safe_message, "id": integration.id})
        await complete_sync_log(db, log_id, "error", 0, safe_message)


async def sync_single_integration(integration: Any) -> None:
    """
    Entry point for background tasks. Opens its own session rather than
    reusing a request-scoped one, which FastAPI closes before background
    tasks run.
    """
    async with AsyncSessionLocal() as db:
        await _run_single_integration_sync(db, integration)


async def sync_all_integrations() -> None:
    print("Querying active integrations for background sync...")
    async with AsyncSessionLocal() as db:
        try:
            query = text("SELECT * FROM integrations WHERE connection_status = 'active'")
            integrations = (await db.execute(query)).fetchall()
            print(f"Found {len(integrations)} active integrations to sync.")

            for integration in integrations:
                await _run_single_integration_sync(db, integration)
        except Exception as e:
            print(f"Error fetching integrations for sync: {safe_error_summary(e)}")
