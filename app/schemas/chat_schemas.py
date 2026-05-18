"""
Pydantic Schemas for Chat System - app/schemas/chat_schemas.py

Request/Response models for:
- Conversations (CRUD, list, archive)
- Messages (send, edit, delete, search, pagination)
- Participants (add, remove, change role)
- Media (upload metadata)
- Real-time events (typing, read receipts, online status)
- WebSocket events
"""

from datetime import datetime
from enum import Enum
from typing import Generic, List, Optional, TypeVar, Any, Dict
from uuid import UUID

from pydantic import BaseModel, Field, validator, EmailStr


# ===========================================================
# ENUMS & TYPE VARIABLES
# ===========================================================

class ConversationType(str, Enum):
    DIRECT = "direct"
    GROUP = "group"


class MessageStatus(str, Enum):
    SENT = "sent"
    DELIVERED = "delivered"
    READ = "read"


class ParticipantRole(str, Enum):
    ADMIN = "admin"
    MODERATOR = "moderator"
    MEMBER = "member"


class MediaType(str, Enum):
    IMAGE = "image"
    FILE = "file"
    VIDEO = "video"
    AUDIO = "audio"


class WebSocketEventType(str, Enum):
    """Real-time WebSocket event types"""
    MESSAGE_SENT = "message.sent"
    MESSAGE_EDITED = "message.edited"
    MESSAGE_DELETED = "message.deleted"
    TYPING_START = "typing.start"
    TYPING_STOP = "typing.stop"
    READ_RECEIPT = "read.receipt"
    USER_ONLINE = "user.online"
    USER_OFFLINE = "user.offline"
    PARTICIPANT_JOINED = "participant.joined"
    PARTICIPANT_LEFT = "participant.left"
    CONVERSATION_CREATED = "conversation.created"
    CONVERSATION_ARCHIVED = "conversation.archived"
    PARTICIPANT_ROLE_CHANGED = "participant.role_changed"


T = TypeVar("T")


# ===========================================================
# PAGINATION & COMMON MODELS
# ===========================================================

class PaginationParams(BaseModel):
    """Standard pagination request parameters"""
    skip: int = Field(0, ge=0, description="Number of items to skip")
    limit: int = Field(50, ge=1, le=100, description="Number of items to return")


class PaginatedResponse(BaseModel, Generic[T]):
    """Generic paginated response"""
    total: int
    skip: int
    limit: int
    items: List[T]


# ===========================================================
# USER REPRESENTATION IN CHAT
# ===========================================================

class UserInChat(BaseModel):
    """User representation in chat context (minimal info)"""
    id: UUID
    first_name: str
    last_name: str
    email: str
    property_id: Optional[UUID] = None

    class Config:
        from_attributes = True


# ===========================================================
# MEDIA & ATTACHMENT SCHEMAS
# ===========================================================

class MessageMediaResponse(BaseModel):
    """Media attachment in message"""
    id: UUID
    media_type: MediaType
    original_filename: str
    file_size_bytes: int
    mime_type: str
    storage_key: str
    thumbnail_key: Optional[str] = None
    width: Optional[int] = None
    height: Optional[int] = None
    duration_seconds: Optional[float] = None  # for audio
    created_at: datetime
    
    class Config:
        from_attributes = True


class MediaUploadRequest(BaseModel):
    """Media upload request metadata"""
    media_type: MediaType = Field(..., description="Type of media")
    mime_type: str = Field(..., description="MIME type (e.g., image/jpeg)")
    file_size_bytes: int = Field(..., gt=0, description="File size in bytes")
    original_filename: str = Field(..., description="Original filename")
    width: Optional[int] = None
    height: Optional[int] = None
    duration_seconds: Optional[float] = None
    
    @validator('file_size_bytes')
    def validate_file_size(cls, v):
        """Validate file size limits"""
        # 50MB limit
        if v > 50 * 1024 * 1024:
            raise ValueError("File size must not exceed 50MB")
        if v < 1:
            raise ValueError("File size must be at least 1 byte")
        return v


