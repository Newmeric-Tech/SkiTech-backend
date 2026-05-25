"""Create document management tables

Revision ID: 003_add_document_management_tables
Revises: 002_add_complaint_tables
Create Date: 2026-05-20 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '004_add_document_mgmt_tables'
down_revision = '003_add_complaint_tables'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create documents table
    op.create_table(
        'documents',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('property_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('title', sa.String(255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('category', sa.String(100), nullable=False),
        sa.Column('department', sa.String(100), nullable=True),
        sa.Column('file_name', sa.String(500), nullable=False),
        sa.Column('file_path', sa.String(1000), nullable=False),
        sa.Column('file_size', sa.Integer(), nullable=True),
        sa.Column('file_type', sa.String(50), nullable=True),
        sa.Column('file_extension', sa.String(20), nullable=True),
        sa.Column('tags', sa.String(500), nullable=True),
        sa.Column('access_scope', sa.String(50), nullable=False, server_default='organization_wide'),
        sa.Column('uploaded_by', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('owner_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('assigned_compliance_reviewer', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('status', sa.String(50), nullable=False, server_default='pending_review'),
        sa.Column('approval_status', sa.String(50), nullable=False, server_default='pending'),
        sa.Column('is_confidential', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('retention_period', sa.Integer(), nullable=True),
        sa.Column('expiry_date', sa.DateTime(), nullable=True),
        sa.Column('requires_signature', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.Column('last_modified', sa.DateTime(), nullable=True),
        sa.Column('deleted_at', sa.DateTime(), nullable=True),
        sa.Column('deleted_by', postgresql.UUID(as_uuid=True), nullable=True),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['property_id'], ['properties.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['uploaded_by'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['owner_id'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['assigned_compliance_reviewer'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_document_tenant', 'documents', ['tenant_id'])
    op.create_index('idx_document_property', 'documents', ['property_id'])
    op.create_index('idx_document_category', 'documents', ['category'])
    op.create_index('idx_document_status', 'documents', ['status'])
    op.create_index('idx_document_uploaded_by', 'documents', ['uploaded_by'])
    op.create_index('idx_document_created_at', 'documents', ['created_at'])
    op.create_index('idx_document_access_scope', 'documents', ['access_scope'])

    # Create document_versions table
    op.create_table(
        'document_versions',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('document_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('version_number', sa.Integer(), nullable=False),
        sa.Column('file_path', sa.String(1000), nullable=False),
        sa.Column('file_size', sa.Integer(), nullable=True),
        sa.Column('uploaded_by', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('change_description', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['document_id'], ['documents.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['uploaded_by'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_document_version_document', 'document_versions', ['document_id'])
    op.create_index('idx_document_version_created', 'document_versions', ['created_at'])

    # Create document_reviews table
    op.create_table(
        'document_reviews',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('document_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('reviewer_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('reviewer_role', sa.String(100), nullable=True),
        sa.Column('review_status', sa.String(50), nullable=False, server_default='pending'),
        sa.Column('review_priority', sa.String(50), nullable=False, server_default='medium'),
        sa.Column('comments', sa.Text(), nullable=True),
        sa.Column('rejection_reason', sa.Text(), nullable=True),
        sa.Column('assigned_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column('review_started_at', sa.DateTime(), nullable=True),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.Column('requires_additional_info', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('additional_info_request', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['document_id'], ['documents.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['reviewer_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_document_review_document', 'document_reviews', ['document_id'])
    op.create_index('idx_document_review_reviewer', 'document_reviews', ['reviewer_id'])
    op.create_index('idx_document_review_status', 'document_reviews', ['review_status'])
    op.create_index('idx_document_review_assigned_at', 'document_reviews', ['assigned_at'])

    # Create document_approvals table
    op.create_table(
        'document_approvals',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('document_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('approver_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('approver_role', sa.String(100), nullable=True),
        sa.Column('approval_status', sa.String(50), nullable=False, server_default='pending'),
        sa.Column('approval_reason', sa.Text(), nullable=True),
        sa.Column('conditions', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('assigned_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column('decided_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['document_id'], ['documents.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['approver_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_document_approval_document', 'document_approvals', ['document_id'])
    op.create_index('idx_document_approval_approver', 'document_approvals', ['approver_id'])
    op.create_index('idx_document_approval_status', 'document_approvals', ['approval_status'])

    # Create document_shares table
    op.create_table(
        'document_shares',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('document_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('shared_with_user_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('shared_with_department_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('shared_by', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('permission_level', sa.String(50), nullable=False, server_default='view'),
        sa.Column('shared_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column('expires_at', sa.DateTime(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['document_id'], ['documents.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['shared_with_user_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['shared_with_department_id'], ['departments.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['shared_by'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_document_share_document', 'document_shares', ['document_id'])
    op.create_index('idx_document_share_user', 'document_shares', ['shared_with_user_id'])
    op.create_index('idx_document_share_department', 'document_shares', ['shared_with_department_id'])
    op.create_index('idx_document_share_shared_at', 'document_shares', ['shared_at'])

    # Create document_signatures table
    op.create_table(
        'document_signatures',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('document_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('signer_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('signer_name', sa.String(255), nullable=False),
        sa.Column('signer_email', sa.String(255), nullable=False),
        sa.Column('signer_role', sa.String(100), nullable=True),
        sa.Column('signature_status', sa.String(50), nullable=False, server_default='pending'),
        sa.Column('signature_image', sa.Text(), nullable=True),
        sa.Column('signature_request_sent_at', sa.DateTime(), nullable=True),
        sa.Column('signed_at', sa.DateTime(), nullable=True),
        sa.Column('decline_reason', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['document_id'], ['documents.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['signer_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_document_signature_document', 'document_signatures', ['document_id'])
    op.create_index('idx_document_signature_signer', 'document_signatures', ['signer_id'])
    op.create_index('idx_document_signature_status', 'document_signatures', ['signature_status'])

    # Create document_activity_logs table
    op.create_table(
        'document_activity_logs',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('document_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('action', sa.String(100), nullable=False),
        sa.Column('activity_type', sa.String(50), nullable=False),
        sa.Column('performed_by', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('performed_by_name', sa.String(255), nullable=True),
        sa.Column('performed_by_role', sa.String(100), nullable=True),
        sa.Column('details', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('ip_address', sa.String(50), nullable=True),
        sa.Column('user_agent', sa.String(500), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['document_id'], ['documents.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['performed_by'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_document_activity_document', 'document_activity_logs', ['document_id'])
    op.create_index('idx_document_activity_performed_by', 'document_activity_logs', ['performed_by'])
    op.create_index('idx_document_activity_action', 'document_activity_logs', ['action'])
    op.create_index('idx_document_activity_created_at', 'document_activity_logs', ['created_at'])

    # Create document_templates table
    op.create_table(
        'document_templates',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('category', sa.String(100), nullable=False),
        sa.Column('template_content', sa.Text(), nullable=False),
        sa.Column('required_fields', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('usage_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.Column('deleted_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_document_template_tenant', 'document_templates', ['tenant_id'])
    op.create_index('idx_document_template_category', 'document_templates', ['category'])


def downgrade() -> None:
    op.drop_index('idx_document_template_category', table_name='document_templates')
    op.drop_index('idx_document_template_tenant', table_name='document_templates')
    op.drop_table('document_templates')
    
    op.drop_index('idx_document_activity_created_at', table_name='document_activity_logs')
    op.drop_index('idx_document_activity_action', table_name='document_activity_logs')
    op.drop_index('idx_document_activity_performed_by', table_name='document_activity_logs')
    op.drop_index('idx_document_activity_document', table_name='document_activity_logs')
    op.drop_table('document_activity_logs')
    
    op.drop_index('idx_document_signature_status', table_name='document_signatures')
    op.drop_index('idx_document_signature_signer', table_name='document_signatures')
    op.drop_index('idx_document_signature_document', table_name='document_signatures')
    op.drop_table('document_signatures')
    
    op.drop_index('idx_document_share_shared_at', table_name='document_shares')
    op.drop_index('idx_document_share_department', table_name='document_shares')
    op.drop_index('idx_document_share_user', table_name='document_shares')
    op.drop_index('idx_document_share_document', table_name='document_shares')
    op.drop_table('document_shares')
    
    op.drop_index('idx_document_approval_status', table_name='document_approvals')
    op.drop_index('idx_document_approval_approver', table_name='document_approvals')
    op.drop_index('idx_document_approval_document', table_name='document_approvals')
    op.drop_table('document_approvals')
    
    op.drop_index('idx_document_review_assigned_at', table_name='document_reviews')
    op.drop_index('idx_document_review_status', table_name='document_reviews')
    op.drop_index('idx_document_review_reviewer', table_name='document_reviews')
    op.drop_index('idx_document_review_document', table_name='document_reviews')
    op.drop_table('document_reviews')
    
    op.drop_index('idx_document_version_created', table_name='document_versions')
    op.drop_index('idx_document_version_document', table_name='document_versions')
    op.drop_table('document_versions')
    
    op.drop_index('idx_document_access_scope', table_name='documents')
    op.drop_index('idx_document_created_at', table_name='documents')
    op.drop_index('idx_document_uploaded_by', table_name='documents')
    op.drop_index('idx_document_status', table_name='documents')
    op.drop_index('idx_document_category', table_name='documents')
    op.drop_index('idx_document_property', table_name='documents')
    op.drop_index('idx_document_tenant', table_name='documents')
    op.drop_table('documents')
