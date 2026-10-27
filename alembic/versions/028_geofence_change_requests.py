"""Add geofence_change_requests (proposed punch locations awaiting approval)

Managers propose a property's punch location (centre + radius); Super
Admin / Tenant Admin / Co Admin approve it, which writes property_geofences.
Rows are never deleted: status pending / approved / rejected / cancelled
plus reviewer, time and note keep every request and decision. A partial
unique index allows one pending request per property.

The app's init_db() create_all may already have created this table from
the model on startup; every statement is IF NOT EXISTS (constraints are
added only if missing), so this migration is safe either way and re-runs
are no-ops. Revision id kept within alembic_version.version_num VARCHAR(32).

Revision ID: 028_geofence_change_requests
Revises: 027_attendance_punch_out_loc
Create Date: 2026-10-27

"""
from alembic import op

revision = "028_geofence_change_requests"
down_revision = "027_attendance_punch_out_loc"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS geofence_change_requests (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            property_id UUID NOT NULL REFERENCES properties(id) ON DELETE CASCADE,
            requested_by UUID REFERENCES users(id) ON DELETE SET NULL,
            center_lat DOUBLE PRECISION NOT NULL,
            center_lng DOUBLE PRECISION NOT NULL,
            radius_meters INTEGER NOT NULL,
            address VARCHAR(255),
            note TEXT,
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
            IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'ck_geofence_request_status') THEN
                ALTER TABLE geofence_change_requests ADD CONSTRAINT ck_geofence_request_status
                    CHECK (status IN ('pending','approved','rejected','cancelled'));
            END IF;
            IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'ck_geofence_request_radius') THEN
                ALTER TABLE geofence_change_requests ADD CONSTRAINT ck_geofence_request_radius
                    CHECK (radius_meters BETWEEN 20 AND 2000);
            END IF;
        END $$
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_geofence_change_requests_tenant_id ON geofence_change_requests (tenant_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_geofence_change_requests_property_id ON geofence_change_requests (property_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_geofence_change_requests_requested_by ON geofence_change_requests (requested_by)")
    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_geofence_request_pending
            ON geofence_change_requests (property_id) WHERE status = 'pending'
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS geofence_change_requests")
