"""Add employee ranking system tables

Revision ID: 006_add_ranking_tables
Revises: 005_fix_media_type_varchar
Create Date: 2026-06-01

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '006_add_ranking_tables'
down_revision = '005_fix_media_type_varchar'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ranking_criteria_config
    op.create_table(
        'ranking_criteria_config',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('property_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('criterion_name', sa.String(100), nullable=False),
        sa.Column('weightage', sa.Float(), nullable=False),
        sa.Column('max_points', sa.Float(), nullable=False, server_default='100'),
        sa.Column('deduction_rules', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('details', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.ForeignKeyConstraint(['property_id'], ['properties.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('property_id', 'criterion_name', name='uq_property_criterion'),
        sa.CheckConstraint('weightage > 0 AND weightage <= 100', name='check_weightage'),
    )
    op.create_index('idx_criteria_tenant_id', 'ranking_criteria_config', ['tenant_id'])
    op.create_index('idx_criteria_property_id', 'ranking_criteria_config', ['property_id'])

    # employee_ranking_scores
    op.create_table(
        'employee_ranking_scores',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('property_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('employee_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('criterion_name', sa.String(100), nullable=False),
        sa.Column('weightage', sa.Float(), nullable=False),
        sa.Column('max_points', sa.Float(), nullable=False, server_default='100'),
        sa.Column('raw_points', sa.Float(), nullable=False),
        sa.Column('deductions', sa.Float(), nullable=False, server_default='0'),
        sa.Column('final_points', sa.Float(), nullable=False),
        sa.Column('deduction_details', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('period_start', sa.DateTime(), nullable=False),
        sa.Column('period_end', sa.DateTime(), nullable=False),
        sa.Column('calculated_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('evidence', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('deleted_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.ForeignKeyConstraint(['employee_id'], ['employees.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['property_id'], ['properties.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('employee_id', 'criterion_name', 'period_start', 'period_end',
                            name='uq_employee_criterion_period'),
        sa.CheckConstraint('raw_points >= 0 AND raw_points <= max_points', name='check_raw_points'),
        sa.CheckConstraint('final_points >= 0', name='check_final_points'),
    )
    op.create_index('idx_scores_employee_id', 'employee_ranking_scores', ['employee_id'])
    op.create_index('idx_scores_property_id', 'employee_ranking_scores', ['property_id'])
    op.create_index('idx_scores_criterion', 'employee_ranking_scores', ['criterion_name'])
    op.create_index('idx_scores_period', 'employee_ranking_scores', ['period_start', 'period_end'])

    # employee_rankings
    op.create_table(
        'employee_rankings',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('property_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('employee_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('period_start', sa.DateTime(), nullable=False),
        sa.Column('period_end', sa.DateTime(), nullable=False),
        sa.Column('ranking_type', sa.String(50), nullable=False),
        sa.Column('overall_score', sa.Float(), nullable=False),
        sa.Column('rank', sa.Integer(), nullable=False),
        sa.Column('total_active_employees', sa.Integer(), nullable=False),
        sa.Column('performance_status', sa.String(50), nullable=False, server_default='consistent'),
        sa.Column('scores_breakdown', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('previous_overall_score', sa.Float(), nullable=True),
        sa.Column('score_change', sa.Float(), nullable=True),
        sa.Column('status', sa.String(50), nullable=False, server_default='active'),
        sa.Column('calculated_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.Column('recalculated_at', sa.DateTime(), nullable=True),
        sa.Column('deleted_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.ForeignKeyConstraint(['employee_id'], ['employees.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['property_id'], ['properties.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('employee_id', 'period_start', 'period_end', 'ranking_type',
                            name='uq_employee_period_ranking'),
        sa.CheckConstraint('overall_score >= 0 AND overall_score <= 100', name='check_overall_score'),
        sa.CheckConstraint('rank >= 1', name='check_rank'),
    )
    op.create_index('idx_ranking_employee_id', 'employee_rankings', ['employee_id'])
    op.create_index('idx_ranking_property_id', 'employee_rankings', ['property_id'])
    op.create_index('idx_ranking_overall_score', 'employee_rankings', ['overall_score'])
    op.create_index('idx_ranking_rank', 'employee_rankings', ['rank'])
    op.create_index('idx_ranking_period', 'employee_rankings', ['period_start', 'period_end'])
    op.create_index('idx_ranking_performance_status', 'employee_rankings', ['performance_status'])

    # ranking_audit_logs
    op.create_table(
        'ranking_audit_logs',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('property_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('employee_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('action', sa.String(50), nullable=False),
        sa.Column('criterion_name', sa.String(100), nullable=True),
        sa.Column('old_value', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('new_value', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('changed_by', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.ForeignKeyConstraint(['changed_by'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['employee_id'], ['employees.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['property_id'], ['properties.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('idx_audit_employee_id', 'ranking_audit_logs', ['employee_id'])
    op.create_index('idx_audit_property_id', 'ranking_audit_logs', ['property_id'])
    op.create_index('idx_audit_action', 'ranking_audit_logs', ['action'])
    op.create_index('idx_audit_created_at', 'ranking_audit_logs', ['created_at'])

    # ranking_insights
    op.create_table(
        'ranking_insights',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('property_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('employee_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('period_start', sa.DateTime(), nullable=False),
        sa.Column('period_end', sa.DateTime(), nullable=False),
        sa.Column('insight_type', sa.String(100), nullable=False),
        sa.Column('title', sa.String(255), nullable=False),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column('metric_name', sa.String(100), nullable=True),
        sa.Column('metric_value', sa.Float(), nullable=True),
        sa.Column('priority', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('is_positive', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.ForeignKeyConstraint(['employee_id'], ['employees.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['property_id'], ['properties.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('idx_insight_employee_id', 'ranking_insights', ['employee_id'])
    op.create_index('idx_insight_property_id', 'ranking_insights', ['property_id'])
    op.create_index('idx_insight_type', 'ranking_insights', ['insight_type'])
    op.create_index('idx_insight_priority', 'ranking_insights', ['priority'])


def downgrade() -> None:
    op.drop_table('ranking_insights')
    op.drop_table('ranking_audit_logs')
    op.drop_table('employee_rankings')
    op.drop_table('employee_ranking_scores')
    op.drop_table('ranking_criteria_config')
