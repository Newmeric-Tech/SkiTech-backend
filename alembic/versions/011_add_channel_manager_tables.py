"""Add Channel Manager tables (integrations, sync_logs, reservations)

Revision ID: 011_add_channel_manager_tables
Revises: 010_fix_kra_id_sequences
Create Date: 2026-09-01

"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "011_add_channel_manager_tables"
down_revision = "010_fix_kra_id_sequences"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()

    if not conn.dialect.has_table(conn, "integrations"):
        op.create_table(
            "integrations",
            sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
            sa.Column("tenant_id", UUID(as_uuid=True), nullable=False, index=True),
            sa.Column("property_id", UUID(as_uuid=True), nullable=False, index=True),
            sa.Column("provider_name", sa.String(50), nullable=False),
            sa.Column("credentials_json", sa.Text(), nullable=False),
            sa.Column("connection_status", sa.String(20), nullable=False, server_default="pending"),
            sa.Column("last_sync_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("error_message", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.UniqueConstraint("property_id", "provider_name", name="uq_property_provider"),
        )

    if not conn.dialect.has_table(conn, "sync_logs"):
        op.create_table(
            "sync_logs",
            sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
            sa.Column(
                "integration_id", UUID(as_uuid=True),
                sa.ForeignKey("integrations.id", ondelete="CASCADE"),
                nullable=False, index=True,
            ),
            sa.Column("started_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("status", sa.String(20), nullable=True),
            sa.Column("records_synced", sa.Integer(), nullable=True, server_default="0"),
            sa.Column("error_message", sa.Text(), nullable=True),
        )

    if not conn.dialect.has_table(conn, "reservations"):
        op.create_table(
            "reservations",
            sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
            sa.Column("tenant_id", UUID(as_uuid=True), nullable=False, index=True),
            sa.Column("property_id", UUID(as_uuid=True), nullable=False, index=True),
            sa.Column(
                "integration_id", UUID(as_uuid=True),
                sa.ForeignKey("integrations.id", ondelete="CASCADE"),
                nullable=False, index=True,
            ),
            sa.Column("external_id", sa.String(255), nullable=False),
            sa.Column("status", sa.String(50), nullable=False),
            sa.Column("guest_name", sa.String(255), nullable=False),
            sa.Column("guest_email", sa.String(255), nullable=True),
            sa.Column("guest_phone", sa.String(255), nullable=True),
            sa.Column("room_number", sa.String(50), nullable=True),
            sa.Column("room_type", sa.String(100), nullable=True),
            sa.Column("check_in_date", sa.DateTime(timezone=False), nullable=False),
            sa.Column("check_out_date", sa.DateTime(timezone=False), nullable=False),
            sa.Column("num_nights", sa.Integer(), nullable=False),
            sa.Column("num_adults", sa.Integer(), nullable=True, server_default="1"),
            sa.Column("num_children", sa.Integer(), nullable=True, server_default="0"),
            sa.Column("total_amount", sa.Numeric(10, 2), nullable=False),
            sa.Column("currency", sa.String(10), nullable=False),
            sa.Column("booking_source", sa.String(100), nullable=True),
            sa.Column("special_requests", sa.Text(), nullable=True),
            sa.Column("booked_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("synced_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.UniqueConstraint("integration_id", "external_id", name="uq_integration_external_id"),
        )


def downgrade() -> None:
    op.drop_table("reservations")
    op.drop_table("sync_logs")
    op.drop_table("integrations")
