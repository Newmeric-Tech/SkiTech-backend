"""
FastAPI Endpoints for Chat System - app/api/v1/endpoints/chat.py

REST API endpoints for:
- Conversations: List, create, update, archive
- Messages: Send, edit, delete, search, get
- Participants: Add, remove, change role
- Media: Upload, download, delete
- WebSocket: Real-time chat

Every endpoint includes:
- JWT authentication
- Multi-tenant validation
- Property authorization
- Conversation membership checks
- Error handling
- Request/response validation
"""

from datetime import datetime
from io import BytesIO
from typing import List, Optional
from uuid import UUID

from fastapi import (
    APIRouter, Depends, HTTPException, status, UploadFile, File,
    Header, Query, WebSocket, WebSocketDisconnect
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db as get_async_session
from app.utils.chat_security import (
    get_chat_security_context, ChatSecurityContext, get_websocket_security_context,
    verify_conversation_membership, verify_message_sender, extract_bearer_token,
    create_security_headers
)
from app.services.chat_service import (
    ConversationService, ParticipantService, MessageService, MediaService
)
from app.websocket.manager import (
    get_websocket_manager, WebSocketEventType, publish_message_sent_event,
    publish_typing_event, publish_read_receipt_event
)
from app.schemas.chat_schemas import (
    ConversationDetailResponse, ConversationListItem, MessageResponse,
    PaginationParams, CreateDirectConversationRequest,
    CreateGroupConversationRequest, UpdateConversationRequest,
    AddParticipantRequest, RemoveParticipantRequest,
    ChangeParticipantRoleRequest, MuteConversationRequest,
    MessageCreateRequest, MessageEditRequest, SendMessageViaWebSocketRequest,
    TypingStartRequest, TypingStopRequest, MarkAsReadRequest,
    MessageSearchRequest, BulkMarkAsReadRequest, MessageMediaResponse,
    WebSocketConnectResponse, WebSocketEvent, UserInChat,
    ConversationStatsResponse, UserChatStatsResponse
)
from app.utils.exceptions import AccessDenied, NotFound, ValidationError


router = APIRouter(prefix="/chat", tags=["chat"])


# ===========================================================
# CONTACTS ENDPOINT
# ===========================================================

@router.get(
    "/contacts",
    response_model=List[UserInChat],
    summary="Get chat contacts based on caller's role",
)
async def get_chat_contacts(
    tenant_id: UUID = Query(...),
    property_id: Optional[UUID] = Query(None),
    authorization: str = Header(...),
    session: AsyncSession = Depends(get_async_session),
):
    """
    Returns users the caller is allowed to chat with, filtered by role.
    property_id is optional — when omitted, Tenant Admins see contacts
    across all properties in their tenant.

    Role rules:
    - Tenant Admin: other Tenant Admins + Managers (same tenant, optional property filter)
    - Manager:      Tenant Admins + Staff (same property)
    - Staff:        Managers + Staff (same property)
    """
    from app.models.models import User as UserModel, Role as RoleModel
    from sqlalchemy import select, and_

    # Verify JWT + tenant; skip property check when property_id is None
    try:
        from app.utils.chat_security import verify_jwt_token, verify_tenant_access, verify_property_access
        user, token_data = await verify_jwt_token(authorization, session)
        await verify_tenant_access(user, tenant_id, session)
        if property_id is not None:
            await verify_property_access(user, tenant_id, property_id, session)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))

    # Determine caller's role name
    role_stmt = (
        select(RoleModel.name)
        .join(UserModel, UserModel.role_id == RoleModel.id)
        .where(UserModel.id == user.id)
    )
    role_result = await session.execute(role_stmt)
    current_role = role_result.scalar_one_or_none() or ""

    role_map = {
        "Tenant Admin": ["Tenant Admin", "Manager"],
        "Manager":      ["Tenant Admin", "Staff"],
        "Staff":        ["Manager", "Staff"],
    }
    allowed_roles = role_map.get(current_role, ["Tenant Admin", "Manager", "Staff"])

    conditions = [
        UserModel.tenant_id == tenant_id,
        UserModel.is_active.is_(True),
        UserModel.deleted_at.is_(None),
        UserModel.id != user.id,
        RoleModel.name.in_(allowed_roles),
    ]
    # Only filter by property when caller has one (or explicitly passes one)
    if property_id is not None:
        conditions.append(UserModel.property_id == property_id)
    elif user.property_id is not None:
        conditions.append(UserModel.property_id == user.property_id)
    # else: Tenant Admin with no property → see contacts across all properties

    stmt = (
        select(UserModel)
        .join(RoleModel, UserModel.role_id == RoleModel.id)
        .where(and_(*conditions))
        .order_by(UserModel.first_name, UserModel.last_name)
    )
    result = await session.execute(stmt)
    users = result.scalars().all()

    return [
        UserInChat(
            id=u.id,
            first_name=u.first_name or "",
            last_name=u.last_name or "",
            email=u.email,
            property_id=u.property_id,
        )
        for u in users
    ]


