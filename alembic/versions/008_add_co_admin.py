"""Add Co Admin role and co_admin_requests table

Revision ID: 008_add_co_admin
Revises: 007_add_otp_fields
Create Date: 2026-06-08

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "008_add_co_admin"
down_revision = "007_add_otp_fields"
branch_labels = None
depends_on = None


def upgrade():
    # Add Co Admin role if not present
    op.execute("""
        INSERT INTO roles (id, name, role_level, description, created_at, updated_at)
        VALUES (gen_random_uuid(), 'Co Admin', 1, 'Property-scoped partner co-administrator', NOW(), NOW())
        ON CONFLICT (name) DO NOTHING;
    """)

    # Create co_admin_requests table
    op.create_table(
        "co_admin_requests",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("requesting_user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("tenant_id", UUID(as_uuid=True), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("property_id", UUID(as_uuid=True), sa.ForeignKey("properties.id", ondelete="CASCADE"), nullable=False),
        sa.Column("proposed_email", sa.String(255), nullable=False),
        sa.Column("proposed_name", sa.String(255), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("superadmin_note", sa.Text, nullable=True),
        sa.Column("invited_user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime, nullable=True),
    )
    op.create_index("ix_co_admin_requests_requesting_user_id", "co_admin_requests", ["requesting_user_id"])
    op.create_index("ix_co_admin_requests_tenant_id", "co_admin_requests", ["tenant_id"])
    op.create_index("ix_co_admin_requests_property_id", "co_admin_requests", ["property_id"])
    op.create_index("ix_co_admin_requests_status", "co_admin_requests", ["status"])


def downgrade():
    op.drop_table("co_admin_requests")
    op.execute("DELETE FROM roles WHERE name = 'Co Admin';")
