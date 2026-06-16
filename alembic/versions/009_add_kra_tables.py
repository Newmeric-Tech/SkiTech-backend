"""Add KRA tables (daily, weekly, monthly, quarterly)

Revision ID: 009_add_kra_tables
Revises: 008_add_co_admin
Create Date: 2026-06-12

"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "009_add_kra_tables"
down_revision = "008_add_co_admin"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()

    if not conn.dialect.has_table(conn, "daily_kras"):
        op.create_table(
            "daily_kras",
            sa.Column("id", sa.Integer(), primary_key=True, index=True, autoincrement=True),
            sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False, index=True),
            sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False, index=True),
            sa.Column("date", sa.Date(), nullable=False, index=True),
            sa.Column("shift_changeover_status", sa.Boolean(), nullable=False, server_default="false"),
            sa.Column("guest_checkin_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("guest_checkout_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("complaints_logged", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("room_availability_checked", sa.Boolean(), nullable=False, server_default="false"),
            sa.Column("maintenance_tasks", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("cash_deposit_amount", sa.Float(), nullable=False, server_default="0.0"),
            sa.Column("google_reviews_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column("is_submitted", sa.Boolean(), nullable=False, server_default="false", index=True),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column("deleted_at", sa.DateTime(), nullable=True),
        )

    if not conn.dialect.has_table(conn, "weekly_kras"):
        op.create_table(
            "weekly_kras",
            sa.Column("id", sa.Integer(), primary_key=True, index=True, autoincrement=True),
            sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False, index=True),
            sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False, index=True),
            sa.Column("week_starting_date", sa.Date(), nullable=False, index=True),
            sa.Column("year", sa.Integer(), nullable=False),
            sa.Column("week_number", sa.Integer(), nullable=False),
            sa.Column("ota_images_uploaded", sa.Boolean(), nullable=False, server_default="false"),
            sa.Column("ota_platforms", sa.Text(), nullable=True),
            sa.Column("supply_stock_reviewed", sa.Boolean(), nullable=False, server_default="false"),
            sa.Column("supply_notes", sa.Text(), nullable=True),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column("is_submitted", sa.Boolean(), nullable=False, server_default="false", index=True),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column("deleted_at", sa.DateTime(), nullable=True),
        )

    if not conn.dialect.has_table(conn, "monthly_kras"):
        op.create_table(
            "monthly_kras",
            sa.Column("id", sa.Integer(), primary_key=True, index=True, autoincrement=True),
            sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False, index=True),
            sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False, index=True),
            sa.Column("month", sa.Integer(), nullable=False),
            sa.Column("year", sa.Integer(), nullable=False, index=True),
            sa.Column("revenue_amount", sa.Float(), nullable=True),
            sa.Column("guest_count", sa.Integer(), nullable=True),
            sa.Column("occupancy_rate", sa.Float(), nullable=True),
            sa.Column("revenue_report_url", sa.Text(), nullable=True),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column("is_submitted", sa.Boolean(), nullable=False, server_default="false", index=True),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column("deleted_at", sa.DateTime(), nullable=True),
        )

    if not conn.dialect.has_table(conn, "quarterly_kras"):
        op.create_table(
            "quarterly_kras",
            sa.Column("id", sa.Integer(), primary_key=True, index=True, autoincrement=True),
            sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False, index=True),
            sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False, index=True),
            sa.Column("quarter", sa.Integer(), nullable=False),
            sa.Column("year", sa.Integer(), nullable=False, index=True),
            sa.Column("revenue_amount", sa.Float(), nullable=True),
            sa.Column("guest_count", sa.Integer(), nullable=True),
            sa.Column("occupancy_rate", sa.Float(), nullable=True),
            sa.Column("revenue_report_url", sa.Text(), nullable=True),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column("is_submitted", sa.Boolean(), nullable=False, server_default="false", index=True),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column("deleted_at", sa.DateTime(), nullable=True),
        )

    if not conn.dialect.has_table(conn, "workforce_entries"):
        op.create_table(
            "workforce_entries",
            sa.Column("id", sa.Integer(), primary_key=True, index=True, autoincrement=True),
            sa.Column("first_name", sa.String(255), nullable=False),
            sa.Column("last_name", sa.String(255), nullable=False),
            sa.Column("email", sa.String(255), nullable=True, index=True),
            sa.Column("phone", sa.String(20), nullable=True),
            sa.Column("property_id", sa.Integer(), nullable=False, index=True),
            sa.Column("employee_id", sa.String(100), nullable=False, unique=True, index=True),
            sa.Column("position", sa.String(100), nullable=False),
            sa.Column("department", sa.String(100), nullable=False, index=True),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true", index=True),
            sa.Column("start_date", sa.Date(), nullable=False),
            sa.Column("end_date", sa.Date(), nullable=True),
            sa.Column("scheduled_hours_per_week", sa.Integer(), nullable=False),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column("deleted_at", sa.DateTime(), nullable=True),
        )


def downgrade() -> None:
    op.drop_table("workforce_entries")
    op.drop_table("quarterly_kras")
    op.drop_table("monthly_kras")
    op.drop_table("weekly_kras")
    op.drop_table("daily_kras")
