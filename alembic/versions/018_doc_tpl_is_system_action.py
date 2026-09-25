"""Add missing document_templates.is_system_action column

Found by the schema-drift audit (compare_metadata against the live DB):
DocumentTemplate.is_system_action in app/models/models.py (Boolean,
default=False, nullable) has never existed on the live table. Same root
cause as 017 — the column is declared in the model and actively selected
by document_service.py / documents.py on every DocumentTemplate query, so
any read of that table crashes with UndefinedColumn on live.

nullable, no server_default — the model's `default=False` is Python-side
(ORM-applied on insert), not enforced by Postgres, so existing rows are
left NULL rather than backfilled to false. That matches what the model
has always actually done for pre-existing rows either way.

Revision ID: 018_doc_tpl_is_system_action
Revises: 017_add_kra_revenue_columns
Create Date: 2026-09-25

"""
from alembic import op
from sqlalchemy import text

revision = "018_doc_tpl_is_system_action"
down_revision = "017_add_kra_revenue_columns"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(text(
        "ALTER TABLE document_templates ADD COLUMN IF NOT EXISTS is_system_action BOOLEAN;"
    ))


def downgrade() -> None:
    op.execute(text(
        "ALTER TABLE document_templates DROP COLUMN IF EXISTS is_system_action;"
    ))
