"""
WebSocket Manager for Real-time Chat - app/websocket/manager.py

Handles:
- WebSocket connection management per conversation
- Broadcasting messages to participants
- Typing indicators
- Online/offline presence
- Real-time event publishing
- Multi-tenant isolation

Future: Redis integration for scaled deployments
"""

from datetime import datetime, timedelta
from typing import Dict, List, Optional, Set
from uuid import UUID
import asyncio
import json

from fastapi import WebSocket


# ===========================================================
# WEBSOCKET CONNECTION
# ===========================================================

class ChatConnection:
    """Represents a single WebSocket connection"""

    def __init__(
        self,
        websocket: WebSocket,
        user_id: UUID,
        conversation_id: UUID,
        tenant_id: UUID,
        property_id: UUID,
        connection_id: str
    ):
        self.websocket = websocket
        self.user_id = user_id
        self.conversation_id = conversation_id
        self.tenant_id = tenant_id
        self.property_id = property_id
        self.connection_id = connection_id
        self.connected_at = datetime.utcnow()
        self.last_activity = datetime.utcnow()
        self.is_typing = False
        self.typing_started_at: Optional[datetime] = None

    async def send_json(self, data: dict) -> None:
        """Send JSON message to client"""
        try:
            await self.websocket.send_json(data)
            self.last_activity = datetime.utcnow()
        except Exception as e:
            # Connection closed or error
            pass

    async def send_text(self, text: str) -> None:
        """Send text message to client"""
        try:
            await self.websocket.send_text(text)
            self.last_activity = datetime.utcnow()
        except Exception as e:
            pass

    async def close(self, code: int = 1000, reason: str = "Closing") -> None:
        """Close connection"""
        try:
            await self.websocket.close(code=code, reason=reason)
        except Exception:
            pass


# ===========================================================
# WEBSOCKET MANAGER
# ===========================================================

