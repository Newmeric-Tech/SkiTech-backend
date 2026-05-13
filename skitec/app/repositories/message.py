"""
Repository for Message model.
Handles database access for messages with multi-tenant isolation.
"""

from typing import List, Optional
from uuid import UUID
from sqlalchemy import select, and_, desc, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.chat import Message, MessageReadReceipt, MessageStatus
from app.repositories.base import BaseRepository


class MessageRepository(BaseRepository[Message]):
    """Repository for message CRUD and queries."""

    def __init__(self, session: AsyncSession):
        super().__init__(session, Message)

    async def get_conversation_messages(
        self,
        conversation_id: UUID,
        tenant_id: UUID,
        skip: int = 0,
        limit: int = 50,
        include_deleted: bool = False,
    ) -> tuple[List[Message], int]:
        """
        Get messages in a conversation, newest first.
        Includes read receipts for each message.
        """
        filters = [
            Message.conversation_id == conversation_id,
            Message.tenant_id == tenant_id,
        ]
        
        if not include_deleted:
            filters.append(Message.is_deleted == False)
        
        # Get total count
        count_query = select(func.count(Message.id)).where(and_(*filters))
        count_result = await self.session.execute(count_query)
        total = count_result.scalar() or 0
        
        # Get paginated results
        query = (
            select(Message)
            .where(and_(*filters))
            .options(
                selectinload(Message.sender),
                selectinload(Message.media),
                selectinload(Message.read_receipts),
            )
            .order_by(desc(Message.created_at))
            .offset(skip)
            .limit(limit)
        )
        
        result = await self.session.execute(query)
        messages = result.scalars().all()
        
        # Reverse to get oldest-first order
        return list(reversed(messages)), total

    async def search_messages(
        self,
        conversation_id: UUID,
        tenant_id: UUID,
        query_text: str,
        skip: int = 0,
        limit: int = 20,
    ) -> tuple[List[Message], int]:
        """
        Search messages in a conversation by content.
        Only searches non-deleted messages.
        """
        search_pattern = f"%{query_text}%"
        
        filters = [
            Message.conversation_id == conversation_id,
            Message.tenant_id == tenant_id,
            Message.is_deleted == False,
            Message.content.ilike(search_pattern),
        ]
        
        # Get total count
        count_query = select(func.count(Message.id)).where(and_(*filters))
        count_result = await self.session.execute(count_query)
        total = count_result.scalar() or 0
        
        # Get paginated results
        query = (
            select(Message)
            .where(and_(*filters))
            .options(
                selectinload(Message.sender),
                selectinload(Message.media),
            )
            .order_by(desc(Message.created_at))
            .offset(skip)
            .limit(limit)
        )
        
        result = await self.session.execute(query)
        return result.scalars().all(), total

    async def get_with_details(
        self,
        message_id: UUID,
        tenant_id: UUID,
    ) -> Optional[Message]:
        """Get message with all related data (sender, media, read receipts)."""
        query = (
            select(Message)
            .where(
                and_(
                    Message.id == message_id,
                    Message.tenant_id == tenant_id,
                )
            )
            .options(
                selectinload(Message.sender),
                selectinload(Message.media),
                selectinload(Message.read_receipts),
                selectinload(Message.reply_to),
            )
        )
        
        result = await self.session.execute(query)
        return result.scalars().first()

    async def get_unread_count(
        self,
        conversation_id: UUID,
        user_id: UUID,
        since: Optional[datetime] = None,
    ) -> int:
        """
        Get count of unread messages in conversation for user.
        Optionally only count messages after a specific datetime.
        """
        filters = [
            Message.conversation_id == conversation_id,
            Message.is_deleted == False,
        ]
        
        # Messages not read by user
        filters.append(
            ~select(MessageReadReceipt.id)
            .where(
                and_(
                    MessageReadReceipt.message_id == Message.id,
                    MessageReadReceipt.user_id == user_id,
                    MessageReadReceipt.status == MessageStatus.READ,
                )
            )
            .correlate(Message)
            .exists()
        )
        
        if since:
            filters.append(Message.created_at >= since)
        
        query = select(func.count(Message.id)).where(and_(*filters))
        result = await self.session.execute(query)
        return result.scalar() or 0

    async def mark_as_deleted(
        self,
        message_id: UUID,
        tenant_id: UUID,
    ) -> bool:
        """Soft delete a message."""
        message = await self.get_by_id(message_id, tenant_id)
        if not message:
            return False
        
        message.is_deleted = True
        self.session.add(message)
        await self.session.flush()
        return True

    async def get_last_message(
        self,
        conversation_id: UUID,
        tenant_id: UUID,
    ) -> Optional[Message]:
        """Get the most recent message in a conversation."""
        query = (
            select(Message)
            .where(
                and_(
                    Message.conversation_id == conversation_id,
                    Message.tenant_id == tenant_id,
                    Message.is_deleted == False,
                )
            )
            .order_by(desc(Message.created_at))
            .limit(1)
            .options(selectinload(Message.sender))
        )
        
        result = await self.session.execute(query)
        return result.scalars().first()


from datetime import datetime
