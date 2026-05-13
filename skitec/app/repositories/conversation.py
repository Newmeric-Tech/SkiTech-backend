"""
Repository for Conversation model.
Handles database access for conversations with multi-tenant/property isolation.
"""

from typing import List, Optional
from uuid import UUID
from sqlalchemy import select, and_, or_, func, desc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.chat import Conversation, ConversationParticipant, Message
from app.repositories.base import BaseRepository


class ConversationRepository(BaseRepository[Conversation]):
    """Repository for conversation CRUD and queries."""

    def __init__(self, session: AsyncSession):
        super().__init__(session, Conversation)

    async def get_conversations_for_user(
        self,
        user_id: UUID,
        tenant_id: UUID,
        property_id: UUID,
        skip: int = 0,
        limit: int = 20,
        include_archived: bool = False,
    ) -> tuple[List[Conversation], int]:
        """
        Get all conversations a user is a participant in.
        Ordered by most recent message.
        """
        # Filter: user is a participant, tenant/property match
        filters = [
            Conversation.tenant_id == tenant_id,
            Conversation.property_id == property_id,
        ]
        
        if not include_archived:
            filters.append(Conversation.is_archived == False)
        
        # Join with participants to check membership
        query = (
            select(Conversation)
            .join(ConversationParticipant)
            .where(
                and_(
                    ConversationParticipant.user_id == user_id,
                    and_(*filters),
                )
            )
            .distinct()
            .order_by(desc(Conversation.updated_at))
            .offset(skip)
            .limit(limit)
        )
        
        result = await self.session.execute(query)
        conversations = result.scalars().all()
        
        # Get total count
        count_query = (
            select(func.count(Conversation.id))
            .join(ConversationParticipant)
            .where(
                and_(
                    ConversationParticipant.user_id == user_id,
                    and_(*filters),
                )
            )
        )
        count_result = await self.session.execute(count_query)
        total = count_result.scalar() or 0
        
        return conversations, total

    async def get_direct_chat(
        self,
        user1_id: UUID,
        user2_id: UUID,
        tenant_id: UUID,
        property_id: UUID,
    ) -> Optional[Conversation]:
        """
        Get existing direct chat between two users.
        Returns None if no direct chat exists.
        """
        query = (
            select(Conversation)
            .where(
                and_(
                    Conversation.tenant_id == tenant_id,
                    Conversation.property_id == property_id,
                    Conversation.type == "direct",
                    # Either user is the creator and the other is participant
                    or_(
                        and_(
                            Conversation.created_by == user1_id,
                            ConversationParticipant.user_id == user2_id,
                        ),
                        and_(
                            Conversation.created_by == user2_id,
                            ConversationParticipant.user_id == user1_id,
                        ),
                    ),
                )
            )
            .join(ConversationParticipant)
            .options(selectinload(Conversation.participants))
        )
        
        result = await self.session.execute(query)
        return result.scalars().first()

    async def search_conversations(
        self,
        query_text: str,
        user_id: UUID,
        tenant_id: UUID,
        property_id: UUID,
        skip: int = 0,
        limit: int = 20,
    ) -> tuple[List[Conversation], int]:
        """
        Search conversations by name or participants.
        Only returns conversations the user is in.
        """
        search_pattern = f"%{query_text}%"
        
        filters = [
            Conversation.tenant_id == tenant_id,
            Conversation.property_id == property_id,
            ConversationParticipant.user_id == user_id,
            # Match on conversation name or participant emails
            or_(
                Conversation.name.ilike(search_pattern),
            ),
        ]
        
        query = (
            select(Conversation)
            .join(ConversationParticipant)
            .where(and_(*filters))
            .distinct()
            .order_by(desc(Conversation.updated_at))
            .offset(skip)
            .limit(limit)
        )
        
        result = await self.session.execute(query)
        conversations = result.scalars().all()
        
        # Get total count
        count_query = (
            select(func.count(Conversation.id))
            .join(ConversationParticipant)
            .where(and_(*filters))
        )
        count_result = await self.session.execute(count_query)
        total = count_result.scalar() or 0
        
        return conversations, total

    async def get_with_participants(
        self,
        conversation_id: UUID,
        tenant_id: UUID,
        property_id: UUID,
    ) -> Optional[Conversation]:
        """Get conversation with all participants loaded."""
        query = (
            select(Conversation)
            .where(
                and_(
                    Conversation.id == conversation_id,
                    Conversation.tenant_id == tenant_id,
                    Conversation.property_id == property_id,
                )
            )
            .options(selectinload(Conversation.participants))
        )
        
        result = await self.session.execute(query)
        return result.scalars().first()

    async def get_participant_count(
        self,
        conversation_id: UUID,
    ) -> int:
        """Get number of participants in a conversation."""
        query = (
            select(func.count(ConversationParticipant.user_id))
            .where(ConversationParticipant.conversation_id == conversation_id)
        )
        
        result = await self.session.execute(query)
        return result.scalar() or 0

    async def is_user_participant(
        self,
        conversation_id: UUID,
        user_id: UUID,
    ) -> bool:
        """Check if user is a participant in conversation."""
        query = (
            select(ConversationParticipant)
            .where(
                and_(
                    ConversationParticipant.conversation_id == conversation_id,
                    ConversationParticipant.user_id == user_id,
                )
            )
        )
        
        result = await self.session.execute(query)
        return result.scalars().first() is not None
