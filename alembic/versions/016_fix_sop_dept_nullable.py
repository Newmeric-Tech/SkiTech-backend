"""Fix sop_items.department_id NOT NULL drift

sop_items was never created by any tracked Alembic migration — the baseline
migration (81aac769860e_baseline.py) is a no-op ("schema already exists in
the database"), so whatever DDL actually ran on day one was never recorded
in code. SOPItem.department_id has always been declared nullable=True in
app/models/models.py, and every other layer (Pydantic schema, the task
creation form) agrees: department is optional. The live table disagreed —
department_id was NOT NULL — so creating a task without a department (the
form has no department field at all) failed with a NotNullViolation on
insert, even though nothing in the codebase ever asked for that constraint.

Same root cause as 012_add_manual_gap_columns and 015_drop_chat_tables:
someone altered the live schema directly, outside Alembic, at some point
before this project's migration history began. This migration brings the
live column in line with the model, which has been correct all along.

Revision ID: 016_fix_sop_dept_nullable
Revises: 015_drop_chat_tables
Create Date: 2026-09-25

"""
from alembic import op
from sqlalchemy import text

revision = "016_fix_sop_dept_nullable"
down_revision = "015_drop_chat_tables"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # DROP NOT NULL is a no-op if the column is already nullable, so this
    # is safe to run against both the drifted production DB and any
    # environment where the column was already correct.
    op.execute(text("ALTER TABLE sop_items ALTER COLUMN department_id DROP NOT NULL;"))


def downgrade() -> None:
    # Mirrors the model's prior (incorrect) live constraint. Will fail if
    # any row has department_id NULL at downgrade time — that's intentional,
    # since silently nulling data or backfilling a fake department would be
    # worse than a loud failure.
    op.execute(text("ALTER TABLE sop_items ALTER COLUMN department_id SET NOT NULL;"))
