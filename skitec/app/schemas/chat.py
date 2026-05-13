"""
Pydantic schemas for chat API requests, responses, and WebSocket messages.
Handles validation, serialization, and type safety.
"""

from typing import Optional, List
from uuid import UUID
from datetime import datetime
from pydantic import BaseModel, Field, field_validator, ConfigDict
from enum import Enum


# ============================================================================
# ENUMS
# ============================================================================

class ConversationTypeEnum(str, Enum):
    DIRECT = "direct"
    GROUP = "group"
    AI = "ai"


class MessageTypeEnum(str, Enum):
    TEXT = "text"
    IMAGE = "image"
    FILE = "file"
    VOICE = "voice"
    SYSTEM = "system"


class ParticipantRoleEnum(str, Enum):
    ADMIN = "admin"
    MODERATOR = "moderator"
    MEMBER = "member"


class MessageStatusEnum(str, Enum):
    SENT = "sent"
    DELIVERED = "delivered"
    READ = "read"


class UserPresenceStatusEnum(str, Enum):
    ONLINE = "online"
    OFFLINE = "offline"
    AWAY = "away"


class WSMessageTypeEnum(str, Enum):
    """WebSocket message types."""
    MESSAGE_SEND = "message:send"
    MESSAGE_READ = "message:read"
    TYPING_START = "typing:start"
    TYPING_STOP = "typing:stop"
    USER_ONLINE = "user:online"
    USER_OFFLINE = "user:offline"
    USER_JOINED = "user:joined"
    USER_LEFT = "user:left"


# ============================================================================
# PAGINATION
# ============================================================================

class PaginationParams(BaseModel):
    """Pagination parameters for list endpoints."""
    skip: int = Field(default=0, ge=0)
    limit: int = Field(default=20, ge=1, le=100)

    model_config = ConfigDict(from_attributes=True)


class PaginatedResponse(BaseModel, Generic):
    """Generic paginated response wrapper."""
    items: List = Field(...)
    total: int = Field(...)
    skip: int = Field(...)
    limit: int = Field(...)

    @property
    def has_more(self) -> bool:
        return (self.skip + self.limit) < self.total


# ============================================================================
# PARTICIPANT SCHEMAS
# ============================================================================

class ParticipantBase(BaseModel):
    """Base participant schema."""
    role: ParticipantRoleEnum = ParticipantRoleEnum.MEMBER
    is_muted: bool = False

    model_config = ConfigDict(from_attributes=True)


class ParticipantCreate(ParticipantBase):
    """Request to add a participant."""
    user_id: UUID

    model_config = ConfigDict(from_attributes=True)


class ParticipantUpdate(BaseModel):
    """Request to update a participant."""
    role: Optional[ParticipantRoleEnum] = None
    is_muted: Optional[bool] = None

    model_config = ConfigDict(from_attributes=True)


class ParticipantResponse(ParticipantBase):
    """Participant response."""
    conversation_id: UUID
    user_id: UUID
    joined_at: datetime
    last_read_at: Optional[datetime] = None
    
    # User info
    user_email: Optional[str] = None
    user_name: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


# ============================================================================
# MEDIA/FILE SCHEMAS
# ============================================================================

class MediaBase(BaseModel):
    """Base media schema."""
    media_type: str
    file_size_bytes: int

    model_config = ConfigDict(from_attributes=True)


class MediaResponse(MediaBase):
    """Media response."""
    id: UUID
    message_id: UUID
    storage_key: str
    thumbnail_key: Optional[str] = None
    uploaded_at: datetime

    model_config = ConfigDict(from_attributes=True)


class FileUploadResponse(BaseModel):
    """File upload response."""
    media_id: UUID
    storage_key: str
    file_size_bytes: int
    media_type: str
    thumbnail_key: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


# ============================================================================
# MESSAGE SCHEMAS
# ============================================================================

class MessageBase(BaseModel):
    """Base message schema."""
    content: Optional[str] = None
    message_type: MessageTypeEnum = MessageTypeEnum.TEXT
    reply_to_id: Optional[UUID] = None

    model_config = ConfigDict(from_attributes=True)


class MessageCreate(MessageBase):
    """Request to send a message."""
    pass

    model_config = ConfigDict(from_attributes=True)


class MessageUpdate(BaseModel):
    """Request to edit a message."""
    content: str

    @field_validator("content")
    @classmethod
    def validate_content(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Message content cannot be empty")
        if len(v) > 5000:
            raise ValueError("Message content too long (max 5000 characters)")
        return v.strip()

    model_config = ConfigDict(from_attributes=True)


class MessageResponse(MessageBase):
    """Message response."""
    id: UUID
    conversation_id: UUID
    sender_id: UUID
    sender_email: Optional[str] = None
    sender_name: Optional[str] = None
    
    created_at: datetime
    edited_at: Optional[datetime] = None
    is_deleted: bool = False
    
    # Media attachments
    media: List[MediaResponse] = []
    
    # Read receipts
    read_by_count: int = 0

    model_config = ConfigDict(from_attributes=True)


class MessageDetailResponse(MessageResponse):
    """Detailed message response with full info."""
    read_receipts: List["ReadReceiptResponse"] = []

    model_config = ConfigDict(from_attributes=True)


class MessageListResponse(PaginatedResponse):
    """Paginated list of messages."""
    items: List[MessageResponse]

    model_config = ConfigDict(from_attributes=True)


# ============================================================================
# READ RECEIPT SCHEMAS
# ============================================================================

class ReadReceiptResponse(BaseModel):
    """Read receipt response."""
    message_id: UUID
    user_id: UUID
    user_email: Optional[str] = None
    user_name: Optional[str] = None
    status: MessageStatusEnum
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ============================================================================
# CONVERSATION SCHEMAS
# ============================================================================

class ConversationBase(BaseModel):
    """Base conversation schema."""
    name: Optional[str] = None
    type: ConversationTypeEnum = ConversationTypeEnum.DIRECT

    model_config = ConfigDict(from_attributes=True)


class ConversationCreate(ConversationBase):
    """Request to create a conversation."""
    participant_ids: Optional[List[UUID]] = None  # For group chats
    
    # Direct chat specific
    other_user_id: Optional[UUID] = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: Optional[str], info) -> Optional[str]:
        if v and len(v) > 120:
            raise ValueError("Conversation name too long (max 120 characters)")
        
        # Group chats should have a name
        if info.data.get("type") == ConversationTypeEnum.GROUP and not v:
            raise ValueError("Group conversations must have a name")
        
        return v

    model_config = ConfigDict(from_attributes=True)


