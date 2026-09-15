"""Formalize is_demo column that was added outside Alembic

users.is_demo already exists on production (added via raw ALTER TABLE
alongside a bulk INSERT of 44 synthetic demo accounts, both entirely
outside git/Alembic history). Adding it here to app/models/models.py
and recording it in migration history, same pattern as
012_add_manual_gap_columns.py. Statement is idempotent so this is safe
to run on both a fresh DB and the already-patched production DB.

Revision ID: 013_add_is_demo_column
Revises: 012_add_manual_gap_columns
Create Date: 2026-09-15

"""
from alembic import op
from sqlalchemy import text

revision = "013_add_is_demo_column"
down_revision = "012_add_manual_gap_columns"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(text("""
        ALTER TABLE users
        ADD COLUMN IF NOT EXISTS is_demo BOOLEAN NOT NULL DEFAULT false;
    """))


def downgrade() -> None:
    op.execute(text("ALTER TABLE users DROP COLUMN IF EXISTS is_demo;"))
