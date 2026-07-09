"""
Meeting scheduler slot-filling flow (PRD 3D).

Deterministic state machine rather than LLM-driven extraction: reliable,
testable, and doesn't depend on the LLM provider being available. Each
WhatsApp message is a separate HTTP request, so state is persisted in
the `meeting_sessions` table between turns.
"""
from database.db import (
    clear_meeting_session,
    create_meeting,
    get_meeting_session,
    start_meeting_session,
    update_meeting_session,
)
from chatbot.intents import is_cancel

_STAGE_PROMPTS = {
    "name": "Sure, I can help you schedule a meeting! What's your name?",
    "preferred_date": "Great, {name}. What date works for you?",
    "preferred_time": "Got it. What time works best that day?",
    "purpose": "And what's the purpose of the meeting?",
}

# field currently being collected -> next stage
_NEXT_STAGE = {
    "name": "preferred_date",
    "preferred_date": "preferred_time",
    "preferred_time": "purpose",
    "purpose": "done",
}


def is_in_meeting_flow(user_number: str) -> bool:
    return get_meeting_session(user_number) is not None


def start_flow(user_number: str) -> str:
    start_meeting_session(user_number)
    return _STAGE_PROMPTS["name"]


def continue_flow(user_number: str, message_text: str) -> tuple[str, bool]:
    """
    Advances the state machine by one turn.
    Returns (reply_text, is_complete).
    """
    if is_cancel(message_text):
        clear_meeting_session(user_number)
        return "No problem, I've cancelled that meeting request. Let me know if you'd like to try again.", True

    session = get_meeting_session(user_number)
    if session is None:
        # Session vanished (e.g. race/restart) — restart cleanly.
        return start_flow(user_number), False

    stage = session["stage"]
    value = message_text.strip()

    if not value:
        return "Sorry, I didn't catch that — could you send that again?", False

    next_stage = _NEXT_STAGE[stage]
    update_meeting_session(user_number, field=stage, value=value, next_stage=next_stage)

    if next_stage != "done":
        prompt = _STAGE_PROMPTS[next_stage]
        # Personalize the date prompt with the name we just captured.
        if next_stage == "preferred_date":
            prompt = prompt.format(name=value)
        return prompt, False

    # All four fields collected — persist to meetings table and confirm.
    session[stage] = value  # include the field just captured
    create_meeting(
        user_number=user_number,
        name=session.get("name"),
        preferred_date=session.get("preferred_date"),
        preferred_time=session.get("preferred_time"),
        purpose=value if stage == "purpose" else session.get("purpose"),
    )
    clear_meeting_session(user_number)

    confirmation = (
        f"Perfect, thanks {session.get('name', '')}! I've noted your meeting request "
        f"for {session.get('preferred_date')} at {session.get('preferred_time')} "
        f"regarding: {value}. Our team will confirm with you shortly."
    )
    return confirmation, True
