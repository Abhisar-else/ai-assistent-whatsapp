"""
Postgres access layer (psycopg2). Every query uses %s placeholders (not
SQLite's ?) and rows come back as real dicts via RealDictCursor.

_ConnWrapper below adds .execute()/.executemany()/.executescript() directly
on the connection object, mirroring sqlite3.Connection's convenience API —
this let the rest of the codebase (admin.py, knowledge_base.py) keep calling
conn.execute(...) unchanged rather than needing an explicit cursor everywhere.
"""
import logging
from contextlib import contextmanager

import psycopg2
import psycopg2.extras

from config.settings import settings
from database.models import SCHEMA

logger = logging.getLogger("db")


class _ConnWrapper:
    def __init__(self, conn):
        self._conn = conn

    def execute(self, sql, params=None):
        cur = self._conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(sql, params or ())
        return cur

    def executemany(self, sql, seq_of_params):
        cur = self._conn.cursor()
        cur.executemany(sql, list(seq_of_params))
        return cur

    def executescript(self, sql):
        cur = self._conn.cursor()
        cur.execute(sql)
        return cur

    def commit(self):
        self._conn.commit()

    def close(self):
        self._conn.close()


@contextmanager
def get_connection():
    if not settings.DATABASE_URL:
        raise RuntimeError(
            "DATABASE_URL is not set. This app requires Postgres — "
            "see README.md 'Database (Postgres)' for how to create a free "
            "instance on Render and set this variable."
        )
    conn = psycopg2.connect(settings.DATABASE_URL)
    wrapper = _ConnWrapper(conn)
    try:
        yield wrapper
        wrapper.commit()
    finally:
        wrapper.close()


def init_db():
    with get_connection() as conn:
        conn.executescript(SCHEMA)


def upsert_user(phone_number: str, name: str | None = None):
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO users (phone_number, name)
            VALUES (%s, %s)
            ON CONFLICT(phone_number) DO UPDATE SET
                last_active = to_char(CURRENT_TIMESTAMP AT TIME ZONE 'UTC', 'YYYY-MM-DD HH24:MI:SS'),
                name = COALESCE(EXCLUDED.name, users.name)
            """,
            (phone_number, name),
        )


def log_conversation(user_number: str, user_message: str, ai_response: str,
                      intent: str | None = None, llm_provider: str | None = None):
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO conversations (user_number, user_message, ai_response, intent, llm_provider)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (user_number, user_message, ai_response, intent, llm_provider),
        )


def get_recent_conversation(user_number: str, limit: int = 10):
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT user_message, ai_response, timestamp
            FROM conversations
            WHERE user_number = %s
            ORDER BY id DESC
            LIMIT %s
            """,
            (user_number, limit),
        ).fetchall()
    return list(reversed([dict(r) for r in rows]))


def search_conversations(query: str | None = None, user_number: str | None = None, limit: int = 100):
    sql = "SELECT * FROM conversations WHERE 1=1"
    params = []
    if user_number:
        sql += " AND user_number = %s"
        params.append(user_number)
    if query:
        sql += " AND (user_message ILIKE %s OR ai_response ILIKE %s)"
        params.extend([f"%{query}%", f"%{query}%"])
    sql += " ORDER BY id DESC LIMIT %s"
    params.append(limit)
    with get_connection() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [dict(r) for r in rows]


def create_meeting(user_number: str, name: str | None, preferred_date: str | None,
                    preferred_time: str | None, purpose: str | None):
    with get_connection() as conn:
        cur = conn.execute(
            """
            INSERT INTO meetings (user_number, name, preferred_date, preferred_time, purpose)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id
            """,
            (user_number, name, preferred_date, preferred_time, purpose),
        )
        return cur.fetchone()["id"]


def list_meetings(status: str | None = None, limit: int = 200):
    sql = "SELECT * FROM meetings WHERE 1=1"
    params = []
    if status:
        sql += " AND status = %s"
        params.append(status)
    sql += " ORDER BY id DESC LIMIT %s"
    params.append(limit)
    with get_connection() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [dict(r) for r in rows]


def get_meeting_session(user_number: str):
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM meeting_sessions WHERE user_number = %s", (user_number,)
        ).fetchone()
    return dict(row) if row else None


def start_meeting_session(user_number: str):
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO meeting_sessions (user_number, stage)
            VALUES (%s, 'name')
            ON CONFLICT(user_number) DO UPDATE SET
                stage = 'name', name = NULL, preferred_date = NULL,
                preferred_time = NULL, purpose = NULL,
                updated_at = to_char(CURRENT_TIMESTAMP AT TIME ZONE 'UTC', 'YYYY-MM-DD HH24:MI:SS')
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
            SET {field} = %s, stage = %s,
                updated_at = to_char(CURRENT_TIMESTAMP AT TIME ZONE 'UTC', 'YYYY-MM-DD HH24:MI:SS')
            WHERE user_number = %s
            """,
            (value, next_stage, user_number),
        )


def clear_meeting_session(user_number: str):
    with get_connection() as conn:
        conn.execute("DELETE FROM meeting_sessions WHERE user_number = %s", (user_number,))


def mark_message_processed(message_id: str) -> bool:
    with get_connection() as conn:
        cur = conn.execute(
            "INSERT INTO processed_messages (message_id) VALUES (%s) ON CONFLICT (message_id) DO NOTHING",
            (message_id,),
        )
        return cur.rowcount > 0


def set_meeting_status(meeting_id: int, status: str) -> bool:
    with get_connection() as conn:
        cur = conn.execute(
            "UPDATE meetings SET status = %s WHERE id = %s",
            (status, meeting_id),
        )
        return cur.rowcount > 0