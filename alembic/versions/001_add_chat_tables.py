"""Add chat system tables

Revision ID: 001_add_chat_tables
Revises:
Create Date: 2026-05-17

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '001_add_chat_tables'
down_revision = '81aac769860e'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Check if tables already exist (created by init_db before Alembic was wired in)
    from sqlalchemy import inspect
    bind = op.get_bind()
    inspector = inspect(bind)
    existing = set(inspector.get_table_names())

    if 'conversations' in existing:
        # Tables already exist from init_db() — just ensure all columns are present
        with op.batch_alter_table('conversations') as batch_op:
            cols = {c['name'] for c in inspector.get_columns('conversations')}
            if 'description' not in cols:
                batch_op.add_column(sa.Column('description', sa.Text, nullable=True))
            if 'avatar_url' not in cols:
                batch_op.add_column(sa.Column('avatar_url', sa.String(512), nullable=True))
        return

    op.create_table(
        'conversations',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('property_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('type', sa.Enum('direct', 'group', name='conversationtype'), nullable=False),
        sa.Column('name', sa.String(255), nullable=True),
        sa.Column('description', sa.Text, nullable=True),
        sa.Column('created_by', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('is_archived', sa.Boolean, nullable=False, server_default='false'),
        sa.Column('last_message_at', sa.DateTime, nullable=True),
        sa.Column('participant_count', sa.Integer, nullable=False, server_default='1'),
        sa.Column('unread_count', sa.Integer, nullable=False, server_default='0'),
        sa.Column('avatar_url', sa.String(512), nullable=True),
        sa.Column('created_at', sa.DateTime, server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime, server_default=sa.text('now()'), onupdate=sa.text('now()'), nullable=False),
        sa.Column('deleted_at', sa.DateTime, nullable=True),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['property_id'], ['properties.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.CheckConstraint("type IN ('direct', 'group')", name='check_conversation_type'),
    )
    op.create_index('idx_conversations_tenant_property', 'conversations', ['tenant_id', 'property_id'])
    op.create_index('idx_conversations_created_by', 'conversations', ['created_by'])
    op.create_index('idx_conversations_is_archived', 'conversations', ['is_archived'])

    op.create_table(
        'messages',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('conversation_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('sender_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('content', sa.Text, nullable=False),
        sa.Column('reply_to_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('edited_at', sa.DateTime, nullable=True),
        sa.Column('edited_count', sa.Integer, nullable=False, server_default='0'),
        sa.Column('mentions', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('created_at', sa.DateTime, server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime, server_default=sa.text('now()'), nullable=False),
        sa.Column('deleted_at', sa.DateTime, nullable=True),
        sa.ForeignKeyConstraint(['conversation_id'], ['conversations.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['sender_id'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['reply_to_id'], ['messages.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('idx_messages_conversation_id', 'messages', ['conversation_id'])
    op.create_index('idx_messages_sender_id', 'messages', ['sender_id'])
    op.create_index('idx_messages_created_at', 'messages', ['created_at'])
    op.create_index('idx_messages_reply_to_id', 'messages', ['reply_to_id'])
    op.create_index('idx_messages_deleted_at', 'messages', ['deleted_at'])

    op.create_table(
        'conversation_participants',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('conversation_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('role', sa.Enum('admin', 'moderator', 'member', name='participantrole'), nullable=False, server_default='member'),
        sa.Column('last_read_at', sa.DateTime, nullable=True),
        sa.Column('last_read_message_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('is_muted', sa.Boolean, nullable=False, server_default='false'),
        sa.Column('left_at', sa.DateTime, nullable=True),
        sa.Column('created_at', sa.DateTime, server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime, server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['conversation_id'], ['conversations.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['last_read_message_id'], ['messages.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('conversation_id', 'user_id', name='uq_conversation_participant'),
        sa.CheckConstraint("role IN ('admin', 'moderator', 'member')", name='check_participant_role'),
    )
    op.create_index('idx_participants_user_id', 'conversation_participants', ['user_id'])
    op.create_index('idx_participants_left_at', 'conversation_participants', ['left_at'])

    op.create_table(
        'message_media',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('message_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('media_type', sa.Enum('image', 'file', 'video', 'audio', name='mediatype'), nullable=False),
        sa.Column('storage_key', sa.String(512), nullable=False),
        sa.Column('thumbnail_key', sa.String(512), nullable=True),
        sa.Column('original_filename', sa.String(255), nullable=False),
        sa.Column('file_size_bytes', sa.Integer, nullable=False),
        sa.Column('mime_type', sa.String(100), nullable=False),
        sa.Column('width', sa.Integer, nullable=True),
        sa.Column('height', sa.Integer, nullable=True),
        sa.Column('duration_seconds', sa.Float, nullable=True),
        sa.Column('is_scanned', sa.Boolean, nullable=False, server_default='false'),
        sa.Column('is_safe', sa.Boolean, nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime, server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime, server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['message_id'], ['messages.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.CheckConstraint("media_type IN ('image', 'file', 'video', 'audio')", name='check_media_type'),
    )
    op.create_index('idx_media_message_id', 'message_media', ['message_id'])
    op.create_index('idx_media_created_at', 'message_media', ['created_at'])

    op.create_table(
        'message_delivery_status',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('message_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('status', sa.Enum('sent', 'delivered', 'read', name='messagestatus'), nullable=False, server_default='sent'),
        sa.Column('status_at', sa.DateTime, server_default=sa.text('now()'), nullable=False),
        sa.Column('created_at', sa.DateTime, server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime, server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['message_id'], ['messages.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('message_id', 'user_id', name='uq_message_user_status'),
        sa.CheckConstraint("status IN ('sent', 'delivered', 'read')", name='check_message_status'),
    )
    op.create_index('idx_status_user_id', 'message_delivery_status', ['user_id'])
    op.create_index('idx_status_message_id', 'message_delivery_status', ['message_id'])

    op.create_table(
        'typing_indicators',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('conversation_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('expires_at', sa.DateTime, nullable=False),
        sa.ForeignKeyConstraint(['conversation_id'], ['conversations.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('conversation_id', 'user_id', name='uq_typing_indicator'),
    )
    op.create_index('idx_typing_expires_at', 'typing_indicators', ['expires_at'])

    op.create_table(
        'chat_notifications',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('message_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('conversation_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('title', sa.String(255), nullable=False),
        sa.Column('body', sa.Text, nullable=False),
        sa.Column('is_read', sa.Boolean, nullable=False, server_default='false'),
        sa.Column('read_at', sa.DateTime, nullable=True),
        sa.Column('sent_at', sa.DateTime, server_default=sa.text('now()'), nullable=False),
        sa.Column('delivery_attempts', sa.Integer, nullable=False, server_default='0'),
        sa.Column('last_delivery_attempt', sa.DateTime, nullable=True),
        sa.Column('created_at', sa.DateTime, server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime, server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['message_id'], ['messages.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['conversation_id'], ['conversations.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('idx_notifications_user_id', 'chat_notifications', ['user_id'])
    op.create_index('idx_notifications_tenant_id', 'chat_notifications', ['tenant_id'])
    op.create_index('idx_notifications_is_read', 'chat_notifications', ['is_read'])
    op.create_index('idx_notifications_created_at', 'chat_notifications', ['created_at'])


def downgrade() -> None:
    op.drop_table('chat_notifications')
    op.drop_table('typing_indicators')
    op.drop_table('message_delivery_status')
    op.drop_table('message_media')
    op.drop_table('conversation_participants')
    op.drop_table('messages')
    op.drop_table('conversations')
    op.execute("DROP TYPE IF EXISTS conversationtype")
    op.execute("DROP TYPE IF EXISTS participantrole")
    op.execute("DROP TYPE IF EXISTS mediatype")
    op.execute("DROP TYPE IF EXISTS messagestatus")