# ===========================================================
# MESSAGE SCHEMAS
# ===========================================================

class MessageStatusUpdate(BaseModel):
    """Real-time message status update"""
    message_id: UUID
    user_id: UUID
    status: MessageStatus
    status_at: datetime


class MessageInConversation(BaseModel):
    """Message in conversation list (with sender)"""
    id: UUID
    conversation_id: UUID
    sender: UserInChat
    content: str
    reply_to_id: Optional[UUID] = None
    media: List[MessageMediaResponse] = []
    mentions: Optional[Dict[str, str]] = None  # user_id -> username
    edited_at: Optional[datetime] = None
    created_at: datetime
    deleted_at: Optional[datetime] = None  # Will be None if not deleted
    
    class Config:
        from_attributes = True


class MessageCreateRequest(BaseModel):
    """Request to send a message"""
    conversation_id: UUID
    content: str = Field(..., min_length=1, max_length=5000)
    reply_to_id: Optional[UUID] = None
    media_ids: Optional[List[UUID]] = []  # Reference uploaded media
    mentions: Optional[Dict[str, str]] = None  # {"user_id": "@username"}


class MessageEditRequest(BaseModel):
    """Request to edit a message"""
    content: str = Field(..., min_length=1, max_length=5000)


class MessageDeleteRequest(BaseModel):
    """Request to delete a message"""
    hard_delete: bool = False  # If True, hard delete. Otherwise soft delete


class MessageSearchRequest(BaseModel):
    """Search messages in a conversation"""
    query: str = Field(..., min_length=1)
    conversation_id: Optional[UUID] = None
    sender_id: Optional[UUID] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    pagination: PaginationParams = Field(default_factory=PaginationParams)


class MessageResponse(BaseModel):
    """Full message response"""
    id: UUID
    conversation_id: UUID
    sender: UserInChat
    content: str
    reply_to_id: Optional[UUID] = None
    media: List[MessageMediaResponse] = []
    read_by_count: int = 0  # Denormalized for UI
    delivery_status: Optional[MessageStatus] = None  # Current user's delivery status
    created_at: datetime
    edited_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True


# ===========================================================
# CONVERSATION SCHEMAS
# ===========================================================

class ParticipantResponse(BaseModel):
    """Conversation participant"""
    id: UUID
    user: UserInChat
    role: ParticipantRole
    joined_at: datetime
    last_read_at: Optional[datetime] = None
    is_muted: bool = False
    
    class Config:
        from_attributes = True


class ConversationListItem(BaseModel):
    """Conversation in list (with latest message preview)"""
    id: UUID
    type: ConversationType
    name: Optional[str] = None
    avatar_url: Optional[str] = None
    last_message: Optional[MessageInConversation] = None
    other_participants: List[UserInChat] = []
    participant_count: int
    unread_count: int
    is_archived: bool
    is_muted: bool
    updated_at: datetime
    property_id: Optional[UUID] = None

    class Config:
        from_attributes = True


class ConversationDetailResponse(BaseModel):
    """Full conversation details"""
    id: UUID
    tenant_id: UUID
    property_id: UUID
    type: ConversationType
    name: Optional[str] = None
    description: Optional[str] = None
    avatar_url: Optional[str] = None
    created_by: Optional[UserInChat] = None
    participants: List[ParticipantResponse]
    is_archived: bool
    is_muted: bool
    participant_count: int
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


class CreateDirectConversationRequest(BaseModel):
    """Request to create direct conversation"""
    other_user_id: UUID


class CreateGroupConversationRequest(BaseModel):
    """Request to create group conversation"""
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    participant_ids: List[UUID] = Field(..., min_items=2)  # At least 2 people
    avatar_url: Optional[str] = None


class UpdateConversationRequest(BaseModel):
    """Request to update conversation"""
    name: Optional[str] = None
    description: Optional[str] = None
    avatar_url: Optional[str] = None


class AddParticipantRequest(BaseModel):
    """Request to add participant to group"""
    user_id: UUID


