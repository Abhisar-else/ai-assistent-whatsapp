"""
WhatsApp webhook (Meta Cloud API).

GET  /webhook  -> verification handshake Meta calls once when you configure the webhook URL.
POST /webhook  -> receives incoming messages/status updates.
"""
import logging

from fastapi import APIRouter, Request, Response, status

from chatbot.engine import handle_message
from config.settings import settings
from database.db import log_conversation, upsert_user
from app.whatsapp_client import send_whatsapp_message

logger = logging.getLogger("webhook")
router = APIRouter()


@router.get("/webhook")
async def verify_webhook(request: Request):
    """Meta's one-time subscription verification handshake."""
    params = request.query_params
    mode = params.get("hub.mode")
    token = params.get("hub.verify_token")
    challenge = params.get("hub.challenge")

    if mode == "subscribe" and token == settings.META_VERIFY_TOKEN:
        logger.info("Webhook verified successfully.")
        return Response(content=challenge, media_type="text/plain")

    logger.warning("Webhook verification failed (bad token or mode).")
    return Response(status_code=status.HTTP_403_FORBIDDEN)


@router.post("/webhook")
async def receive_message(request: Request):
    """
    Handle incoming WhatsApp events. Meta's payload shape:
    entry -> changes -> value -> messages[] (present only for actual user messages;
    absent for delivery/read status callbacks, which we just acknowledge).
    """
    payload = await request.json()

    try:
        entries = payload.get("entry", [])
        for entry in entries:
            for change in entry.get("changes", []):
                value = change.get("value", {})
                messages = value.get("messages")
                if not messages:
                    continue  # status callback (sent/delivered/read) — nothing to do

                contacts = value.get("contacts", [])
                sender_name = contacts[0]["profile"]["name"] if contacts else None

                for msg in messages:
                    await _process_incoming_message(msg, sender_name)

    except Exception:
        # Never let a malformed/unexpected payload crash the webhook —
        # Meta will retry aggressively on non-2xx responses.
        logger.exception("Error while processing webhook payload")

    # Always ack quickly so Meta doesn't retry/back off.
    return Response(status_code=status.HTTP_200_OK)


async def _process_incoming_message(msg: dict, sender_name: str | None):
    user_number = msg.get("from")
    msg_type = msg.get("type")

    if msg_type != "text":
        # Day 3+/bonus: handle audio, images, etc. For now, politely decline.
        text_in = f"[unsupported message type: {msg_type}]"
        reply_text = "I can currently only read text messages — could you type that as text?"
        if user_number:
            upsert_user(user_number, sender_name)
            log_conversation(user_number, text_in, reply_text, intent="unsupported")
            await send_whatsapp_message(user_number, reply_text)
        return

    text_in = msg.get("text", {}).get("body", "")
    if not user_number or not text_in:
        return

    upsert_user(user_number, sender_name)

    result = handle_message(user_number, text_in)

    log_conversation(
        user_number=user_number,
        user_message=text_in,
        ai_response=result.text,
        intent=result.intent,
        llm_provider=result.provider,
    )

    await send_whatsapp_message(user_number, result.text)
