"""Fix missing auto-increment sequence on KRA table id columns

The id columns on daily_kras/weekly_kras/monthly_kras/quarterly_kras were
created without a backing sequence/default, so INSERTs that don't supply
an id fail with a NotNullViolationError. This attaches a proper serial
sequence to each, seeded past any existing rows.

Revision ID: 010_fix_kra_id_sequences
Revises: 009_add_kra_tables
Create Date: 2026-06-17

"""
from alembic import op

revision = "010_fix_kra_id_sequences"
down_revision = "009_add_kra_tables"
branch_labels = None
depends_on = None

KRA_TABLES = ["daily_kras", "weekly_kras", "monthly_kras", "quarterly_kras"]


def upgrade() -> None:
    conn = op.get_bind()
    for table in KRA_TABLES:
        if not conn.dialect.has_table(conn, table):
            continue
        seq_name = f"{table}_id_seq"
        op.execute(f"CREATE SEQUENCE IF NOT EXISTS {seq_name}")
        op.execute(f"ALTER SEQUENCE {seq_name} OWNED BY {table}.id")
        op.execute(
            f"SELECT setval('{seq_name}', COALESCE((SELECT MAX(id) FROM {table}), 0) + 1, false)"
        )
        op.execute(f"ALTER TABLE {table} ALTER COLUMN id SET DEFAULT nextval('{seq_name}')")


def downgrade() -> None:
    for table in KRA_TABLES:
        op.execute(f"ALTER TABLE {table} ALTER COLUMN id DROP DEFAULT")
        op.execute(f"DROP SEQUENCE IF EXISTS {table}_id_seq")
