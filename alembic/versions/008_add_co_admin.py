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

    conn = op.get_bind()

    # Check if table already exists
    table_exists = conn.execute(sa.text(
        "SELECT 1 FROM information_schema.tables WHERE table_name='co_admin_requests'"
    )).scalar()

    if not table_exists:
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

    # Create indexes only if they don't exist
    existing_indexes = {row[0] for row in conn.execute(sa.text(
        "SELECT indexname FROM pg_indexes WHERE tablename='co_admin_requests'"
    ))}
    for idx_name, col in [
        ("ix_co_admin_requests_requesting_user_id", "requesting_user_id"),
        ("ix_co_admin_requests_tenant_id",          "tenant_id"),
        ("ix_co_admin_requests_property_id",        "property_id"),
        ("ix_co_admin_requests_status",             "status"),
    ]:
        if idx_name not in existing_indexes:
            op.create_index(idx_name, "co_admin_requests", [col])


def downgrade():
    op.drop_table("co_admin_requests")
    op.execute("DELETE FROM roles WHERE name = 'Co Admin';")
