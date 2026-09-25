"""Add missing revenue/guest/occupancy columns to monthly_kras and quarterly_kras

Found by the schema-drift audit (compare_metadata against the live DB):
MonthlyKRA and QuarterlyKRA in app/models/kra.py have always declared
revenue_amount (Float), guest_count (Integer), and occupancy_rate (Float),
but the live tables never had these columns — same "someone changed the
live schema outside Alembic" root cause as 012 and 016. Unlike 016, this
isn't a constraint disagreement; the columns are simply absent, so any
code path reading or writing them (KRA monthly/quarterly submit forms)
would fail with UndefinedColumn.

All three columns are nullable=True with no default in the model, so
adding them is a pure additive change — no backfill needed, existing rows
just get NULL.

Revision ID: 017_add_kra_revenue_columns
Revises: 016_fix_sop_dept_nullable
Create Date: 2026-09-25

"""
from alembic import op
from sqlalchemy import text

revision = "017_add_kra_revenue_columns"
down_revision = "016_fix_sop_dept_nullable"
branch_labels = None
depends_on = None

_TABLES = ("monthly_kras", "quarterly_kras")
_COLUMNS = (
    ("revenue_amount", "FLOAT"),
    ("guest_count", "INTEGER"),
    ("occupancy_rate", "FLOAT"),
)


def upgrade() -> None:
    for table in _TABLES:
        for column, coltype in _COLUMNS:
            op.execute(text(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {column} {coltype};"))


def downgrade() -> None:
    for table in _TABLES:
        for column, _coltype in _COLUMNS:
            op.execute(text(f"ALTER TABLE {table} DROP COLUMN IF EXISTS {column};"))
