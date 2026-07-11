"""
Lightweight SQLite access layer. No ORM — the schema is small enough that
raw SQL keeps things transparent and easy for an admin to inspect.
"""
import sqlite3
from contextlib import contextmanager
from pathlib import Path

from config.settings import settings
from database.models import SCHEMA


def _ensure_parent_dir():
    Path(settings.DATABASE_PATH).parent.mkdir(parents=True, exist_ok=True)


@contextmanager
def get_connection():
    _ensure_parent_dir()
    conn = sqlite3.connect(settings.DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    """Create tables if they don't exist. Safe to call on every startup."""
    with get_connection() as conn:
        conn.executescript(SCHEMA)


# ---------- users ----------

def upsert_user(phone_number: str, name: str | None = None):
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO users (phone_number, name)
            VALUES (?, ?)
            ON CONFLICT(phone_number) DO UPDATE SET
                last_active = datetime('now'),
                name = COALESCE(excluded.name, users.name)
            """,
            (phone_number, name),
        )


# ---------- conversations ----------

def log_conversation(user_number: str, user_message: str, ai_response: str,
                      intent: str | None = None, llm_provider: str | None = None):
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO conversations (user_number, user_message, ai_response, intent, llm_provider)
            VALUES (?, ?, ?, ?, ?)
            """,
            (user_number, user_message, ai_response, intent, llm_provider),
        )


def get_recent_conversation(user_number: str, limit: int = 10):
    """Most recent N turns for a user, oldest first (for LLM context)."""
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT user_message, ai_response, timestamp
            FROM conversations
            WHERE user_number = ?
            ORDER BY id DESC
            LIMIT ?
            """,
            (user_number, limit),
        ).fetchall()
    return list(reversed([dict(r) for r in rows]))


def search_conversations(query: str | None = None, user_number: str | None = None, limit: int = 100):
    sql = "SELECT * FROM conversations WHERE 1=1"
    params = []
    if user_number:
        sql += " AND user_number = ?"
        params.append(user_number)
    if query:
        sql += " AND (user_message LIKE ? OR ai_response LIKE ?)"
        params.extend([f"%{query}%", f"%{query}%"])
    sql += " ORDER BY id DESC LIMIT ?"
    params.append(limit)
    with get_connection() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [dict(r) for r in rows]


# ---------- meetings ----------

def create_meeting(user_number: str, name: str | None, preferred_date: str | None,
                    preferred_time: str | None, purpose: str | None):
    with get_connection() as conn:
        cur = conn.execute(
            """
            INSERT INTO meetings (user_number, name, preferred_date, preferred_time, purpose)
            VALUES (?, ?, ?, ?, ?)
            """,
            (user_number, name, preferred_date, preferred_time, purpose),
        )
        return cur.lastrowid


def list_meetings(status: str | None = None, limit: int = 200):
    sql = "SELECT * FROM meetings WHERE 1=1"
    params = []
    if status:
        sql += " AND status = ?"
        params.append(status)
    sql += " ORDER BY id DESC LIMIT ?"
    params.append(limit)
    with get_connection() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [dict(r) for r in rows]


# ---------- meeting_sessions (slot-filling state machine) ----------

def get_meeting_session(user_number: str):
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM meeting_sessions WHERE user_number = ?", (user_number,)
        ).fetchone()
    return dict(row) if row else None


def start_meeting_session(user_number: str):
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO meeting_sessions (user_number, stage)
            VALUES (?, 'name')
            ON CONFLICT(user_number) DO UPDATE SET
                stage = 'name', name = NULL, preferred_date = NULL,
                preferred_time = NULL, purpose = NULL, updated_at = datetime('now')
            """,
            (user_number,),
        )


def update_meeting_session(user_number: str, field: str, value: str, next_stage: str):
    if field not in {"name", "preferred_date", "preferred_time", "purpose"}:
        raise ValueError(f"Invalid meeting session field: {field!r}")
    with get_connection() as conn:
        conn.execute(
            f"""
            UPDATE meeting_sessions
            SET {field} = ?, stage = ?, updated_at = datetime('now')
            WHERE user_number = ?
            """,
            (value, next_stage, user_number),
        )


def clear_meeting_session(user_number: str):
    with get_connection() as conn:
        conn.execute("DELETE FROM meeting_sessions WHERE user_number = ?", (user_number,))



# ---------- processed_messages (dedup Meta webhook retries) ----------

def mark_message_processed(message_id: str) -> bool:
    """Returns True if this message_id hasn't been seen before (safe to
    process), False if it's a duplicate delivery that should be skipped."""
    with get_connection() as conn:
        cur = conn.execute(
            "INSERT OR IGNORE INTO processed_messages (message_id) VALUES (?)",
            (message_id,),
        )
        return cur.rowcount > 0


# ---------- meeting status updates ----------

def set_meeting_status(meeting_id: int, status: str) -> bool:
    """Returns True if a row was actually updated (meeting_id existed)."""
    with get_connection() as conn:
        cur = conn.execute(
            "UPDATE meetings SET status = ? WHERE id = ?",
            (status, meeting_id),
        )
        return cur.rowcount > 0
