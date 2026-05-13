"""
SQLAlchemy ORM models for the chat system.
Supports direct chat, group chat, file sharing, typing indicators, and read receipts.
All models enforce multi-tenant and property isolation.
"""

from uuid import UUID, uuid4
from datetime import datetime, timezone
from sqlalchemy import (
    Column, String, UUID as SQLALCHEMY_UUID, ForeignKey, DateTime,
    Boolean, Integer, BigInteger, Text, Index, UniqueConstraint,
    Enum, TIMESTAMP, func, CheckConstraint, JSONB
)
from sqlalchemy.orm import relationship, declarative_base
from sqlalchemy.ext.hybrid import hybrid_property
import enum

from app.core.database import Base


class ConversationType(str, enum.Enum):
    """Types of conversations supported."""
    DIRECT = "direct"      # 1-to-1 chat
    GROUP = "group"        # Many-to-many chat
    AI = "ai"             # Future: AI assistant chat


class MessageType(str, enum.Enum):
    """Types of messages."""
    TEXT = "text"                    # Plain text message
    IMAGE = "image"                  # Image attachment
    FILE = "file"                    # File attachment
    VOICE = "voice"                  # Voice note
    SYSTEM = "system"                # System message (user joined, left, etc.)


class ParticipantRole(str, enum.Enum):
    """Roles within a conversation."""
    ADMIN = "admin"          # Can manage participants, delete messages
    MODERATOR = "moderator"  # Can delete messages
    MEMBER = "member"        # Regular participant


class MessageStatus(str, enum.Enum):
    """Status of a message for a user."""
    SENT = "sent"           # Message sent but not delivered to user
    DELIVERED = "delivered" # Message delivered to user's device
    READ = "read"           # Message read by user


class UserPresenceStatus(str, enum.Enum):
    """User online/offline status."""
    ONLINE = "online"
    OFFLINE = "offline"
    AWAY = "away"


# ============================================================================
# CONVERSATION MODELS
# ============================================================================

