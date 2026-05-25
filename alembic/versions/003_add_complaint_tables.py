"""Create complaint management tables

Revision ID: 002_add_complaint_tables
Revises: 001_add_scheduling_tables
Create Date: 2026-05-18 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '003_add_complaint_tables'
down_revision = '002_add_scheduling_tables'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create complaint and related tables"""
    
    # Create complaints table
    op.create_table(
        'complaints',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('property_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('created_by', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('assigned_to', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('assigned_by', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('resolved_by', postgresql.UUID(as_uuid=True), nullable=True),
        
        sa.Column('title', sa.String(255), nullable=False),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column('category', sa.String(100), nullable=False),
        sa.Column('complaint_type', sa.String(50), nullable=False),
        sa.Column('priority', sa.String(20), nullable=False, server_default='medium'),
        sa.Column('status', sa.String(50), nullable=False, server_default='open'),
        
        sa.Column('room_number', sa.String(50), nullable=True),
        sa.Column('location', sa.String(255), nullable=True),
        
        sa.Column('assigned_at', sa.DateTime(), nullable=True),
        sa.Column('resolved_at', sa.DateTime(), nullable=True),
        sa.Column('resolution_notes', sa.Text(), nullable=True),
        
        sa.Column('attachment_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('comment_count', sa.Integer(), nullable=False, server_default='0'),
        
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('deleted_at', sa.DateTime(), nullable=True),
        
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['property_id'], ['properties.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['assigned_to'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['assigned_by'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['resolved_by'], ['users.id'], ondelete='SET NULL'),
        
        sa.PrimaryKeyConstraint('id')
    )
    
    # Create indexes for complaints
    op.create_index('idx_complaint_tenant', 'complaints', ['tenant_id'])
    op.create_index('idx_complaint_property', 'complaints', ['property_id'])
    op.create_index('idx_complaint_created_by', 'complaints', ['created_by'])
    op.create_index('idx_complaint_assigned_to', 'complaints', ['assigned_to'])
    op.create_index('idx_complaint_status', 'complaints', ['status'])
    op.create_index('idx_complaint_priority', 'complaints', ['priority'])
    op.create_index('idx_complaint_category', 'complaints', ['category'])
    op.create_index('idx_complaint_type', 'complaints', ['complaint_type'])
    op.create_index('idx_complaint_created_at', 'complaints', ['created_at'])
    op.create_index('idx_complaint_resolved_at', 'complaints', ['resolved_at'])
    
    # Create complaint_comments table
    op.create_table(
        'complaint_comments',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('complaint_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=True),
        
        sa.Column('comment', sa.Text(), nullable=False),
        sa.Column('is_internal', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('attachment_count', sa.Integer(), nullable=False, server_default='0'),
        
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['complaint_id'], ['complaints.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='SET NULL'),
        
        sa.PrimaryKeyConstraint('id')
    )
    
    # Create indexes for complaint_comments
    op.create_index('idx_complaint_comment_complaint', 'complaint_comments', ['complaint_id'])
    op.create_index('idx_complaint_comment_user', 'complaint_comments', ['user_id'])
    op.create_index('idx_complaint_comment_created', 'complaint_comments', ['created_at'])
    
    # Create complaint_assignments table
    op.create_table(
        'complaint_assignments',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('complaint_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('assigned_to', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('assigned_by', postgresql.UUID(as_uuid=True), nullable=True),
        
        sa.Column('assigned_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['complaint_id'], ['complaints.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['assigned_to'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['assigned_by'], ['users.id'], ondelete='SET NULL'),
        
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('complaint_id', 'assigned_to', name='uq_complaint_assignment')
    )
    
    # Create indexes for complaint_assignments
    op.create_index('idx_assignment_complaint', 'complaint_assignments', ['complaint_id'])
    op.create_index('idx_assignment_assigned_to', 'complaint_assignments', ['assigned_to'])
    op.create_index('idx_assignment_assigned_at', 'complaint_assignments', ['assigned_at'])
    
    # Create complaint_attachments table
    op.create_table(
        'complaint_attachments',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('complaint_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('uploaded_by', postgresql.UUID(as_uuid=True), nullable=True),
        
        sa.Column('file_name', sa.String(255), nullable=False),
        sa.Column('file_path', sa.String(500), nullable=False),
        sa.Column('file_size', sa.Integer(), nullable=True),
        sa.Column('file_type', sa.String(50), nullable=True),
        
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['complaint_id'], ['complaints.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['uploaded_by'], ['users.id'], ondelete='SET NULL'),
        
        sa.PrimaryKeyConstraint('id')
    )
    
    # Create indexes for complaint_attachments
    op.create_index('idx_attachment_complaint', 'complaint_attachments', ['complaint_id'])
    op.create_index('idx_attachment_uploaded_by', 'complaint_attachments', ['uploaded_by'])
    
    # Create complaint_comment_attachments table
    op.create_table(
        'complaint_comment_attachments',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('comment_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('uploaded_by', postgresql.UUID(as_uuid=True), nullable=True),
        
        sa.Column('file_name', sa.String(255), nullable=False),
        sa.Column('file_path', sa.String(500), nullable=False),
        sa.Column('file_size', sa.Integer(), nullable=True),
        sa.Column('file_type', sa.String(50), nullable=True),
        
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['comment_id'], ['complaint_comments.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['uploaded_by'], ['users.id'], ondelete='SET NULL'),
        
        sa.PrimaryKeyConstraint('id')
    )
    
    # Create indexes for complaint_comment_attachments
    op.create_index('idx_comment_attachment_comment', 'complaint_comment_attachments', ['comment_id'])
    op.create_index('idx_comment_attachment_uploaded_by', 'complaint_comment_attachments', ['uploaded_by'])


def downgrade() -> None:
    """Drop complaint and related tables"""
    
    # Drop indexes
    op.drop_index('idx_comment_attachment_uploaded_by', 'complaint_comment_attachments')
    op.drop_index('idx_comment_attachment_comment', 'complaint_comment_attachments')
    op.drop_index('idx_attachment_uploaded_by', 'complaint_attachments')
    op.drop_index('idx_attachment_complaint', 'complaint_attachments')
    op.drop_index('idx_assignment_assigned_at', 'complaint_assignments')
    op.drop_index('idx_assignment_assigned_to', 'complaint_assignments')
    op.drop_index('idx_assignment_complaint', 'complaint_assignments')
    op.drop_index('idx_complaint_comment_created', 'complaint_comments')
    op.drop_index('idx_complaint_comment_user', 'complaint_comments')
    op.drop_index('idx_complaint_comment_complaint', 'complaint_comments')
    op.drop_index('idx_complaint_resolved_at', 'complaints')
    op.drop_index('idx_complaint_created_at', 'complaints')
    op.drop_index('idx_complaint_type', 'complaints')
    op.drop_index('idx_complaint_category', 'complaints')
    op.drop_index('idx_complaint_priority', 'complaints')
    op.drop_index('idx_complaint_status', 'complaints')
    op.drop_index('idx_complaint_assigned_to', 'complaints')
    op.drop_index('idx_complaint_created_by', 'complaints')
    op.drop_index('idx_complaint_property', 'complaints')
    op.drop_index('idx_complaint_tenant', 'complaints')
    
    # Drop tables
    op.drop_table('complaint_comment_attachments')
    op.drop_table('complaint_attachments')
    op.drop_table('complaint_assignments')
    op.drop_table('complaint_comments')
    op.drop_table('complaints')
