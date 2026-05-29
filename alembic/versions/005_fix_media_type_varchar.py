"""Fix message_media.media_type: convert from native ENUM to VARCHAR(20)

Revision ID: 005_fix_media_type_varchar
Revises: 004_add_document_mgmt_tables
Create Date: 2026-05-29

Root cause:
    Migration 001 created message_media.media_type as a native PostgreSQL ENUM
    type (``mediatype``). The ORM model uses SQLEnum(MediaType, native_enum=False)
    which tells SQLAlchemy to treat the column as a VARCHAR. asyncpg's binary
    protocol sends string parameters with type OID 25 (text). PostgreSQL's
    prepared-statement protocol rejects inserting a text-typed parameter into a
    native ENUM column because there is no implicit pg_cast entry for
    text → custom ENUM. Result: every file-upload INSERT into message_media fails
    with a type-mismatch error, the exception is caught, and the MessageMedia
    record is never persisted — messages refresh as plain text.

Fix:
    ALTER the column to VARCHAR(20). The existing CHECK constraint
    (check_media_type) continues to enforce valid values, so validation is
    equivalent. The native ``mediatype`` ENUM type is then dropped.
"""

from alembic import op
import sqlalchemy as sa


revision = '005_fix_media_type_varchar'
down_revision = '004_add_document_mgmt_tables'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Drop the CHECK constraint so the column type can be changed freely
    op.drop_constraint('check_media_type', 'message_media', type_='check')

    # Alter from native ENUM to VARCHAR; USING clause converts existing values
    op.execute(
        "ALTER TABLE message_media "
        "ALTER COLUMN media_type TYPE VARCHAR(20) "
        "USING media_type::text"
    )

    # Recreate the CHECK constraint on the now-VARCHAR column
    op.create_check_constraint(
        'check_media_type',
        'message_media',
        "media_type IN ('image', 'file', 'video', 'audio')"
    )

    # Drop the now-unused native ENUM type
    op.execute("DROP TYPE IF EXISTS mediatype")


def downgrade() -> None:
    # Recreate the native ENUM type
    op.execute(
        "CREATE TYPE mediatype AS ENUM ('image', 'file', 'video', 'audio')"
    )

    # Drop the VARCHAR CHECK constraint before changing the column type
    op.drop_constraint('check_media_type', 'message_media', type_='check')

    # Revert to native ENUM
    op.execute(
        "ALTER TABLE message_media "
        "ALTER COLUMN media_type TYPE mediatype "
        "USING media_type::mediatype"
    )

    # Restore the original CHECK constraint
    op.create_check_constraint(
        'check_media_type',
        'message_media',
        "media_type IN ('image', 'file', 'video', 'audio')"
    )
