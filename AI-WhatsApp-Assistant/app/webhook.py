"""
WhatsApp webhook — accepts both Meta Cloud API (JSON) and Twilio Sandbox
(form-encoded) payload shapes on the same route, branching on Content-Type.

GET  /webhook  -> Meta's verification handshake (Twilio has no equivalent step).
POST /webhook  -> receives incoming messages/status updates from either provider.

Reliability/security properties:
1. Signature verification on both channels — Meta's X-Hub-Signature-256
   (enforced whenever META_APP_SECRET is set) and Twilio's X-Twilio-Signature
   (enforced whenever TWILIO_AUTH_TOKEN is set). Either is skipped with a
   loud warning if its secret isn't configured, so local/dev testing with
   plain curl still works.
2. Fast ack + background processing — Meta retries webhooks that don't get
   a fast 200; some LLM calls run longer than that window, so we ack
   immediately and do the real work in a background task.
3. Message-id dedup — guards against duplicate replies/meeting rows if a
   provider retries delivery of the same message.
"""
import base64
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
        return True  # not configured (e.g. local dev) — allow through
    if not signature_header or not signature_header.startswith("sha256="):
        return False
    expected = hmac.new(settings.META_APP_SECRET.encode(), raw_body, hashlib.sha256).hexdigest()
    provided = signature_header.removeprefix("sha256=")
    return hmac.compare_digest(expected, provided)


def _twilio_signature_valid(url: str, form_params: dict, signature_header: str | None) -> bool:
    """
    Twilio's documented algorithm: HMAC-SHA1 over the full request URL with
    every POST param (sorted by name) appended directly as `key+value`,
    keyed by the Auth Token, then base64-encoded.

    NOTE: `url` must exactly match what Twilio thinks it POSTed to, including
    scheme. Behind ngrok or a Render/Railway proxy, uvicorn needs to be told
    to trust forwarded headers or it may see `http://` internally even
    though Twilio called `https://` — run with
    `uvicorn main:app --proxy-headers --forwarded-allow-ips='*'` or this
    will fail signature checks even with a correct Auth Token.
    """
    if not settings.TWILIO_AUTH_TOKEN:
        return True  # not configured (e.g. local dev) — allow through
    if not signature_header:
        return False
    data = url + "".join(f"{k}{v}" for k, v in sorted(form_params.items()))
    expected = base64.b64encode(
        hmac.new(settings.TWILIO_AUTH_TOKEN.encode(), data.encode(), hashlib.sha1).digest()
    ).decode()
    return hmac.compare_digest(expected, signature_header)


@router.post("/webhook")
async def receive_message(request: Request, background_tasks: BackgroundTasks):
    content_type = request.headers.get("content-type", "")

    # --- Twilio Sandbox: form-encoded body, different field names entirely ---
    if "application/x-www-form-urlencoded" in content_type:
        form = await request.form()
        form_dict = dict(form)

        if not _twilio_signature_valid(str(request.url), form_dict, request.headers.get("X-Twilio-Signature")):
            logger.warning("Twilio webhook signature verification failed — rejecting request.")
            return Response(status_code=status.HTTP_403_FORBIDDEN)

        from_raw = form.get("From", "")  # e.g. "whatsapp:+919999999999"
        user_number = from_raw.removeprefix("whatsapp:").removeprefix("+")
        body_text = form.get("Body", "")
        message_id = form.get("MessageSid")
        sender_name = form.get("ProfileName") or None

        if message_id and not mark_message_processed(message_id):
            logger.info("Skipping duplicate Twilio delivery of message %s", message_id)
            return Response(status_code=status.HTTP_200_OK)

        if user_number and body_text:
            msg = {"id": message_id, "from": user_number, "type": "text", "text": {"body": body_text}}
            background_tasks.add_task(_process_incoming_message, msg, sender_name)

        return Response(status_code=status.HTTP_200_OK)

    # --- Meta Cloud API: JSON body ---
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
                    if message_id and not mark_message_processed(message_id):
                        logger.info("Skipping duplicate delivery of message %s", message_id)
                        continue
                    background_tasks.add_task(_process_incoming_message, msg, sender_name)

    except Exception:
        logger.exception("Error while scheduling webhook payload for processing")

    return Response(status_code=status.HTTP_200_OK)


async def _process_incoming_message(msg: dict, sender_name: str | None):
    try:
        user_number = msg.get("from")
        msg_type = msg.get("type")

        if msg_type != "text":
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

        text_in = text_in[:2000]  # cheap abuse/cost control

        upsert_user(user_number, sender_name)

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
        logger.exception("Error while processing message in background task")