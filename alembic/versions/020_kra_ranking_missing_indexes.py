"""Add missing indexes on KRA and ranking tables

Found by the schema-drift audit: every column below is declared
index=True in app/models/kra.py and app/models/ranking_models.py, but has
no corresponding index live (confirmed by diffing exact table+column pairs
against live pg_indexes — this excludes the ~77 cases elsewhere in the
audit where a live index exists under a different name than SQLAlchemy
would generate; those are naming noise, not missing coverage, and are
intentionally left alone).

Not a correctness risk — these tables work fine without the index, just
slower as rows grow (KRA submission history, ranking score history). Lower
urgency than 016/017/018/019, but worth closing before it's a production
performance incident instead of a migration.

All indexes use SQLAlchemy's own default auto-generated name
(ix_<table>_<column>) so a future autogenerate diff recognizes them as
already satisfied instead of re-flagging a name mismatch.

Revision ID: 020_kra_ranking_missing_idx
Revises: 019_governance_workflows_unique
Create Date: 2026-09-25

"""
from alembic import op
from sqlalchemy import text

revision = "020_kra_ranking_missing_idx"
down_revision = "019_governance_workflows_unique"
branch_labels = None
depends_on = None

_TARGETS = {
    "daily_kras": ["date", "is_submitted", "user_id"],
    "weekly_kras": ["is_submitted", "user_id", "week_starting_date"],
    "monthly_kras": ["is_submitted", "user_id", "year"],
    "quarterly_kras": ["is_submitted", "user_id", "year"],
    "employee_ranking_scores": ["employee_id", "property_id", "tenant_id"],
    "employee_rankings": ["employee_id", "property_id", "tenant_id"],
    "ranking_audit_logs": ["property_id", "tenant_id"],
    "ranking_criteria_config": ["property_id", "tenant_id"],
    "ranking_insights": ["employee_id", "property_id", "tenant_id"],
}


def upgrade() -> None:
    for table, columns in _TARGETS.items():
        for column in columns:
            op.execute(text(
                f"CREATE INDEX IF NOT EXISTS ix_{table}_{column} ON {table} ({column});"
            ))


def downgrade() -> None:
    for table, columns in _TARGETS.items():
        for column in columns:
            op.execute(text(f"DROP INDEX IF EXISTS ix_{table}_{column};"))
