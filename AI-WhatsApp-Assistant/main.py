"""
AI WhatsApp Executive Assistant — entrypoint.

Run with:  uvicorn main:app --reload --port 8000
"""
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from config.settings import settings
from database.db import init_db
from chatbot.knowledge_base import load_knowledge_base
from app.webhook import router as webhook_router
from app.admin import router as admin_router

# --- logging setup ---
Path(settings.LOGS_DIR).mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler(Path(settings.LOGS_DIR) / "app.log"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger("main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    load_knowledge_base()
    logger.info("%s starting up (env=%s, db=%s)", settings.APP_NAME, settings.ENV, settings.DATABASE_PATH)
    yield
    logger.info("Shutting down.")


app = FastAPI(title=settings.APP_NAME, lifespan=lifespan)

app.include_router(webhook_router, tags=["whatsapp"])
app.include_router(admin_router)
app.mount("/static", StaticFiles(directory=str(settings.BASE_DIR / "static")), name="static")


@app.get("/")
async def root():
    return {"status": "ok", "app": settings.APP_NAME}


@app.get("/health")
async def health():
    return {"status": "healthy"}
