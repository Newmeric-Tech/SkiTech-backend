"""Fix weekly_kras.ota_images_uploaded column type (jsonb -> boolean)

The live database has this column as jsonb while the model has always
expected a boolean, causing asyncpg type errors on Weekly KRA submission.

Note: the KRA tables' id columns are UUID (not integer) in the live
database — this predates the migration that documents these tables, so
no migration is needed for that; app/models/kra.py was updated to use
UUIDMixin to match reality instead.

Revision ID: 010_fix_kra_id_sequences
Revises: 009_add_kra_tables
Create Date: 2026-06-17

"""
from alembic import op
from sqlalchemy import text

revision = "010_fix_kra_id_sequences"
down_revision = "009_add_kra_tables"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    if not conn.dialect.has_table(conn, "weekly_kras"):
        return

    col_type = conn.execute(
        text(
            "SELECT data_type FROM information_schema.columns "
            "WHERE table_name = 'weekly_kras' AND column_name = 'ota_images_uploaded'"
        )
    ).scalar()

    if col_type == "jsonb":
        op.execute(
            "ALTER TABLE weekly_kras "
            "ALTER COLUMN ota_images_uploaded TYPE boolean "
            "USING COALESCE((ota_images_uploaded #>> '{}')::boolean, false)"
        )
        op.execute("ALTER TABLE weekly_kras ALTER COLUMN ota_images_uploaded SET DEFAULT false")


def downgrade() -> None:
    op.execute("ALTER TABLE weekly_kras ALTER COLUMN ota_images_uploaded TYPE jsonb USING to_jsonb(ota_images_uploaded)")
