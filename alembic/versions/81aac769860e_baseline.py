"""Baseline — represents schema already in database before chat tables

Revision ID: 81aac769860e
Revises:
Create Date: 2026-05-17

"""
from alembic import op

revision = '81aac769860e'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass  # schema already exists in the database


def downgrade() -> None:
    pass
