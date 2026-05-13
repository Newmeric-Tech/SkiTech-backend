"""
REST API endpoints for the chat system.
Handles all HTTP requests for conversations, messages, and file uploads.
All endpoints enforce JWT authentication and multi-tenant/property isolation.
"""

from typing import List
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.schemas.chat import (
    ConversationCreate,
    ConversationResponse,
    ConversationDetailResponse,
    ConversationListResponse,
    ConversationUpdate,
    MessageCreate,
    MessageResponse,
    MessageDetailResponse,
    MessageListResponse,
    MessageUpdate,
    ParticipantCreate,
    ParticipantResponse,
    SearchConversationsRequest,
    SearchMessagesRequest,
    FileUploadResponse,
)
from app.services.chat_service import ConversationService, MessageService
from app.services.storage.local_storage import LocalStorageService
from app.utils.exceptions import NotFoundError, UnauthorizedError, ValidationError

router = APIRouter(prefix="/v1/chats", tags=["chats"])


# ============================================================================
# DEPENDENCY INJECTION
# ============================================================================

async def get_conversation_service(
    db: AsyncSession = Depends(get_db),
) -> ConversationService:
    """Get conversation service instance."""
    storage_service = LocalStorageService(base_path="./storage")
    return ConversationService(db, storage_service)


async def get_message_service(
    db: AsyncSession = Depends(get_db),
) -> MessageService:
    """Get message service instance."""
    storage_service = LocalStorageService(base_path="./storage")
    return MessageService(db, storage_service)


# ============================================================================
# CONVERSATION ENDPOINTS
# ============================================================================

@router.post("", response_model=ConversationResponse, status_code=status.HTTP_201_CREATED)
async def create_conversation(
    req: ConversationCreate,
    current_user: User = Depends(get_current_user),
    service: ConversationService = Depends(get_conversation_service),
) -> ConversationResponse:
    """
    Create a new conversation (direct or group).
    
    For direct chat: provide `other_user_id`
    For group chat: provide `name` and `participant_ids`
    """
    try:
        if req.type == "direct":
            if not req.other_user_id:
                raise ValidationError("Direct chat requires other_user_id")
            
            conv = await service.create_direct_chat(
                creator_id=current_user.id,
                other_user_id=req.other_user_id,
                tenant_id=current_user.tenant_id,
                property_id=current_user.property_id,
            )
        else:  # group
            conv = await service.create_group_chat(
                name=req.name,
                creator_id=current_user.id,
                participant_ids=req.participant_ids or [],
                tenant_id=current_user.tenant_id,
                property_id=current_user.property_id,
            )
        
        return ConversationResponse(
            id=conv.id,
            type=conv.type,
            name=conv.name,
            created_by=conv.created_by,
            created_at=conv.created_at,
            updated_at=conv.updated_at,
            is_archived=conv.is_archived,
            participant_count=len(conv.participants),
        )
    except ValidationError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("", response_model=ConversationListResponse)
async def list_conversations(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    include_archived: bool = Query(False),
    current_user: User = Depends(get_current_user),
    service: ConversationService = Depends(get_conversation_service),
) -> ConversationListResponse:
    """
    Get all conversations for the current user.
    Results are paginated and sorted by most recent.
    """
    conversations, total = await service.get_conversations(
        user_id=current_user.id,
        tenant_id=current_user.tenant_id,
        property_id=current_user.property_id,
        skip=skip,
        limit=limit,
        include_archived=include_archived,
    )
    
    return ConversationListResponse(
        items=conversations,
        total=total,
        skip=skip,
        limit=limit,
    )


@router.get("/{conversation_id}", response_model=ConversationDetailResponse)
async def get_conversation(
    conversation_id: UUID,
    current_user: User = Depends(get_current_user),
    service: ConversationService = Depends(get_conversation_service),
) -> ConversationDetailResponse:
    """Get detailed information about a conversation."""
    try:
        conv = await service.get_conversation(
            conversation_id=conversation_id,
            user_id=current_user.id,
            tenant_id=current_user.tenant_id,
            property_id=current_user.property_id,
        )
        
        participants = [
            ParticipantResponse(
                conversation_id=p.conversation_id,
                user_id=p.user_id,
                role=p.role,
                is_muted=p.is_muted,
                joined_at=p.joined_at,
                last_read_at=p.last_read_at,
                user_email=p.user.email if p.user else None,
                user_name=f"{p.user.first_name} {p.user.last_name}" if p.user else None,
            )
            for p in conv.participants
        ]
        
        return ConversationDetailResponse(
            id=conv.id,
            type=conv.type,
            name=conv.name,
            created_by=conv.created_by,
            created_at=conv.created_at,
            updated_at=conv.updated_at,
            is_archived=conv.is_archived,
            participant_count=len(participants),
            participants=participants,
        )
    except NotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except UnauthorizedError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))


