"""
Chat service layer for business logic.
Handles conversation management, messaging, file uploads, and read receipts.
All operations enforce strict multi-tenant and property isolation.
"""

from typing import List, Optional, Tuple
from uuid import UUID, uuid4
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.chat import (
    Conversation,
    ConversationType,
    ConversationParticipant,
    Message,
    MessageType,
    MessageMedia,
    MessageReadReceipt,
    MessageStatus,
    UserPresence,
    TypingIndicator,
    ChatNotification,
    ParticipantRole,
)
from app.repositories.conversation import ConversationRepository
from app.repositories.message import MessageRepository
from app.repositories.participant import ParticipantRepository
from app.services.storage.storage_service import StorageService
from app.schemas.chat import (
    ConversationCreate,
    ConversationResponse,
    MessageCreate,
    MessageResponse,
    ParticipantCreate,
)
from app.utils.exceptions import (
    NotFoundError,
    UnauthorizedError,
    ValidationError,
)


class ConversationService:
    """Service for conversation management."""

    def __init__(
        self,
        session: AsyncSession,
        storage_service: StorageService,
    ):
        self.session = session
        self.storage_service = storage_service
        self.conv_repo = ConversationRepository(session)
        self.msg_repo = MessageRepository(session)
        self.participant_repo = ParticipantRepository(session)

    async def create_direct_chat(
        self,
        creator_id: UUID,
        other_user_id: UUID,
        tenant_id: UUID,
        property_id: UUID,
    ) -> Conversation:
        """
        Create a direct 1-to-1 chat between two users.
        If chat already exists, returns existing one (idempotent).
        """
        # Check if direct chat already exists
        existing = await self.conv_repo.get_direct_chat(
            creator_id,
            other_user_id,
            tenant_id,
            property_id,
        )
        if existing:
            return existing

        # Create new conversation
        conv = await self.conv_repo.create(
            {
                "type": ConversationType.DIRECT,
                "created_by": creator_id,
                "property_id": property_id,
            },
            tenant_id=tenant_id,
        )

        # Add both users as participants
        await self.participant_repo.add_participant(
            conv.id,
            creator_id,
            role=ParticipantRole.ADMIN,
        )
        await self.participant_repo.add_participant(
            conv.id,
            other_user_id,
            role=ParticipantRole.MEMBER,
        )

        await self.session.commit()
        return conv

    async def create_group_chat(
        self,
        name: str,
        creator_id: UUID,
        participant_ids: List[UUID],
        tenant_id: UUID,
        property_id: UUID,
    ) -> Conversation:
        """Create a group conversation with multiple participants."""
        if not name or len(name) > 120:
            raise ValidationError("Invalid group name")

        if not participant_ids or len(participant_ids) < 2:
            raise ValidationError("Group must have at least 2 participants")

        # Create conversation
        conv = await self.conv_repo.create(
            {
                "type": ConversationType.GROUP,
                "name": name,
                "created_by": creator_id,
                "property_id": property_id,
            },
            tenant_id=tenant_id,
        )

        # Add creator as admin
        await self.participant_repo.add_participant(
            conv.id,
            creator_id,
            role=ParticipantRole.ADMIN,
        )

        # Add other participants
        for user_id in participant_ids:
            if user_id != creator_id:
                await self.participant_repo.add_participant(
                    conv.id,
                    user_id,
                    role=ParticipantRole.MEMBER,
                )

        await self.session.commit()
        return conv

    async def get_conversations(
        self,
        user_id: UUID,
        tenant_id: UUID,
        property_id: UUID,
        skip: int = 0,
        limit: int = 20,
        include_archived: bool = False,
    ) -> Tuple[List[ConversationResponse], int]:
        """Get all conversations for a user."""
        conversations, total = await self.conv_repo.get_conversations_for_user(
            user_id,
            tenant_id,
            property_id,
            skip=skip,
            limit=limit,
            include_archived=include_archived,
        )

        # Convert to response schemas
        responses = []
        for conv in conversations:
            last_msg = await self.msg_repo.get_last_message(conv.id, tenant_id)
            unread_count = await self.msg_repo.get_unread_count(
                conv.id,
                user_id,
            )

            responses.append(
                ConversationResponse(
                    id=conv.id,
                    type=conv.type,
                    name=conv.name,
                    created_by=conv.created_by,
                    created_at=conv.created_at,
                    updated_at=conv.updated_at,
                    is_archived=conv.is_archived,
                    participant_count=len(conv.participants),
                    last_message_preview=last_msg.content[:100] if last_msg else None,
                    last_message_at=last_msg.created_at if last_msg else None,
                    unread_count=unread_count,
                )
            )

        return responses, total

    async def get_conversation(
        self,
        conversation_id: UUID,
        user_id: UUID,
        tenant_id: UUID,
        property_id: UUID,
    ) -> Conversation:
        """Get a specific conversation with authorization check."""
        conv = await self.conv_repo.get_with_participants(
            conversation_id,
            tenant_id,
            property_id,
        )

        if not conv:
            raise NotFoundError("Conversation not found")

        # Check user is a participant
        if not await self.conv_repo.is_user_participant(conversation_id, user_id):
            raise UnauthorizedError(
                "You are not a member of this conversation"
            )

        return conv

    async def archive_conversation(
        self,
        conversation_id: UUID,
        user_id: UUID,
        tenant_id: UUID,
        property_id: UUID,
    ) -> Conversation:
        """Archive a conversation (soft delete)."""
        conv = await self.get_conversation(
            conversation_id,
            user_id,
            tenant_id,
            property_id,
        )

        # Only admin can archive
        participant = await self.participant_repo.get_participant(
            conversation_id,
            user_id,
        )
        if participant.role != ParticipantRole.ADMIN:
            raise UnauthorizedError("Only admin can archive conversation")

        conv.is_archived = True
        self.session.add(conv)
        await self.session.commit()
        return conv

    async def search_conversations(
        self,
        query: str,
        user_id: UUID,
        tenant_id: UUID,
        property_id: UUID,
        skip: int = 0,
        limit: int = 20,
    ) -> Tuple[List[ConversationResponse], int]:
        """Search conversations by name."""
        conversations, total = await self.conv_repo.search_conversations(
            query,
            user_id,
            tenant_id,
            property_id,
            skip=skip,
            limit=limit,
        )

        responses = []
        for conv in conversations:
            responses.append(
                ConversationResponse(
                    id=conv.id,
                    type=conv.type,
                    name=conv.name,
                    created_by=conv.created_by,
                    created_at=conv.created_at,
                    updated_at=conv.updated_at,
                    is_archived=conv.is_archived,
                    participant_count=len(conv.participants),
                )
            )

        return responses, total


