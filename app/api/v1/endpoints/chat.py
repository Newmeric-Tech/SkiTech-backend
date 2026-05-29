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

import json
from datetime import datetime
from io import BytesIO
from typing import List, Optional
from uuid import UUID

import logging

from fastapi import (
    APIRouter, Depends, HTTPException, status, UploadFile, File,
    Header, Query, WebSocket, WebSocketDisconnect, Body, Form
)
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger("skitech")

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
    from sqlalchemy import select, and_, or_

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
        "Super Admin":  ["Tenant Admin", "Manager", "Staff", "Super Admin"],
        "Tenant Admin": ["Tenant Admin", "Manager", "Staff"],
        "Owner":        ["Tenant Admin", "Manager", "Staff"],
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
    # Property filter: always include users with null property_id (Tenant Admins / unassigned)
    # alongside users explicitly at the target property, so managers can always see the owner.
    effective_prop = property_id if property_id is not None else user.property_id
    if effective_prop is not None:
        conditions.append(
            or_(
                UserModel.property_id == effective_prop,
                UserModel.property_id.is_(None),
            )
        )
    # else: Tenant Admin with no property → no filter, sees everyone in the tenant

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
    property_id: Optional[UUID] = Query(None, description="Property ID (omit for Tenant Admin to see all properties)"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    include_archived: bool = Query(False),
    authorization: str = Header(...),
    session: AsyncSession = Depends(get_async_session)
):
    """
    Get all conversations for the authenticated user.

    - Tenant Admin (no property_id): returns conversations across ALL properties in the tenant.
    - Manager/Staff: returns conversations for their property.
    """
    from app.utils.chat_security import verify_jwt_token, verify_tenant_access, verify_property_access
    try:
        user, _token_data = await verify_jwt_token(authorization, session)
        await verify_tenant_access(user, tenant_id, session)
        # Effective property: explicit param → user's own property → None (Tenant Admin sees all)
        effective_prop = property_id if property_id is not None else user.property_id
        if effective_prop is not None:
            await verify_property_access(user, tenant_id, effective_prop, session)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))

    service = ConversationService(session)
    try:
        conversations, total = await service.get_user_conversations(
            user_id=user.id,
            tenant_id=tenant_id,
            property_id=effective_prop,
            skip=skip,
            limit=limit,
            include_archived=include_archived
        )
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

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
    property_id: Optional[UUID] = Query(None),
    request: CreateDirectConversationRequest = Body(...),
    authorization: str = Header(...),
    session: AsyncSession = Depends(get_async_session)
):
    """Create new direct conversation or get existing one"""
    from app.utils.chat_security import verify_jwt_token, verify_tenant_access, verify_property_access
    from app.models.models import User as UserModel
    from sqlalchemy import select as sa_select
    try:
        user, _token_data = await verify_jwt_token(authorization, session)
        await verify_tenant_access(user, tenant_id, session)
        effective_prop = property_id if property_id is not None else user.property_id

        # Tenant Admin has no property — derive it from the other participant
        if effective_prop is None:
            other_stmt = sa_select(UserModel.property_id).where(UserModel.id == request.other_user_id)
            other_result = await session.execute(other_stmt)
            effective_prop = other_result.scalar_one_or_none()

        if effective_prop is not None:
            await verify_property_access(user, tenant_id, effective_prop, session)

        if effective_prop is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot determine property for this conversation — neither participant has an assigned property"
            )
        from app.utils.chat_security import ChatSecurityContext
        security = ChatSecurityContext(
            user_id=user.id,
            tenant_id=tenant_id,
            property_id=effective_prop,
            username=f"{user.first_name or ''} {user.last_name or ''}".strip(),
            email=user.email,
            token_data=_token_data,
        )
    except HTTPException:
        raise
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
        logger.error(f"create_direct_conversation failed: {type(e).__name__}: {e}", exc_info=True)
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
    property_id: Optional[UUID] = Query(None),
    request: CreateGroupConversationRequest = Body(...),
    authorization: str = Header(...),
    session: AsyncSession = Depends(get_async_session)
):
    """Create new group conversation"""
    from app.utils.chat_security import verify_jwt_token, verify_tenant_access, verify_property_access
    from app.utils.chat_security import ChatSecurityContext
    from app.models.models import User as UserModel
    from sqlalchemy import select as sa_select
    try:
        user, _token_data = await verify_jwt_token(authorization, session)
        await verify_tenant_access(user, tenant_id, session)
        effective_prop = property_id if property_id is not None else user.property_id

        # Tenant Admin has no property — derive from any participant who has one
        if effective_prop is None:
            for pid in request.participant_ids:
                p_stmt = sa_select(UserModel.property_id).where(UserModel.id == pid)
                p_result = await session.execute(p_stmt)
                p_prop = p_result.scalar_one_or_none()
                if p_prop:
                    effective_prop = p_prop
                    break

        if effective_prop is not None:
            await verify_property_access(user, tenant_id, effective_prop, session)

        if effective_prop is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot determine property for this group — no participant has an assigned property"
            )

        security = ChatSecurityContext(
            user_id=user.id,
            tenant_id=tenant_id,
            property_id=effective_prop,
            username=f"{user.first_name or ''} {user.last_name or ''}".strip(),
            email=user.email,
            token_data=_token_data,
        )
    except HTTPException:
        raise
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
    property_id: Optional[UUID] = Query(None),
    authorization: str = Header(...),
    session: AsyncSession = Depends(get_async_session)
):
    """Get full conversation details with participants"""
    from app.utils.chat_security import verify_jwt_token, verify_tenant_access, verify_property_access
    try:
        user, _token_data = await verify_jwt_token(authorization, session)
        await verify_tenant_access(user, tenant_id, session)
        effective_prop = property_id if property_id is not None else user.property_id
        if effective_prop is not None:
            await verify_property_access(user, tenant_id, effective_prop, session)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))

    service = ConversationService(session)
    try:
        conversation = await service.get_conversation_detail(
            conversation_id=conversation_id,
            tenant_id=tenant_id,
            property_id=effective_prop,
            user_id=user.id
        )
        return conversation
    except AccessDenied as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except NotFound as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.exception("get_conversation failed: %s", e)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.put(
    "/conversations/{conversation_id}",
    response_model=ConversationDetailResponse,
    summary="Update conversation"
)
async def update_conversation(
    conversation_id: UUID,
    tenant_id: UUID = Query(...),
    property_id: UUID = Query(...),
    request: UpdateConversationRequest = Body(...),
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
    request: MuteConversationRequest = Body(...),
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
    request: MessageCreateRequest = Body(...),
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
            tenant_id=security.tenant_id,
            reply_to_id=request.reply_to_id,
            mentions=request.mentions
        )
    except AccessDenied as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except Exception as e:
        logger.exception("send_message service error: %s", e)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    # WS broadcast is fire-and-forget — must not abort the HTTP response
    try:
        manager = get_websocket_manager()
        await publish_message_sent_event(
            manager=manager,
            conversation_id=conversation_id,
            tenant_id=security.tenant_id,
            property_id=security.property_id,
            message_data=json.loads(message.model_dump_json())
        )
    except Exception as e:
        logger.warning("WS broadcast failed (non-fatal): %s", e)

    return message


