"""Add FK constraints declared in models but never enforced live

Found by the schema-drift audit: these columns have carried a
ForeignKey(...) in app/models/models.py since they were written, but were
never enforced at the DB level — same "created outside Alembic" root cause
as everything else in this audit. sop_executions and workflow_instances in
particular have *zero* FK enforcement on any column today.

Every column here was checked for orphaned values (child value with no
matching parent row) before writing this migration — all clean, 0 orphans
across sop_executions.{user_id,property_id,tenant_id},
workflow_instances.*, sop_items.assigned_user_id, documents.deleted_by,
employees.department_id, and inventory_movements.{tenant_id,property_id}.

sop_executions.sop_id is deliberately NOT included here — it has 4 rows
referencing sop_items that were hard-deleted (2 completed, 1 approved, 1
still pending), so a validated FK would fail on this table today. That
needs a decision on the orphaned rows themselves, not a schema change, and
is being handled separately.

ON DELETE behavior matches each column's existing ForeignKey(...) in the
model exactly (CASCADE where declared, SET NULL where declared, default
NO ACTION where neither is specified).

Revision ID: 021_add_missing_fks
Revises: 020_kra_ranking_missing_idx
Create Date: 2026-09-25

"""
from alembic import op
from sqlalchemy import text

revision = "021_add_missing_fks"
down_revision = "020_kra_ranking_missing_idx"
branch_labels = None
depends_on = None

# (constraint_name, table, column, parent_table, parent_column, on_delete_or_None)
_FKS = [
    ("sop_executions_user_id_fkey", "sop_executions", "user_id", "users", "id", "CASCADE"),
    ("sop_executions_property_id_fkey", "sop_executions", "property_id", "properties", "id", "CASCADE"),
    ("sop_executions_tenant_id_fkey", "sop_executions", "tenant_id", "tenants", "id", "CASCADE"),
    ("workflow_instances_workflow_id_fkey", "workflow_instances", "workflow_id", "governance_workflows", "id", None),
    ("workflow_instances_requested_by_id_fkey", "workflow_instances", "requested_by_id", "users", "id", None),
    ("workflow_instances_current_approver_id_fkey", "workflow_instances", "current_approver_id", "users", "id", None),
    ("sop_items_assigned_user_id_fkey", "sop_items", "assigned_user_id", "users", "id", "SET NULL"),
    ("documents_deleted_by_fkey", "documents", "deleted_by", "users", "id", "SET NULL"),
    ("employees_department_id_fkey", "employees", "department_id", "departments", "id", None),
    ("inventory_movements_tenant_id_fkey", "inventory_movements", "tenant_id", "tenants", "id", None),
    ("inventory_movements_property_id_fkey", "inventory_movements", "property_id", "properties", "id", None),
]


def upgrade() -> None:
    for conname, table, column, parent_table, parent_col, on_delete in _FKS:
        on_delete_clause = f" ON DELETE {on_delete}" if on_delete else ""
        op.execute(text(f"""
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM pg_constraint WHERE conname = '{conname}'
                ) THEN
                    ALTER TABLE {table}
                    ADD CONSTRAINT {conname}
                    FOREIGN KEY ({column}) REFERENCES {parent_table}({parent_col}){on_delete_clause};
                END IF;
            END $$;
        """))


def downgrade() -> None:
    for conname, table, _column, _parent_table, _parent_col, _on_delete in _FKS:
        op.execute(text(f"ALTER TABLE {table} DROP CONSTRAINT IF EXISTS {conname};"))
