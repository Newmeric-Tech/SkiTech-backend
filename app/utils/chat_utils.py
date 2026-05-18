"""
Chat System Utilities & Helpers - app/utils/chat_utils.py

Utility functions for:
- UUID validation and conversion
- Pagination helpers
- Media type detection
- Date/time formatting
- Error messages
"""

from uuid import UUID
from typing import Optional, Tuple
from datetime import datetime
from enum import Enum


# ===========================================================
# UUID UTILITIES
# ===========================================================

def str_to_uuid(value: str) -> UUID:
    """Convert string to UUID"""
    try:
        return UUID(value)
    except ValueError:
        raise ValueError(f"Invalid UUID format: {value}")


def uuid_to_str(value: UUID) -> str:
    """Convert UUID to string"""
    return str(value)


def validate_uuid(value: str) -> bool:
    """Check if string is valid UUID"""
    try:
        UUID(value)
        return True
    except ValueError:
        return False


# ===========================================================
# PAGINATION UTILITIES
# ===========================================================

def validate_pagination_params(skip: int, limit: int) -> Tuple[int, int]:
    """Validate and normalize pagination parameters"""
    skip = max(0, skip)
    limit = max(1, min(limit, 100))  # Cap at 100
    return skip, limit


def calculate_offset(page: int, page_size: int) -> int:
    """Calculate offset from page number"""
    if page < 1:
        page = 1
    return (page - 1) * page_size