@router.post(
    "/conversations/{conversation_id}/messages/with-media",
    response_model=MessageResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Send message with file attachment (atomic)"
)
async def send_message_with_media(
    conversation_id: UUID,
    tenant_id: UUID = Query(...),
    property_id: UUID = Query(...),
    file: UploadFile = File(...),
    content: str = Form(""),
    authorization: str = Header(...),
    session: AsyncSession = Depends(get_async_session)
):
    """
    Create a message and attach a file in a single atomic request.
    The WS broadcast fires only after the media is stored, so recipients
    always see the file bubble — never a plain-text filename.
    """
    try:
        security = await get_chat_security_context(authorization, tenant_id, property_id, session)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))

    # Use filename as message content when no caption is provided
    effective_content = content.strip() or (file.filename or "attachment")

    msg_service = MessageService(session)
    try:
        message = await msg_service.send_message(
            conversation_id=conversation_id,
            sender_id=security.user_id,
            content=effective_content,
            tenant_id=security.tenant_id,
        )
    except AccessDenied as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except Exception as e:
        logger.exception("send_message_with_media: message creation failed: %s", e)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    # Read and upload the file
    try:
        file_bytes = await file.read()
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Failed to read file: {e}")

    media_type = "file"
    ct = file.content_type or ""
    if ct.startswith("image/"):
        media_type = "image"
    elif ct.startswith("audio/"):
        media_type = "audio"
    elif ct.startswith("video/"):
        media_type = "video"

    try:
        media_service = MediaService(session)
    except RuntimeError as e:
        logger.error("send_message_with_media: storage not initialised: %s", e)
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="File storage not available")

    try:
        media_response = await media_service.upload_media(
            conversation_id=conversation_id,
            message_id=message.id,
            file_bytes=file_bytes,
            original_filename=file.filename or effective_content,
            media_type=media_type,
            mime_type=ct or "application/octet-stream",
        )
    except ValidationError as e:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail=str(e))
    except Exception as e:
        logger.exception("send_message_with_media: upload failed: %s", e)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    # Build the full response by injecting the media into the message — avoids
    # a DB re-fetch that could return a stale (empty media) result from the session cache.
    try:
        full_response = message.model_copy(update={"media": [media_response]})
    except Exception as e:
        logger.exception("send_message_with_media: model_copy failed: %s", e)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    # Broadcast with media attached — recipients see the file bubble, not plain text
    try:
        manager = get_websocket_manager()
        await publish_message_sent_event(
            manager=manager,
            conversation_id=conversation_id,
            tenant_id=security.tenant_id,
            property_id=security.property_id,
            message_data=json.loads(full_response.model_dump_json())
        )
    except Exception as e:
        logger.warning("WS broadcast failed (non-fatal): %s", e)

    return full_response


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
    request: MessageEditRequest = Body(...),
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

    from app.core.security import decode_token
    token_data = decode_token(token)
    if not token_data:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    service = MessageService(session)
    try:
        await service.mark_as_read(message_id, conversation_id, UUID(token_data["sub"]))
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
    request: AddParticipantRequest = Body(...),
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
