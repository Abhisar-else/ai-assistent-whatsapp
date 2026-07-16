"""
Central configuration for the AI WhatsApp Executive Assistant.
All secrets/config come from environment variables (.env) — nothing is hardcoded.
"""
import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env from project root regardless of where the app is launched from
BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


class Settings:
    # --- App ---
    APP_NAME: str = "AI WhatsApp Executive Assistant"
    ENV: str = os.getenv("ENV", "development")
    BASE_DIR: Path = BASE_DIR

    # --- Database (postgres) ---
    DATABASE_URL: str = os.getenv("DATABASE_URL", "")

    # --- Knowledge base ---
    KNOWLEDGE_BASE_DIR: str = os.getenv("KNOWLEDGE_BASE_DIR", str(BASE_DIR / "knowledge_base"))

    # --- Logs ---
    LOGS_DIR: str = os.getenv("LOGS_DIR", str(BASE_DIR / "logs"))

    # --- LLM providers (fallback order: Gemini -> Groq/OpenRouter -> heuristic) ---
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
    GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-3.5-flash")

    GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "")
    GROQ_MODEL: str = os.getenv("GROQ_MODEL", "llama-3.1-8b-instant")

    OPENROUTER_API_KEY: str = os.getenv("OPENROUTER_API_KEY", "")
    OPENROUTER_MODEL: str = os.getenv("OPENROUTER_MODEL", "meta-llama/llama-3.1-8b-instruct:free")

    # --- Conversation memory ---
    CONTEXT_WINDOW_TURNS: int = int(os.getenv("CONTEXT_WINDOW_TURNS", "10"))

    # --- WhatsApp: Meta Cloud API (primary) ---
    META_WHATSAPP_TOKEN: str = os.getenv("META_WHATSAPP_TOKEN", "")
    META_PHONE_NUMBER_ID: str = os.getenv("META_PHONE_NUMBER_ID", "")
    META_VERIFY_TOKEN: str = os.getenv("META_VERIFY_TOKEN", "")
    META_APP_SECRET: str = os.getenv("META_APP_SECRET", "")
    META_GRAPH_API_VERSION: str = os.getenv("META_GRAPH_API_VERSION", "v20.0")

    # --- WhatsApp: Twilio Sandbox (fallback channel) ---
    WHATSAPP_PROVIDER: str = os.getenv("WHATSAPP_PROVIDER", "meta")  # "meta" | "twilio"
    TWILIO_ACCOUNT_SID: str = os.getenv("TWILIO_ACCOUNT_SID", "")
    TWILIO_AUTH_TOKEN: str = os.getenv("TWILIO_AUTH_TOKEN", "")
    TWILIO_WHATSAPP_FROM: str = os.getenv("TWILIO_WHATSAPP_FROM", "")

    # --- Admin ---
    ADMIN_API_KEY: str = os.getenv("ADMIN_API_KEY", "change-me")


settings = Settings()