# ===========================================================
# CONVERSATION ENDPOINTS
# ===========================================================

@router.get(
    "/conversations",
    response_model=dict,
    summary="List user's conversations",
    responses={401: {"description": "Unauthorized"}}
)
async def list_conversations(
    tenant_id: UUID = Query(..., description="Tenant ID"),
    property_id: UUID = Query(..., description="Property ID"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    include_archived: bool = Query(False),
    authorization: str = Header(...),
    session: AsyncSession = Depends(get_async_session)
):
    """
    Get all conversations for user in property.
    
    Multi-tenant isolation:
    - Only returns conversations from user's property
    - Excludes other tenant/property conversations
    - Verifies user membership
    """
    try:
        security = await get_chat_security_context(authorization, tenant_id, property_id, session)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))

    service = ConversationService(session)
    conversations, total = await service.get_user_conversations(
        user_id=security.user_id,
        tenant_id=security.tenant_id,
        property_id=security.property_id,
        skip=skip,
        limit=limit,
        include_archived=include_archived
    )

    return {
        "total": total,
        "skip": skip,
        "limit": limit,
        "items": conversations
    }


@router.post(
    "/conversations/direct",
    response_model=ConversationDetailResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create or get direct conversation"
)
async def create_direct_conversation(
    tenant_id: UUID = Query(...),
    property_id: UUID = Query(...),
    request: CreateDirectConversationRequest = None,
    authorization: str = Header(...),
    session: AsyncSession = Depends(get_async_session)
):
    """Create new direct conversation or get existing one"""
    try:
        security = await get_chat_security_context(authorization, tenant_id, property_id, session)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))

    if request.other_user_id == security.user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot create conversation with yourself"
        )

    service = ConversationService(session)
    try:
        conversation = await service.create_direct_conversation(
            user_id=security.user_id,
            other_user_id=request.other_user_id,
            tenant_id=security.tenant_id,
            property_id=security.property_id
        )
        return conversation
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.post(
    "/conversations/group",
    response_model=ConversationDetailResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create group conversation"
)
async def create_group_conversation(
    tenant_id: UUID = Query(...),
    property_id: UUID = Query(...),
    request: CreateGroupConversationRequest = None,
    authorization: str = Header(...),
    session: AsyncSession = Depends(get_async_session)
):
    """Create new group conversation"""
    try:
        security = await get_chat_security_context(authorization, tenant_id, property_id, session)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))

    service = ConversationService(session)
    try:
        conversation = await service.create_group_conversation(
            name=request.name,
            participant_ids=request.participant_ids,
            tenant_id=security.tenant_id,
            property_id=security.property_id,
            created_by=security.user_id,
            description=request.description,
            avatar_url=request.avatar_url
        )
        return conversation
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.get(
    "/conversations/{conversation_id}",
    response_model=ConversationDetailResponse,
    summary="Get conversation details"
)
async def get_conversation(
    conversation_id: UUID,
    tenant_id: UUID = Query(...),
    property_id: UUID = Query(...),
    authorization: str = Header(...),
    session: AsyncSession = Depends(get_async_session)
):
    """Get full conversation details with participants"""
    try:
        security = await get_chat_security_context(authorization, tenant_id, property_id, session)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))

    service = ConversationService(session)
    try:
        conversation = await service.get_conversation_detail(
            conversation_id=conversation_id,
            tenant_id=security.tenant_id,
            property_id=security.property_id,
            user_id=security.user_id
        )
        return conversation
    except AccessDenied as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except NotFound as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.put(
    "/conversations/{conversation_id}",
    response_model=ConversationDetailResponse,
    summary="Update conversation"
)
async def update_conversation(
    conversation_id: UUID,
    tenant_id: UUID = Query(...),
    property_id: UUID = Query(...),
    request: UpdateConversationRequest = None,
    authorization: str = Header(...),
    session: AsyncSession = Depends(get_async_session)
):
    """Update conversation name, description, avatar"""
    try:
        security = await get_chat_security_context(authorization, tenant_id, property_id, session)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))

    service = ConversationService(session)
    try:
        conversation = await service.update_conversation(
            conversation_id=conversation_id,
            tenant_id=security.tenant_id,
            property_id=security.property_id,
            user_id=security.user_id,
            name=request.name,
            description=request.description,
            avatar_url=request.avatar_url
        )
        return conversation
    except AccessDenied as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post(
    "/conversations/{conversation_id}/archive",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Archive conversation"
)
async def archive_conversation(
    conversation_id: UUID,
    tenant_id: UUID = Query(...),
    property_id: UUID = Query(...),
    authorization: str = Header(...),
    session: AsyncSession = Depends(get_async_session)
):
    """Archive conversation"""
    try:
        security = await get_chat_security_context(authorization, tenant_id, property_id, session)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))

    service = ConversationService(session)
    try:
        await service.archive_conversation(
            conversation_id=conversation_id,
            tenant_id=security.tenant_id,
            property_id=security.property_id,
            user_id=security.user_id
        )
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post(
    "/conversations/{conversation_id}/mute",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Mute/unmute conversation"
)
async def mute_conversation(
    conversation_id: UUID,
    tenant_id: UUID = Query(...),
    property_id: UUID = Query(...),
    request: MuteConversationRequest = None,
    authorization: str = Header(...),
    session: AsyncSession = Depends(get_async_session)
):
    """Mute or unmute notifications for conversation"""
    try:
        security = await get_chat_security_context(authorization, tenant_id, property_id, session)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))

    service = ParticipantService(session)
    try:
        await service.participant_repo.mute_conversation(
            conversation_id=conversation_id,
            user_id=security.user_id,
            is_muted=request.is_muted
        )
        await session.commit()
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


