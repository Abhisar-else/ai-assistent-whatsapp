# AI WhatsApp Executive Assistant — Positiveway Solutions

An AI-powered WhatsApp assistant that answers business/internship questions
from a knowledge base, holds context across a conversation, schedules
meetings, and gives an admin visibility into everything happening.

Built for the Positiveway Solutions internship 

## How it works

```
WhatsApp user
   │
   ▼
Meta Cloud API (JSON) or Twilio Sandbox (form) ──POST──▶ /webhook (FastAPI)
                                       │        (signature verified either way)
                         ┌─────────────┼──────────────┐
                         ▼             ▼               ▼
                 meeting_flow.py   intents.py    knowledge_base.py
                 (slot-filling)    (classify)    (keyword search over
                         │             │           SQLite-mirrored KB)
                         │             ▼
                         │        llm.py — Gemini → Groq → OpenRouter →
                         │        heuristic (first available provider wins)
                         ▼             │
                    SQLite (conversations, meetings, users) ◀──log every turn
                         │
                         ▼
                 /admin/* endpoints + dashboard (history, search, meetings, stats, export)
```

## Project structure

```
AI-WhatsApp-Assistant/
├── app/
│   ├── webhook.py        # Meta Cloud API webhook (verify + receive)
│   ├── whatsapp_client.py# outbound sending (Meta / Twilio)
│   └── admin.py          # admin API (history, meetings, stats, export)
├── chatbot/
│   ├── engine.py          # orchestrates: meeting flow -> intent -> KB -> LLM
│   ├── intents.py         # keyword-based intent detection
│   ├── meeting_flow.py    # meeting-scheduler slot-filling state machine
│   ├── knowledge_base.py  # loads KB files into SQLite + keyword search
│   └── llm.py             # Gemini -> Groq -> OpenRouter -> heuristic fallback
├── database/
│   ├── models.py           # SQL schema (DDL)
│   └── db.py                # connection + all CRUD helpers
├── knowledge_base/          # EDIT THESE FILES to change what the bot knows
│   ├── company.md
│   ├── services.md
│   ├── internship.md
│   └── faq.json
├── config/settings.py       # loads .env, single source of config
├── logs/app.log              # runtime logs (generated)
├── templates/admin_dashboard.html  # admin dashboard shell
├── static/dashboard.js, dashboard.css  # admin dashboard client
├── diagnose.py                 # standalone LLM-provider troubleshooting script
├── main.py                    # FastAPI app entrypoint
├── requirements.txt
└── .env.example
```

## 1. Prerequisites

