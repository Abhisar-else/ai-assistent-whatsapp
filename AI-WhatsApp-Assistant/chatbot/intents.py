"""
Simple keyword-based intent detection. No ML classifier needed at this
scale — a small curated trigger list is transparent, fast, and easy for
an admin to extend.
"""

MEETING_TRIGGERS = [
    "meeting", "schedule", "book a call", "book time", "set up a call",
    "appointment", "arrange a call", "talk to someone", "speak with someone",
    "speak to a human", "talk to a human",
]

INTERNSHIP_TRIGGERS = [
    "intern", "internship", "resume", "cv", "apply", "application process",
]

CANCEL_TRIGGERS = ["cancel", "never mind", "nevermind", "stop", "forget it"]


def is_meeting_request(text: str) -> bool:
    lowered = text.lower()
    return any(trigger in lowered for trigger in MEETING_TRIGGERS)


def is_internship_query(text: str) -> bool:
    lowered = text.lower()
    return any(trigger in lowered for trigger in INTERNSHIP_TRIGGERS)


def is_cancel(text: str) -> bool:
    lowered = text.lower().strip()
    return lowered in CANCEL_TRIGGERS or any(t == lowered for t in CANCEL_TRIGGERS)


def detect_intent(text: str) -> str:
    """Returns 'meeting' | 'internship' | 'general'."""
    if is_meeting_request(text):
        return "meeting"
    if is_internship_query(text):
        return "internship"
    return "general"
