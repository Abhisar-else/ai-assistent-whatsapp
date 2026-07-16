"""
Postgres schema for the AI WhatsApp Executive Assistant.

Tables:
- users             : one row per WhatsApp number seen
- conversations      : every message/response pair (PRD 3F)
- meetings            : meeting requests captured by the scheduler (PRD 3D)
- meeting_sessions    : in-progress slot-filling state (separate stateless HTTP requests)
- knowledge_base      : mirror of knowledge_base/*.md and *.json
- processed_messages  : dedup guard against webhook retries

Timestamp columns are TEXT (not native TIMESTAMP) storing exactly
'YYYY-MM-DD HH:MM:SS' in UTC — this matches SQLite's original
datetime('now') output byte-for-byte, so the admin dashboard's JS
(which parses these as ISO-ish strings) needed zero changes when
migrating off SQLite.
"""

_NOW = "to_char(CURRENT_TIMESTAMP AT TIME ZONE 'UTC', 'YYYY-MM-DD HH24:MI:SS')"

SCHEMA = f"""
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    phone_number TEXT UNIQUE NOT NULL,
    name TEXT,
    first_seen TEXT NOT NULL DEFAULT {_NOW},
    last_active TEXT NOT NULL DEFAULT {_NOW}
);

CREATE TABLE IF NOT EXISTS conversations (
    id SERIAL PRIMARY KEY,
    user_number TEXT NOT NULL,
    user_message TEXT NOT NULL,
    ai_response TEXT NOT NULL,
    intent TEXT,
    llm_provider TEXT,
    timestamp TEXT NOT NULL DEFAULT {_NOW},
    FOREIGN KEY (user_number) REFERENCES users(phone_number)
);

CREATE TABLE IF NOT EXISTS meetings (
    id SERIAL PRIMARY KEY,
    user_number TEXT NOT NULL,
    name TEXT,
    preferred_date TEXT,
    preferred_time TEXT,
    purpose TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    created_at TEXT NOT NULL DEFAULT {_NOW},
    FOREIGN KEY (user_number) REFERENCES users(phone_number)
);

CREATE INDEX IF NOT EXISTS idx_conversations_user ON conversations(user_number);
CREATE INDEX IF NOT EXISTS idx_conversations_time ON conversations(timestamp);
CREATE INDEX IF NOT EXISTS idx_meetings_user ON meetings(user_number);

CREATE TABLE IF NOT EXISTS knowledge_base (
    id SERIAL PRIMARY KEY,
    topic TEXT NOT NULL,
    content TEXT NOT NULL,
    source_file TEXT NOT NULL,
    updated_at TEXT NOT NULL DEFAULT {_NOW}
);

CREATE INDEX IF NOT EXISTS idx_kb_topic ON knowledge_base(topic);

CREATE TABLE IF NOT EXISTS meeting_sessions (
    user_number TEXT PRIMARY KEY,
    name TEXT,
    preferred_date TEXT,
    preferred_time TEXT,
    purpose TEXT,
    stage TEXT NOT NULL DEFAULT 'name',
    updated_at TEXT NOT NULL DEFAULT {_NOW}
);

CREATE TABLE IF NOT EXISTS processed_messages (
    message_id TEXT PRIMARY KEY,
    processed_at TEXT NOT NULL DEFAULT {_NOW}
);
"""