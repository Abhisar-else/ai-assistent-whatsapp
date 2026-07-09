# Demo Video Script (target: 4 minutes)

Record your screen (WhatsApp on phone/emulator + the admin dashboard side by
side, or switch between them) with a simple screen recorder (OBS, or your
phone's built-in recorder + a laptop browser for the dashboard).

## 0:00–0:30 — Intro
"Hi, I'm Abhisar, and this is the AI WhatsApp Executive Assistant I built
for Positiveway Solutions — a WhatsApp bot that answers business and
internship questions, schedules meetings, and gives an admin full visibility
into every conversation."
*(Show the architecture diagram from the README on screen briefly.)*

## 0:30–1:30 — General Q&A + context
- Send: **"Hi, what services do you offer?"** → show the reply.
- Send a follow-up that relies on context, e.g. **"Tell me more about the
  branding one"** → show it correctly picks up on the previous topic.
- Say: "Replies come from Google Gemini, with automatic fallback to Groq,
  OpenRouter, and finally a rule-based response if every AI provider is
  unavailable — so it never hard-fails."

## 1:30–2:15 — Internship FAQ
- Send: **"Do you offer internships?"**
- Send: **"How do I apply?"**
- Say: "Internship info comes from a plain knowledge base file — an admin
  can edit `knowledge_base/internship.md` with zero code changes."

## 2:15–3:15 — Meeting scheduler
- Send: **"I'd like to schedule a meeting"**
- Walk through all 4 prompts: name → date → time → purpose.
- Show the confirmation message.
- Say: "That's now saved to the database and visible to the admin
  immediately."

## 3:15–3:50 — Admin dashboard
- Switch to `/admin/dashboard` in a browser.
- Point out: stat cards, the LLM fallback-chain panel (showing which
  provider is actually answering), the conversation you just had, and the
  meeting request you just created.
- Click **Export conversations CSV** to show the download.

## 3:50–4:00 — Close
"That covers the core flow — WhatsApp in, AI + knowledge base + meeting
scheduler in the middle, full admin visibility on the other end. Thanks for
watching!"

---
### Recording tips
- Keep your Meta test token fresh (it expires every 24h) — refresh it in
  `.env` right before recording if it's been a day.
- Pre-load the knowledge base and send 1-2 throwaway test messages *before*
  recording so the first on-camera reply isn't your very first cold call to
  the Gemini API (avoids an awkward pause).
- If Gemini's quota is exhausted during recording, that's fine — it's a good
  moment to point out the fallback chain in `/admin/stats` after Groq or the
  heuristic responder picks it up.
