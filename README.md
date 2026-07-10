# AI WhatsApp Executive Assistant — Positiveway Solutions

An AI-powered WhatsApp assistant that answers business/internship questions
from a knowledge base, holds context across a conversation, schedules
meetings, and gives an admin visibility into everything happening.

Built for the Positiveway Solutions internship 4-day sprint (8–12 July 2026).

## How it works

```
WhatsApp user
   │
   ▼
Meta WhatsApp Cloud API  ──POST──▶  /webhook  (FastAPI)
                                       │
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
                 /admin/* endpoints (history, search, meetings, stats, export)
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
| `META_VERIFY_TOKEN` | Any random string you choose — used only for the handshake |
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

### Fallback: Twilio WhatsApp Sandbox

If Meta setup is slow to approve, set `WHATSAPP_PROVIDER=twilio` in `.env`,
fill in `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_WHATSAPP_FROM`
from the [Twilio Console → WhatsApp Sandbox](https://console.twilio.com/),
and point the Sandbox's "when a message comes in" webhook at your
`/webhook` ngrok URL (Twilio uses form-encoded POSTs — see note in
`app/webhook.py` if you need to adapt parsing).

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
| `GET /admin/export/conversations` | Download all conversation logs as CSV |
| `POST /admin/knowledge-base/reload` | Reload KB from files without restarting |
| `GET /admin/stats` | Totals + usage by LLM provider + by intent |

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
- Start command: `uvicorn main:app --host 0.0.0.0 --port $PORT`
- Set the same environment variables from `.env` in the host's dashboard.
- Update the Meta webhook Callback URL to the deployed URL once live.

## 9. Testing

There's no separate test suite yet — the flows above (webhook verification,
message handling, meeting slot-filling, admin auth) were manually verified
end-to-end during development. See the commit history / demo video for a
walkthrough.

## Tech stack

Python · FastAPI · SQLite · Google Gemini API (+ Groq/OpenRouter fallback)
· Meta WhatsApp Cloud API (Twilio Sandbox fallback)

admin key (kX9vTm2QpLwR7nZsA4bYcDfEgHjK6uWx)