# ===========================================================
# MESSAGE ENDPOINTS
# ===========================================================

@router.post(
    "/conversations/{conversation_id}/messages",
    response_model=MessageResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Send message"
)
async def send_message(
    conversation_id: UUID,
    tenant_id: UUID = Query(...),
    property_id: UUID = Query(...),
    request: MessageCreateRequest = None,
    authorization: str = Header(...),
    session: AsyncSession = Depends(get_async_session)
):
    """Send message to conversation"""
    try:
        security = await get_chat_security_context(authorization, tenant_id, property_id, session)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))

    service = MessageService(session)
    try:
        message = await service.send_message(
            conversation_id=conversation_id,
            sender_id=security.user_id,
            content=request.content,
            reply_to_id=request.reply_to_id,
            mentions=request.mentions
        )

        # Publish real-time event
        manager = get_websocket_manager()
        await publish_message_sent_event(
            manager=manager,
            conversation_id=conversation_id,
            tenant_id=security.tenant_id,
            property_id=security.property_id,
            message_data=message.dict()
        )

        return message
    except AccessDenied as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get(
    "/conversations/{conversation_id}/messages",
    response_model=dict,
    summary="Get messages in conversation"
)
async def get_messages(
    conversation_id: UUID,
    tenant_id: UUID = Query(...),
    property_id: UUID = Query(...),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    authorization: str = Header(...),
    session: AsyncSession = Depends(get_async_session)
):
    """Get paginated messages in conversation"""
    try:
        security = await get_chat_security_context(authorization, tenant_id, property_id, session)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))

    service = MessageService(session)
    try:
        messages, total = await service.get_conversation_messages(
            conversation_id=conversation_id,
            user_id=security.user_id,
            skip=skip,
            limit=limit
        )
        return {
            "total": total,
            "skip": skip,
            "limit": limit,
            "items": messages
        }
    except AccessDenied as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))


