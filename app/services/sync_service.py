from typing import Any
import json
from datetime import datetime, timedelta
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import AsyncSessionLocal
from app.utils.crypto import decrypt
from app.services.adapters import get_adapter

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


async def _run_single_integration_sync(db: AsyncSession, integration: Any) -> None:
    log_id = await create_sync_log(db, str(integration.id))
    print(f"Starting sync for integration {integration.id} ({integration.provider_name})")

    try:
        # 1. Decrypt credentials
        credentials_raw = decrypt(integration.credentials_json)
        credentials = json.loads(credentials_raw)

        # 2. Get correct adapter
        adapter = get_adapter(integration.provider_name)

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
            print(f"Non-blocking warning: Failed to sync availability for {integration.provider_name}: {avail_err}")

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
        print(f"Sync error for integration {integration.id}: {err}")
        # 8. Mark integration as error
        error_query = text("""
            UPDATE integrations
            SET connection_status = 'error', error_message = :error_message
            WHERE id = :id
        """)
        await db.execute(error_query, {"error_message": str(err), "id": integration.id})
        await complete_sync_log(db, log_id, "error", 0, str(err))


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
            print(f"Error fetching integrations for sync: {e}")