@router.put("/{conversation_id}", response_model=ConversationResponse)
async def update_conversation(
    conversation_id: UUID,
    req: ConversationUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ConversationResponse:
    """Update conversation metadata (name, archived status)."""
    from app.repositories.conversation import ConversationRepository
    
    repo = ConversationRepository(db)
    try:
        conv = await repo.get_with_participants(
            conversation_id,
            current_user.tenant_id,
            current_user.property_id,
        )
        
        if not conv:
            raise NotFoundError("Conversation not found")
        
        # Check admin permission
        is_admin = any(
            p.user_id == current_user.id and p.role == "admin"
            for p in conv.participants
        )
        if not is_admin:
            raise UnauthorizedError("Only admin can update conversation")
        
        if req.name:
            conv.name = req.name
        if req.is_archived is not None:
            conv.is_archived = req.is_archived
        
        db.add(conv)
        await db.commit()
        
        return ConversationResponse(
            id=conv.id,
            type=conv.type,
            name=conv.name,
            created_by=conv.created_by,
            created_at=conv.created_at,
            updated_at=conv.updated_at,
            is_archived=conv.is_archived,
            participant_count=len(conv.participants),
        )
    except (NotFoundError, UnauthorizedError) as e:
        status_code = status.HTTP_404_NOT_FOUND if isinstance(e, NotFoundError) else status.HTTP_403_FORBIDDEN
        raise HTTPException(status_code=status_code, detail=str(e))


@router.delete("/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def archive_conversation(
    conversation_id: UUID,
    current_user: User = Depends(get_current_user),
    service: ConversationService = Depends(get_conversation_service),
):
    """Archive a conversation (soft delete)."""
    try:
        await service.archive_conversation(
            conversation_id=conversation_id,
            user_id=current_user.id,
            tenant_id=current_user.tenant_id,
            property_id=current_user.property_id,
        )
    except (NotFoundError, UnauthorizedError) as e:
        status_code = status.HTTP_404_NOT_FOUND if isinstance(e, NotFoundError) else status.HTTP_403_FORBIDDEN
        raise HTTPException(status_code=status_code, detail=str(e))


@router.get("/search/conversations")
async def search_conversations(
    req: SearchConversationsRequest = Depends(),
    current_user: User = Depends(get_current_user),
    service: ConversationService = Depends(get_conversation_service),
) -> ConversationListResponse:
    """Search conversations by name."""
    conversations, total = await service.search_conversations(
        query=req.query,
        user_id=current_user.id,
        tenant_id=current_user.tenant_id,
        property_id=current_user.property_id,
        skip=req.skip,
        limit=req.limit,
    )
    
    return ConversationListResponse(
        items=conversations,
        total=total,
        skip=req.skip,
        limit=req.limit,
    )


# ============================================================================
# PARTICIPANT MANAGEMENT
# ============================================================================

@router.post("/{conversation_id}/participants", response_model=ParticipantResponse, status_code=status.HTTP_201_CREATED)
async def add_participant(
    conversation_id: UUID,
    req: ParticipantCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ParticipantResponse:
    """Add a user to a conversation."""
    from app.repositories.conversation import ConversationRepository
    from app.repositories.participant import ParticipantRepository
    
    try:
        conv_repo = ConversationRepository(db)
        part_repo = ParticipantRepository(db)
        
        # Get conversation
        conv = await conv_repo.get_with_participants(
            conversation_id,
            current_user.tenant_id,
            current_user.property_id,
        )
        
        if not conv:
            raise NotFoundError("Conversation not found")
        
        # Check current user is admin
        is_admin = any(
            p.user_id == current_user.id and p.role == "admin"
            for p in conv.participants
        )
        if not is_admin:
            raise UnauthorizedError("Only admin can add participants")
        
        # Add participant
        participant = await part_repo.add_participant(
            conversation_id,
            req.user_id,
            role=req.role,
        )
        await db.commit()
        
        return ParticipantResponse(
            conversation_id=participant.conversation_id,
            user_id=participant.user_id,
            role=participant.role,
            is_muted=participant.is_muted,
            joined_at=participant.joined_at,
            last_read_at=participant.last_read_at,
        )
    except (NotFoundError, UnauthorizedError) as e:
        status_code = status.HTTP_404_NOT_FOUND if isinstance(e, NotFoundError) else status.HTTP_403_FORBIDDEN
        raise HTTPException(status_code=status_code, detail=str(e))


@router.delete("/{conversation_id}/participants/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_participant(
    conversation_id: UUID,
    user_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Remove a user from a conversation."""
    from app.repositories.conversation import ConversationRepository
    from app.repositories.participant import ParticipantRepository
    
    try:
        conv_repo = ConversationRepository(db)
        part_repo = ParticipantRepository(db)
        
        # Get conversation
        conv = await conv_repo.get_with_participants(
            conversation_id,
            current_user.tenant_id,
            current_user.property_id,
        )
        
        if not conv:
            raise NotFoundError("Conversation not found")
        
        # Check current user is admin
        is_admin = any(
            p.user_id == current_user.id and p.role == "admin"
            for p in conv.participants
        )
        if not is_admin:
            raise UnauthorizedError("Only admin can remove participants")
        
        # Remove participant
        success = await part_repo.remove_participant(conversation_id, user_id)
        if success:
            await db.commit()
    except (NotFoundError, UnauthorizedError) as e:
        status_code = status.HTTP_404_NOT_FOUND if isinstance(e, NotFoundError) else status.HTTP_403_FORBIDDEN
        raise HTTPException(status_code=status_code, detail=str(e))


# ============================================================================
# MESSAGE ENDPOINTS
# ============================================================================

@router.post("/{conversation_id}/messages", response_model=MessageResponse, status_code=status.HTTP_201_CREATED)
async def send_message(
    conversation_id: UUID,
    req: MessageCreate,
    current_user: User = Depends(get_current_user),
    service: MessageService = Depends(get_message_service),
) -> MessageResponse:
    """Send a message to a conversation."""
    try:
        msg = await service.send_message(
            conversation_id=conversation_id,
            sender_id=current_user.id,
            tenant_id=current_user.tenant_id,
            content=req.content,
            message_type=req.message_type,
            reply_to_id=req.reply_to_id,
        )
        
        return MessageResponse(
            id=msg.id,
            conversation_id=msg.conversation_id,
            sender_id=msg.sender_id,
            sender_email=msg.sender.email if msg.sender else None,
            sender_name=f"{msg.sender.first_name} {msg.sender.last_name}" if msg.sender else None,
            content=msg.content,
            message_type=msg.message_type,
            reply_to_id=msg.reply_to_id,
            created_at=msg.created_at,
            edited_at=msg.edited_at,
            is_deleted=msg.is_deleted,
            media=[],
            read_by_count=0,
        )
    except (ValidationError, UnauthorizedError) as e:
        status_code = status.HTTP_400_BAD_REQUEST if isinstance(e, ValidationError) else status.HTTP_403_FORBIDDEN
        raise HTTPException(status_code=status_code, detail=str(e))


@router.get("/{conversation_id}/messages", response_model=MessageListResponse)
async def get_messages(
    conversation_id: UUID,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    service: MessageService = Depends(get_message_service),
) -> MessageListResponse:
    """Get messages in a conversation."""
    try:
        messages, total = await service.get_messages(
            conversation_id=conversation_id,
            user_id=current_user.id,
            tenant_id=current_user.tenant_id,
            skip=skip,
            limit=limit,
        )
        
        msg_responses = [
            MessageResponse(
                id=m.id,
                conversation_id=m.conversation_id,
                sender_id=m.sender_id,
                sender_email=m.sender.email if m.sender else None,
                sender_name=f"{m.sender.first_name} {m.sender.last_name}" if m.sender else None,
                content=m.content,
                message_type=m.message_type,
                reply_to_id=m.reply_to_id,
                created_at=m.created_at,
                edited_at=m.edited_at,
                is_deleted=m.is_deleted,
                media=[],
                read_by_count=len([r for r in m.read_receipts if r.status == "read"]),
            )
            for m in messages
        ]
        
        return MessageListResponse(
            items=msg_responses,
            total=total,
            skip=skip,
            limit=limit,
        )
    except UnauthorizedError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))


@router.put("/{conversation_id}/messages/{message_id}", response_model=MessageResponse)
async def edit_message(
    conversation_id: UUID,
    message_id: UUID,
    req: MessageUpdate,
    current_user: User = Depends(get_current_user),
    service: MessageService = Depends(get_message_service),
) -> MessageResponse:
    """Edit a message (only sender can edit)."""
    try:
        msg = await service.edit_message(
            message_id=message_id,
            sender_id=current_user.id,
            tenant_id=current_user.tenant_id,
            new_content=req.content,
        )
        
        return MessageResponse(
            id=msg.id,
            conversation_id=msg.conversation_id,
            sender_id=msg.sender_id,
            sender_email=msg.sender.email if msg.sender else None,
            sender_name=f"{msg.sender.first_name} {msg.sender.last_name}" if msg.sender else None,
            content=msg.content,
            message_type=msg.message_type,
            reply_to_id=msg.reply_to_id,
            created_at=msg.created_at,
            edited_at=msg.edited_at,
            is_deleted=msg.is_deleted,
            media=[],
            read_by_count=0,
        )
    except (NotFoundError, UnauthorizedError, ValidationError) as e:
        if isinstance(e, NotFoundError):
            status_code = status.HTTP_404_NOT_FOUND
        elif isinstance(e, UnauthorizedError):
            status_code = status.HTTP_403_FORBIDDEN
        else:
            status_code = status.HTTP_400_BAD_REQUEST
        raise HTTPException(status_code=status_code, detail=str(e))


@router.delete("/{conversation_id}/messages/{message_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_message(
    conversation_id: UUID,
    message_id: UUID,
    current_user: User = Depends(get_current_user),
    service: MessageService = Depends(get_message_service),
):
    """Delete a message (soft delete)."""
    try:
        await service.delete_message(
            message_id=message_id,
            user_id=current_user.id,
            tenant_id=current_user.tenant_id,
        )
    except (NotFoundError, UnauthorizedError) as e:
        status_code = status.HTTP_404_NOT_FOUND if isinstance(e, NotFoundError) else status.HTTP_403_FORBIDDEN
        raise HTTPException(status_code=status_code, detail=str(e))


@router.post("/{conversation_id}/messages/{message_id}/read", status_code=status.HTTP_204_NO_CONTENT)
async def mark_message_read(
    conversation_id: UUID,
    message_id: UUID,
    current_user: User = Depends(get_current_user),
    service: MessageService = Depends(get_message_service),
):
    """Mark a message as read by current user."""
    try:
        await service.mark_as_read(
            message_id=message_id,
            user_id=current_user.id,
            tenant_id=current_user.tenant_id,
        )
    except NotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.get("/{conversation_id}/messages/search", response_model=MessageListResponse)
async def search_messages_endpoint(
    conversation_id: UUID,
    query: str = Query(..., min_length=1, max_length=100),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    service: MessageService = Depends(get_message_service),
) -> MessageListResponse:
    """Search messages in a conversation."""
    try:
        messages, total = await service.search_messages(
            conversation_id=conversation_id,
            user_id=current_user.id,
            tenant_id=current_user.tenant_id,
            query=query,
            skip=skip,
            limit=limit,
        )
        
        msg_responses = [
            MessageResponse(
                id=m.id,
                conversation_id=m.conversation_id,
                sender_id=m.sender_id,
                sender_email=m.sender.email if m.sender else None,
                sender_name=f"{m.sender.first_name} {m.sender.last_name}" if m.sender else None,
                content=m.content,
                message_type=m.message_type,
                reply_to_id=m.reply_to_id,
                created_at=m.created_at,
                edited_at=m.edited_at,
                is_deleted=m.is_deleted,
                media=[],
                read_by_count=0,
            )
            for m in messages
        ]
        
        return MessageListResponse(
            items=msg_responses,
            total=total,
            skip=skip,
            limit=limit,
        )
    except UnauthorizedError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
