"""Add attendance_correction_requests (claimed punch-out for auto_closed records)

A person whose open shift was auto-closed (no punch-out, hours NULL)
claims the time they left, with a reason; a Manager of the property (for
staff) or Super Admin / Tenant Admin / Co Admin approve it, which
completes the attendance record with hours from the approved time. Rows
are never deleted: status pending / approved / rejected / cancelled plus
reviewer, time and note keep every request and decision. A partial unique
index allows one pending request per attendance record.

The app's init_db() create_all may already have created this table from
the model on startup; every statement is IF NOT EXISTS (constraints are
added only if missing), so this migration is safe either way and re-runs
are no-ops. Revision id kept within alembic_version.version_num VARCHAR(32).

Revision ID: 029_attendance_corrections
Revises: 028_geofence_change_requests
Create Date: 2026-10-27

"""
from alembic import op

revision = "029_attendance_corrections"
down_revision = "028_geofence_change_requests"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS attendance_correction_requests (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            property_id UUID NOT NULL REFERENCES properties(id) ON DELETE CASCADE,
            attendance_id UUID NOT NULL REFERENCES attendance_records(id) ON DELETE RESTRICT,
            requested_by UUID REFERENCES users(id) ON DELETE SET NULL,
            requester_role VARCHAR(50) NOT NULL,
            claimed_punch_out_time TIMESTAMPTZ NOT NULL,
            reason TEXT NOT NULL,
            status VARCHAR(20) NOT NULL DEFAULT 'pending',
            reviewed_by UUID REFERENCES users(id) ON DELETE SET NULL,
            reviewed_at TIMESTAMPTZ,
            review_note TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'ck_attendance_correction_status') THEN
                ALTER TABLE attendance_correction_requests ADD CONSTRAINT ck_attendance_correction_status
                    CHECK (status IN ('pending','approved','rejected','cancelled'));
            END IF;
        END $$
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_attendance_correction_requests_tenant_id "
               "ON attendance_correction_requests (tenant_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_attendance_correction_requests_property_id "
               "ON attendance_correction_requests (property_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_attendance_correction_requests_attendance_id "
               "ON attendance_correction_requests (attendance_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_attendance_correction_requests_requested_by "
               "ON attendance_correction_requests (requested_by)")
    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_attendance_correction_pending
            ON attendance_correction_requests (attendance_id) WHERE status = 'pending'
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS attendance_correction_requests")
