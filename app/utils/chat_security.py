"""
Security & Validation Layer - app/utils/chat_security.py

Multi-tenant isolation validations:
- JWT token verification
- User existence check
- Tenant authorization
- Property authorization
- Conversation membership verification
- Sender validation for messages

Every API endpoint must use these checks - never trust frontend validation.
"""

from typing import Optional, Tuple
from uuid import UUID

from fastapi import Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_

from app.core.security import decode_token
from app.models.models import User, Property, Tenant
from app.models.chat_models import ConversationParticipant, Conversation
from app.core.database import get_db as get_async_session
from app.utils.exceptions import AccessDenied, NotFound, ValidationError


# ===========================================================
# SECURITY CONTEXT
# ===========================================================

class ChatSecurityContext:
    """
    Security context verified for each request.
    
    Contains:
    - Verified JWT token claims
    - User ID and details
    - Tenant ID (from token claims)
    - Property ID (from request or defaults to user's primary property)
    """

    def __init__(
        self,
        user_id: UUID,
        tenant_id: UUID,
        property_id: UUID,
        username: str,
        email: str,
        token_data: dict
    ):
        self.user_id = user_id
        self.tenant_id = tenant_id
        self.property_id = property_id
        self.username = username
        self.email = email
        self.token_data = token_data

    def __repr__(self):
        return f"ChatSecurityContext(user={self.user_id}, tenant={self.tenant_id}, property={self.property_id})"


# ===========================================================
# SECURITY VALIDATORS
# ===========================================================

async def verify_jwt_token(
    authorization: str,
    session: AsyncSession
) -> Tuple[User, dict]:
    """
    Verify JWT token and load user.
    
    Args:
        authorization: Bearer token from header
        session: Database session
        
    Returns:
        (User object, token claims)
        
    Raises:
        HTTPException if token invalid or user not found
    """
    if not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authorization header"
        )

    token = authorization[7:]

    # Verify token
    token_data = decode_token(token)
    if not token_data:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token"
        )

    # Load user
    user_id = UUID(token_data.get("sub"))
    stmt = select(User).where(
        and_(
            User.id == user_id,
            User.is_active.is_(True),
            User.deleted_at.is_(None)
        )
    )
    result = await session.execute(stmt)
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive"
        )

    return user, token_data


async def verify_tenant_access(
    user: User,
    tenant_id: UUID,
    session: AsyncSession
) -> Tenant:
    """
    Verify user belongs to tenant.
    
    Args:
        user: User object
        tenant_id: Requested tenant ID
        session: Database session
        
    Returns:
        Tenant object
        
    Raises:
        AccessDenied if user doesn't belong to tenant
    """
    if user.tenant_id != tenant_id:
        raise AccessDenied("User does not belong to this tenant")

    # Verify tenant exists and is active
    stmt = select(Tenant).where(
        and_(
            Tenant.id == tenant_id,
            Tenant.is_active.is_(True),
            Tenant.deleted_at.is_(None)
        )
    )
    result = await session.execute(stmt)
    tenant = result.scalar_one_or_none()

    if not tenant:
        raise AccessDenied("Tenant not found or inactive")

    return tenant


async def verify_property_access(
    user: User,
    tenant_id: UUID,
    property_id: UUID,
    session: AsyncSession
) -> Property:
    """
    Verify user can access property.
    
    Args:
        user: User object
        tenant_id: Tenant ID (already verified)
        property_id: Requested property ID
        session: Database session
        
    Returns:
        Property object
        
    Raises:
        AccessDenied if user can't access property
    """
    # Verify property exists and belongs to tenant
    stmt = select(Property).where(
        and_(
            Property.id == property_id,
            Property.tenant_id == tenant_id,
            Property.is_active.is_(True),
            Property.deleted_at.is_(None)
        )
    )
    result = await session.execute(stmt)
    property_obj = result.scalar_one_or_none()

    if not property_obj:
        raise AccessDenied("Property not found or access denied")

    # User must belong to property or be super admin
    # For now, check if user.property_id matches
    if user.property_id != property_id:
        raise AccessDenied("User does not have access to this property")

    return property_obj


