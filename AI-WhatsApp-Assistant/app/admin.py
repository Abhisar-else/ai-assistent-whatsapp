"""
Admin endpoints (PRD 3G): view conversation history, search conversations,
view meeting requests, manage/reload the knowledge base, export logs, and
monitor AI activity.

Auth: a single shared admin key passed as header `X-Admin-Key`. This is
deliberately simple (no user accounts) — appropriate for a solo-admin
internal tool built in a 4-day sprint. Swap for real auth before any
multi-admin or public deployment.
"""
import csv
import io

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from fastapi.responses import FileResponse, StreamingResponse

from chatbot.knowledge_base import load_knowledge_base
from config.settings import settings
from database.db import get_connection, list_meetings, search_conversations
from models.schemas import (
    ConversationsResponse,
    KnowledgeBaseReloadResponse,
    MeetingsResponse,
    StatsResponse,
)

router = APIRouter(prefix="/admin", tags=["admin"])


def require_admin(x_admin_key: str = Header(default="")):
    if not x_admin_key or x_admin_key != settings.ADMIN_API_KEY:
        raise HTTPException(status_code=401, detail="Invalid or missing X-Admin-Key header")


@router.get("/dashboard")
async def dashboard():
    """Serves the admin console shell. Data inside it is fetched client-side
    and requires the admin key, so the page itself needs no server auth."""
    return FileResponse(settings.BASE_DIR / "templates" / "admin_dashboard.html")


@router.get("/conversations", response_model=ConversationsResponse, dependencies=[Depends(require_admin)])
async def get_conversations(
    query: str | None = Query(default=None, description="Search text in message or response"),
    user_number: str | None = Query(default=None),
    limit: int = Query(default=100, le=1000),
):
    """View + search conversation history."""
    return {"results": search_conversations(query=query, user_number=user_number, limit=limit)}


@router.get("/meetings", response_model=MeetingsResponse, dependencies=[Depends(require_admin)])
async def get_meetings(status: str | None = Query(default=None, description="pending | confirmed | cancelled")):
    """View scheduled meeting requests."""
    return {"results": list_meetings(status=status)}


@router.get("/export/conversations", dependencies=[Depends(require_admin)])
async def export_conversations():
    """Export all conversation logs as a downloadable CSV."""
    rows = search_conversations(limit=100000)
    buffer = io.StringIO()
    if rows:
        writer = csv.DictWriter(buffer, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    buffer.seek(0)
    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=conversations_export.csv"},
    )


@router.post("/knowledge-base/reload", response_model=KnowledgeBaseReloadResponse, dependencies=[Depends(require_admin)])
async def reload_knowledge_base():
    """
    Re-read knowledge_base/*.md and *.json into SQLite. Call this after
    editing KB files so changes take effect without restarting the app.
    """
    load_knowledge_base()
    with get_connection() as conn:
        count = conn.execute("SELECT COUNT(*) AS c FROM knowledge_base").fetchone()["c"]
    return {"status": "reloaded", "entries": count}


@router.get("/stats", response_model=StatsResponse, dependencies=[Depends(require_admin)])
async def get_stats():
    """Monitor AI activity: volume, provider usage, intent breakdown."""
    with get_connection() as conn:
        total_conversations = conn.execute("SELECT COUNT(*) AS c FROM conversations").fetchone()["c"]
        total_users = conn.execute("SELECT COUNT(*) AS c FROM users").fetchone()["c"]
        total_meetings = conn.execute("SELECT COUNT(*) AS c FROM meetings").fetchone()["c"]
        provider_rows = conn.execute(
            "SELECT llm_provider, COUNT(*) AS c FROM conversations GROUP BY llm_provider"
        ).fetchall()
        intent_rows = conn.execute(
            "SELECT intent, COUNT(*) AS c FROM conversations GROUP BY intent"
        ).fetchall()

    return {
        "total_conversations": total_conversations,
        "total_users": total_users,
        "total_meetings": total_meetings,
        # defensively drop any NULL keys (shouldn't occur — intent/provider are always set)
        "by_provider": {r["llm_provider"]: r["c"] for r in provider_rows if r["llm_provider"] is not None},
        "by_intent": {r["intent"]: r["c"] for r in intent_rows if r["intent"] is not None},
    }
