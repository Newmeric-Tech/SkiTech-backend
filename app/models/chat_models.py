"""
SQLAlchemy ORM Models for Chat System - app/models/chat_models.py

Includes:
- Conversation: Direct/group chats with multi-tenant property isolation
- ConversationParticipant: User membership and roles
- Message: Chat messages with replies, soft delete, read receipts
- MessageMedia: Attachments (images, files, voice notes)
- MessageStatus: Delivery and read receipts
"""

import uuid
from datetime import datetime
from enum import Enum
from typing import Optional

from sqlalchemy import (
    Boolean, CheckConstraint, Column, DateTime, Enum as SQLEnum, Float, ForeignKey,
    Index, Integer, String, Text, UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.models.base import Base, UUIDMixin, TimestampMixin, SoftDeleteMixin


# ===========================================================
# ENUMS
# ===========================================================

class ConversationType(str, Enum):
    """Conversation types"""
    DIRECT = "direct"
    GROUP = "group"


class MessageStatus(str, Enum):
    """Message delivery status"""
    SENT = "sent"
    DELIVERED = "delivered"
    READ = "read"


class ParticipantRole(str, Enum):
    """Participant role in group conversations"""
    ADMIN = "admin"
    MODERATOR = "moderator"
    MEMBER = "member"


class MediaType(str, Enum):
    """Type of media attachment"""
    IMAGE = "image"
    FILE = "file"
    VIDEO = "video"
    AUDIO = "audio"  # voice notes


# ===========================================================
# CONVERSATIONS - Multi-tenant Property-isolated Chat Rooms
# ===========================================================

class Conversation(Base, UUIDMixin, TimestampMixin, SoftDeleteMixin):
    """
    Chat conversation (direct or group).
    
    Strict isolation at property level:
    - tenant_id: Multi-tenant isolation
    - property_id: All participants must belong to same property
    - type: 'direct' (1-on-1) or 'group' (multi-participant)
    - is_archived: Soft archive without deletion
    """
    __tablename__ = "conversations"

    # Multi-tenant and property isolation
    tenant_id: UUID = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    property_id: UUID = Column(UUID(as_uuid=True), ForeignKey("properties.id", ondelete="CASCADE"), nullable=False, index=True)
    
    # Conversation metadata
    type: str = Column(String(50), nullable=False, default=ConversationType.DIRECT)
    name: str = Column(String(255), nullable=True)  # Only used for group chats
    description: Optional[str] = Column(Text, nullable=True)
    
    # Admin/creator info
    created_by: UUID = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    
    # Chat state
    is_archived: bool = Column(Boolean, nullable=False, default=False, index=True)
    last_message_at: Optional[datetime] = Column(DateTime, nullable=True)  # For sorting
    
    # Denormalized for performance
    participant_count: int = Column(Integer, nullable=False, default=1)
    unread_count: int = Column(Integer, nullable=False, default=0)
    
    # Media/files storage
    avatar_url: Optional[str] = Column(String(512), nullable=True)  # Group chat avatar

    __table_args__ = (
        CheckConstraint("type IN ('direct', 'group')", name="check_conversation_type"),
        Index("idx_conversations_tenant_property", "tenant_id", "property_id"),
        Index("idx_conversations_created_by", "created_by"),
        Index("idx_conversations_is_archived", "is_archived"),
    )

    # Relationships
    participants = relationship(
        "ConversationParticipant",
        back_populates="conversation",
        cascade="all, delete-orphan",
        foreign_keys="ConversationParticipant.conversation_id"
    )
    messages = relationship(
        "Message",
        back_populates="conversation",
        cascade="all, delete-orphan",
        foreign_keys="Message.conversation_id"
    )
    creator = relationship("User", foreign_keys=[created_by])


# ===========================================================
# CONVERSATION PARTICIPANTS - Membership & Roles
# ===========================================================

class ConversationParticipant(Base, UUIDMixin, TimestampMixin):
    """
    User membership in a conversation.
    
    Tracks:
    - User participation status
    - Role in group chats (admin, moderator, member)
    - Last read message for read receipts
    - Muted status for notifications
    """
    __tablename__ = "conversation_participants"

    conversation_id: UUID = Column(
        UUID(as_uuid=True), ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: UUID = Column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    
    # Role in group conversations
    role: str = Column(
        SQLEnum(ParticipantRole, native_enum=False), nullable=False, default=ParticipantRole.MEMBER
    )
    
    # Read receipts
    last_read_at: Optional[datetime] = Column(DateTime, nullable=True)
    last_read_message_id: Optional[UUID] = Column(
        UUID(as_uuid=True), ForeignKey("messages.id", ondelete="SET NULL"), nullable=True
    )
    
    # Notification preferences
    is_muted: bool = Column(Boolean, nullable=False, default=False)
    
    # Soft exit (removed from group)
    left_at: Optional[datetime] = Column(DateTime, nullable=True)

    __table_args__ = (
        UniqueConstraint("conversation_id", "user_id", name="uq_conversation_participant"),
        CheckConstraint("role IN ('admin', 'moderator', 'member')", name="check_participant_role"),
        Index("idx_participants_user_id", "user_id"),
        Index("idx_participants_left_at", "left_at"),
    )

    # Relationships
    conversation = relationship("Conversation", back_populates="participants")
    user = relationship("User")
    last_read_message = relationship("Message", foreign_keys=[last_read_message_id])


# ===========================================================
# MESSAGES - Chat Messages with Threading & Soft Delete
# ===========================================================

class Message(Base, UUIDMixin, TimestampMixin, SoftDeleteMixin):
    """
    Chat message with rich features:
    
    Features:
    - Multi-tenant isolation (tenant_id from conversation)
    - Message threading (reply_to_id for quoted/threaded messages)
    - Soft delete support
    - Edit history tracking
    - Media attachments via relationship
    - Read receipt tracking
    """
    __tablename__ = "messages"

    # Tenant isolation (denormalized from conversation for efficient filtering)
    tenant_id: UUID = Column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # Conversation context
    conversation_id: UUID = Column(
        UUID(as_uuid=True), ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # Sender (must be conversation participant - validated at service layer)
    sender_id: UUID = Column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    
    # Message content
    content: str = Column(Text, nullable=False)
    
    # Threading support (replies/quotes)
    reply_to_id: Optional[UUID] = Column(
        UUID(as_uuid=True), ForeignKey("messages.id", ondelete="SET NULL"), nullable=True
    )
    
    # Edit tracking
    edited_at: Optional[datetime] = Column(DateTime, nullable=True)
    edited_count: int = Column(Integer, nullable=False, default=0)
    
    # Metadata
    mentions: Optional[dict] = Column(JSONB, nullable=True)  # @mentions JSON: {"user_id": "username"}
    
    __table_args__ = (
        Index("idx_messages_conversation_id", "conversation_id"),
        Index("idx_messages_sender_id", "sender_id"),
        Index("idx_messages_created_at", "created_at"),
        Index("idx_messages_reply_to_id", "reply_to_id"),
        Index("idx_messages_deleted_at", "deleted_at"),
    )

    # Relationships
    conversation = relationship("Conversation", back_populates="messages")
    sender = relationship("User")
    media = relationship(
        "MessageMedia",
        back_populates="message",
        cascade="all, delete-orphan",
        foreign_keys="MessageMedia.message_id"
    )
    statuses = relationship(
        "MessageDeliveryStatus",
        back_populates="message",
        cascade="all, delete-orphan",
        foreign_keys="MessageDeliveryStatus.message_id"
    )
    replies = relationship(
        "Message",
        remote_side="Message.id",
        backref="replied_message",
        foreign_keys=[reply_to_id]
    )


# ===========================================================
# MESSAGE MEDIA - Attachments (Files, Images, Voice Notes)
# ===========================================================

class MessageMedia(Base, UUIDMixin, TimestampMixin):
    """
    Media attachment metadata for messages.
    
    Supports:
    - Images (PNG, JPEG, WebP)
    - Files (PDF, DOC, etc.)
    - Videos
    - Audio (voice notes)
    
    Storage abstraction:
    - storage_key: Path/key in storage backend (local or S3)
    - thumbnail_key: Cached thumbnail for performance
    - File metadata for validation and UI
    """
    __tablename__ = "message_media"

    message_id: UUID = Column(
        UUID(as_uuid=True), ForeignKey("messages.id", ondelete="CASCADE"), nullable=False, index=True
    )
    
    # Media type
    media_type: str = Column(
        SQLEnum(MediaType, native_enum=False), nullable=False
    )
    
    # Storage paths (abstracted for local/S3 migration)
    storage_key: str = Column(String(512), nullable=False)  # relative path or S3 key
    thumbnail_key: Optional[str] = Column(String(512), nullable=True)  # for images/videos
    
    # File metadata
    original_filename: str = Column(String(255), nullable=False)
    file_size_bytes: int = Column(Integer, nullable=False)
    mime_type: str = Column(String(100), nullable=False)
    
    # Image/Video dimensions
    width: Optional[int] = Column(Integer, nullable=True)
    height: Optional[int] = Column(Integer, nullable=True)
    
    # Audio duration in seconds
    duration_seconds: Optional[float] = Column(Float, nullable=True)
    
    # Virus scan status (future integration)
    is_scanned: bool = Column(Boolean, nullable=False, default=False)
    is_safe: bool = Column(Boolean, nullable=False, default=True)

    __table_args__ = (
        CheckConstraint("media_type IN ('image', 'file', 'video', 'audio')", name="check_media_type"),
        Index("idx_media_message_id", "message_id"),
        Index("idx_media_created_at", "created_at"),
    )

    # Relationships
    message = relationship("Message", back_populates="media")


# ===========================================================
# MESSAGE DELIVERY STATUS - Read Receipts
# ===========================================================

class MessageDeliveryStatus(Base, UUIDMixin, TimestampMixin):
    """
    Per-user message delivery and read status.
    
    Tracks:
    - SENT: Message delivered to server
    - DELIVERED: Message sent to user's device
    - READ: User opened and read the message
    
    Performance optimization:
    - Indexed for quick filtering
    - Enables real-time read receipts
    - Denormalized counts in Conversation for sorting
    """
    __tablename__ = "message_delivery_status"

    message_id: UUID = Column(
        UUID(as_uuid=True), ForeignKey("messages.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: UUID = Column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    
    # Status progression: SENT -> DELIVERED -> READ
    status: str = Column(
        SQLEnum(MessageStatus, native_enum=False), nullable=False, default=MessageStatus.SENT
    )
    
    # Timestamp when status changed
    status_at: datetime = Column(DateTime, nullable=False, server_default=func.now())

    __table_args__ = (
        UniqueConstraint("message_id", "user_id", name="uq_message_user_status"),
        CheckConstraint("status IN ('sent', 'delivered', 'read')", name="check_message_status"),
        Index("idx_status_user_id", "user_id"),
        Index("idx_status_message_id", "message_id"),
    )

    # Relationships
    message = relationship("Message", back_populates="statuses")
    user = relationship("User")


# ===========================================================
# TYPING INDICATORS (Real-time - Redis in future)
# ===========================================================

class TypingIndicator(Base, UUIDMixin):
    """
    Temporary typing indicator state.
    
    NOTE: This table is for persistence/recovery.
    Primary storage should be Redis for performance.
    
    Expires after 5 seconds (user stopped typing).
    """
    __tablename__ = "typing_indicators"

    conversation_id: UUID = Column(
        UUID(as_uuid=True), ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: UUID = Column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    
    # When typing indicator expires
    expires_at: datetime = Column(DateTime, nullable=False, index=True)

    __table_args__ = (
        UniqueConstraint("conversation_id", "user_id", name="uq_typing_indicator"),
        Index("idx_typing_expires_at", "expires_at"),
    )


# ===========================================================
# CHAT NOTIFICATIONS (For logging - Redis for real-time)
# ===========================================================

class ChatNotification(Base, UUIDMixin, TimestampMixin):
    """
    Chat notification log for users.
    
    Used for:
    - Push notifications
    - Notification history/replay
    - Unread message counts
    
    NOTE: Real-time notification state should use Redis.
    This table is for history and retry logic.
    """
    __tablename__ = "chat_notifications"

    # Multi-tenant
    tenant_id: UUID = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    
    # Recipient
    user_id: UUID = Column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    
    # Trigger
    message_id: Optional[UUID] = Column(
        UUID(as_uuid=True), ForeignKey("messages.id", ondelete="SET NULL"), nullable=True
    )
    conversation_id: UUID = Column(
        UUID(as_uuid=True), ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False
    )
    
    # Content
    title: str = Column(String(255), nullable=False)
    body: str = Column(Text, nullable=False)
    
    # State
    is_read: bool = Column(Boolean, nullable=False, default=False)
    read_at: Optional[datetime] = Column(DateTime, nullable=True)
    sent_at: datetime = Column(DateTime, nullable=False, server_default=func.now())
    
    # Retry tracking for delivery
    delivery_attempts: int = Column(Integer, nullable=False, default=0)
    last_delivery_attempt: Optional[datetime] = Column(DateTime, nullable=True)

    __table_args__ = (
        Index("idx_notifications_user_id", "user_id"),
        Index("idx_notifications_tenant_id", "tenant_id"),
        Index("idx_notifications_is_read", "is_read"),
        Index("idx_notifications_created_at", "created_at"),
    )

    # Relationships
    message = relationship("Message")
    conversation = relationship("Conversation")
    user = relationship("User")