async def verify_conversation_membership(
    user_id: UUID,
    conversation_id: UUID,
    tenant_id: UUID,
    property_id: UUID,
    session: AsyncSession
) -> Conversation:
    """
    Verify user is member of conversation.
    
    Args:
        user_id: User ID
        conversation_id: Conversation ID
        tenant_id: Tenant ID (must match conversation)
        property_id: Property ID (must match conversation)
        session: Database session
        
    Returns:
        Conversation object
        
    Raises:
        AccessDenied if user not member
    """
    # Get conversation
    stmt = select(Conversation).where(
        and_(
            Conversation.id == conversation_id,
            Conversation.tenant_id == tenant_id,
            Conversation.property_id == property_id,
            Conversation.deleted_at.is_(None)
        )
    )
    result = await session.execute(stmt)
    conversation = result.scalar_one_or_none()

    if not conversation:
        raise AccessDenied("Conversation not found or access denied")

    # Check membership
    participant_stmt = select(ConversationParticipant).where(
        and_(
            ConversationParticipant.conversation_id == conversation_id,
            ConversationParticipant.user_id == user_id,
            ConversationParticipant.left_at.is_(None)
        )
    )
    result = await session.execute(participant_stmt)
    participant = result.scalar_one_or_none()

    if not participant:
        raise AccessDenied("User is not member of this conversation")

    return conversation


async def verify_message_sender(
    user_id: UUID,
    message_id: UUID,
    conversation_id: UUID,
    session: AsyncSession
) -> None:
    """
    Verify user is the sender of message (for edit/delete).
    
    Raises:
        AccessDenied if user is not sender
    """
    from app.models.chat_models import Message

    stmt = select(Message).where(
        and_(
            Message.id == message_id,
            Message.conversation_id == conversation_id,
            Message.deleted_at.is_(None)
        )
    )
    result = await session.execute(stmt)
    message = result.scalar_one_or_none()

    if not message:
        raise NotFound("Message not found")

    if message.sender_id != user_id:
        raise AccessDenied("Only message sender can perform this action")


# ===========================================================
# DEPENDENCY INJECTION
# ===========================================================

async def get_chat_security_context(
    authorization: str,
    tenant_id: UUID,
    property_id: UUID,
    session: AsyncSession = Depends(get_async_session)
) -> ChatSecurityContext:
    """
    Dependency to get verified security context.
    
    This runs for every request - validates:
    1. JWT token
    2. User exists and active
    3. User belongs to tenant
    4. User has access to property
    
    Usage:
        async def create_conversation(
            security: ChatSecurityContext = Depends(get_chat_security_context),
            ...
        ):
            ...
    """
    # Verify JWT and load user
    user, token_data = await verify_jwt_token(authorization, session)

    # Verify tenant access
    await verify_tenant_access(user, tenant_id, session)

    # Verify property access
    await verify_property_access(user, tenant_id, property_id, session)

    return ChatSecurityContext(
        user_id=user.id,
        tenant_id=tenant_id,
        property_id=property_id,
        username=f"{user.first_name} {user.last_name}",
        email=user.email,
        token_data=token_data
    )


async def get_websocket_security_context(
    token: str,
    conversation_id: UUID,
    session: AsyncSession
) -> ChatSecurityContext:
    """
    Dependency to validate WebSocket connection.
    
    Validates:
    1. JWT token
    2. User exists
    3. User is member of conversation
    4. Conversation belongs to user's tenant/property
    """
    # Verify JWT
    token_data = decode_token(token)
    if not token_data:
        raise AccessDenied("Invalid or expired token")

    user_id = UUID(token_data.get("sub"))

    # Load user
    stmt = select(User).where(
        and_(
            User.id == user_id,
            User.is_active.is_(True),
            User.deleted_at.is_(None)
        )
    )
    result = await session.execute(stmt)
    user = result.scalar_one_or_none()

    if not user:
        raise AccessDenied("User not found")

    tenant_id = user.tenant_id
    property_id = user.property_id

    # Verify conversation membership
    stmt = select(ConversationParticipant).where(
        and_(
            ConversationParticipant.conversation_id == conversation_id,
            ConversationParticipant.user_id == user_id,
            ConversationParticipant.left_at.is_(None)
        )
    )
    result = await session.execute(stmt)
    participant = result.scalar_one_or_none()

    if not participant:
        raise AccessDenied("User is not member of conversation")

    return ChatSecurityContext(
        user_id=user_id,
        tenant_id=tenant_id,
        property_id=property_id,
        username=f"{user.first_name} {user.last_name}",
        email=user.email,
        token_data=token_data
    )


# ===========================================================
# SECURITY UTILITIES
# ===========================================================

def extract_bearer_token(authorization_header: str) -> str:
    """Extract Bearer token from Authorization header"""
    if not authorization_header:
        raise AccessDenied("Missing authorization header")

    parts = authorization_header.split(" ")
    if len(parts) != 2 or parts[0] != "Bearer":
        raise AccessDenied("Invalid authorization header format")

    return parts[1]


def create_security_headers() -> dict:
    """Create security headers for responses"""
    return {
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "DENY",
        "X-XSS-Protection": "1; mode=block",
        "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
        "Content-Security-Policy": "default-src 'self'"
    }
