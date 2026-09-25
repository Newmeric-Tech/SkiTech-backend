"""Drop 8 orphaned tables found by the schema-drift audit

weekly_reports, daily_reports, monthly_reports, guest_requests,
tenant_features, location_anomalies, task_assignments, location_logs have
no SQLAlchemy model and zero references anywhere in this codebase
(confirmed via full-repo search) — same "predates Alembic, never
formalized" origin as everything else this audit found, except these were
simply abandoned rather than kept in use. Row counts were all small
(0-20) and checked before this migration was written.

tasks (216 rows, also orphaned/model-less) is deliberately NOT included —
it has real historical data and needs its own archive-vs-drop decision,
not a blanket cleanup.

Dependency note: tasks.guest_request_id has a live FK into guest_requests
(ON DELETE SET NULL). That FK is dropped first so guest_requests can be
dropped; tasks itself and its guest_request_id column are untouched, they
just lose that constraint. location_anomalies.log_id references
location_logs, so it's dropped before location_logs.

downgrade() recreates all 8 tables from DDL generated via SQLAlchemy
reflection against the live DB immediately before this migration was
written, so column types/defaults/constraints/indexes are exact, not
hand-typed.

Revision ID: 024_drop_orphaned_tables
Revises: 023_fix_emp_dept_fk_ondelete
Create Date: 2026-09-25

"""
from alembic import op
from sqlalchemy import text

revision = "024_drop_orphaned_tables"
down_revision = "023_fix_emp_dept_fk_ondelete"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(text(
        "ALTER TABLE tasks DROP CONSTRAINT IF EXISTS tasks_guest_request_id_fkey;"
    ))

    op.execute(text("DROP TABLE IF EXISTS location_anomalies;"))
    op.execute(text("DROP TABLE IF EXISTS guest_requests;"))
    op.execute(text("DROP TABLE IF EXISTS location_logs;"))
    op.execute(text("DROP TABLE IF EXISTS weekly_reports;"))
    op.execute(text("DROP TABLE IF EXISTS daily_reports;"))
    op.execute(text("DROP TABLE IF EXISTS monthly_reports;"))
    op.execute(text("DROP TABLE IF EXISTS tenant_features;"))
    op.execute(text("DROP TABLE IF EXISTS task_assignments;"))