class RemoveParticipantRequest(BaseModel):
    """Request to remove participant from group"""
    user_id: UUID


class ChangeParticipantRoleRequest(BaseModel):
    """Request to change participant role"""
    user_id: UUID
    new_role: ParticipantRole


class MuteConversationRequest(BaseModel):
    """Request to mute/unmute conversation"""
    is_muted: bool


# ===========================================================
# REAL-TIME WEBSOCKET EVENT SCHEMAS
# ===========================================================

class WebSocketEvent(BaseModel):
    """Base WebSocket event"""
    type: WebSocketEventType
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    data: Dict[str, Any] = {}


class TypingIndicatorEvent(BaseModel):
    """Typing indicator event data"""
    conversation_id: UUID
    user_id: UUID
    user: UserInChat


class MessageSentEvent(BaseModel):
    """Message sent event data"""
    message: MessageResponse


class ReadReceiptEvent(BaseModel):
    """Read receipt event data"""
    message_id: UUID
    user_id: UUID
    status: MessageStatus


class UserPresenceEvent(BaseModel):
    """User online/offline event data"""
    user_id: UUID
    conversation_id: Optional[UUID] = None  # None if general presence
    is_online: bool


class ParticipantJoinedEvent(BaseModel):
    """Participant joined group event"""
    conversation_id: UUID
    participant: ParticipantResponse


class ParticipantLeftEvent(BaseModel):
    """Participant left group event"""
    conversation_id: UUID
    user_id: UUID


# ===========================================================
# WEBSOCKET REQUEST/RESPONSE MODELS
# ===========================================================

class WebSocketConnectRequest(BaseModel):
    """Initial WebSocket connection request"""
    token: str = Field(..., description="JWT token")
    conversation_id: UUID = Field(..., description="Conversation to join")


class WebSocketConnectResponse(BaseModel):
    """WebSocket connection response"""
    success: bool
    message: str
    conversation_id: UUID
    unread_count: int
    online_members: List[UserInChat]


class SendMessageViaWebSocketRequest(BaseModel):
    """Send message via WebSocket"""
    content: str = Field(..., min_length=1, max_length=5000)
    reply_to_id: Optional[UUID] = None
    media_ids: Optional[List[UUID]] = []


class MarkAsReadRequest(BaseModel):
    """Mark message as read"""
    message_id: UUID


class MarkConversationAsReadRequest(BaseModel):
    """Mark all messages in conversation as read"""
    conversation_id: UUID


class TypingStartRequest(BaseModel):
    """Start typing indicator"""
    pass  # Just presence in the message


class TypingStopRequest(BaseModel):
    """Stop typing indicator"""
    pass


# ===========================================================
# BATCH/BULK OPERATION SCHEMAS
# ===========================================================

class BulkMarkAsReadRequest(BaseModel):
    """Bulk mark messages as read"""
    message_ids: List[UUID] = Field(..., min_items=1)


class BulkDeleteRequest(BaseModel):
    """Bulk delete messages"""
    message_ids: List[UUID] = Field(..., min_items=1)
    hard_delete: bool = False


# ===========================================================
# NOTIFICATION SCHEMAS
# ===========================================================

class ChatNotificationResponse(BaseModel):
    """Chat notification response"""
    id: UUID
    user_id: UUID
    conversation_id: UUID
    message_id: Optional[UUID] = None
    title: str
    body: str
    is_read: bool
    created_at: datetime
    read_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True


# ===========================================================
# STATISTICS & ANALYTICS SCHEMAS
# ===========================================================

class ConversationStatsResponse(BaseModel):
    """Conversation statistics"""
    conversation_id: UUID
    total_messages: int
    total_participants: int
    active_participants: int
    average_response_time_seconds: Optional[float] = None
    last_activity_at: Optional[datetime] = None


class UserChatStatsResponse(BaseModel):
    """User chat statistics"""
    user_id: UUID
    total_conversations: int
    total_messages_sent: int
    unread_conversations: int
    unread_messages: int
    last_active_at: Optional[datetime] = None
