"""
WhatsApp webhook (Meta Cloud API).

GET  /webhook  -> verification handshake Meta calls once when you configure the webhook URL.
POST /webhook  -> receives incoming messages/status updates.

Two reliability/security properties that are easy to miss and important in
production:
1. Signature verification (X-Hub-Signature-256) — without this, anyone who
   discovers the webhook URL can POST fake messages. Enforced whenever
   META_APP_SECRET is configured; skipped with a loud warning otherwise so
   local/dev testing with plain curl still works.
2. Fast ack + background processing — Meta expects a 200 within a few
   seconds or it will retry delivery of the *same* message. Since an LLM
   call can take longer than that, we ack immediately and do the actual
   work (LLM call, DB writes, sending the reply) in a background task.
   Combined with message-id dedup below, this avoids duplicate replies /
   duplicate meeting rows if Meta does retry anyway.
"""
import hashlib
import hmac
import json
import logging
from asyncio import to_thread

from fastapi import APIRouter, BackgroundTasks, Request, Response, status

from chatbot.engine import handle_message
from config.settings import settings
from database.db import log_conversation, mark_message_processed, upsert_user
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


def _signature_valid(raw_body: bytes, signature_header: str | None) -> bool:
    if not settings.META_APP_SECRET:
        # Not configured (e.g. local dev) — allow through, but this was
        # already logged loudly at startup (see main.py).
        return True
    if not signature_header or not signature_header.startswith("sha256="):
        return False
    expected = hmac.new(settings.META_APP_SECRET.encode(), raw_body, hashlib.sha256).hexdigest()
    provided = signature_header.removeprefix("sha256=")
    return hmac.compare_digest(expected, provided)


@router.post("/webhook")
async def receive_message(request: Request, background_tasks: BackgroundTasks):
    """
    Handle incoming WhatsApp events. Meta's payload shape:
    entry -> changes -> value -> messages[] (present only for actual user messages;
    absent for delivery/read status callbacks, which we just acknowledge).
    """
    raw_body = await request.body()

    if not _signature_valid(raw_body, request.headers.get("X-Hub-Signature-256")):
        logger.warning("Webhook signature verification failed — rejecting request.")
        return Response(status_code=status.HTTP_403_FORBIDDEN)

    try:
        payload = json.loads(raw_body)
    except json.JSONDecodeError:
        logger.warning("Webhook received non-JSON body — ignoring.")
        return Response(status_code=status.HTTP_200_OK)

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
                    message_id = msg.get("id")
                    # Dedup up front so a Meta retry never gets scheduled twice,
                    # even if this message_id has no id (defensively processed once).
                    if message_id and not mark_message_processed(message_id):
                        logger.info("Skipping duplicate delivery of message %s", message_id)
                        continue
                    background_tasks.add_task(_process_incoming_message, msg, sender_name)

    except Exception:
        # Never let a malformed/unexpected payload crash the webhook —
        # Meta will retry aggressively on non-2xx responses.
        logger.exception("Error while scheduling webhook payload for processing")

    # Ack immediately; the real work happens in the background task above.
    return Response(status_code=status.HTTP_200_OK)


async def _process_incoming_message(msg: dict, sender_name: str | None):
    try:
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

        # Cap message length fed into the engine/LLM — cheap abuse & cost control.
        text_in = text_in[:2000]

        upsert_user(user_number, sender_name)

        # handle_message() makes blocking HTTP calls to LLM providers — run it
        # off the event loop so one slow reply doesn't stall every other
        # concurrent webhook request being handled by this process.
        result = await to_thread(handle_message, user_number, text_in)

        log_conversation(
            user_number=user_number,
            user_message=text_in,
            ai_response=result.text,
            intent=result.intent,
            llm_provider=result.provider,
        )

        await send_whatsapp_message(user_number, result.text)

    except Exception:
        # This runs in a background task after the webhook already returned
        # 200 to Meta, so there's no request left to fail — just log loudly.
        logger.exception("Error while processing message in background task")