@router.put(
    "/messages/{message_id}",
    response_model=MessageResponse,
    summary="Edit message"
)
async def edit_message(
    message_id: UUID,
    tenant_id: UUID = Query(...),
    property_id: UUID = Query(...),
    conversation_id: UUID = Query(...),
    request: MessageEditRequest = None,
    authorization: str = Header(...),
    session: AsyncSession = Depends(get_async_session)
):
    """Edit message (only sender can edit)"""
    try:
        security = await get_chat_security_context(authorization, tenant_id, property_id, session)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))

    service = MessageService(session)
    try:
        message = await service.edit_message(
            message_id=message_id,
            conversation_id=conversation_id,
            user_id=security.user_id,
            new_content=request.content
        )
        return message
    except AccessDenied as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except NotFound as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.delete(
    "/messages/{message_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete message"
)
async def delete_message(
    message_id: UUID,
    tenant_id: UUID = Query(...),
    property_id: UUID = Query(...),
    conversation_id: UUID = Query(...),
    hard_delete: bool = Query(False),
    authorization: str = Header(...),
    session: AsyncSession = Depends(get_async_session)
):
    """Delete message (soft or hard delete)"""
    try:
        security = await get_chat_security_context(authorization, tenant_id, property_id, session)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))

    service = MessageService(session)
    try:
        await service.delete_message(
            message_id=message_id,
            conversation_id=conversation_id,
            user_id=security.user_id,
            hard_delete=hard_delete
        )
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post(
    "/messages/{message_id}/mark-as-read",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Mark message as read"
)
async def mark_message_as_read(
    message_id: UUID,
    conversation_id: UUID = Query(...),
    authorization: str = Header(...),
    session: AsyncSession = Depends(get_async_session)
):
    """Mark message as read by current user"""
    try:
        # Extract token for user validation
        token = extract_bearer_token(authorization)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))

    service = MessageService(session)
    try:
        await service.mark_as_read(message_id, conversation_id, UUID(token))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get(
    "/conversations/{conversation_id}/search",
    response_model=dict,
    summary="Search messages"
)
async def search_messages(
    conversation_id: UUID,
    query: str = Query(..., min_length=1),
    tenant_id: UUID = Query(...),
    property_id: UUID = Query(...),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    authorization: str = Header(...),
    session: AsyncSession = Depends(get_async_session)
):
    """Search messages in conversation"""
    try:
        security = await get_chat_security_context(authorization, tenant_id, property_id, session)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))

    service = MessageService(session)
    try:
        messages, total = await service.search_messages(
            conversation_id=conversation_id,
            user_id=security.user_id,
            query=query,
            skip=skip,
            limit=limit
        )
        return {
            "total": total,
            "skip": skip,
            "limit": limit,
            "items": messages
        }
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


# ===========================================================
# PARTICIPANT ENDPOINTS
# ===========================================================

@router.post(
    "/conversations/{conversation_id}/participants",
    status_code=status.HTTP_201_CREATED,
    summary="Add participant to group"
)
async def add_participant(
    conversation_id: UUID,
    tenant_id: UUID = Query(...),
    property_id: UUID = Query(...),
    request: AddParticipantRequest = None,
    authorization: str = Header(...),
    session: AsyncSession = Depends(get_async_session)
):
    """Add user to group conversation"""
    try:
        security = await get_chat_security_context(authorization, tenant_id, property_id, session)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))

    service = ParticipantService(session)
    try:
        participant = await service.add_participant(
            conversation_id=conversation_id,
            tenant_id=security.tenant_id,
            property_id=security.property_id,
            user_id=security.user_id,
            new_participant_id=request.user_id
        )
        return participant
    except AccessDenied as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.delete(
    "/conversations/{conversation_id}/participants/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove participant"
)
async def remove_participant(
    conversation_id: UUID,
    user_id: UUID,
    tenant_id: UUID = Query(...),
    property_id: UUID = Query(...),
    authorization: str = Header(...),
    session: AsyncSession = Depends(get_async_session)
):
    """Remove user from group conversation"""
    try:
        security = await get_chat_security_context(authorization, tenant_id, property_id, session)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))

    service = ParticipantService(session)
    try:
        await service.remove_participant(
            conversation_id=conversation_id,
            tenant_id=security.tenant_id,
            property_id=security.property_id,
            user_id=security.user_id,
            participant_to_remove_id=user_id
        )
    except AccessDenied as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


# ===========================================================
# MEDIA ENDPOINTS
# ===========================================================

@router.post(
    "/conversations/{conversation_id}/media/upload",
    response_model=MessageMediaResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload media file"
)
async def upload_media(
    conversation_id: UUID,
    tenant_id: UUID = Query(...),
    property_id: UUID = Query(...),
    message_id: UUID = Query(...),
    file: UploadFile = File(...),
    authorization: str = Header(...),
    session: AsyncSession = Depends(get_async_session)
):
    """
    Upload media file (image, file, audio, video).
    
    Returns metadata for attaching to message.
    """
    try:
        security = await get_chat_security_context(authorization, tenant_id, property_id, session)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))

    # Verify conversation membership
    try:
        await verify_conversation_membership(
            user_id=security.user_id,
            conversation_id=conversation_id,
            tenant_id=security.tenant_id,
            property_id=security.property_id,
            session=session
        )
    except AccessDenied as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))

    # Read file
    try:
        file_bytes = await file.read()
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to read file: {str(e)}"
        )

    service = MediaService(session)
    try:
        # Detect media type from MIME
        media_type = "file"
        if file.content_type.startswith("image/"):
            media_type = "image"
        elif file.content_type.startswith("audio/"):
            media_type = "audio"
        elif file.content_type.startswith("video/"):
            media_type = "video"

        media = await service.upload_media(
            conversation_id=conversation_id,
            message_id=message_id,
            file_bytes=file_bytes,
            original_filename=file.filename,
            media_type=media_type,
            mime_type=file.content_type
        )
        return media
    except ValidationError as e:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get(
    "/media/{media_id}/download",
    summary="Download media file"
)
async def download_media(
    media_id: UUID,
    authorization: str = Header(...),
    session: AsyncSession = Depends(get_async_session)
):
    """Download media file"""
    try:
        extract_bearer_token(authorization)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))

    service = MediaService(session)
    try:
        file_bytes = await service.download_media(media_id)
        return {
            "content": file_bytes,
            "media_type": "application/octet-stream"
        }
    except NotFound as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


