"""Evidence-Grounded Dataset Interaction / Chat Module (Step 8 / Roadmap #7).

Exposes:
- DatasetChatEngine
- execute_chat_turn
- ConversationContext, ChatMessage, ChatRequest, ChatResponse, ChatIntentType
"""

from orchestrator.chat.engine import DatasetChatEngine, default_chat_engine, execute_chat_turn
from orchestrator.chat.schemas import (
    ChatIntentType,
    ChatMessage,
    ChatRequest,
    ChatResponse,
    ChatRole,
    ConversationContext,
)

__all__ = [
    "ChatIntentType",
    "ChatMessage",
    "ChatRequest",
    "ChatResponse",
    "ChatRole",
    "ConversationContext",
    "DatasetChatEngine",
    "default_chat_engine",
    "execute_chat_turn",
]
