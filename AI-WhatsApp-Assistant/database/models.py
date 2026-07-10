"""
SQLite schema for the AI WhatsApp Executive Assistant.

Tables:
- users          : one row per WhatsApp number seen
- conversations   : every message/response pair (PRD 3F)
- meetings         : meeting requests captured by the scheduler (PRD 3D)
"""

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    phone_number TEXT UNIQUE NOT NULL,
    name TEXT,
    first_seen TEXT NOT NULL DEFAULT (datetime('now')),
    last_active TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS conversations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_number TEXT NOT NULL,
    user_message TEXT NOT NULL,
    ai_response TEXT NOT NULL,
    intent TEXT,                       -- e.g. faq | meeting | general | internship
    llm_provider TEXT,                 -- gemini | groq | openrouter | heuristic
    timestamp TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (user_number) REFERENCES users(phone_number)
);

CREATE TABLE IF NOT EXISTS meetings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_number TEXT NOT NULL,
    name TEXT,
    preferred_date TEXT,
    preferred_time TEXT,
    purpose TEXT,
    status TEXT NOT NULL DEFAULT 'pending',   -- pending | confirmed | cancelled
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (user_number) REFERENCES users(phone_number)
);

CREATE INDEX IF NOT EXISTS idx_conversations_user ON conversations(user_number);
CREATE INDEX IF NOT EXISTS idx_conversations_time ON conversations(timestamp);
CREATE INDEX IF NOT EXISTS idx_meetings_user ON meetings(user_number);

-- Mirrors knowledge_base/*.md and *.json. Files are the source of truth;
-- this table is rebuilt on every startup so admins edit content, not code.
CREATE TABLE IF NOT EXISTS knowledge_base (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    topic TEXT NOT NULL,
    content TEXT NOT NULL,
    source_file TEXT NOT NULL,
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_kb_topic ON knowledge_base(topic);

-- Tracks an in-progress meeting-request conversation (slot filling) since
-- each WhatsApp message arrives as a separate, stateless HTTP request.
CREATE TABLE IF NOT EXISTS meeting_sessions (
    user_number TEXT PRIMARY KEY,
    name TEXT,
    preferred_date TEXT,
    preferred_time TEXT,
    purpose TEXT,
    stage TEXT NOT NULL DEFAULT 'name',   -- name -> date -> time -> purpose -> done
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Guards against Meta re-delivering the same webhook message (which it does
-- if it doesn't receive a fast 200) causing duplicate replies/meeting rows.
CREATE TABLE IF NOT EXISTS processed_messages (
    message_id TEXT PRIMARY KEY,
    processed_at TEXT NOT NULL DEFAULT (datetime('now'))
);
"""