class WebSocketManager:
    """
    Centralized WebSocket connection manager.
    
    Tracks active connections per conversation with tenant/property isolation.
    
    Data structure:
    {
        tenant_id: {
            property_id: {
                conversation_id: {
                    user_id: [ChatConnection, ChatConnection, ...]
                }
            }
        }
    }
    """

    def __init__(self):
        # Active connections: tenant_id -> property_id -> conversation_id -> user_id -> [connections]
        self.active_connections: Dict = {}
        
        # Typing indicators: (conversation_id, user_id) -> expires_at
        self.typing_indicators: Dict[tuple, datetime] = {}
        
        # Online users: (tenant_id, property_id) -> set(user_ids)
        self.online_users: Dict[tuple, Set[UUID]] = {}
        
        # Connection counter for unique IDs
        self._connection_counter = 0

    def _get_connection_id(self) -> str:
        """Generate unique connection ID"""
        self._connection_counter += 1
        return f"conn_{self._connection_counter}_{datetime.utcnow().timestamp()}"

    async def connect(
        self,
        websocket: WebSocket,
        conversation_id: UUID,
        user_id: UUID,
        tenant_id: UUID,
        property_id: UUID
    ) -> ChatConnection:
        """
        Register new WebSocket connection.
        
        Called when user connects to a conversation.
        """
        await websocket.accept()

        connection_id = self._get_connection_id()
        connection = ChatConnection(
            websocket=websocket,
            user_id=user_id,
            conversation_id=conversation_id,
            tenant_id=tenant_id,
            property_id=property_id,
            connection_id=connection_id
        )

        # Store connection in nested dict structure
        if tenant_id not in self.active_connections:
            self.active_connections[tenant_id] = {}
        if property_id not in self.active_connections[tenant_id]:
            self.active_connections[tenant_id][property_id] = {}
        if conversation_id not in self.active_connections[tenant_id][property_id]:
            self.active_connections[tenant_id][property_id][conversation_id] = {}
        if user_id not in self.active_connections[tenant_id][property_id][conversation_id]:
            self.active_connections[tenant_id][property_id][conversation_id][user_id] = []

        self.active_connections[tenant_id][property_id][conversation_id][user_id].append(connection)

        # Mark user as online
        online_key = (tenant_id, property_id)
        if online_key not in self.online_users:
            self.online_users[online_key] = set()
        self.online_users[online_key].add(user_id)

        return connection

    async def disconnect(self, connection: ChatConnection) -> None:
        """
        Unregister WebSocket connection.
        Called when connection closes.
        """
        try:
            tenant_id = connection.tenant_id
            property_id = connection.property_id
            conversation_id = connection.conversation_id
            user_id = connection.user_id

            # Remove connection
            if (tenant_id in self.active_connections and
                property_id in self.active_connections[tenant_id] and
                conversation_id in self.active_connections[tenant_id][property_id] and
                user_id in self.active_connections[tenant_id][property_id][conversation_id]):

                connections = self.active_connections[tenant_id][property_id][conversation_id][user_id]
                connections = [c for c in connections if c.connection_id != connection.connection_id]

                if connections:
                    self.active_connections[tenant_id][property_id][conversation_id][user_id] = connections
                else:
                    del self.active_connections[tenant_id][property_id][conversation_id][user_id]

            # If user has no more connections in property, mark offline
            user_connections = self._get_user_connections(tenant_id, property_id, user_id)
            if not user_connections:
                online_key = (tenant_id, property_id)
                if online_key in self.online_users:
                    self.online_users[online_key].discard(user_id)

        except Exception as e:
            pass

    # ===========================================================
    # QUERY METHODS
    # ===========================================================

    def _get_user_connections(
        self,
        tenant_id: UUID,
        property_id: UUID,
        user_id: UUID
    ) -> List[ChatConnection]:
        """Get all connections for user across all conversations in property"""
        connections = []
        if (tenant_id in self.active_connections and
            property_id in self.active_connections[tenant_id]):

            for conversation_id, conv_users in self.active_connections[tenant_id][property_id].items():
                if user_id in conv_users:
                    connections.extend(conv_users[user_id])

        return connections

    def get_conversation_connections(
        self,
        conversation_id: UUID,
        tenant_id: UUID,
        property_id: UUID
    ) -> List[ChatConnection]:
        """Get all connections in a conversation"""
        connections = []
        try:
            if (tenant_id in self.active_connections and
                property_id in self.active_connections[tenant_id] and
                conversation_id in self.active_connections[tenant_id][property_id]):

                for user_id, user_connections in self.active_connections[tenant_id][property_id][conversation_id].items():
                    connections.extend(user_connections)
        except Exception:
            pass

        return connections

    def get_conversation_participants(
        self,
        conversation_id: UUID,
        tenant_id: UUID,
        property_id: UUID
    ) -> Dict[UUID, int]:
        """
        Get online participants in conversation.
        Returns {user_id: connection_count}
        """
        participants = {}
        try:
            if (tenant_id in self.active_connections and
                property_id in self.active_connections[tenant_id] and
                conversation_id in self.active_connections[tenant_id][property_id]):

                conv_users = self.active_connections[tenant_id][property_id][conversation_id]
                for user_id, connections in conv_users.items():
                    participants[user_id] = len(connections)
        except Exception:
            pass

        return participants

    def get_online_users(
        self,
        tenant_id: UUID,
        property_id: UUID
    ) -> Set[UUID]:
        """Get all online users in property"""
        online_key = (tenant_id, property_id)
        return self.online_users.get(online_key, set())

    # ===========================================================
    # BROADCASTING
    # ===========================================================

    async def broadcast_to_conversation(
        self,
        conversation_id: UUID,
        tenant_id: UUID,
        property_id: UUID,
        message: dict,
        exclude_user_id: Optional[UUID] = None
    ) -> None:
        """
        Broadcast message to all users in conversation.
        
        Args:
            message: Dict with 'type' and 'data' keys
            exclude_user_id: Don't send to this user (optional)
        """
        connections = self.get_conversation_connections(
            conversation_id=conversation_id,
            tenant_id=tenant_id,
            property_id=property_id
        )

        for conn in connections:
            if exclude_user_id and conn.user_id == exclude_user_id:
                continue

            await conn.send_json({
                **message,
                "timestamp": datetime.utcnow().isoformat()
            })

    async def broadcast_to_user(
        self,
        user_id: UUID,
        tenant_id: UUID,
        property_id: UUID,
        message: dict
    ) -> None:
        """Send message to all connections of a user across property"""
        connections = self._get_user_connections(tenant_id, property_id, user_id)

        for conn in connections:
            await conn.send_json({
                **message,
                "timestamp": datetime.utcnow().isoformat()
            })

    # ===========================================================
    # TYPING INDICATORS
    # ===========================================================

    def set_typing(
        self,
        conversation_id: UUID,
        user_id: UUID,
        duration_seconds: int = 5
    ) -> None:
        """Mark user as typing for duration"""
        key = (conversation_id, user_id)
        self.typing_indicators[key] = datetime.utcnow() + timedelta(seconds=duration_seconds)

    def stop_typing(self, conversation_id: UUID, user_id: UUID) -> None:
        """Mark user as stopped typing"""
        key = (conversation_id, user_id)
        self.typing_indicators.pop(key, None)

    def get_typing_users(self, conversation_id: UUID) -> List[UUID]:
        """Get users currently typing in conversation"""
        typing_users = []
        now = datetime.utcnow()

        for (conv_id, user_id), expires_at in self.typing_indicators.items():
            if conv_id == conversation_id and expires_at > now:
                typing_users.append(user_id)

        # Clean expired indicators
        self.typing_indicators = {
            k: v for k, v in self.typing_indicators.items()
            if v > now
        }

        return typing_users

    # ===========================================================
    # REDIS INTEGRATION (FUTURE)
    # ===========================================================

    async def broadcast_to_all_servers(
        self,
        conversation_id: UUID,
        tenant_id: UUID,
        property_id: UUID,
        message: dict
    ) -> None:
        """
        Broadcast to all servers (Redis pub/sub).
        
        TODO: Implement Redis integration for multi-server deployments
        
        When deployed across multiple servers, need:
        - Redis PUBLISH to broadcast across servers
        - Redis SUBSCRIBE to receive from other servers
        - Connection tracking in Redis (with expiration)
        """
        # For now, just local broadcast
        await self.broadcast_to_conversation(
            conversation_id=conversation_id,
            tenant_id=tenant_id,
            property_id=property_id,
            message=message
        )


