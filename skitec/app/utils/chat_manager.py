"""
WebSocket connection manager for real-time chat.
Manages active connections, message broadcasting, and presence tracking.
"""

import json
from typing import Dict, Set, Optional
from uuid import UUID
from datetime import datetime, timezone
from fastapi import WebSocket
from logging import getLogger

logger = getLogger(__name__)


class ChatConnectionManager:
    """
    Manages WebSocket connections for real-time chat.
    
    Tracks:
    - Active connections per user per conversation
    - User presence (online/offline)
    - Typing indicators
    - Message broadcasts to conversation participants
    """

    def __init__(self):
        # Format: {conversation_id: {user_id: websocket}}
        self.active_conversations: Dict[UUID, Dict[UUID, Set[WebSocket]]] = {}
        
        # Format: {user_id: {"online": bool, "last_seen": datetime, "active_conv": UUID}}
        self.user_presence: Dict[UUID, dict] = {}
        
        # Format: {conversation_id: {user_id: datetime}}
        self.typing_users: Dict[UUID, Dict[UUID, datetime]] = {}

    async def connect(
        self,
        websocket: WebSocket,
        conversation_id: UUID,
        user_id: UUID,
        tenant_id: UUID,
        property_id: UUID,
    ):
        """Register a user connection to a conversation."""
        await websocket.accept()
        
        # Initialize conversation dict if needed
        if conversation_id not in self.active_conversations:
            self.active_conversations[conversation_id] = {}
        
        if user_id not in self.active_conversations[conversation_id]:
            self.active_conversations[conversation_id][user_id] = set()
        
        # Add websocket
        self.active_conversations[conversation_id][user_id].add(websocket)
        
        # Update presence
        self.user_presence[user_id] = {
            "online": True,
            "last_seen": datetime.now(timezone.utc),
            "active_conversation": conversation_id,
            "tenant_id": tenant_id,
            "property_id": property_id,
        }
        
        logger.info(
            f"User {user_id} connected to conversation {conversation_id}"
        )

    async def disconnect(
        self,
        websocket: WebSocket,
        conversation_id: UUID,
        user_id: UUID,
    ):
        """Unregister a user connection."""
        if (
            conversation_id in self.active_conversations
            and user_id in self.active_conversations[conversation_id]
        ):
            self.active_conversations[conversation_id][user_id].discard(websocket)
            
            # Clean up empty structures
            if not self.active_conversations[conversation_id][user_id]:
                del self.active_conversations[conversation_id][user_id]
            
            if not self.active_conversations[conversation_id]:
                del self.active_conversations[conversation_id]
        
        # Update presence - mark user as offline
        if user_id in self.user_presence:
            self.user_presence[user_id]["online"] = False
        
        logger.info(
            f"User {user_id} disconnected from conversation {conversation_id}"
        )

    async def broadcast_to_conversation(
        self,
        conversation_id: UUID,
        message: dict,
        exclude_user_id: Optional[UUID] = None,
    ):
        """
        Broadcast a message to all users in a conversation.
        
        Args:
            conversation_id: Target conversation
            message: Message dict to send
            exclude_user_id: Optionally exclude a user (e.g., sender)
        """
        if conversation_id not in self.active_conversations:
            return
        
        disconnected = set()
        
        for user_id, websockets in self.active_conversations[conversation_id].items():
            # Skip excluded user
            if exclude_user_id and user_id == exclude_user_id:
                continue
            
            for websocket in websockets:
                try:
                    await websocket.send_json(message)
                except Exception as e:
                    logger.error(f"Error sending to {user_id}: {e}")
                    disconnected.add((user_id, websocket))
        
        # Clean up disconnected
        for user_id, websocket in disconnected:
            await self.disconnect(websocket, conversation_id, user_id)

    async def broadcast_to_user(
        self,
        user_id: UUID,
        message: dict,
    ):
        """
        Broadcast a message to all connections of a user (across all conversations).
        Used for notifications, presence updates, etc.
        """
        disconnected = set()
        
        for conversation_id, users in self.active_conversations.items():
            if user_id in users:
                for websocket in users[user_id]:
                    try:
                        await websocket.send_json(message)
                    except Exception as e:
                        logger.error(f"Error sending to {user_id}: {e}")
                        disconnected.add((conversation_id, user_id, websocket))
        
        # Clean up disconnected
        for conversation_id, user_id_disc, websocket in disconnected:
            await self.disconnect(websocket, conversation_id, user_id_disc)

    def get_online_users(self, conversation_id: UUID) -> List[UUID]:
        """Get list of currently online users in a conversation."""
        if conversation_id not in self.active_conversations:
            return []
        
        return [
            user_id
            for user_id in self.active_conversations[conversation_id].keys()
            if self.user_presence.get(user_id, {}).get("online", False)
        ]

    def is_user_online(self, user_id: UUID) -> bool:
        """Check if a user is currently online."""
        return self.user_presence.get(user_id, {}).get("online", False)

    def get_user_active_conversation(self, user_id: UUID) -> Optional[UUID]:
        """Get the conversation a user is currently viewing."""
        return self.user_presence.get(user_id, {}).get("active_conversation")

    async def set_typing(
        self,
        conversation_id: UUID,
        user_id: UUID,
    ):
        """Mark a user as typing in a conversation."""
        if conversation_id not in self.typing_users:
            self.typing_users[conversation_id] = {}
        
        self.typing_users[conversation_id][user_id] = datetime.now(timezone.utc)

    async def unset_typing(
        self,
        conversation_id: UUID,
        user_id: UUID,
    ):
        """Mark a user as done typing."""
        if (
            conversation_id in self.typing_users
            and user_id in self.typing_users[conversation_id]
        ):
            del self.typing_users[conversation_id][user_id]

    def get_typing_users(self, conversation_id: UUID) -> List[UUID]:
        """
        Get list of users currently typing in a conversation.
        Expires typing status after 5 seconds of inactivity.
        """
        if conversation_id not in self.typing_users:
            return []
        
        now = datetime.now(timezone.utc)
        active_typists = []
        to_remove = []
        
        for user_id, last_typing in self.typing_users[conversation_id].items():
            age_seconds = (now - last_typing).total_seconds()
            
            if age_seconds < 5:
                active_typists.append(user_id)
            else:
                to_remove.append(user_id)
        
        # Clean up expired
        for user_id in to_remove:
            del self.typing_users[conversation_id][user_id]
        
        return active_typists


# Global chat manager instance
chat_manager = ChatConnectionManager()


from typing import List