def downgrade() -> None:
    op.execute(text("""
        CREATE TABLE location_logs (
            id UUID DEFAULT gen_random_uuid() NOT NULL,
            user_id UUID NOT NULL,
            property_id UUID NOT NULL,
            tenant_id UUID NOT NULL,
            event_type VARCHAR(20) NOT NULL,
            latitude DOUBLE PRECISION NOT NULL,
            longitude DOUBLE PRECISION NOT NULL,
            accuracy_meters DOUBLE PRECISION,
            altitude_meters DOUBLE PRECISION,
            recorded_at TIMESTAMP WITH TIME ZONE NOT NULL,
            server_received_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
            ip_address INET,
            device_id VARCHAR(128),
            device_platform VARCHAR(32),
            app_version VARCHAR(20),
            is_mock_suspected BOOLEAN DEFAULT false,
            geofence_status VARCHAR(10) DEFAULT 'unknown',
            CONSTRAINT location_logs_pkey PRIMARY KEY (id),
            CONSTRAINT location_logs_property_id_fkey FOREIGN KEY(property_id) REFERENCES properties (id),
            CONSTRAINT location_logs_tenant_id_fkey FOREIGN KEY(tenant_id) REFERENCES tenants (id) ON DELETE CASCADE,
            CONSTRAINT location_logs_user_id_fkey FOREIGN KEY(user_id) REFERENCES users (id)
        );
        CREATE INDEX idx_loc_logs_tenant ON location_logs (tenant_id);
    """))

    op.execute(text("""
        CREATE TABLE location_anomalies (
            id UUID DEFAULT gen_random_uuid() NOT NULL,
            user_id UUID,
            tenant_id UUID NOT NULL,
            log_id UUID,
            anomaly_type VARCHAR(30),
            distance_from_property_meters INTEGER,
            detected_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
            reviewed_by UUID,
            resolved BOOLEAN DEFAULT false,
            notes TEXT,
            CONSTRAINT location_anomalies_pkey PRIMARY KEY (id),
            CONSTRAINT location_anomalies_log_id_fkey FOREIGN KEY(log_id) REFERENCES location_logs (id),
            CONSTRAINT location_anomalies_reviewed_by_fkey FOREIGN KEY(reviewed_by) REFERENCES users (id),
            CONSTRAINT location_anomalies_tenant_id_fkey FOREIGN KEY(tenant_id) REFERENCES tenants (id) ON DELETE CASCADE,
            CONSTRAINT location_anomalies_user_id_fkey FOREIGN KEY(user_id) REFERENCES users (id)
        );
        CREATE INDEX idx_anomalies_tenant ON location_anomalies (tenant_id);
    """))

    op.execute(text("""
        CREATE TABLE guest_requests (
            tenant_id UUID NOT NULL,
            property_id UUID NOT NULL,
            reservation_id UUID NOT NULL,
            guest_name VARCHAR(255) NOT NULL,
            category VARCHAR(100) NOT NULL,
            message TEXT NOT NULL,
            priority VARCHAR(20) NOT NULL,
            status VARCHAR(50) NOT NULL,
            assigned_department_id UUID,
            assigned_employee_id UUID,
            expected_completion_time TIMESTAMP WITHOUT TIME ZONE,
            completed_at TIMESTAMP WITHOUT TIME ZONE,
            is_demo BOOLEAN DEFAULT true NOT NULL,
            id UUID NOT NULL,
            created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT now() NOT NULL,
            updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT now() NOT NULL,
            CONSTRAINT guest_requests_pkey PRIMARY KEY (id),
            CONSTRAINT guest_requests_assigned_department_id_fkey FOREIGN KEY(assigned_department_id) REFERENCES departments (id) ON DELETE SET NULL,
            CONSTRAINT guest_requests_assigned_employee_id_fkey FOREIGN KEY(assigned_employee_id) REFERENCES employees (id) ON DELETE SET NULL,
            CONSTRAINT guest_requests_property_id_fkey FOREIGN KEY(property_id) REFERENCES properties (id) ON DELETE CASCADE,
            CONSTRAINT guest_requests_reservation_id_fkey FOREIGN KEY(reservation_id) REFERENCES bookings (id) ON DELETE CASCADE,
            CONSTRAINT guest_requests_tenant_id_fkey FOREIGN KEY(tenant_id) REFERENCES tenants (id) ON DELETE CASCADE
        );
        CREATE INDEX ix_guest_requests_priority ON guest_requests (priority);
        CREATE INDEX ix_guest_requests_property_id ON guest_requests (property_id);
        CREATE INDEX ix_guest_requests_category ON guest_requests (category);
        CREATE INDEX ix_guest_requests_status ON guest_requests (status);
        CREATE INDEX ix_guest_requests_reservation_id ON guest_requests (reservation_id);
        CREATE INDEX ix_guest_requests_tenant_id ON guest_requests (tenant_id);
    """))

    op.execute(text("""
        ALTER TABLE tasks
        ADD CONSTRAINT tasks_guest_request_id_fkey
        FOREIGN KEY (guest_request_id) REFERENCES guest_requests(id) ON DELETE SET NULL;
    """))

    op.execute(text("""
        CREATE TABLE weekly_reports (
            id UUID NOT NULL,
            property_id UUID NOT NULL,
            tenant_id UUID NOT NULL,
            week_start_date DATE NOT NULL,
            week_end_date DATE NOT NULL,
            total_revenue NUMERIC(14, 2),
            kra_compliance_percentage NUMERIC(5, 2),
            created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT now() NOT NULL,
            updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT now() NOT NULL,
            CONSTRAINT weekly_reports_pkey PRIMARY KEY (id),
            CONSTRAINT weekly_reports_property_id_fkey FOREIGN KEY(property_id) REFERENCES properties (id) ON DELETE CASCADE,
            CONSTRAINT weekly_reports_tenant_id_fkey FOREIGN KEY(tenant_id) REFERENCES tenants (id) ON DELETE CASCADE,
            CONSTRAINT uq_weekly_report_property_week UNIQUE (property_id, week_start_date)
        );
        CREATE INDEX idx_weekly_reports_property_id ON weekly_reports (property_id);
        CREATE INDEX idx_weekly_reports_tenant_id ON weekly_reports (tenant_id);
    """))

    op.execute(text("""
        CREATE TABLE daily_reports (
            id UUID NOT NULL,
            property_id UUID NOT NULL,
            tenant_id UUID NOT NULL,
            date DATE NOT NULL,
            total_checkins INTEGER DEFAULT 0 NOT NULL,
            total_checkouts INTEGER DEFAULT 0 NOT NULL,
            total_complaints INTEGER DEFAULT 0 NOT NULL,
            total_revenue NUMERIC(14, 2),
            kra_compliance_percentage NUMERIC(5, 2),
            created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT now() NOT NULL,
            updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT now() NOT NULL,
            CONSTRAINT daily_reports_pkey PRIMARY KEY (id),
            CONSTRAINT daily_reports_property_id_fkey FOREIGN KEY(property_id) REFERENCES properties (id) ON DELETE CASCADE,
            CONSTRAINT daily_reports_tenant_id_fkey FOREIGN KEY(tenant_id) REFERENCES tenants (id) ON DELETE CASCADE,
            CONSTRAINT uq_daily_report_property_date UNIQUE (property_id, date)
        );
        CREATE INDEX idx_daily_reports_property_id ON daily_reports (property_id);
        CREATE INDEX idx_daily_reports_tenant_id ON daily_reports (tenant_id);
    """))

    op.execute(text("""
        CREATE TABLE monthly_reports (
            id UUID NOT NULL,
            property_id UUID NOT NULL,
            tenant_id UUID NOT NULL,
            month INTEGER NOT NULL,
            year INTEGER NOT NULL,
            total_revenue NUMERIC(14, 2),
            kra_compliance_percentage NUMERIC(5, 2),
            created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT now() NOT NULL,
            updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT now() NOT NULL,
            CONSTRAINT monthly_reports_pkey PRIMARY KEY (id),
            CONSTRAINT monthly_reports_property_id_fkey FOREIGN KEY(property_id) REFERENCES properties (id) ON DELETE CASCADE,
            CONSTRAINT monthly_reports_tenant_id_fkey FOREIGN KEY(tenant_id) REFERENCES tenants (id) ON DELETE CASCADE,
            CONSTRAINT uq_monthly_report_property_month_year UNIQUE (property_id, month, year)
        );
        CREATE INDEX idx_monthly_reports_tenant_id ON monthly_reports (tenant_id);
        CREATE INDEX idx_monthly_reports_property_id ON monthly_reports (property_id);
    """))

    op.execute(text("""
        CREATE TABLE tenant_features (
            tenant_id UUID NOT NULL,
            feature_name VARCHAR(100) NOT NULL,
            is_enabled BOOLEAN DEFAULT true NOT NULL,
            id UUID DEFAULT gen_random_uuid() NOT NULL,
            created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT now() NOT NULL,
            updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT now() NOT NULL,
            CONSTRAINT tenant_features_pkey PRIMARY KEY (id)
        );
    """))

    op.execute(text("""
        CREATE TABLE task_assignments (
            id UUID DEFAULT gen_random_uuid() NOT NULL,
            tenant_id UUID NOT NULL,
            property_id UUID NOT NULL,
            task_id UUID NOT NULL,
            assigned_by UUID NOT NULL,
            assigned_by_name VARCHAR(255) NOT NULL,
            assigned_to UUID NOT NULL,
            assigned_to_name VARCHAR(255) NOT NULL,
            status VARCHAR(20) DEFAULT 'pending' NOT NULL,
            submitted_at TIMESTAMP WITH TIME ZONE,
            reviewed_by UUID,
            reviewed_at TIMESTAMP WITH TIME ZONE,
            rejection_reason TEXT,
            due_date TIMESTAMP WITH TIME ZONE,
            notes TEXT,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
            CONSTRAINT task_assignments_pkey PRIMARY KEY (id),
            CONSTRAINT task_assignments_assigned_by_fkey FOREIGN KEY(assigned_by) REFERENCES users (id) ON DELETE RESTRICT,
            CONSTRAINT task_assignments_assigned_to_fkey FOREIGN KEY(assigned_to) REFERENCES employees (id) ON DELETE RESTRICT,
            CONSTRAINT task_assignments_property_id_fkey FOREIGN KEY(property_id) REFERENCES properties (id) ON DELETE CASCADE,
            CONSTRAINT task_assignments_reviewed_by_fkey FOREIGN KEY(reviewed_by) REFERENCES users (id),
            CONSTRAINT task_assignments_task_id_fkey FOREIGN KEY(task_id) REFERENCES sop_items (id) ON DELETE CASCADE,
            CONSTRAINT task_assignments_tenant_id_fkey FOREIGN KEY(tenant_id) REFERENCES tenants (id) ON DELETE CASCADE
        );
        CREATE INDEX idx_task_assignments_assigned_to ON task_assignments (assigned_to);
        CREATE INDEX idx_task_assignments_tenant_id ON task_assignments (tenant_id);
        CREATE INDEX idx_task_assignments_task_id ON task_assignments (task_id);
        CREATE INDEX idx_task_assignments_assigned_by ON task_assignments (assigned_by);
    """))
