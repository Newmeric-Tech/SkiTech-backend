"""Add sop_executions.sop_id FK as NOT VALID (4 pre-existing orphans)

sop_executions has never had any FK enforcement (see 021). sop_id is the
one column of the four that can't get a normally-validated FK today: 4
existing rows reference sop_items that were hard-deleted before this
column had any constraint stopping that. Those 4 rows are real history
(2 completed, 1 approved, 1 still pending) and are deliberately left
alone rather than deleted or backfilled.

NOT VALID adds and enforces the constraint for every future INSERT/UPDATE
without validating existing rows, so:
  - new orphaned sop_id values become impossible from this point on
  - the 4 existing orphans are left exactly as they are, no data touched
  - app/api/v1/endpoints/sop.py's my-tasks / pending-approval joins already
    handle a missing sop_items row gracefully (outer join, sop_title falls
    back to None -> frontend shows "Unknown Task"), so nothing downstream
    needs to change for this

If the 4 rows are ever cleaned up (e.g. their sop_items rows get restored,
or the executions are explicitly deleted), a follow-up migration can run
`ALTER TABLE sop_executions VALIDATE CONSTRAINT sop_executions_sop_id_fkey`
to fully validate — not done here since that's a data decision, not a
schema one.

Revision ID: 022_sop_exec_sop_id_fk
Revises: 021_add_missing_fks
Create Date: 2026-09-25

"""
from alembic import op
from sqlalchemy import text

revision = "022_sop_exec_sop_id_fk"
down_revision = "021_add_missing_fks"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(text("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint WHERE conname = 'sop_executions_sop_id_fkey'
            ) THEN
                ALTER TABLE sop_executions
                ADD CONSTRAINT sop_executions_sop_id_fkey
                FOREIGN KEY (sop_id) REFERENCES sop_items(id) ON DELETE CASCADE
                NOT VALID;
            END IF;
        END $$;
    """))


def downgrade() -> None:
    op.execute(text(
        "ALTER TABLE sop_executions DROP CONSTRAINT IF EXISTS sop_executions_sop_id_fkey;"
    ))
