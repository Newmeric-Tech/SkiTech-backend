"""
Migration: add missing columns and tables

Run once:
    python migrate_missing_columns.py
"""

import asyncio
from sqlalchemy import text
from app.core.database import engine
from app.models.base import Base
import app.models  # noqa — registers all models


async def migrate():
    async with engine.begin() as conn:
        # 1. Add employees.user_id if missing
        await conn.execute(text("""
            ALTER TABLE employees
            ADD COLUMN IF NOT EXISTS user_id UUID REFERENCES users(id) ON DELETE SET NULL;
        """))
        print("✓ employees.user_id ensured")

        # 2. Create sop_executions table (new) and add proof columns if it already existed
        await conn.run_sync(Base.metadata.create_all)
        print("✓ sop_executions table ensured")

        # 3. Add assigned_user_id to sop_items if missing
        await conn.execute(text("""
            ALTER TABLE sop_items
            ADD COLUMN IF NOT EXISTS assigned_user_id UUID REFERENCES users(id) ON DELETE SET NULL;
        """))
        print("✓ sop_items.assigned_user_id ensured")

        # 4. Add proof columns to sop_executions if they don't exist yet
        proof_columns = [
            ("proof_image",         "TEXT"),
            ("proof_submitted_at",  "TIMESTAMP"),
            ("proof_location_lat",  "DOUBLE PRECISION"),
            ("proof_location_lng",  "DOUBLE PRECISION"),
            ("proof_location_name", "VARCHAR(255)"),
            ("rejection_reason",    "TEXT"),
        ]
        for col_name, col_type in proof_columns:
            await conn.execute(text(f"""
                ALTER TABLE sop_executions
                ADD COLUMN IF NOT EXISTS {col_name} {col_type};
            """))
            print(f"✓ sop_executions.{col_name} ensured")

    print("\nMigration complete. Restart your server.")


if __name__ == "__main__":
    asyncio.run(migrate())
