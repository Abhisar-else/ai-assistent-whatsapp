"""
Pydantic response models for the admin API. Keeping these separate from
the raw SQL layer gives FastAPI accurate OpenAPI docs and catches
schema drift between database/db.py and what the API actually returns.
"""
from pydantic import BaseModel


class ConversationRecord(BaseModel):
    id: int
    user_number: str
    user_message: str
    ai_response: str
    intent: str | None = None
    llm_provider: str | None = None
    timestamp: str


class ConversationsResponse(BaseModel):
    results: list[ConversationRecord]


class MeetingRecord(BaseModel):
    id: int
    user_number: str
    name: str | None = None
    preferred_date: str | None = None
    preferred_time: str | None = None
    purpose: str | None = None
    status: str
    created_at: str


class MeetingsResponse(BaseModel):
    results: list[MeetingRecord]


class StatsResponse(BaseModel):
    total_conversations: int
    total_users: int
    total_meetings: int
    by_provider: dict[str, int]
    by_intent: dict[str, int]


class KnowledgeBaseReloadResponse(BaseModel):
    status: str
    entries: int
