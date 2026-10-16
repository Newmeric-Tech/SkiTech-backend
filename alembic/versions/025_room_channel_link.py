"""Link rooms to the channel manager integration that imported them

Adds rooms.integration_id / external_id / synced_at plus a partial unique
index on (integration_id, external_id), for the room import in
sync_service. Existing rooms keep NULLs and stay manual.

rooms has never had its own migration: it predates Alembic and is created by
init_db()'s create_all, which runs at app startup, after `alembic upgrade
head`. On a fresh database the table therefore does not exist yet when this
runs; the migration does nothing and create_all builds rooms from the model,
which already carries these columns.

The existence check is done in SQL (to_regclass) rather than with
dialect.has_table() so the migration renders with `alembic upgrade --sql`.
Every statement is IF [NOT] EXISTS, so a re-run is a no-op.

Revision ID: 025_room_channel_link
Revises: 024_drop_orphaned_tables
Create Date: 2026-10-16

"""
from alembic import op

revision = "025_room_channel_link"
down_revision = "024_drop_orphaned_tables"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        DO $$
        BEGIN
            IF to_regclass('rooms') IS NULL THEN
                RETURN;
            END IF;

            ALTER TABLE rooms ADD COLUMN IF NOT EXISTS integration_id UUID;
            ALTER TABLE rooms ADD COLUMN IF NOT EXISTS external_id VARCHAR(255);
            ALTER TABLE rooms ADD COLUMN IF NOT EXISTS synced_at TIMESTAMPTZ;

            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint
                WHERE conname = 'rooms_integration_id_fkey' AND conrelid = 'rooms'::regclass
            ) THEN
                ALTER TABLE rooms ADD CONSTRAINT rooms_integration_id_fkey
                    FOREIGN KEY (integration_id) REFERENCES integrations(id) ON DELETE SET NULL;
            END IF;

            CREATE UNIQUE INDEX IF NOT EXISTS uq_room_integration_external
                ON rooms (integration_id, external_id)
                WHERE external_id IS NOT NULL;
        END $$
    """)


def downgrade() -> None:
    op.execute("""
        DO $$
        BEGIN
            IF to_regclass('rooms') IS NULL THEN
                RETURN;
            END IF;

            DROP INDEX IF EXISTS uq_room_integration_external;
            ALTER TABLE rooms DROP CONSTRAINT IF EXISTS rooms_integration_id_fkey;
            ALTER TABLE rooms DROP COLUMN IF EXISTS synced_at;
            ALTER TABLE rooms DROP COLUMN IF EXISTS external_id;
            ALTER TABLE rooms DROP COLUMN IF EXISTS integration_id;
        END $$
    """)