class Conversation(Base):
    """
    Represents a conversation (direct or group chat).
    
    Multi-tenant isolation:
    - tenant_id: Required on all queries
    - property_id: Required on all queries (property-level isolation)
    - created_by: Only creator (and admins) can modify
    """
    __tablename__ = "conversations"

    id = Column(SQLALCHEMY_UUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id = Column(SQLALCHEMY_UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    property_id = Column(SQLALCHEMY_UUID(as_uuid=True), ForeignKey("properties.id", ondelete="CASCADE"), nullable=False)
    
    # Conversation metadata
    type = Column(String(10), nullable=False, default=ConversationType.DIRECT)
    name = Column(String(120))  # For group chats
    created_by = Column(SQLALCHEMY_UUID(as_uuid=True), ForeignKey("users.id", ondelete="NO ACTION"), nullable=False)
    
    # Lifecycle
    created_at = Column(TIMESTAMP(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(TIMESTAMP(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    is_archived = Column(Boolean, default=False)

    # Relationships
    participants = relationship(
        "ConversationParticipant",
        back_populates="conversation",
        cascade="all, delete-orphan",
        lazy="select"
    )
    messages = relationship(
        "Message",
        back_populates="conversation",
        cascade="all, delete-orphan",
        lazy="select"
    )
    
    # Indexes for common queries
    __table_args__ = (
        Index("idx_conversations_tenant", "tenant_id"),
        Index("idx_conversations_property", "property_id"),
        Index("idx_conversations_created_by", "created_by"),
        Index("idx_conversations_type", "type"),
        Index("idx_conversations_tenant_property", "tenant_id", "property_id"),
        CheckConstraint("type IN ('direct', 'group', 'ai')", name="ck_conversation_type"),
    )

    def __repr__(self):
        return f"<Conversation {self.id} ({self.type})>"


class ConversationParticipant(Base):
    """
    Represents a user's participation in a conversation.
    Tracks read status, mute settings, and participant role.
    
    Multi-tenant isolation:
    - Implicit via conversation's tenant_id and property_id
    - Cannot add users from other properties
    """
    __tablename__ = "conversation_participants"

    conversation_id = Column(
        SQLALCHEMY_UUID(as_uuid=True),
        ForeignKey("conversations.id", ondelete="CASCADE"),
        primary_key=True
    )
    user_id = Column(
        SQLALCHEMY_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True
    )
    
    # Participant settings
    role = Column(String(10), default=ParticipantRole.MEMBER, nullable=False)
    is_muted = Column(Boolean, default=False)
    
    # Read tracking
    joined_at = Column(TIMESTAMP(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    last_read_at = Column(TIMESTAMP(timezone=True))
    last_read_message_id = Column(SQLALCHEMY_UUID(as_uuid=True))

    # Relationships
    conversation = relationship(
        "Conversation",
        back_populates="participants",
        lazy="joined"
    )
    user = relationship("User", lazy="joined")

    __table_args__ = (
        Index("idx_participants_user", "user_id"),
        Index("idx_participants_conversation", "conversation_id"),
        CheckConstraint("role IN ('admin', 'moderator', 'member')", name="ck_participant_role"),
    )

    def __repr__(self):
        return f"<ConversationParticipant {self.conversation_id} / {self.user_id}>"


# ============================================================================
# MESSAGE MODELS
# ============================================================================

class Message(Base):
    """
    Represents a message in a conversation.
    
    Multi-tenant isolation:
    - tenant_id: Required on all queries
    - sender must be participant in conversation
    - Only sender (and admins) can edit/delete
    """
    __tablename__ = "messages"

    id = Column(SQLALCHEMY_UUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id = Column(SQLALCHEMY_UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    conversation_id = Column(SQLALCHEMY_UUID(as_uuid=True), ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False)
    sender_id = Column(SQLALCHEMY_UUID(as_uuid=True), ForeignKey("users.id", ondelete="NO ACTION"), nullable=False)
    
    # Message content
    content = Column(Text)
    message_type = Column(String(10), default=MessageType.TEXT, nullable=False)
    
    # Reply-to support
    reply_to_id = Column(SQLALCHEMY_UUID(as_uuid=True), ForeignKey("messages.id", ondelete="NO ACTION"))
    
    # Lifecycle
    created_at = Column(TIMESTAMP(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    edited_at = Column(TIMESTAMP(timezone=True))
    is_deleted = Column(Boolean, default=False)  # Soft delete
    
    # Relationships
    conversation = relationship("Conversation", back_populates="messages", lazy="joined")
    sender = relationship("User", foreign_keys=[sender_id], lazy="joined")
    media = relationship(
        "MessageMedia",
        back_populates="message",
        cascade="all, delete-orphan",
        lazy="select"
    )
    read_receipts = relationship(
        "MessageReadReceipt",
        back_populates="message",
        cascade="all, delete-orphan",
        lazy="select"
    )
    reply_to = relationship(
        "Message",
        remote_side=[id],
        backref="replies",
        lazy="joined"
    )

    __table_args__ = (
        Index("idx_messages_tenant", "tenant_id"),
        Index("idx_messages_conversation", "conversation_id"),
        Index("idx_messages_sender", "sender_id"),
        Index("idx_messages_created_at", "created_at"),
        Index("idx_messages_tenant_conversation", "tenant_id", "conversation_id"),
        CheckConstraint("message_type IN ('text', 'image', 'file', 'voice', 'system')", name="ck_message_type"),
    )

    def __repr__(self):
        return f"<Message {self.id} from {self.sender_id}>"


class MessageMedia(Base):
    """
    Represents a media file (image, document, voice) attached to a message.
    Stores reference to file in storage service (local or S3).
    
    Multi-tenant isolation:
    - Implicit via message's tenant_id
    - Storage service validates tenant access
    """
    __tablename__ = "message_media"

    id = Column(SQLALCHEMY_UUID(as_uuid=True), primary_key=True, default=uuid4)
    message_id = Column(SQLALCHEMY_UUID(as_uuid=True), ForeignKey("messages.id", ondelete="CASCADE"), nullable=False)
    
    # File reference
    storage_key = Column(String(512), nullable=False)  # Path/key in storage service
    media_type = Column(String(50), nullable=False)  # MIME type (e.g., image/jpeg)
    file_size_bytes = Column(BigInteger, nullable=False)
    
    # Thumbnail (optional)
    thumbnail_key = Column(String(512))
    thumbnail_size_bytes = Column(BigInteger)
    
    uploaded_at = Column(TIMESTAMP(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))

    # Relationships
    message = relationship("Message", back_populates="media", lazy="joined")

    __table_args__ = (
        Index("idx_message_media_message", "message_id"),
    )

    def __repr__(self):
        return f"<MessageMedia {self.id} for {self.message_id}>"


class MessageReadReceipt(Base):
    """
    Tracks read/delivered status of a message for each user.
    
    Multi-tenant isolation:
    - Implicit via message's tenant_id
    """
    __tablename__ = "message_read_receipts"

    id = Column(SQLALCHEMY_UUID(as_uuid=True), primary_key=True, default=uuid4)
    message_id = Column(SQLALCHEMY_UUID(as_uuid=True), ForeignKey("messages.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(SQLALCHEMY_UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    
    # Status
    status = Column(String(10), nullable=False, default=MessageStatus.SENT)
    
    # Timestamps
    created_at = Column(TIMESTAMP(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(TIMESTAMP(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Relationships
    message = relationship("Message", back_populates="read_receipts", lazy="joined")
    user = relationship("User", lazy="joined")

    __table_args__ = (
        Index("idx_read_receipts_message", "message_id"),
        Index("idx_read_receipts_user", "user_id"),
        Index("idx_read_receipts_message_user", "message_id", "user_id"),
        UniqueConstraint("message_id", "user_id", name="uq_message_read_receipt"),
        CheckConstraint("status IN ('sent', 'delivered', 'read')", name="ck_read_receipt_status"),
    )

    def __repr__(self):
        return f"<MessageReadReceipt {self.message_id} / {self.user_id}: {self.status}>"


# ============================================================================
# PRESENCE AND NOTIFICATIONS
# ============================================================================

class UserPresence(Base):
    """
    Tracks user online/offline status.
    Used by WebSocket manager to know which conversations to update.
    
    Note: In production, this would be stored in Redis, not PostgreSQL.
    For now, we keep it in DB for simplicity. Will migrate to Redis later.
    """
    __tablename__ = "user_presences"

    id = Column(SQLALCHEMY_UUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id = Column(SQLALCHEMY_UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    tenant_id = Column(SQLALCHEMY_UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    property_id = Column(SQLALCHEMY_UUID(as_uuid=True), ForeignKey("properties.id", ondelete="CASCADE"), nullable=False)
    
    # Presence data
    status = Column(String(10), nullable=False, default=UserPresenceStatus.ONLINE)
    active_conversation_id = Column(SQLALCHEMY_UUID(as_uuid=True), ForeignKey("conversations.id"))
    
    # Timestamps
    created_at = Column(TIMESTAMP(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(TIMESTAMP(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    last_seen_at = Column(TIMESTAMP(timezone=True))

    __table_args__ = (
        Index("idx_presence_user", "user_id"),
        Index("idx_presence_tenant", "tenant_id"),
        Index("idx_presence_property", "property_id"),
        Index("idx_presence_status", "status"),
        UniqueConstraint("user_id", "tenant_id", "property_id", name="uq_user_presence"),
        CheckConstraint("status IN ('online', 'offline', 'away')", name="ck_presence_status"),
    )

    def __repr__(self):
        return f"<UserPresence {self.user_id}: {self.status}>"


class TypingIndicator(Base):
    """
    Tracks when users are typing in a conversation.
    Temporary data - ideally stored in Redis.
    Expires after 5 seconds of inactivity.
    """
    __tablename__ = "typing_indicators"

    id = Column(SQLALCHEMY_UUID(as_uuid=True), primary_key=True, default=uuid4)
    conversation_id = Column(SQLALCHEMY_UUID(as_uuid=True), ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(SQLALCHEMY_UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    tenant_id = Column(SQLALCHEMY_UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    
    created_at = Column(TIMESTAMP(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        Index("idx_typing_conversation", "conversation_id"),
        Index("idx_typing_user", "user_id"),
        UniqueConstraint("conversation_id", "user_id", name="uq_typing_indicator"),
    )

    def __repr__(self):
        return f"<TypingIndicator {self.user_id} in {self.conversation_id}>"


class ChatNotification(Base):
    """
    Notifications for chat events (mentions, replies, etc.).
    In future, will integrate with notification service and send via email/push.
    """
    __tablename__ = "chat_notifications"

    id = Column(SQLALCHEMY_UUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id = Column(SQLALCHEMY_UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    property_id = Column(SQLALCHEMY_UUID(as_uuid=True), ForeignKey("properties.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(SQLALCHEMY_UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    
    # Notification details
    conversation_id = Column(SQLALCHEMY_UUID(as_uuid=True), ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False)
    message_id = Column(SQLALCHEMY_UUID(as_uuid=True), ForeignKey("messages.id", ondelete="CASCADE"), nullable=False)
    triggered_by = Column(SQLALCHEMY_UUID(as_uuid=True), ForeignKey("users.id", ondelete="NO ACTION"))
    
    # Notification type
    notification_type = Column(String(50), nullable=False)  # 'mention', 'reply', 'group_message'
    
    # Status
    is_read = Column(Boolean, default=False)
    
    created_at = Column(TIMESTAMP(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    read_at = Column(TIMESTAMP(timezone=True))

    __table_args__ = (
        Index("idx_notifications_user", "user_id"),
        Index("idx_notifications_conversation", "conversation_id"),
        Index("idx_notifications_tenant", "tenant_id"),
        Index("idx_notifications_is_read", "is_read"),
    )

    def __repr__(self):
        return f"<ChatNotification {self.id} for {self.user_id}>"
