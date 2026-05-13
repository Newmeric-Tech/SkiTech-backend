"""
Schemas Module - Initialization

Exports all Pydantic schemas for API validation.
"""

from .common import (
    ErrorResponse,
    PaginatedResponse,
    PaginationParams,
    SuccessResponse,
    TimestampedModel,
)
from .chat import (
    # Enums
    ConversationTypeEnum,
    MessageTypeEnum,
    ParticipantRoleEnum,
    MessageStatusEnum,
    UserPresenceStatusEnum,
    WSMessageTypeEnum,
    # Participant
    ParticipantCreate,
    ParticipantResponse,
    ParticipantUpdate,
    # Media
    MediaResponse,
    FileUploadResponse,
    # Message
    MessageCreate,
    MessageResponse,
    MessageDetailResponse,
    MessageListResponse,
    MessageUpdate,
    ReadReceiptResponse,
    # Conversation
    ConversationCreate,
    ConversationResponse,
    ConversationDetailResponse,
    ConversationListResponse,
    ConversationUpdate,
    # Search
    SearchConversationsRequest,
    SearchMessagesRequest,
    # WebSocket
    WSMessage,
    WSSendMessage,
    WSReadMessage,
    WSTypingStart,
    WSTypingStop,
    WSUserOnline,
    WSUserOffline,
    WSMessageReceived,
    # Presence
    UserPresenceResponse,
    # Notifications
    ChatNotificationResponse,
)
from .governance import (
    GovernanceWorkflowCreate,
    GovernanceWorkflowResponse,
    WorkflowInstanceApprove,
    WorkflowInstanceCreate,
    WorkflowInstanceReject,
    WorkflowInstanceResponse,
)
from .property import (
    PropertyCreate,
    PropertyResponse,
    PropertySummary,
    PropertyUpdate,
)
from .user import (
    LoginRequest,
    RefreshTokenRequest,
    TokenResponse,
    UserCreate,
    UserResponse,
    UserUpdate,
)
from .workforce import (
    WorkforceCreate,
    WorkforceSummary,
    WorkforceUpdate,
    WorkforceResponse,
)
from .kra import (
    DailyKRACreate,
    DailyKRAResponse,
    DailyKRAUpdate,
    DailyKRAListResponse,
    WeeklyKRACreate,
    WeeklyKRAResponse,
    WeeklyKRAUpdate,
    WeeklyKRAListResponse,
)
from .attendance import (
    GeolocationData,
    PunchInRequest,
    PunchOutRequest,
    AttendanceRecordResponse,
    PunchInResponse,
    PunchOutResponse,
    PropertyGeofenceCreate,
    PropertyGeofenceResponse,
    GeolocationHistoryFilter,
)

__all__ = [
    # Common
    "PaginationParams",
    "PaginatedResponse",
    "TimestampedModel",
    "ErrorResponse",
    "SuccessResponse",
    # Chat - Enums
    "ConversationTypeEnum",
    "MessageTypeEnum",
    "ParticipantRoleEnum",
    "MessageStatusEnum",
    "UserPresenceStatusEnum",
    "WSMessageTypeEnum",
    # Chat - Participant
    "ParticipantCreate",
    "ParticipantResponse",
    "ParticipantUpdate",
    # Chat - Media
    "MediaResponse",
    "FileUploadResponse",
    # Chat - Message
    "MessageCreate",
    "MessageResponse",
    "MessageDetailResponse",
    "MessageListResponse",
    "MessageUpdate",
    "ReadReceiptResponse",
    # Chat - Conversation
    "ConversationCreate",
    "ConversationResponse",
    "ConversationDetailResponse",
    "ConversationListResponse",
    "ConversationUpdate",
    # Chat - Search
    "SearchConversationsRequest",
    "SearchMessagesRequest",
    # Chat - WebSocket
    "WSMessage",
    "WSSendMessage",
    "WSReadMessage",
    "WSTypingStart",
    "WSTypingStop",
    "WSUserOnline",
    "WSUserOffline",
    "WSMessageReceived",
    # Chat - Presence
    "UserPresenceResponse",
    # Chat - Notifications
    "ChatNotificationResponse",
    # User
    "UserCreate",
    "UserResponse",
    "UserUpdate",
    "LoginRequest",
    "TokenResponse",
    "RefreshTokenRequest",
    # Property
    "PropertyCreate",
    "PropertyResponse",
    "PropertyUpdate",
    "PropertySummary",
    # Workforce
    "WorkforceCreate",
    "WorkforceResponse",
    "WorkforceUpdate",
    "WorkforceSummary",
    # Governance
    "GovernanceWorkflowCreate",
    "GovernanceWorkflowResponse",
    "WorkflowInstanceCreate",
    "WorkflowInstanceResponse",
    "WorkflowInstanceApprove",
    "WorkflowInstanceReject",
    # KRA
    "DailyKRACreate",
    "DailyKRAResponse",
    "DailyKRAUpdate",
    "DailyKRAListResponse",
    "WeeklyKRACreate",
    "WeeklyKRAResponse",
    "WeeklyKRAUpdate",
    "WeeklyKRAListResponse",
    # Attendance & Geolocation
    "GeolocationData",
    "PunchInRequest",
    "PunchOutRequest",
    "AttendanceRecordResponse",
    "PunchInResponse",
    "PunchOutResponse",
    "PropertyGeofenceCreate",
    "PropertyGeofenceResponse",
    "GeolocationHistoryFilter",
]