class MessageService:
    """Service for message management."""

    def __init__(
        self,
        session: AsyncSession,
        storage_service: StorageService,
    ):
        self.session = session
        self.storage_service = storage_service
        self.msg_repo = MessageRepository(session)
        self.participant_repo = ParticipantRepository(session)
        self.conv_repo = ConversationRepository(session)

    async def send_message(
        self,
        conversation_id: UUID,
        sender_id: UUID,
        tenant_id: UUID,
        content: str,
        message_type: str = MessageType.TEXT,
        reply_to_id: Optional[UUID] = None,
    ) -> Message:
        """Send a message in a conversation."""
        # Validate sender is a participant
        if not await self.conv_repo.is_user_participant(conversation_id, sender_id):
            raise UnauthorizedError(
                "You are not a member of this conversation"
            )

        # Validate content
        if not content or len(content) > 5000:
            raise ValidationError("Invalid message content")

        # Create message
        msg = await self.msg_repo.create(
            {
                "conversation_id": conversation_id,
                "sender_id": sender_id,
                "content": content,
                "message_type": message_type,
                "reply_to_id": reply_to_id,
            },
            tenant_id=tenant_id,
        )

        # Create read receipts for all participants (sent status)
        conv = await self.conv_repo.get_with_participants(
            conversation_id,
            tenant_id,
            None,
        )

        for participant in conv.participants:
            if participant.user_id != sender_id:
                receipt = MessageReadReceipt(
                    message_id=msg.id,
                    user_id=participant.user_id,
                    status=MessageStatus.SENT,
                )
                self.session.add(receipt)

        await self.session.commit()
        return msg

    async def edit_message(
        self,
        message_id: UUID,
        sender_id: UUID,
        tenant_id: UUID,
        new_content: str,
    ) -> Message:
        """Edit a message (only sender can edit)."""
        msg = await self.msg_repo.get_with_details(message_id, tenant_id)

        if not msg:
            raise NotFoundError("Message not found")

        if msg.sender_id != sender_id:
            raise UnauthorizedError("You can only edit your own messages")

        if msg.is_deleted:
            raise ValidationError("Cannot edit deleted message")

        msg.content = new_content
        msg.edited_at = datetime.now(timezone.utc)
        self.session.add(msg)
        await self.session.commit()
        return msg

    async def delete_message(
        self,
        message_id: UUID,
        user_id: UUID,
        tenant_id: UUID,
    ) -> bool:
        """Soft delete a message (only sender or admin can delete)."""
        msg = await self.msg_repo.get_with_details(message_id, tenant_id)

        if not msg:
            raise NotFoundError("Message not found")

        # Check permissions
        if msg.sender_id != user_id:
            # Check if user is admin in conversation
            participant = await self.participant_repo.get_participant(
                msg.conversation_id,
                user_id,
            )
            if not participant or participant.role != ParticipantRole.ADMIN:
                raise UnauthorizedError(
                    "Only sender or admin can delete message"
                )

        return await self.msg_repo.mark_as_deleted(message_id, tenant_id)

    async def get_messages(
        self,
        conversation_id: UUID,
        user_id: UUID,
        tenant_id: UUID,
        skip: int = 0,
        limit: int = 50,
    ) -> Tuple[List[Message], int]:
        """Get messages in a conversation."""
        # Verify user is participant
        if not await self.conv_repo.is_user_participant(
            conversation_id,
            user_id,
        ):
            raise UnauthorizedError(
                "You are not a member of this conversation"
            )

        return await self.msg_repo.get_conversation_messages(
            conversation_id,
            tenant_id,
            skip=skip,
            limit=limit,
        )

    async def search_messages(
        self,
        conversation_id: UUID,
        user_id: UUID,
        tenant_id: UUID,
        query: str,
        skip: int = 0,
        limit: int = 20,
    ) -> Tuple[List[Message], int]:
        """Search messages in a conversation."""
        # Verify user is participant
        if not await self.conv_repo.is_user_participant(
            conversation_id,
            user_id,
        ):
            raise UnauthorizedError(
                "You are not a member of this conversation"
            )

        return await self.msg_repo.search_messages(
            conversation_id,
            tenant_id,
            query,
            skip=skip,
            limit=limit,
        )

    async def mark_as_read(
        self,
        message_id: UUID,
        user_id: UUID,
        tenant_id: UUID,
    ) -> bool:
        """Mark a message as read by user."""
        # Get message
        msg = await self.msg_repo.get_with_details(message_id, tenant_id)
        if not msg:
            raise NotFoundError("Message not found")

        # Get or create read receipt
        query_result = await self.session.execute(
            select(MessageReadReceipt).where(
                and_(
                    MessageReadReceipt.message_id == message_id,
                    MessageReadReceipt.user_id == user_id,
                )
            )
        )
        receipt = query_result.scalars().first()

        if not receipt:
            receipt = MessageReadReceipt(
                message_id=message_id,
                user_id=user_id,
                status=MessageStatus.READ,
            )
            self.session.add(receipt)
        else:
            receipt.status = MessageStatus.READ
            receipt.updated_at = datetime.now(timezone.utc)

        await self.session.commit()
        return True


from sqlalchemy import select, and_
