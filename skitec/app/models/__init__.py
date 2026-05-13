"""
Models Module - Initialization

Exports all ORM models for use throughout the application.
Ensures all models are registered with the declarative base.
"""

from .attendance import AttendanceRecord, PropertyGeofence
from .audit import AuditLog
from .base import Base, IdMixin, SoftDeleteMixin, TimestampMixin
from .chat import (
    Conversation,
    ConversationParticipant,
    Message,
    MessageMedia,
    MessageReadReceipt,
    UserPresence,
    TypingIndicator,
    ChatNotification,
    ConversationType,
    MessageType,
    ParticipantRole,
    MessageStatus,
    UserPresenceStatus,
)
from .governance import GovernanceWorkflow, WorkflowInstance
from .kra import DailyKRA, WeeklyKRA
from .property import Property
from .user import User
from .workforce import WorkforceEntry

__all__ = [
    "Base",
    "IdMixin",
    "TimestampMixin",
    "SoftDeleteMixin",
    "User",
    "Property",
    "WorkforceEntry",
    "GovernanceWorkflow",
    "WorkflowInstance",
    "AuditLog",
    "DailyKRA",
    "WeeklyKRA",
    "AttendanceRecord",
    "PropertyGeofence",
    # Chat models
    "Conversation",
    "ConversationParticipant",
    "Message",
    "MessageMedia",
    "MessageReadReceipt",
    "UserPresence",
    "TypingIndicator",
    "ChatNotification",
    "ConversationType",
    "MessageType",
    "ParticipantRole",
    "MessageStatus",
    "UserPresenceStatus",
]
