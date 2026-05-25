"""Add Employee Scheduling Tables

Revision ID: 001_add_scheduling_tables
Revises: 
Create Date: 2026-05-18 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '002_add_scheduling_tables'
down_revision = '001_add_chat_tables'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create EmployeeAvailability table
    op.create_table(
        'employee_availability',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('property_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('employee_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('availability_date', sa.DateTime(), nullable=False),
        sa.Column('status', sa.String(50), nullable=False),
        sa.Column('reason', sa.String(255), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.TIMESTAMP(), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['employee_id'], ['employees.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['property_id'], ['properties.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('employee_id', 'availability_date', name='uq_employee_availability_date'),
    )
    op.create_index('idx_availability_employee', 'employee_availability', ['employee_id'])
    op.create_index('idx_availability_property', 'employee_availability', ['property_id'])
    op.create_index('idx_availability_date', 'employee_availability', ['availability_date'])

    # Create WeeklySchedule table
    op.create_table(
        'weekly_schedules',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('property_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('employee_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('week_start_date', sa.DateTime(), nullable=False),
        sa.Column('week_end_date', sa.DateTime(), nullable=False),
        sa.Column('department_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('status', sa.String(50), nullable=False, server_default='draft'),
        sa.Column('assigned_by', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('assigned_at', sa.DateTime(), nullable=True),
        sa.Column('published_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.TIMESTAMP(), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['assigned_by'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['department_id'], ['departments.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['employee_id'], ['employees.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['property_id'], ['properties.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('employee_id', 'week_start_date', name='uq_employee_weekly_schedule'),
    )
    op.create_index('idx_schedule_employee', 'weekly_schedules', ['employee_id'])
    op.create_index('idx_schedule_property', 'weekly_schedules', ['property_id'])
    op.create_index('idx_schedule_week', 'weekly_schedules', ['week_start_date', 'week_end_date'])
    op.create_index('idx_schedule_status', 'weekly_schedules', ['status'])

    # Create ShiftAssignment table
    op.create_table(
        'shift_assignments',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('property_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('schedule_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('employee_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('shift_date', sa.DateTime(), nullable=False),
        sa.Column('shift_start_time', sa.String(5), nullable=False),
        sa.Column('shift_end_time', sa.String(5), nullable=False),
        sa.Column('shift_type', sa.String(50), nullable=True),
        sa.Column('status', sa.String(50), nullable=False, server_default='scheduled'),
        sa.Column('created_at', sa.TIMESTAMP(), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.TIMESTAMP(), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['employee_id'], ['employees.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['property_id'], ['properties.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['schedule_id'], ['weekly_schedules.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('idx_shift_assignment_employee', 'shift_assignments', ['employee_id'])
    op.create_index('idx_shift_assignment_schedule', 'shift_assignments', ['schedule_id'])
    op.create_index('idx_shift_assignment_date', 'shift_assignments', ['shift_date'])
    op.create_index('idx_shift_assignment_status', 'shift_assignments', ['status'])

    # Create ReplacementRequest table
    op.create_table(
        'replacement_requests',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('property_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('shift_assignment_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('original_employee_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('replacement_employee_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('request_date', sa.DateTime(), nullable=False),
        sa.Column('shift_date', sa.DateTime(), nullable=False),
        sa.Column('shift_start_time', sa.String(5), nullable=False),
        sa.Column('shift_end_time', sa.String(5), nullable=False),
        sa.Column('reason', sa.String(255), nullable=True),
        sa.Column('priority', sa.String(50), nullable=False, server_default='normal'),
        sa.Column('request_type', sa.String(50), nullable=False),
        sa.Column('status', sa.String(50), nullable=False, server_default='pending'),
        sa.Column('ai_recommended', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('created_by', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('responded_by', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('responded_at', sa.DateTime(), nullable=True),
        sa.Column('response_reason', sa.Text(), nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.TIMESTAMP(), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['original_employee_id'], ['employees.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['property_id'], ['properties.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['replacement_employee_id'], ['employees.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['responded_by'], ['employees.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['shift_assignment_id'], ['shift_assignments.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('idx_replacement_original_employee', 'replacement_requests', ['original_employee_id'])
    op.create_index('idx_replacement_employee', 'replacement_requests', ['replacement_employee_id'])
    op.create_index('idx_replacement_status', 'replacement_requests', ['status'])
    op.create_index('idx_replacement_shift_date', 'replacement_requests', ['shift_date'])
    op.create_index('idx_replacement_priority', 'replacement_requests', ['priority'])

    # Create ShiftResponse table
    op.create_table(
        'shift_responses',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('property_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('replacement_request_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('employee_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('response_type', sa.String(50), nullable=False),
        sa.Column('reason', sa.Text(), nullable=True),
        sa.Column('responded_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('created_at', sa.TIMESTAMP(), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['employee_id'], ['employees.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['property_id'], ['properties.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['replacement_request_id'], ['replacement_requests.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('replacement_request_id', 'employee_id', name='uq_shift_response'),
    )
    op.create_index('idx_shift_response_employee', 'shift_responses', ['employee_id'])
    op.create_index('idx_shift_response_request', 'shift_responses', ['replacement_request_id'])

    # Create EmployeeSkill table
    op.create_table(
        'employee_skills',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('employee_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('skill_name', sa.String(100), nullable=False),
        sa.Column('proficiency_level', sa.String(50), nullable=True),
        sa.Column('years_of_experience', sa.Integer(), nullable=True),
        sa.Column('verified', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('created_at', sa.TIMESTAMP(), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.TIMESTAMP(), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['employee_id'], ['employees.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('idx_employee_skills_employee', 'employee_skills', ['employee_id'])
    op.create_index('idx_employee_skills_skill', 'employee_skills', ['skill_name'])


def downgrade() -> None:
    op.drop_index('idx_employee_skills_skill', table_name='employee_skills')
    op.drop_index('idx_employee_skills_employee', table_name='employee_skills')
    op.drop_table('employee_skills')
    op.drop_index('idx_shift_response_request', table_name='shift_responses')
    op.drop_index('idx_shift_response_employee', table_name='shift_responses')
    op.drop_table('shift_responses')
    op.drop_index('idx_replacement_priority', table_name='replacement_requests')
    op.drop_index('idx_replacement_shift_date', table_name='replacement_requests')
    op.drop_index('idx_replacement_status', table_name='replacement_requests')
    op.drop_index('idx_replacement_employee', table_name='replacement_requests')
    op.drop_index('idx_replacement_original_employee', table_name='replacement_requests')
    op.drop_table('replacement_requests')
    op.drop_index('idx_shift_assignment_status', table_name='shift_assignments')
    op.drop_index('idx_shift_assignment_date', table_name='shift_assignments')
    op.drop_index('idx_shift_assignment_schedule', table_name='shift_assignments')
    op.drop_index('idx_shift_assignment_employee', table_name='shift_assignments')
    op.drop_table('shift_assignments')
    op.drop_index('idx_schedule_status', table_name='weekly_schedules')
    op.drop_index('idx_schedule_week', table_name='weekly_schedules')
    op.drop_index('idx_schedule_property', table_name='weekly_schedules')
    op.drop_index('idx_schedule_employee', table_name='weekly_schedules')
    op.drop_table('weekly_schedules')
    op.drop_index('idx_availability_date', table_name='employee_availability')
    op.drop_index('idx_availability_property', table_name='employee_availability')
    op.drop_index('idx_availability_employee', table_name='employee_availability')
    op.drop_table('employee_availability')
