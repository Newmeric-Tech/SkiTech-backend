"""
WebSocket endpoint for real-time chat functionality.
Handles message delivery, typing indicators, presence, and read receipts in real-time.
"""

import json
from typing import Optional
from uuid import UUID
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query, status, Depends
from sqlalchemy.ext.asyncio import AsyncSession
import logging

from app.core.database import get_db
from app.core.security import get_current_user_from_token
from app.models.user import User
from app.repositories.conversation import ConversationRepository
from app.services.chat_service import MessageService, ConversationService
from app.services.storage.local_storage import LocalStorageService
from app.utils.chat_manager import chat_manager
from app.schemas.chat import (
    WSMessageTypeEnum,
    WSSendMessage,
    WSReadMessage,
    WSTypingStart,
    WSTypingStop,
    WSUserOnline,
    WSUserOffline,
    WSMessageReceived,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/ws", tags=["websocket"])


@router.websocket("/chat/{conversation_id}")
async def websocket_chat(
    websocket: WebSocket,
    conversation_id: UUID,
    token: str = Query(...),
    db: Optional[AsyncSession] = None,
):
    """
    WebSocket endpoint for real-time chat.
    
    URL: ws://localhost:8000/v1/ws/chat/{conversation_id}?token={jwt_token}
    
    Supports events:
    - message:send - Send a new message
    - message:read - Mark message as read
    - typing:start - User started typing
    - typing:stop - User stopped typing
    """
    
    # Initialize DB if not provided (for async context)
    if db is None:
        db_generator = get_db()
        db = await db_generator.__anext__()
    
    try:
        # Authenticate user from JWT token
        current_user = await get_current_user_from_token(token)
        if not current_user:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Invalid token")
            return
        
        # Verify user is a participant in this conversation
        conv_repo = ConversationRepository(db)
        if not await conv_repo.is_user_participant(conversation_id, current_user.id):
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Not a conversation member")
            return
        
        # Connect to WebSocket and register with chat manager
        await chat_manager.connect(
            websocket,
            conversation_id,
            current_user.id,
            current_user.tenant_id,
            current_user.property_id,
        )
        
        # Notify others that user is online
        online_users = chat_manager.get_online_users(conversation_id)
        await chat_manager.broadcast_to_conversation(
            conversation_id,
            {
                "type": WSMessageTypeEnum.USER_ONLINE,
                "user_id": str(current_user.id),
                "user_name": f"{current_user.first_name} {current_user.last_name}",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "online_users": [str(u) for u in online_users],
            },
            exclude_user_id=current_user.id,
        )
        
        # Initialize services
        storage_service = LocalStorageService(base_path="./storage")
        msg_service = MessageService(db, storage_service)
        
        # Main message loop
        while True:
            # Receive message from client
            data = await websocket.receive_text()
            
            try:
                msg_data = json.loads(data)
                msg_type = msg_data.get("type")
                
                logger.debug(f"WebSocket message from {current_user.id}: {msg_type}")
                
                # ============================================================
                # SEND MESSAGE
                # ============================================================
                if msg_type == WSMessageTypeEnum.MESSAGE_SEND:
                    content = msg_data.get("content", "").strip()
                    
                    if not content:
                        await websocket.send_json({
                            "type": "error",
                            "message": "Message content cannot be empty",
                        })
                        continue
                    
                    # Save message to database
                    msg = await msg_service.send_message(
                        conversation_id=conversation_id,
                        sender_id=current_user.id,
                        tenant_id=current_user.tenant_id,
                        content=content,
                        message_type=msg_data.get("message_type", "text"),
                        reply_to_id=msg_data.get("reply_to_id"),
                    )
                    
                    # Broadcast to all participants
                    await chat_manager.broadcast_to_conversation(
                        conversation_id,
                        {
                            "type": WSMessageTypeEnum.MESSAGE_SEND,
                            "message_id": str(msg.id),
                            "conversation_id": str(conversation_id),
                            "sender_id": str(current_user.id),
                            "sender_name": f"{current_user.first_name} {current_user.last_name}",
                            "content": msg.content,
                            "message_type": msg.message_type,
                            "created_at": msg.created_at.isoformat(),
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                        },
                    )
                    
                    # Clear typing indicator
                    await chat_manager.unset_typing(conversation_id, current_user.id)
                
                # ============================================================
                # MARK AS READ
                # ============================================================
                elif msg_type == WSMessageTypeEnum.MESSAGE_READ:
                    message_id = msg_data.get("message_id")
                    
                    if not message_id:
                        continue
                    
                    try:
                        message_uuid = UUID(message_id)
                        await msg_service.mark_as_read(
                            message_id=message_uuid,
                            user_id=current_user.id,
                            tenant_id=current_user.tenant_id,
                        )
                        
                        # Broadcast read receipt
                        await chat_manager.broadcast_to_conversation(
                            conversation_id,
                            {
                                "type": WSMessageTypeEnum.MESSAGE_READ,
                                "message_id": message_id,
                                "user_id": str(current_user.id),
                                "user_name": f"{current_user.first_name} {current_user.last_name}",
                                "timestamp": datetime.now(timezone.utc).isoformat(),
                            },
                        )
                    except (ValueError, Exception) as e:
                        logger.error(f"Error marking message as read: {e}")
                
                # ============================================================
                # TYPING START
                # ============================================================
                elif msg_type == WSMessageTypeEnum.TYPING_START:
                    await chat_manager.set_typing(conversation_id, current_user.id)
                    
                    # Broadcast to others
                    await chat_manager.broadcast_to_conversation(
                        conversation_id,
                        {
                            "type": WSMessageTypeEnum.TYPING_START,
                            "user_id": str(current_user.id),
                            "user_name": f"{current_user.first_name} {current_user.last_name}",
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                        },
                        exclude_user_id=current_user.id,
                    )
                
                # ============================================================
                # TYPING STOP
                # ============================================================
                elif msg_type == WSMessageTypeEnum.TYPING_STOP:
                    await chat_manager.unset_typing(conversation_id, current_user.id)
                    
                    # Broadcast to others
                    await chat_manager.broadcast_to_conversation(
                        conversation_id,
                        {
                            "type": WSMessageTypeEnum.TYPING_STOP,
                            "user_id": str(current_user.id),
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                        },
                        exclude_user_id=current_user.id,
                    )
                
                else:
                    logger.warning(f"Unknown WebSocket message type: {msg_type}")
            
            except json.JSONDecodeError:
                await websocket.send_json({
                    "type": "error",
                    "message": "Invalid JSON",
                })
            except Exception as e:
                logger.error(f"WebSocket error: {e}", exc_info=True)
                await websocket.send_json({
                    "type": "error",
                    "message": f"Server error: {str(e)}",
                })
    
    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected: {current_user.id} from {conversation_id}")
        
        # Unregister from chat manager
        await chat_manager.disconnect(
            websocket,
            conversation_id,
            current_user.id,
        )
        
        # Notify others that user is offline
        online_users = chat_manager.get_online_users(conversation_id)
        await chat_manager.broadcast_to_conversation(
            conversation_id,
            {
                "type": WSMessageTypeEnum.USER_OFFLINE,
                "user_id": str(current_user.id),
                "user_name": f"{current_user.first_name} {current_user.last_name}",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "online_users": [str(u) for u in online_users],
            },
        )
    
    except Exception as e:
        logger.error(f"Unexpected WebSocket error: {e}", exc_info=True)
        try:
            await websocket.close(code=status.WS_1011_SERVER_ERROR, reason="Internal server error")
        except:
            pass
    
    finally:
        # Cleanup
        try:
            await chat_manager.disconnect(websocket, conversation_id, current_user.id)
        except:
            pass


from datetime import datetime, timezone
