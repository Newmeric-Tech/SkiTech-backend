"""Add columns/table that were previously applied outside Alembic

migrate_missing_columns.py and migrate_room_number_start.py (loose scripts
in the repo root) ran raw ALTER TABLE / create_all directly against the
live DB, so these were never recorded in migration history. Verified via
`alembic check` against production that these match app/models/models.py
exactly (Employee.user_id, SOPItem.assigned_user_id, SOPExecution,
Property.room_number_start) with no other drift. Statements are
idempotent so this is safe to run on both a fresh DB and the already
-patched production DB.

Revision ID: 012_add_manual_gap_columns
Revises: 011_add_channel_manager_tables
Create Date: 2026-09-13

"""
from alembic import op
from sqlalchemy import text

revision = "012_add_manual_gap_columns"
down_revision = "011_add_channel_manager_tables"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()

    # 1. employees.user_id
    op.execute(text("""
        ALTER TABLE employees
        ADD COLUMN IF NOT EXISTS user_id UUID REFERENCES users(id) ON DELETE SET NULL;
    """))

    # 2. sop_items.assigned_user_id (+ index, matches SOPItem.__table_args__)
    op.execute(text("""
        ALTER TABLE sop_items
        ADD COLUMN IF NOT EXISTS assigned_user_id UUID REFERENCES users(id) ON DELETE SET NULL;
    """))
    op.execute(text("""
        CREATE INDEX IF NOT EXISTS idx_sop_user ON sop_items (assigned_user_id);
    """))

    # 3. properties.room_number_start
    op.execute(text("""
        ALTER TABLE properties
        ADD COLUMN IF NOT EXISTS room_number_start INTEGER DEFAULT 101;
    """))

    # 4. sop_executions table (matches app/models/models.py SOPExecution exactly)
    if not conn.dialect.has_table(conn, "sop_executions"):
        op.execute(text("""
            CREATE TABLE sop_executions (
                id UUID PRIMARY KEY,
                sop_id UUID NOT NULL REFERENCES sop_items(id) ON DELETE CASCADE,
                user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                property_id UUID NOT NULL REFERENCES properties(id) ON DELETE CASCADE,
                tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
                status VARCHAR(50) NOT NULL DEFAULT 'pending',
                completed_at TIMESTAMP NULL,
                proof_image TEXT NULL,
                proof_submitted_at TIMESTAMP NULL,
                proof_location_lat DOUBLE PRECISION NULL,
                proof_location_lng DOUBLE PRECISION NULL,
                proof_location_name VARCHAR(255) NULL,
                rejection_reason TEXT NULL,
                created_at TIMESTAMP NOT NULL DEFAULT now(),
                updated_at TIMESTAMP NOT NULL DEFAULT now()
            );
        """))
        op.execute(text("CREATE INDEX IF NOT EXISTS idx_sop_exec_user ON sop_executions (user_id);"))
        op.execute(text("CREATE INDEX IF NOT EXISTS idx_sop_exec_sop ON sop_executions (sop_id);"))
        op.execute(text("CREATE INDEX IF NOT EXISTS idx_sop_exec_status ON sop_executions (status);"))


def downgrade() -> None:
    op.execute(text("DROP TABLE IF EXISTS sop_executions CASCADE;"))
    op.execute(text("ALTER TABLE properties DROP COLUMN IF EXISTS room_number_start;"))
    op.execute(text("ALTER TABLE sop_items DROP COLUMN IF EXISTS assigned_user_id;"))
    op.execute(text("ALTER TABLE employees DROP COLUMN IF EXISTS user_id;"))
