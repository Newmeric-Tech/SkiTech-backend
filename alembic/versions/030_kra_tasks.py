"""Add kra_definitions, kra_assignments, kra_occurrences (assigned KRA tasks)

Managers and admins build tasks with a frequency for a property and assign
them to users; each assignee gets one occurrence per period to mark completed
or delayed. The older self-submitted KRA tables are not touched.

The app's init_db() create_all may already have created these tables from the
models on startup; every statement is IF NOT EXISTS (constraints are added only
if missing), so this migration is safe either way and re-runs are no-ops.
Revision id kept within alembic_version.version_num VARCHAR(32).

Revision ID: 030_kra_tasks
Revises: 029_attendance_corrections
Create Date: 2026-10-30

"""
from alembic import op

revision = "030_kra_tasks"
down_revision = "029_attendance_corrections"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS kra_definitions (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            property_id UUID NOT NULL REFERENCES properties(id) ON DELETE CASCADE,
            title VARCHAR(200) NOT NULL,
            description TEXT,
            frequency VARCHAR(20) NOT NULL,
            value_label VARCHAR(100),
            created_by UUID REFERENCES users(id) ON DELETE SET NULL,
            is_active BOOLEAN NOT NULL DEFAULT true,
            created_at TIMESTAMP NOT NULL DEFAULT now(),
            updated_at TIMESTAMP NOT NULL DEFAULT now(),
            deleted_at TIMESTAMP
        )
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS kra_assignments (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            property_id UUID NOT NULL REFERENCES properties(id) ON DELETE CASCADE,
            definition_id UUID NOT NULL REFERENCES kra_definitions(id) ON DELETE CASCADE,
            assignee_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            assigned_by UUID REFERENCES users(id) ON DELETE SET NULL,
            start_date DATE NOT NULL,
            is_active BOOLEAN NOT NULL DEFAULT true,
            ended_at TIMESTAMP
        )
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS kra_occurrences (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            property_id UUID NOT NULL REFERENCES properties(id) ON DELETE CASCADE,
            assignment_id UUID NOT NULL REFERENCES kra_assignments(id) ON DELETE CASCADE,
            definition_id UUID NOT NULL REFERENCES kra_definitions(id) ON DELETE CASCADE,
            assignee_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            period_start DATE NOT NULL,
            period_end DATE NOT NULL,
            status VARCHAR(20) NOT NULL DEFAULT 'pending',
            was_delayed BOOLEAN NOT NULL DEFAULT false,
            delayed_at TIMESTAMP,
            delay_reason TEXT,
            completed_at TIMESTAMP,
            completion_note TEXT,
            completion_value NUMERIC(14, 2),
            created_at TIMESTAMP NOT NULL DEFAULT now(),
            updated_at TIMESTAMP NOT NULL DEFAULT now()
        )
    """)
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'ck_kra_definition_frequency') THEN
                ALTER TABLE kra_definitions ADD CONSTRAINT ck_kra_definition_frequency
                    CHECK (frequency IN ('daily','weekly','monthly','quarterly'));
            END IF;
            IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'ck_kra_occurrence_status') THEN
                ALTER TABLE kra_occurrences ADD CONSTRAINT ck_kra_occurrence_status
                    CHECK (status IN ('pending','delayed','completed'));
            END IF;
            IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'uq_kra_occurrence_period') THEN
                ALTER TABLE kra_occurrences ADD CONSTRAINT uq_kra_occurrence_period
                    UNIQUE (assignment_id, period_start);
            END IF;
        END $$
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_kra_definitions_tenant_id ON kra_definitions (tenant_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_kra_definitions_property_id ON kra_definitions (property_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_kra_assignments_tenant_id ON kra_assignments (tenant_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_kra_assignments_property_id ON kra_assignments (property_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_kra_assignments_definition_id ON kra_assignments (definition_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_kra_assignments_assignee_id ON kra_assignments (assignee_id)")
    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_kra_assignment_active
            ON kra_assignments (definition_id, assignee_id) WHERE is_active
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_kra_occurrences_tenant_id ON kra_occurrences (tenant_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_kra_occurrences_property_id ON kra_occurrences (property_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_kra_occurrences_definition_id ON kra_occurrences (definition_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_kra_occurrences_assignee_id ON kra_occurrences (assignee_id)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS kra_occurrences")
    op.execute("DROP TABLE IF EXISTS kra_assignments")
    op.execute("DROP TABLE IF EXISTS kra_definitions")
