"""Add otp_code and otp_expires_at to users table

Revision ID: 007_add_otp_fields
Revises: 006_add_ranking_tables
Create Date: 2026-06-03

"""
from alembic import op
import sqlalchemy as sa

revision = "007_add_otp_fields"
down_revision = "006_add_ranking_tables"
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    existing = {row[0] for row in conn.execute(sa.text(
        "SELECT column_name FROM information_schema.columns WHERE table_name='users'"
    ))}
    if "otp_code" not in existing:
        op.add_column("users", sa.Column("otp_code", sa.String(6), nullable=True))
    if "otp_expires_at" not in existing:
        op.add_column("users", sa.Column("otp_expires_at", sa.DateTime(), nullable=True))


def downgrade():
    op.drop_column("users", "otp_expires_at")
    op.drop_column("users", "otp_code")