class ConversationUpdate(BaseModel):
    """Request to update a conversation."""
    name: Optional[str] = None
    is_archived: Optional[bool] = None

    model_config = ConfigDict(from_attributes=True)


class ConversationResponse(ConversationBase):
    """Conversation response."""
    id: UUID
    created_by: UUID
    created_at: datetime
    updated_at: datetime
    is_archived: bool = False
    
    # Participation info
    participant_count: int = 0
    last_message_preview: Optional[str] = None
    last_message_at: Optional[datetime] = None
    unread_count: int = 0

    model_config = ConfigDict(from_attributes=True)


class ConversationDetailResponse(ConversationResponse):
    """Detailed conversation response."""
    participants: List[ParticipantResponse] = []
    last_message: Optional[MessageResponse] = None

    model_config = ConfigDict(from_attributes=True)


class ConversationListResponse(PaginatedResponse):
    """Paginated list of conversations."""
    items: List[ConversationResponse]

    model_config = ConfigDict(from_attributes=True)


# ============================================================================
# SEARCH SCHEMAS
# ============================================================================

class SearchConversationsRequest(BaseModel):
    """Request to search conversations."""
    query: str = Field(..., min_length=1, max_length=100)
    skip: int = Field(default=0, ge=0)
    limit: int = Field(default=20, ge=1, le=100)

    model_config = ConfigDict(from_attributes=True)


class SearchMessagesRequest(BaseModel):
    """Request to search messages in a conversation."""
    query: str = Field(..., min_length=1, max_length=100)
    conversation_id: UUID
    skip: int = Field(default=0, ge=0)
    limit: int = Field(default=20, ge=1, le=100)

    model_config = ConfigDict(from_attributes=True)


# ============================================================================
# WEBSOCKET SCHEMAS
# ============================================================================

class WSMessage(BaseModel):
    """Base WebSocket message."""
    type: WSMessageTypeEnum
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    user_id: Optional[UUID] = None
    conversation_id: Optional[UUID] = None

    model_config = ConfigDict(from_attributes=True)


class WSSendMessage(WSMessage):
    """WebSocket message: Send new message."""
    type: WSMessageTypeEnum = WSMessageTypeEnum.MESSAGE_SEND
    content: str = Field(..., min_length=1, max_length=5000)
    message_type: MessageTypeEnum = MessageTypeEnum.TEXT
    reply_to_id: Optional[UUID] = None

    model_config = ConfigDict(from_attributes=True)


class WSReadMessage(WSMessage):
    """WebSocket message: Mark messages as read."""
    type: WSMessageTypeEnum = WSMessageTypeEnum.MESSAGE_READ
    message_id: UUID

    model_config = ConfigDict(from_attributes=True)


class WSTypingStart(WSMessage):
    """WebSocket message: User started typing."""
    type: WSMessageTypeEnum = WSMessageTypeEnum.TYPING_START

    model_config = ConfigDict(from_attributes=True)


class WSTypingStop(WSMessage):
    """WebSocket message: User stopped typing."""
    type: WSMessageTypeEnum = WSMessageTypeEnum.TYPING_STOP

    model_config = ConfigDict(from_attributes=True)


class WSUserOnline(WSMessage):
    """WebSocket message: User came online."""
    type: WSMessageTypeEnum = WSMessageTypeEnum.USER_ONLINE

    model_config = ConfigDict(from_attributes=True)


class WSUserOffline(WSMessage):
    """WebSocket message: User went offline."""
    type: WSMessageTypeEnum = WSMessageTypeEnum.USER_OFFLINE

    model_config = ConfigDict(from_attributes=True)


class WSMessageReceived(BaseModel):
    """WebSocket message: Server broadcasts to client."""
    type: WSMessageTypeEnum
    data: dict  # Flexible data structure for different message types
    timestamp: datetime = Field(default_factory=datetime.utcnow)

    model_config = ConfigDict(from_attributes=True)


# ============================================================================
# PRESENCE SCHEMAS
# ============================================================================

class UserPresenceResponse(BaseModel):
    """User presence response."""
    user_id: UUID
    status: UserPresenceStatusEnum
    active_conversation_id: Optional[UUID] = None
    last_seen_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


# ============================================================================
# NOTIFICATION SCHEMAS
# ============================================================================

class ChatNotificationResponse(BaseModel):
    """Chat notification response."""
    id: UUID
    conversation_id: UUID
    message_id: UUID
    notification_type: str
    triggered_by_email: Optional[str] = None
    is_read: bool
    created_at: datetime
    read_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


# Fix circular import
from typing import Generic, TypeVar

T = TypeVar("T")


class PaginatedResponse(BaseModel, Generic[T]):
    """Generic paginated response wrapper."""
    items: List[T]
    total: int
    skip: int
    limit: int

    @property
    def has_more(self) -> bool:
        return (self.skip + self.limit) < self.total

    model_config = ConfigDict(from_attributes=True)