- Python 3.11+
- A free [Google AI Studio](https://aistudio.google.com/) account for a Gemini API key
- A Meta developer account for the WhatsApp Cloud API free test environment
  (or a Twilio account for the Sandbox fallback)
- [ngrok](https://ngrok.com/) (or similar) for exposing your local server during development

## 2. Setup

```bash
git clone <your-repo-url>
cd AI-WhatsApp-Assistant
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env            # then fill in the values below
```

### Fill in `.env`

| Variable | Where to get it |
|---|---|
| `GEMINI_API_KEY` | [aistudio.google.com](https://aistudio.google.com/) → Get API key (free tier) |
| `GROQ_API_KEY` *(optional fallback)* | [console.groq.com](https://console.groq.com/) → API Keys (free tier) |
| `OPENROUTER_API_KEY` *(optional fallback)* | [openrouter.ai](https://openrouter.ai/) → Keys (free models) |
| `META_WHATSAPP_TOKEN`, `META_PHONE_NUMBER_ID` | Meta App → WhatsApp → API Setup (see below) |
| `META_APP_SECRET` | Meta App → Settings → Basic → App Secret. **Required for production** — without it, webhook signature verification is disabled and anyone who finds your webhook URL could send it fake messages. Safe to leave blank only for local/dev testing. |
| `META_VERIFY_TOKEN` | Any random string you choose — used only for the handshake |
| `TWILIO_AUTH_TOKEN` | Twilio Console → Account → Auth Token. Also required to verify `X-Twilio-Signature` on incoming webhooks if you're using Twilio as your channel — same "disabled if blank" behavior as `META_APP_SECRET`. |
| `ADMIN_API_KEY` | Any random string you choose — required in `X-Admin-Key` header for `/admin/*` |

`.env` is git-ignored — never commit real keys.

## 3. Meta WhatsApp Cloud API setup (free test environment)

1. Go to [developers.facebook.com](https://developers.facebook.com/) → **My Apps** → **Create App** → type **Business**.
2. Add the **WhatsApp** product to the app.
3. Under **WhatsApp → API Setup** you'll get a temporary access token, a
   test phone number, and a **Phone Number ID** — put those into
   `META_WHATSAPP_TOKEN` and `META_PHONE_NUMBER_ID` in `.env`.
4. Add your own WhatsApp number as a test recipient on that same page (free
   tier only sends to pre-approved numbers).
5. Run the app locally (`uvicorn main:app --reload --port 8000`), then in a
   second terminal:
   ```bash
   ngrok http 8000
   ```
6. Copy the `https://xxxx.ngrok-free.app` URL. In **WhatsApp → Configuration
   → Webhook**, set:
   - **Callback URL:** `https://xxxx.ngrok-free.app/webhook`
   - **Verify token:** the same string you put in `META_VERIFY_TOKEN`
   - Subscribe to the **messages** field.
7. Message your test number from WhatsApp — you should get a reply within a
   few seconds, and see it logged in `logs/app.log`.

> The Meta test token expires every 24 hours. Refresh it from the same API
> Setup page — no code changes needed, just update `.env` and restart.

### Twilio WhatsApp Sandbox (verified working channel)

Set `WHATSAPP_PROVIDER=twilio` in `.env`, fill in `TWILIO_ACCOUNT_SID`,
`TWILIO_AUTH_TOKEN`, `TWILIO_WHATSAPP_FROM` from the
[Twilio Console → WhatsApp Sandbox](https://console.twilio.com/), and point
the Sandbox's "when a message comes in" webhook at your `/webhook` URL
(ngrok locally, or your deployed URL in production).

From your own WhatsApp, message the Sandbox number with the `join <code>`
phrase shown on that Twilio Console page once to opt in — after that,
message it normally.

Twilio requests are verified against `X-Twilio-Signature` using
`TWILIO_AUTH_TOKEN` (skipped with a warning if unset, same as Meta). One
gotcha: this check needs the exact URL Twilio POSTed to, including scheme —
behind ngrok/Render's proxy, run uvicorn with
`--proxy-headers --forwarded-allow-ips='*'` (see section 8) or signature
checks can fail even with a correct token.

## 4. Run locally

```bash
uvicorn main:app --reload --port 8000
```

- Health check: `GET http://localhost:8000/health`
- Webhook: `POST/GET http://localhost:8000/webhook`
- Admin API: `http://localhost:8000/admin/*` (requires `X-Admin-Key` header)

## 5. Editing the knowledge base

Edit the files in `knowledge_base/` — no code changes needed:

- `.md` files: use `## Heading` to start a new topic; everything under it
  until the next heading is that topic's content.
- `faq.json`: a list of `{"question": ..., "answer": ...}` objects.

Changes take effect on next restart, or immediately via:

```bash
curl -X POST http://localhost:8000/admin/knowledge-base/reload \
  -H "X-Admin-Key: <your ADMIN_API_KEY>"
```

## 6. Admin API reference

All endpoints require header `X-Admin-Key: <ADMIN_API_KEY>`.

| Endpoint | Purpose |
|---|---|
| `GET /admin/conversations?query=&user_number=&limit=` | View / search conversation history |
| `GET /admin/meetings?status=` | View meeting requests |
| `PATCH /admin/meetings/{id}` | Update a meeting's status (`pending`/`confirmed`/`cancelled`) — body: `{"status": "confirmed"}` |
| `GET /admin/export/conversations` | Download all conversation logs as CSV |
| `POST /admin/knowledge-base/reload` | Reload KB from files without restarting |
| `GET /admin/stats` | Totals + usage by LLM provider + by intent |

## 6a. Security & reliability notes

- **Webhook signature verification**: incoming requests are checked against `X-Hub-Signature-256` (Meta, using `META_APP_SECRET`) or `X-Twilio-Signature` (Twilio, using `TWILIO_AUTH_TOKEN`) — HMAC-SHA256 and HMAC-SHA1 respectively, compared with constant-time comparison. Either check is skipped with a loud warning if its secret isn't set, so local testing with curl/Postman still works.
- **Fast ack + background processing**: the webhook responds `200` immediately and processes the message (LLM call, DB writes, sending the reply) in a background task, off the event loop via a worker thread. This matters because both Meta and Twilio retry a webhook delivery if they don't get a fast response, and an LLM call can take longer than that window.
- **Message deduplication**: each incoming message's provider-assigned ID is recorded, so a retried delivery is silently skipped instead of generating a duplicate reply or duplicate meeting entry.
- **CSV export sanitization**: any cell starting with `=`, `+`, `-`, or `@` is prefixed with `'` before export, so a crafted WhatsApp message can't execute as a formula if the CSV is opened in Excel/Sheets.
- **Meeting field length caps**: name/date/time are capped at 100 characters, purpose at 300 — independent of the general 2000-character message cap, since these are meant to be short answers.
- **Prompt injection mitigation**: the LLM system prompt wraps each user message in `<user_message>` tags with explicit instructions to treat its contents as data, not commands, and to never reveal the system prompt. This reduces risk; it doesn't eliminate it — no prompt-only defense fully can against a determined attacker.
- **Prompt injection mitigation**: the user's message is wrapped in `<user_message>` tags with an explicit system-prompt instruction to treat its contents as data, never as instructions, and to never reveal the system prompt. This reduces but doesn't eliminate prompt-injection risk — no prompt-only defense fully can.
- **Admin key comparison** uses `hmac.compare_digest` (constant-time) rather than `==`, avoiding a timing side-channel.

## 7. LLM fallback chain

`GEMINI_API_KEY` set and reachable → used.
Otherwise `GROQ_API_KEY` → used. Otherwise `OPENROUTER_API_KEY` → used.
If none are set/reachable, a rule-based heuristic reply (best-matching
knowledge base snippet, or a "an admin will follow up" message) is used so
the assistant never hard-fails. Which provider answered each message is
logged per-conversation (see `/admin/stats`).

## 8. Deployment

Any Python host works (Render, Railway, Fly.io). Example for Render/Railway:

- Build command: `pip install -r requirements.txt`
- Start command: `uvicorn main:app --host 0.0.0.0 --port $PORT --proxy-headers --forwarded-allow-ips='*'`
  (the proxy flags matter — without them, Twilio signature verification can fail behind a reverse proxy even with a correct `TWILIO_AUTH_TOKEN`)
- Set the same environment variables from `.env` in the host's dashboard.
- Update the Meta webhook Callback URL, or the Twilio Sandbox webhook, to the deployed URL once live.
- Free tiers on Render/Railway spin down after inactivity and take ~30s to wake on the next request — send a test message a few minutes before a live demo so it's already warm.

## 9. Testing & troubleshooting

There's no automated test suite yet — the flows (webhook verification on
both providers, message handling, meeting slot-filling, admin auth,
signature checks, dedup) were manually verified end-to-end during
development, including live messages through the Twilio Sandbox with real
replies from Groq.

**`diagnose.py`** is included at the project root for troubleshooting LLM
provider issues without digging through logs — run `python diagnose.py`
from the project folder. It confirms your API keys actually loaded from
`.env`, then calls Gemini and Groq directly and prints either a successful
reply or the exact exception (invalid key, wrong/deprecated model name,
quota exceeded, network error), so you know precisely which provider is
failing and why instead of just seeing it fall through to the heuristic
responder.

## Tech stack

Python · FastAPI · SQLite · Google Gemini API (+ Groq/OpenRouter fallback)
· Meta WhatsApp Cloud API (Twilio Sandbox fallback)
