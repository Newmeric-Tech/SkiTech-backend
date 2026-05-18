"""
migrate_room_number_start.py

Adds room_number_start column to the properties table.
Idempotent — safe to run multiple times.

Usage:
    cd skitech_backend
    python migrate_room_number_start.py
"""

import asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from app.core.config import settings

connect_args = {}
if "neon.tech" in settings.DATABASE_URL or settings.is_production:
    connect_args = {"ssl": "require", "server_settings": {"application_name": "skitech-migrate"}}

engine = create_async_engine(settings.DATABASE_URL, echo=False, connect_args=connect_args)


async def migrate():
    async with engine.begin() as conn:
        await conn.execute(text("""
            ALTER TABLE properties
            ADD COLUMN IF NOT EXISTS room_number_start INTEGER DEFAULT 101
        """))
        print("✓ properties.room_number_start — done")

    await engine.dispose()
    print("Migration complete.")


if __name__ == "__main__":
    asyncio.run(migrate())