def get_pagination_meta(
    total: int,
    skip: int,
    limit: int
) -> dict:
    """Generate pagination metadata"""
    total_pages = (total + limit - 1) // limit  # Ceiling division
    current_page = (skip // limit) + 1

    return {
        "total": total,
        "skip": skip,
        "limit": limit,
        "total_pages": total_pages,
        "current_page": current_page,
        "has_next": skip + limit < total,
        "has_previous": skip > 0
    }


# ===========================================================
# MEDIA TYPE UTILITIES
# ===========================================================

class MediaTypeInfo(Enum):
    """Media type information"""
    IMAGE = {"types": ["image/jpeg", "image/png", "image/webp", "image/gif"], "max_size": 10 * 1024 * 1024}
    FILE = {"types": ["application/pdf", "application/msword", "text/plain"], "max_size": 50 * 1024 * 1024}
    VIDEO = {"types": ["video/mp4", "video/quicktime"], "max_size": 100 * 1024 * 1024}
    AUDIO = {"types": ["audio/mpeg", "audio/wav", "audio/ogg"], "max_size": 20 * 1024 * 1024}


def detect_media_type(mime_type: str) -> str:
    """Detect media type from MIME type"""
    mime_lower = mime_type.lower()

    if mime_lower.startswith("image/"):
        return "image"
    elif mime_lower.startswith("video/"):
        return "video"
    elif mime_lower.startswith("audio/"):
        return "audio"
    else:
        return "file"


def validate_media_mime_type(mime_type: str) -> bool:
    """Check if MIME type is allowed"""
    allowed_types = []
    for media_type in MediaTypeInfo:
        allowed_types.extend(media_type.value["types"])

    return mime_type.lower() in allowed_types


def get_max_file_size(media_type: str) -> int:
    """Get max file size for media type"""
    try:
        return MediaTypeInfo[media_type.upper()].value["max_size"]
    except KeyError:
        return 50 * 1024 * 1024  # Default 50MB


def validate_file_size(file_size_bytes: int, media_type: str) -> bool:
    """Validate file size"""
    max_size = get_max_file_size(media_type)
    return file_size_bytes <= max_size


# ===========================================================
# DATE/TIME UTILITIES
# ===========================================================

def get_current_timestamp() -> datetime:
    """Get current UTC timestamp"""
    return datetime.utcnow()


def format_timestamp(dt: datetime) -> str:
    """Format datetime to ISO string"""
    return dt.isoformat() + "Z" if dt else None


def parse_timestamp(ts: str) -> datetime:
    """Parse ISO timestamp"""
    try:
        if ts.endswith("Z"):
            ts = ts[:-1]
        return datetime.fromisoformat(ts)
    except ValueError:
        return None


def get_relative_time_string(dt: datetime) -> str:
    """Get human-readable relative time (e.g., '5 minutes ago')"""
    now = datetime.utcnow()
    delta = now - dt

    if delta.total_seconds() < 60:
        return "Just now"
    elif delta.total_seconds() < 3600:
        minutes = int(delta.total_seconds() / 60)
        return f"{minutes}m ago"
    elif delta.total_seconds() < 86400:
        hours = int(delta.total_seconds() / 3600)
        return f"{hours}h ago"
    elif delta.total_seconds() < 604800:
        days = int(delta.total_seconds() / 86400)
        return f"{days}d ago"
    else:
        return dt.strftime("%Y-%m-%d")


# ===========================================================
# STRING UTILITIES
# ===========================================================

def truncate_string(s: str, max_length: int = 100, suffix: str = "...") -> str:
    """Truncate string to max length"""
    if len(s) <= max_length:
        return s
    return s[:max_length - len(suffix)] + suffix


def sanitize_message_content(content: str) -> str:
    """Sanitize message content (remove XSS, etc.)"""
    # TODO: Implement HTML sanitization
    # For now, just strip leading/trailing whitespace
    return content.strip()


def extract_mentions(content: str) -> list:
    """Extract @mentions from message content"""
    # Simple regex: @username or @user_id
    import re
    matches = re.findall(r'@([a-zA-Z0-9_-]+)', content)
    return matches


def extract_urls(content: str) -> list:
    """Extract URLs from message content"""
    import re
    url_pattern = r'https?://[^\s]+'
    matches = re.findall(url_pattern, content)
    return matches


# ===========================================================
# ERROR MESSAGE UTILITIES
# ===========================================================

class ChatErrorMessages:
    """Standardized error messages"""
    
    UNAUTHORIZED = "Unauthorized - Invalid or missing token"
    FORBIDDEN = "Forbidden - Access denied"
    NOT_FOUND = "Resource not found"
    
    USER_NOT_FOUND = "User not found"
    CONVERSATION_NOT_FOUND = "Conversation not found"
    MESSAGE_NOT_FOUND = "Message not found"
    MEDIA_NOT_FOUND = "Media not found"
    
    NOT_CONVERSATION_MEMBER = "You are not a member of this conversation"
    NOT_MESSAGE_SENDER = "Only the message sender can perform this action"
    NOT_ADMIN = "Only admins can perform this action"
    
    INVALID_TENANT = "Invalid tenant ID"
    INVALID_PROPERTY = "Invalid property ID"
    INVALID_CONVERSATION_TYPE = "Invalid conversation type"
    
    FILE_TOO_LARGE = "File size exceeds maximum allowed"
    INVALID_FILE_TYPE = "File type not allowed"
    
    MESSAGE_TOO_LONG = "Message exceeds maximum length"
    INVALID_PAGINATION = "Invalid pagination parameters"
    
    INTERNAL_ERROR = "An internal error occurred"


def get_error_message(error_type: str) -> str:
    """Get standardized error message"""
    return getattr(ChatErrorMessages, error_type, ChatErrorMessages.INTERNAL_ERROR)


# ===========================================================
# CONVERSATION UTILITIES
# ===========================================================

def get_conversation_display_name(
    conversation_type: str,
    conversation_name: Optional[str],
    participant_names: list
) -> str:
    """Get display name for conversation"""
    if conversation_type == "group":
        return conversation_name or ", ".join(participant_names[:2]) + ("..." if len(participant_names) > 2 else "")
    else:  # direct
        return participant_names[0] if participant_names else "Unknown"


def format_conversation_summary(
    total_messages: int,
    participant_count: int,
    last_message_time: datetime
) -> dict:
    """Format conversation summary"""
    return {
        "total_messages": total_messages,
        "participant_count": participant_count,
        "last_activity": get_relative_time_string(last_message_time),
        "last_activity_timestamp": format_timestamp(last_message_time)
    }


# ===========================================================
# MESSAGE UTILITIES
# ===========================================================

def format_message_content(content: str, max_preview_length: int = 100) -> dict:
    """Format and prepare message content"""
    return {
        "full_content": content,
        "preview": truncate_string(content, max_preview_length),
        "mentions": extract_mentions(content),
        "urls": extract_urls(content)
    }


def is_message_edited(created_at: datetime, edited_at: datetime) -> bool:
    """Check if message was edited"""
    return edited_at is not None and edited_at > created_at


def get_message_timestamp_display(created_at: datetime, edited_at: Optional[datetime]) -> dict:
    """Get formatted timestamps for message"""
    return {
        "created_at": format_timestamp(created_at),
        "created_at_relative": get_relative_time_string(created_at),
        "edited_at": format_timestamp(edited_at) if edited_at else None,
        "edited_at_relative": get_relative_time_string(edited_at) if edited_at else None,
        "is_edited": is_message_edited(created_at, edited_at)
    }


# ===========================================================
# RATE LIMITING UTILITIES (Future)
# ===========================================================

class RateLimitConfig:
    """Rate limiting configuration"""
    
    # Messages per minute per user
    MESSAGES_PER_MINUTE = 10
    
    # File uploads per hour per user
    UPLOADS_PER_HOUR = 50
    
    # API calls per minute per user
    API_CALLS_PER_MINUTE = 100
    
    # WebSocket messages per second
    WS_MESSAGES_PER_SECOND = 5


def check_rate_limit(
    user_id: str,
    limit_key: str,
    limit: int,
    window_seconds: int
) -> bool:
    """
    Check if user has exceeded rate limit.
    
    TODO: Implement with Redis
    """
    # return redis.incr(f"ratelimit:{user_id}:{limit_key}") <= limit
    pass
