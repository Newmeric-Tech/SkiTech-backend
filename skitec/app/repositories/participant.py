"""
Repository for ConversationParticipant model.
Handles database access for managing conversation participants.
"""

from typing import List, Optional
from uuid import UUID
from sqlalchemy import select, and_, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.chat import ConversationParticipant, Conversation
from app.repositories.base import BaseRepository


class ParticipantRepository:
    """Repository for participant management."""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.model_class = ConversationParticipant

    async def add_participant(
        self,
        conversation_id: UUID,
        user_id: UUID,
        role: str = "member",
    ) -> ConversationParticipant:
        """Add a user to a conversation."""
        participant = ConversationParticipant(
            conversation_id=conversation_id,
            user_id=user_id,
            role=role,
        )
        self.session.add(participant)
        await self.session.flush()
        await self.session.refresh(participant)
        return participant

    async def remove_participant(
        self,
        conversation_id: UUID,
        user_id: UUID,
    ) -> bool:
        """Remove a user from a conversation."""
        query = select(ConversationParticipant).where(
            and_(
                ConversationParticipant.conversation_id == conversation_id,
                ConversationParticipant.user_id == user_id,
            )
        )
        
        result = await self.session.execute(query)
        participant = result.scalars().first()
        
        if not participant:
            return False
        
        await self.session.delete(participant)
        await self.session.flush()
        return True

    async def get_participant(
        self,
        conversation_id: UUID,
        user_id: UUID,
    ) -> Optional[ConversationParticipant]:
        """Get a specific participant."""
        query = select(ConversationParticipant).where(
            and_(
                ConversationParticipant.conversation_id == conversation_id,
                ConversationParticipant.user_id == user_id,
            )
        )
        
        result = await self.session.execute(query)
        return result.scalars().first()

    async def get_all_participants(
        self,
        conversation_id: UUID,
    ) -> List[ConversationParticipant]:
        """Get all participants in a conversation."""
        query = (
            select(ConversationParticipant)
            .where(ConversationParticipant.conversation_id == conversation_id)
            .options(selectinload(ConversationParticipant.user))
        )
        
        result = await self.session.execute(query)
        return result.scalars().all()

    async def update_participant_role(
        self,
        conversation_id: UUID,
        user_id: UUID,
        new_role: str,
    ) -> Optional[ConversationParticipant]:
        """Update a participant's role."""
        participant = await self.get_participant(conversation_id, user_id)
        if not participant:
            return None
        
        participant.role = new_role
        self.session.add(participant)
        await self.session.flush()
        await self.session.refresh(participant)
        return participant

    async def update_last_read(
        self,
        conversation_id: UUID,
        user_id: UUID,
        message_id: Optional[UUID] = None,
    ) -> Optional[ConversationParticipant]:
        """Update participant's last read message."""
        from datetime import datetime, timezone
        
        participant = await self.get_participant(conversation_id, user_id)
        if not participant:
            return None
        
        participant.last_read_at = datetime.now(timezone.utc)
        participant.last_read_message_id = message_id
        self.session.add(participant)
        await self.session.flush()
        await self.session.refresh(participant)
        return participant

    async def update_mute_status(
        self,
        conversation_id: UUID,
        user_id: UUID,
        is_muted: bool,
    ) -> Optional[ConversationParticipant]:
        """Update participant's mute status."""
        participant = await self.get_participant(conversation_id, user_id)
        if not participant:
            return None
        
        participant.is_muted = is_muted
        self.session.add(participant)
        await self.session.flush()
        await self.session.refresh(participant)
        return participant

    async def get_participant_count(
        self,
        conversation_id: UUID,
    ) -> int:
        """Get number of participants in conversation."""
        query = select(func.count(ConversationParticipant.user_id)).where(
            ConversationParticipant.conversation_id == conversation_id
        )
        
        result = await self.session.execute(query)
        return result.scalar() or 0

    async def has_admin(
        self,
        conversation_id: UUID,
    ) -> bool:
        """Check if conversation has at least one admin."""
        query = select(ConversationParticipant).where(
            and_(
                ConversationParticipant.conversation_id == conversation_id,
                ConversationParticipant.role == "admin",
            )
        )
        
        result = await self.session.execute(query)
        return result.scalars().first() is not None
