"""Store the room-sync result on each sync_logs row

Adds a nullable sync_logs.rooms_summary JSONB holding the room import counts
(insert / adopt / update / conflict) and the conflict reasons with room
numbers for that run. Existing rows keep NULL.

sync_logs is created by 011_add_channel_manager_tables, so it normally exists
here; the to_regclass check only keeps the migration a no-op on a database
where it does not. The check is done in SQL rather than with
dialect.has_table() so the migration renders with `alembic upgrade --sql`.
Every statement is IF [NOT] EXISTS, so a re-run is a no-op.

Revision ID: 026_sync_log_rooms_summary
Revises: 025_room_channel_link
Create Date: 2026-10-21

"""
from alembic import op

revision = "026_sync_log_rooms_summary"
down_revision = "025_room_channel_link"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        DO $$
        BEGIN
            IF to_regclass('sync_logs') IS NULL THEN
                RETURN;
            END IF;

            ALTER TABLE sync_logs ADD COLUMN IF NOT EXISTS rooms_summary JSONB;
        END $$
    """)


def downgrade() -> None:
    op.execute("""
        DO $$
        BEGIN
            IF to_regclass('sync_logs') IS NULL THEN
                RETURN;
            END IF;

            ALTER TABLE sync_logs DROP COLUMN IF EXISTS rooms_summary;
        END $$
    """)