# ===========================================================
# WEBSOCKET ENDPOINT
# ===========================================================

@router.websocket(
    "/conversations/{conversation_id}/ws"
)
async def websocket_endpoint(
    websocket: WebSocket,
    conversation_id: UUID,
    token: str = Query(...),
    session: AsyncSession = Depends(get_async_session)
):
    """
    WebSocket endpoint for real-time chat.
    
    Validates JWT token and conversation membership before accepting connection.
    
    Message flow:
    1. Client connects with JWT token
    2. Server validates token and membership
    3. Server sends connection confirmation with online users
    4. Client sends messages, typing indicators, read receipts
    5. Server broadcasts to all participants in real-time
    """
    try:
        security = await get_websocket_security_context(token, conversation_id, session)
    except AccessDenied as e:
        await websocket.close(code=1008, reason=str(e))
        return

    manager = get_websocket_manager()

    # Accept connection
    connection = await manager.connect(
        websocket=websocket,
        conversation_id=conversation_id,
        user_id=security.user_id,
        tenant_id=security.tenant_id,
        property_id=security.property_id
    )

    # Send connection confirmation
    participants = manager.get_conversation_participants(
        conversation_id=conversation_id,
        tenant_id=security.tenant_id,
        property_id=security.property_id
    )

    await connection.send_json({
        "type": "connection.established",
        "data": {
            "message": "Connected to conversation",
            "conversation_id": str(conversation_id),
            "user_id": str(security.user_id),
            "participants": {str(uid): count for uid, count in participants.items()}
        }
    })

    # Notify others of new connection
    await manager.broadcast_to_conversation(
        conversation_id=conversation_id,
        tenant_id=security.tenant_id,
        property_id=security.property_id,
        message={
            "type": "user.online",
            "data": {
                "user_id": str(security.user_id),
                "timestamp": datetime.utcnow().isoformat()
            }
        },
        exclude_user_id=security.user_id
    )

    try:
        while True:
            data = await connection.websocket.receive_json()
            event_type = data.get("type")

            # Handle typing indicator
            if event_type == "typing.start":
                manager.set_typing(conversation_id, security.user_id)
                await manager.broadcast_to_conversation(
                    conversation_id=conversation_id,
                    tenant_id=security.tenant_id,
                    property_id=security.property_id,
                    message={
                        "type": "typing.start",
                        "data": {
                            "user_id": str(security.user_id),
                            "username": security.username
                        }
                    },
                    exclude_user_id=security.user_id
                )

            elif event_type == "typing.stop":
                manager.stop_typing(conversation_id, security.user_id)
                await manager.broadcast_to_conversation(
                    conversation_id=conversation_id,
                    tenant_id=security.tenant_id,
                    property_id=security.property_id,
                    message={
                        "type": "typing.stop",
                        "data": {"user_id": str(security.user_id)}
                    },
                    exclude_user_id=security.user_id
                )

            elif event_type == "read.receipt":
                # Process read receipt
                await manager.broadcast_to_conversation(
                    conversation_id=conversation_id,
                    tenant_id=security.tenant_id,
                    property_id=security.property_id,
                    message={
                        "type": "read.receipt",
                        "data": {
                            "message_id": data.get("message_id"),
                            "user_id": str(security.user_id)
                        }
                    }
                )

    except WebSocketDisconnect:
        await manager.disconnect(connection)

        # Notify others of disconnection
        await manager.broadcast_to_conversation(
            conversation_id=conversation_id,
            tenant_id=security.tenant_id,
            property_id=security.property_id,
            message={
                "type": "user.offline",
                "data": {
                    "user_id": str(security.user_id),
                    "timestamp": datetime.utcnow().isoformat()
                }
            }
        )

    except Exception as e:
        await manager.disconnect(connection)
        await connection.close(code=1011, reason=f"Error: {str(e)}")
