"""Store the punch-out location check on attendance_records

Adds nullable attendance_records.punch_out_acc (GPS accuracy in metres),
punch_out_within_fence and punch_out_distance_meters, written by
create_punch_out. Existing rows keep NULLs (location result unknown).

attendance_records has never had its own migration: it is created by
init_db()'s create_all at app startup. On a fresh database the table does
not exist yet when this runs, so the migration does nothing and create_all
builds the table from the model, which already carries these columns.

The existence check is done in SQL (to_regclass) rather than with
dialect.has_table() so the migration renders with `alembic upgrade --sql`.
Every statement is IF [NOT] EXISTS, so a re-run is a no-op.

Revision ID: 027_attendance_punch_out_location
Revises: 026_sync_log_rooms_summary
Create Date: 2026-10-27

"""
from alembic import op

revision = "027_attendance_punch_out_location"
down_revision = "026_sync_log_rooms_summary"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        DO $$
        BEGIN
            IF to_regclass('attendance_records') IS NULL THEN
                RETURN;
            END IF;

            ALTER TABLE attendance_records ADD COLUMN IF NOT EXISTS punch_out_acc DOUBLE PRECISION;
            ALTER TABLE attendance_records ADD COLUMN IF NOT EXISTS punch_out_within_fence BOOLEAN;
            ALTER TABLE attendance_records ADD COLUMN IF NOT EXISTS punch_out_distance_meters DOUBLE PRECISION;
        END $$
    """)


def downgrade() -> None:
    op.execute("""
        DO $$
        BEGIN
            IF to_regclass('attendance_records') IS NULL THEN
                RETURN;
            END IF;

            ALTER TABLE attendance_records DROP COLUMN IF EXISTS punch_out_distance_meters;
            ALTER TABLE attendance_records DROP COLUMN IF EXISTS punch_out_within_fence;
            ALTER TABLE attendance_records DROP COLUMN IF EXISTS punch_out_acc;
        END $$
    """)
