"""Fix employees.department_id FK to match the model's ondelete="SET NULL"

021_add_missing_fks added this constraint without an ON DELETE clause —
a transcription mistake in that migration, not a live-DB finding. The
model has declared `ForeignKey("departments.id", ondelete="SET NULL")`
for Employee.department_id the entire time; the post-021 drift re-audit
caught the mismatch immediately (compare_type/compare_server_default
flagged it as both add_fk and remove_fk for the same column).

Postgres has no ALTER CONSTRAINT for changing ON DELETE behavior, so this
drops and re-adds the constraint with the correct clause.

Revision ID: 023_fix_emp_dept_fk_ondelete
Revises: 022_sop_exec_sop_id_fk
Create Date: 2026-09-25

"""
from alembic import op
from sqlalchemy import text

revision = "023_fix_emp_dept_fk_ondelete"
down_revision = "022_sop_exec_sop_id_fk"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(text(
        "ALTER TABLE employees DROP CONSTRAINT IF EXISTS employees_department_id_fkey;"
    ))
    op.execute(text("""
        ALTER TABLE employees
        ADD CONSTRAINT employees_department_id_fkey
        FOREIGN KEY (department_id) REFERENCES departments(id) ON DELETE SET NULL;
    """))


def downgrade() -> None:
    op.execute(text(
        "ALTER TABLE employees DROP CONSTRAINT IF EXISTS employees_department_id_fkey;"
    ))
    op.execute(text("""
        ALTER TABLE employees
        ADD CONSTRAINT employees_department_id_fkey
        FOREIGN KEY (department_id) REFERENCES departments(id);
    """))
