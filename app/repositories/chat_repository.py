"""
Repository Layer for Chat System - app/repositories/chat_repository.py

Data access layer with strict multi-tenant and property isolation.

Every query includes:
- tenant_id check: Prevent tenant data leakage
- property_id check: Prevent property data leakage
- Conversation membership validation: Users can only access their conversations
- Soft delete handling: Exclude deleted records by default

Uses SQLAlchemy 2.0 with async support and proper indexing.
"""

from typing import List, Optional, Tuple
from uuid import UUID

from sqlalchemy import and_, desc, func, not_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.chat_models import (
    Conversation, ConversationParticipant, Message, MessageMedia,
    MessageDeliveryStatus, TypingIndicator, ChatNotification,
    ConversationType, MessageStatus
)
from app.models.models import User, Property, Tenant


# ===========================================================
# CONVERSATION REPOSITORY
# ===========================================================

class ConversationRepository:
    """Data access for conversations with isolation"""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_id(
        self,
        conversation_id: UUID,
        tenant_id: UUID,
        property_id: Optional[UUID],
        user_id: UUID
    ) -> Optional[Conversation]:
        """
        Get conversation by ID with multi-level isolation:
        - Must belong to tenant
        - Must belong to property (skipped when property_id is None — Tenant Admin cross-property access)
        - User must be participant
        """
        conditions = [
            Conversation.id == conversation_id,
            Conversation.tenant_id == tenant_id,
            Conversation.deleted_at.is_(None),
        ]
        if property_id is not None:
            conditions.append(Conversation.property_id == property_id)

        stmt = (
            select(Conversation)
            .where(and_(*conditions))
            .options(
                selectinload(Conversation.participants).selectinload(ConversationParticipant.user),
                selectinload(Conversation.creator),
            )
        )
        result = await self.session.execute(stmt)
        conversation = result.scalar_one_or_none()

        # Verify user is participant
        if conversation:
            is_participant = any(p.user_id == user_id for p in conversation.participants)
            if not is_participant:
                return None

        return conversation

    async def get_user_conversations(
        self,
        user_id: UUID,
        tenant_id: UUID,
        property_id: Optional[UUID] = None,
        skip: int = 0,
        limit: int = 50,
        include_archived: bool = False
    ) -> Tuple[List[Conversation], int]:
        """
        Get all conversations for user in property, ordered by last activity.
        When property_id is None (Tenant Admin), returns conversations from all properties.
        Returns (conversations, total_count)
        """
        conditions = [
            Conversation.tenant_id == tenant_id,
            Conversation.deleted_at.is_(None),
        ]
        if property_id is not None:
            conditions.append(Conversation.property_id == property_id)

        # Base query: conversations where user is participant and not deleted
        base_query = (
            select(Conversation)
            .join(
                ConversationParticipant,
                and_(
                    Conversation.id == ConversationParticipant.conversation_id,
                    ConversationParticipant.user_id == user_id,
                    ConversationParticipant.left_at.is_(None)  # Still member
                )
            )
            .where(and_(*conditions))
        )

        # Filter archived if needed
        if not include_archived:
            base_query = base_query.where(Conversation.is_archived.is_(False))

        # Count query — must use .subquery() for SQLAlchemy 2.0 compatibility
        count_stmt = select(func.count()).select_from(base_query.subquery())
        count_result = await self.session.execute(count_stmt)
        total_count = count_result.scalar()

        # Fetch paginated results, ordered by last activity
        stmt = (
            base_query
            .options(
                selectinload(Conversation.participants).selectinload(ConversationParticipant.user)
            )
            .order_by(desc(Conversation.last_message_at), desc(Conversation.created_at))
            .offset(skip)
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        conversations = result.unique().scalars().all()

        return conversations, total_count

    async def get_direct_conversation(
        self,
        user_id1: UUID,
        user_id2: UUID,
        tenant_id: UUID,
        property_id: UUID
    ) -> Optional[Conversation]:
        """
        Find existing direct conversation between two users.
        Returns None if doesn't exist.
        """
        stmt = (
            select(Conversation)
            .where(
                and_(
                    Conversation.type == ConversationType.DIRECT.value,
                    Conversation.tenant_id == tenant_id,
                    Conversation.property_id == property_id,
                    Conversation.deleted_at.is_(None)
                )
            )
            .options(selectinload(Conversation.participants))
        )
        result = await self.session.execute(stmt)
        conversations = result.scalars().all()

        # Check both participants (participants already eagerly loaded above)
        for conv in conversations:
            participants_ids = {p.user_id for p in conv.participants}
            if user_id1 in participants_ids and user_id2 in participants_ids:
                return conv

        return None

    async def create(
        self,
        conversation_type: ConversationType,
        tenant_id: UUID,
        property_id: UUID,
        created_by: UUID,
        name: Optional[str] = None,
        description: Optional[str] = None,
        avatar_url: Optional[str] = None
    ) -> Conversation:
        """Create new conversation"""
        conversation = Conversation(
            type=conversation_type,
            tenant_id=tenant_id,
            property_id=property_id,
            created_by=created_by,
            name=name,
            description=description,
            avatar_url=avatar_url,
            participant_count=0
        )
        self.session.add(conversation)
        await self.session.flush()
        return conversation

    async def update(
        self,
        conversation_id: UUID,
        tenant_id: UUID,
        property_id: UUID,
        name: Optional[str] = None,
        description: Optional[str] = None,
        avatar_url: Optional[str] = None
    ) -> Optional[Conversation]:
        """Update conversation (name, description, avatar)"""
        stmt = (
            select(Conversation)
            .where(
                and_(
                    Conversation.id == conversation_id,
                    Conversation.tenant_id == tenant_id,
                    Conversation.property_id == property_id,
                    Conversation.deleted_at.is_(None)
                )
            )
        )
        result = await self.session.execute(stmt)
        conversation = result.scalar_one_or_none()

        if not conversation:
            return None

        if name is not None:
            conversation.name = name
        if description is not None:
            conversation.description = description
        if avatar_url is not None:
            conversation.avatar_url = avatar_url

        await self.session.flush()
        return conversation

    async def archive(
        self,
        conversation_id: UUID,
        tenant_id: UUID,
        property_id: UUID
    ) -> Optional[Conversation]:
        """Archive conversation (soft delete logic)"""
        stmt = (
            select(Conversation)
            .where(
                and_(
                    Conversation.id == conversation_id,
                    Conversation.tenant_id == tenant_id,
                    Conversation.property_id == property_id,
                    Conversation.deleted_at.is_(None)
                )
            )
        )
        result = await self.session.execute(stmt)
        conversation = result.scalar_one_or_none()

        if not conversation:
            return None

        conversation.is_archived = True
        await self.session.flush()
        return conversation

    async def delete(
        self,
        conversation_id: UUID,
        tenant_id: UUID,
        property_id: UUID
    ) -> bool:
        """Hard delete conversation"""
        stmt = (
            select(Conversation)
            .where(
                and_(
                    Conversation.id == conversation_id,
                    Conversation.tenant_id == tenant_id,
                    Conversation.property_id == property_id
                )
            )
        )
        result = await self.session.execute(stmt)
        conversation = result.scalar_one_or_none()

        if not conversation:
            return False

        await self.session.delete(conversation)
        await self.session.flush()
        return True


# ===========================================================
# PARTICIPANT REPOSITORY
# ===========================================================

class ParticipantRepository:
    """Data access for conversation participants"""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def add_participant(
        self,
        conversation_id: UUID,
        user_id: UUID,
        role: str = "member"
    ) -> Optional[ConversationParticipant]:
        """Add user to conversation"""
        # Check if already participant
        stmt = select(ConversationParticipant).where(
            and_(
                ConversationParticipant.conversation_id == conversation_id,
                ConversationParticipant.user_id == user_id
            )
        )
        result = await self.session.execute(stmt)
        existing = result.scalar_one_or_none()

        if existing and existing.left_at is None:
            return existing  # Already participant

        if existing and existing.left_at is not None:
            # Rejoin conversation
            existing.left_at = None
            await self.session.flush()
            return existing

        # Create new participant
        participant = ConversationParticipant(
            conversation_id=conversation_id,
            user_id=user_id,
            role=role
        )
        self.session.add(participant)
        await self.session.flush()
        return participant

    async def get_participant(
        self,
        conversation_id: UUID,
        user_id: UUID
    ) -> Optional[ConversationParticipant]:
        """Get participant (must not have left)"""
        stmt = select(ConversationParticipant).where(
            and_(
                ConversationParticipant.conversation_id == conversation_id,
                ConversationParticipant.user_id == user_id,
                ConversationParticipant.left_at.is_(None)
            )
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_participants(
        self,
        conversation_id: UUID
    ) -> List[ConversationParticipant]:
        """Get all active participants in conversation"""
        stmt = (
            select(ConversationParticipant)
            .where(
                and_(
                    ConversationParticipant.conversation_id == conversation_id,
                    ConversationParticipant.left_at.is_(None)
                )
            )
            .options(selectinload(ConversationParticipant.user))
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def remove_participant(
        self,
        conversation_id: UUID,
        user_id: UUID
    ) -> bool:
        """Remove user from conversation (soft delete)"""
        stmt = select(ConversationParticipant).where(
            and_(
                ConversationParticipant.conversation_id == conversation_id,
                ConversationParticipant.user_id == user_id,
                ConversationParticipant.left_at.is_(None)
            )
        )
        result = await self.session.execute(stmt)
        participant = result.scalar_one_or_none()

        if not participant:
            return False

        from datetime import datetime
        participant.left_at = datetime.utcnow()
        await self.session.flush()
        return True

    async def update_role(
        self,
        conversation_id: UUID,
        user_id: UUID,
        new_role: str
    ) -> Optional[ConversationParticipant]:
        """Change participant role"""
        stmt = select(ConversationParticipant).where(
            and_(
                ConversationParticipant.conversation_id == conversation_id,
                ConversationParticipant.user_id == user_id,
                ConversationParticipant.left_at.is_(None)
            )
        )
        result = await self.session.execute(stmt)
        participant = result.scalar_one_or_none()

        if not participant:
            return None

        participant.role = new_role
        await self.session.flush()
        return participant

    async def mute_conversation(
        self,
        conversation_id: UUID,
        user_id: UUID,
        is_muted: bool
    ) -> Optional[ConversationParticipant]:
        """Mute/unmute conversation for user"""
        stmt = select(ConversationParticipant).where(
            and_(
                ConversationParticipant.conversation_id == conversation_id,
                ConversationParticipant.user_id == user_id
            )
        )
        result = await self.session.execute(stmt)
        participant = result.scalar_one_or_none()

        if not participant:
            return None

        participant.is_muted = is_muted
        await self.session.flush()
        return participant


# ===========================================================
# MESSAGE REPOSITORY
# ===========================================================

class MessageRepository:
    """Data access for messages with search and pagination"""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(
        self,
        conversation_id: UUID,
        sender_id: UUID,
        content: str,
        tenant_id: UUID,
        reply_to_id: Optional[UUID] = None,
        mentions: Optional[dict] = None
    ) -> Message:
        """Create new message"""
        message = Message(
            conversation_id=conversation_id,
            sender_id=sender_id,
            content=content,
            tenant_id=tenant_id,
            reply_to_id=reply_to_id,
            mentions=mentions
        )
        self.session.add(message)
        await self.session.flush()
        return message

    async def get_by_id(
        self,
        message_id: UUID,
        conversation_id: UUID
    ) -> Optional[Message]:
        """Get message by ID (not deleted)"""
        stmt = (
            select(Message)
            .where(
                and_(
                    Message.id == message_id,
                    Message.conversation_id == conversation_id,
                    Message.deleted_at.is_(None)
                )
            )
            .options(
                selectinload(Message.sender),
                selectinload(Message.media),
                selectinload(Message.statuses)
            )
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_conversation_messages(
        self,
        conversation_id: UUID,
        skip: int = 0,
        limit: int = 50
    ) -> Tuple[List[Message], int]:
        """
        Get messages in conversation with pagination (newest first).
        Returns (messages, total_count)
        """
        # Count active messages
        count_stmt = (
            select(func.count())
            .select_from(Message)
            .where(
                and_(
                    Message.conversation_id == conversation_id,
                    Message.deleted_at.is_(None)
                )
            )
        )
        count_result = await self.session.execute(count_stmt)
        total_count = count_result.scalar()

        # Fetch paginated messages
        stmt = (
            select(Message)
            .where(
                and_(
                    Message.conversation_id == conversation_id,
                    Message.deleted_at.is_(None)
                )
            )
            .options(
                selectinload(Message.sender),
                selectinload(Message.media),
                selectinload(Message.statuses)
            )
            .order_by(desc(Message.created_at))
            .offset(skip)
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        messages = result.unique().scalars().all()
        messages.reverse()  # Return in ascending order (oldest first)

        return messages, total_count

    async def search(
        self,
        conversation_id: UUID,
        query: str,
        skip: int = 0,
        limit: int = 50
    ) -> Tuple[List[Message], int]:
        """Search messages by content"""
        # Full text search (ILIKE for case-insensitive)
        search_query = f"%{query}%"

        count_stmt = (
            select(func.count())
            .select_from(Message)
            .where(
                and_(
                    Message.conversation_id == conversation_id,
                    Message.deleted_at.is_(None),
                    Message.content.ilike(search_query)
                )
            )
        )
        count_result = await self.session.execute(count_stmt)
        total_count = count_result.scalar()

        stmt = (
            select(Message)
            .where(
                and_(
                    Message.conversation_id == conversation_id,
                    Message.deleted_at.is_(None),
                    Message.content.ilike(search_query)
                )
            )
            .options(
                selectinload(Message.sender),
                selectinload(Message.media)
            )
            .order_by(desc(Message.created_at))
            .offset(skip)
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        messages = result.unique().scalars().all()

        return messages, total_count

    async def update(
        self,
        message_id: UUID,
        conversation_id: UUID,
        content: str
    ) -> Optional[Message]:
        """Edit message"""
        from datetime import datetime
        
        stmt = (
            select(Message)
            .where(
                and_(
                    Message.id == message_id,
                    Message.conversation_id == conversation_id,
                    Message.deleted_at.is_(None)
                )
            )
        )
        result = await self.session.execute(stmt)
        message = result.scalar_one_or_none()

        if not message:
            return None

        message.content = content
        message.edited_at = datetime.utcnow()
        message.edited_count += 1
        await self.session.flush()
        return message

    async def soft_delete(
        self,
        message_id: UUID,
        conversation_id: UUID
    ) -> bool:
        """Soft delete message"""
        from datetime import datetime
        
        stmt = (
            select(Message)
            .where(
                and_(
                    Message.id == message_id,
                    Message.conversation_id == conversation_id,
                    Message.deleted_at.is_(None)
                )
            )
        )
        result = await self.session.execute(stmt)
        message = result.scalar_one_or_none()

        if not message:
            return False

        message.deleted_at = datetime.utcnow()
        await self.session.flush()
        return True

    async def hard_delete(
        self,
        message_id: UUID,
        conversation_id: UUID
    ) -> bool:
        """Hard delete message and media"""
        stmt = (
            select(Message)
            .where(
                and_(
                    Message.id == message_id,
                    Message.conversation_id == conversation_id
                )
            )
        )
        result = await self.session.execute(stmt)
        message = result.scalar_one_or_none()

        if not message:
            return False

        await self.session.delete(message)
        await self.session.flush()
        return True

    async def get_last_messages_for_conversations(
        self,
        conversation_ids: List[UUID]
    ) -> dict:
        """Get the latest non-deleted message for each conversation in one query."""
        if not conversation_ids:
            return {}

        subq = (
            select(
                Message.conversation_id,
                func.max(Message.created_at).label("max_created_at")
            )
            .where(
                and_(
                    Message.conversation_id.in_(conversation_ids),
                    Message.deleted_at.is_(None)
                )
            )
            .group_by(Message.conversation_id)
            .subquery()
        )

        stmt = (
            select(Message)
            .join(
                subq,
                and_(
                    Message.conversation_id == subq.c.conversation_id,
                    Message.created_at == subq.c.max_created_at
                )
            )
            .where(Message.deleted_at.is_(None))
            .options(
                selectinload(Message.sender),
                selectinload(Message.media)
            )
        )
        result = await self.session.execute(stmt)
        messages = result.unique().scalars().all()
        return {m.conversation_id: m for m in messages}


# ===========================================================
# MESSAGE MEDIA REPOSITORY
# ===========================================================

class MessageMediaRepository:
    """Data access for message attachments"""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(
        self,
        message_id: UUID,
        media_type: str,
        storage_key: str,
        original_filename: str,
        file_size_bytes: int,
        mime_type: str,
        thumbnail_key: Optional[str] = None,
        width: Optional[int] = None,
        height: Optional[int] = None,
        duration_seconds: Optional[float] = None
    ) -> MessageMedia:
        """Create media attachment record"""
        media = MessageMedia(
            message_id=message_id,
            media_type=media_type,
            storage_key=storage_key,
            original_filename=original_filename,
            file_size_bytes=file_size_bytes,
            mime_type=mime_type,
            thumbnail_key=thumbnail_key,
            width=width,
            height=height,
            duration_seconds=duration_seconds
        )
        self.session.add(media)
        await self.session.flush()
        return media

    async def get_by_id(self, media_id: UUID) -> Optional[MessageMedia]:
        """Get media by ID"""
        stmt = select(MessageMedia).where(MessageMedia.id == media_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_message_media(self, message_id: UUID) -> List[MessageMedia]:
        """Get all media for message"""
        stmt = (
            select(MessageMedia)
            .where(MessageMedia.message_id == message_id)
            .order_by(MessageMedia.created_at)
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def delete(self, media_id: UUID) -> bool:
        """Delete media record"""
        stmt = select(MessageMedia).where(MessageMedia.id == media_id)
        result = await self.session.execute(stmt)
        media = result.scalar_one_or_none()

        if not media:
            return False

        await self.session.delete(media)
        await self.session.flush()
        return True


# ===========================================================
# MESSAGE DELIVERY STATUS REPOSITORY
# ===========================================================

class MessageDeliveryStatusRepository:
    """Data access for message delivery and read receipts"""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_or_update(
        self,
        message_id: UUID,
        user_id: UUID,
        status: str
    ) -> MessageDeliveryStatus:
        """Create or update delivery status"""
        stmt = select(MessageDeliveryStatus).where(
            and_(
                MessageDeliveryStatus.message_id == message_id,
                MessageDeliveryStatus.user_id == user_id
            )
        )
        result = await self.session.execute(stmt)
        delivery_status = result.scalar_one_or_none()

        if delivery_status:
            delivery_status.status = status
        else:
            delivery_status = MessageDeliveryStatus(
                message_id=message_id,
                user_id=user_id,
                status=status
            )
            self.session.add(delivery_status)

        await self.session.flush()
        return delivery_status

    async def get_message_statuses(
        self,
        message_id: UUID
    ) -> List[MessageDeliveryStatus]:
        """Get all statuses for message"""
        stmt = (
            select(MessageDeliveryStatus)
            .where(MessageDeliveryStatus.message_id == message_id)
            .options(selectinload(MessageDeliveryStatus.user))
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def get_user_status(
        self,
        message_id: UUID,
        user_id: UUID
    ) -> Optional[MessageDeliveryStatus]:
        """Get delivery status for specific user"""
        stmt = select(MessageDeliveryStatus).where(
            and_(
                MessageDeliveryStatus.message_id == message_id,
                MessageDeliveryStatus.user_id == user_id
            )
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()
