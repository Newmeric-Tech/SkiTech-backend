"""Add missing uniqueness enforcement on governance_workflows

Found by the schema-drift audit: GovernanceWorkflow.name (unique=True) and
.code (unique=True, index=True) in app/models/models.py have both declared
uniqueness since the model was written, but live introspection shows the
table has only its primary key — no unique constraint on name, no unique
index on code.

This isn't just documentation drift: app/api/v1/endpoints/governance.py
create_workflow() does a bare db.add()/commit() with no pre-check for an
existing name or code, and relies entirely on the DB to reject duplicates.
With no constraint/index live, two workflows can silently share a name or
code today — a silent duplicate-row bug, not a crash, which is worse in
that nothing signals it happened. Confirmed via live query: 0 rows
currently in governance_workflows, so both can be added directly with no
dedup step needed.

`code` uses IF NOT EXISTS (Postgres index DDL supports it natively). `name`
needs a guarded DO block since ADD CONSTRAINT has no IF NOT EXISTS form;
the constraint name matches Postgres' own default auto-naming
(<table>_<column>_key) to stay consistent with how every other live
constraint in this DB was named (this schema predates Alembic entirely,
so nothing here was named by a naming_convention).

Revision ID: 019_governance_workflows_unique
Revises: 018_doc_tpl_is_system_action
Create Date: 2026-09-25

"""
from alembic import op
from sqlalchemy import text

revision = "019_governance_workflows_unique"
down_revision = "018_doc_tpl_is_system_action"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(text("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint WHERE conname = 'governance_workflows_name_key'
            ) THEN
                ALTER TABLE governance_workflows
                ADD CONSTRAINT governance_workflows_name_key UNIQUE (name);
            END IF;
        END $$;
    """))
    op.execute(text(
        "CREATE UNIQUE INDEX IF NOT EXISTS ix_governance_workflows_code "
        "ON governance_workflows (code);"
    ))


def downgrade() -> None:
    op.execute(text("DROP INDEX IF EXISTS ix_governance_workflows_code;"))
    op.execute(text(
        "ALTER TABLE governance_workflows DROP CONSTRAINT IF EXISTS governance_workflows_name_key;"
    ))
