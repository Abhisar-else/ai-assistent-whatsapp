"""
Outbound WhatsApp sending. Two backends, chosen by settings.WHATSAPP_PROVIDER:
  - "meta"   -> Meta WhatsApp Cloud API (free test environment)
  - "twilio" -> Twilio WhatsApp Sandbox

Keeping this behind one function (send_whatsapp_message) means the webhook
and chatbot code never need to know which provider is active.
"""
import logging

import httpx

from config.settings import settings

logger = logging.getLogger("whatsapp_client")


async def send_whatsapp_message(to: str, text: str) -> bool:
    """Send a text message to `to` (E.164 number, no '+'). Returns True on success."""
    if settings.WHATSAPP_PROVIDER == "twilio":
        return await _send_via_twilio(to, text)
    return await _send_via_meta(to, text)


async def _send_via_meta(to: str, text: str) -> bool:
    if not settings.META_WHATSAPP_TOKEN or not settings.META_PHONE_NUMBER_ID:
        logger.warning("Meta credentials missing — skipping send (dev mode). Would send to %s: %s", to, text)
        return False

    url = (
        f"https://graph.facebook.com/{settings.META_GRAPH_API_VERSION}"
        f"/{settings.META_PHONE_NUMBER_ID}/messages"
    )
    headers = {
        "Authorization": f"Bearer {settings.META_WHATSAPP_TOKEN}",
        "Content-Type": "application/json",
    }
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "text",
        "text": {"body": text, "preview_url": False},
    }

    async with httpx.AsyncClient(timeout=15) as client:
        try:
            resp = await client.post(url, headers=headers, json=payload)
            if resp.status_code >= 400:
                logger.error("Meta send failed [%s]: %s", resp.status_code, resp.text)
                return False
            return True
        except httpx.HTTPError as exc:
            logger.error("Meta send exception: %s", exc)
            return False


async def _send_via_twilio(to: str, text: str) -> bool:
    if not settings.TWILIO_ACCOUNT_SID or not settings.TWILIO_AUTH_TOKEN:
        logger.warning("Twilio credentials missing — skipping send (dev mode). Would send to %s: %s", to, text)
        return False

    url = f"https://api.twilio.com/2010-04-01/Accounts/{settings.TWILIO_ACCOUNT_SID}/Messages.json"

    # TWILIO_WHATSAPP_FROM already includes "whatsapp:+..." — don't double-wrap.
    from_number = settings.TWILIO_WHATSAPP_FROM
    if not from_number.startswith("whatsapp:"):
        from_number = f"whatsapp:{from_number}"

    # `to` may arrive without a leading + (stripped in webhook parsing)
    to_number = to if to.startswith("+") else f"+{to}"
    if not to_number.startswith("whatsapp:"):
        to_number = f"whatsapp:{to_number}"

    data = {
        "From": from_number,
        "To": to_number,
        "Body": text,
    }
    auth = (settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)

    async with httpx.AsyncClient(timeout=15) as client:
        try:
            resp = await client.post(url, data=data, auth=auth)
            if resp.status_code >= 400:
                logger.error("Twilio send failed [%s]: %s", resp.status_code, resp.text)
                return False
            return True
        except httpx.HTTPError as exc:
            logger.error("Twilio send exception: %s", exc)
            return False
