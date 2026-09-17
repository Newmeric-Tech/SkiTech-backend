"""Add inbox_items table

Cross-module "needs your attention" feed. v1 sources are Complaints
(escalated) and Inventory (low stock) only — see DEVELOPMENT_LOG.md
Architecture Debt for why SOP approvals and shift-replacement requests
are held back as future source types on this same table.

Revision ID: 014_add_inbox_items
Revises: 013_add_is_demo_column
Create Date: 2026-09-17

"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "014_add_inbox_items"
down_revision = "013_add_is_demo_column"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()

    if not conn.dialect.has_table(conn, "inbox_items"):
        op.create_table(
            "inbox_items",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False, index=True),
            sa.Column("property_id", postgresql.UUID(as_uuid=True), nullable=True, index=True),
            sa.Column("source_module", sa.String(50), nullable=False, index=True),
            sa.Column("item_type", sa.String(50), nullable=False, index=True),
            sa.Column("source_record_id", postgresql.UUID(as_uuid=True), nullable=False, index=True),
            sa.Column("recipient_user_id", postgresql.UUID(as_uuid=True), nullable=True, index=True),
            sa.Column("recipient_role", sa.String(50), nullable=True, index=True),
            sa.Column("title", sa.String(255), nullable=False),
            sa.Column("body", sa.Text(), nullable=False),
            sa.Column("status", sa.String(20), nullable=False, server_default="unread", index=True),
            sa.Column("read_at", sa.DateTime(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        )


def downgrade() -> None:
    op.drop_table("inbox_items")
