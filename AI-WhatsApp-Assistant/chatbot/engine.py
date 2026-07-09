"""
Conversation engine — the single entry point the webhook calls to turn an
incoming message into a reply.

Flow:
1. If the user has an in-progress meeting request, continue that slot-filling
   flow regardless of message content (they're mid-conversation).
2. Otherwise detect intent: meeting / internship / general.
3. For "meeting", start the slot-filling flow.
4. For "internship" / "general", search the knowledge base for relevant
   context and generate a reply via the LLM fallback chain (Gemini -> Groq
   -> OpenRouter -> heuristic).
"""
from dataclasses import dataclass

from chatbot import intents, meeting_flow
from chatbot.knowledge_base import search_knowledge_base
from chatbot.llm import generate_reply
from config.settings import settings
from database.db import get_recent_conversation


@dataclass
class EngineResponse:
    text: str
    intent: str
    provider: str


def handle_message(user_number: str, message_text: str) -> EngineResponse:
    # 1. Mid-flow meeting scheduling takes priority over everything else.
    if meeting_flow.is_in_meeting_flow(user_number):
        reply_text, _completed = meeting_flow.continue_flow(user_number, message_text)
        return EngineResponse(text=reply_text, intent="meeting", provider="rule")

    intent = intents.detect_intent(message_text)

    # 2. Fresh meeting request.
    if intent == "meeting":
        reply_text = meeting_flow.start_flow(user_number)
        return EngineResponse(text=reply_text, intent="meeting", provider="rule")

    # 3. Internship / general queries -> knowledge base + LLM.
    kb_matches = search_knowledge_base(message_text, top_k=3)
    kb_context = "\n\n".join(f"{topic}: {content}" for topic, content, _score in kb_matches)

    history = get_recent_conversation(user_number, limit=settings.CONTEXT_WINDOW_TURNS)

    reply_text, provider = generate_reply(message_text, kb_context, history)
    return EngineResponse(text=reply_text, intent=intent, provider=provider)