# ===========================================================
# GLOBAL WEBSOCKET MANAGER
# ===========================================================

_manager: Optional[WebSocketManager] = None


def init_websocket_manager() -> WebSocketManager:
    """Initialize global WebSocket manager"""
    global _manager
    if _manager is None:
        _manager = WebSocketManager()
    return _manager


def get_websocket_manager() -> WebSocketManager:
    """Get global WebSocket manager"""
    if _manager is None:
        raise RuntimeError("WebSocket manager not initialized. Call init_websocket_manager() first.")
    return _manager


# ===========================================================
# EVENT TYPES (Real-time Events)
# ===========================================================

class WebSocketEventType:
    """Real-time event type constants"""
    MESSAGE_SENT = "message.sent"
    MESSAGE_EDITED = "message.edited"
    MESSAGE_DELETED = "message.deleted"
    TYPING_START = "typing.start"
    TYPING_STOP = "typing.stop"
    READ_RECEIPT = "read.receipt"
    USER_ONLINE = "user.online"
    USER_OFFLINE = "user.offline"
    PARTICIPANT_JOINED = "participant.joined"
    PARTICIPANT_LEFT = "participant.left"
    CONVERSATION_CREATED = "conversation.created"
    CONVERSATION_ARCHIVED = "conversation.archived"
    PARTICIPANT_ROLE_CHANGED = "participant.role_changed"


# ===========================================================
# EVENT PUBLISHING HELPERS
# ===========================================================

async def publish_message_sent_event(
    manager: WebSocketManager,
    conversation_id: UUID,
    tenant_id: UUID,
    property_id: UUID,
    message_data: dict
) -> None:
    """Publish message sent event"""
    await manager.broadcast_to_conversation(
        conversation_id=conversation_id,
        tenant_id=tenant_id,
        property_id=property_id,
        message={
            "type": WebSocketEventType.MESSAGE_SENT,
            "data": message_data
        }
    )


async def publish_typing_event(
    manager: WebSocketManager,
    conversation_id: UUID,
    tenant_id: UUID,
    property_id: UUID,
    user_id: UUID,
    user_data: dict,
    is_typing: bool
) -> None:
    """Publish typing indicator event"""
    if is_typing:
        manager.set_typing(conversation_id, user_id)
    else:
        manager.stop_typing(conversation_id, user_id)

    await manager.broadcast_to_conversation(
        conversation_id=conversation_id,
        tenant_id=tenant_id,
        property_id=property_id,
        message={
            "type": WebSocketEventType.TYPING_START if is_typing else WebSocketEventType.TYPING_STOP,
            "data": {
                "user_id": str(user_id),
                "user": user_data
            }
        },
        exclude_user_id=user_id
    )


async def publish_read_receipt_event(
    manager: WebSocketManager,
    conversation_id: UUID,
    tenant_id: UUID,
    property_id: UUID,
    message_id: UUID,
    user_id: UUID,
    status: str
) -> None:
    """Publish read receipt event"""
    await manager.broadcast_to_conversation(
        conversation_id=conversation_id,
        tenant_id=tenant_id,
        property_id=property_id,
        message={
            "type": WebSocketEventType.READ_RECEIPT,
            "data": {
                "message_id": str(message_id),
                "user_id": str(user_id),
                "status": status
            }
        }
    )
