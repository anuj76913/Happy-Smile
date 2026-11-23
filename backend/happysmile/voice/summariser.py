"""Post-call summary: 3 lines + captured answers (architecture §4.10; plan P3-10).

The structured facts come from the agent's session, so they are always right. Groq,
when configured, rewrites them into three readable lines; its output is validated
against the facts and discarded if it contradicts them, has digits that look like
personal data, or is malformed. The deterministic summary is the fallback.
"""

from __future__ import annotations

import re

from .. import llm
from ..config import IST, get_settings
from ..handovers import TAGS
from .lines import TREATMENT

PROMPT_VERSION = "summary-v1"


def captured(session: dict) -> dict:
    s = session
    slot = None
    if s.get("booking"):
        from datetime import datetime
        st = s["booking"]["start_at"]
        st = datetime.fromisoformat(st) if isinstance(st, str) else st
        slot = st.astimezone(IST).strftime("%a %d %b, %I:%M %p").replace(" 0", " ")
    elif s.get("day_offset") is not None or s.get("start_min") is not None:
        day = {0: "today", 1: "tomorrow"}.get(s.get("day_offset"), f"in {s.get('day_offset')} days" if s.get("day_offset") else "")
        band = ""
        if s.get("start_min") is not None:
            band = "morning" if s["start_min"] < 720 else "afternoon" if s["start_min"] < 960 else "evening"
        slot = " ".join(x for x in (day, band) if x) or None
    ho = s.get("handover") or {}
    urgent = ho.get("urgency") == "urgent"
    return {
        "treatment": TREATMENT.get(s.get("treatment"), TREATMENT["other"])["en"],
        "slot": slot or "Not captured",
        "urgency": "Urgent: " + TAGS.get(ho.get("reason") if ho.get("reason") != "emergency" else "emergency", "") if urgent
        else ("Not urgent" if s.get("stage") not in ("open", "callback_time", "confirm_need", "ask_treatment") else "Unknown"),
        "language": "Hindi" if s.get("lang") == "hi" else "English",
    }


def deterministic(session: dict) -> list[str]:
    s, cap = session, captured(session)
    out = s.get("outcome")
    ho = s.get("handover") or {}
    first = f"Enquired about {cap['treatment']}; call in {cap['language']}."
    if out == "transferred":
        second = f"Asked for a person; transferred live to {ho.get('staff', 'staff')}."
    elif out == "booked" and s.get("booking"):
        second = f"Assistant booked a consultation: {cap['slot']} with {s['booking']['dentist']}."
    elif out in ("handover", "dropped", "ended_abusive") and ho:
        second = f"Handed over: {TAGS.get(ho.get('reason'), ho.get('reason'))}."
    elif out == "callback":
        second = "Asked to be called back later; a call is scheduled."
    elif out == "not_interested":
        second = "Said they are not interested."
    elif out in ("suppressed", "wrong_person"):
        second = "Asked not to be contacted; number suppressed." if out == "suppressed" else "Said they never enquired; number suppressed."
    else:
        second = f"Call ended at stage '{s.get('stage')}'."
    if ho.get("reason") in ("pain_swelling", "emergency"):
        third = "Reported pain or swelling; assistant gave safe-care advice and did not book."
    elif ho.get("promise") == "transfer":
        third = "Staff member took the call; record the outcome."
    elif ho:
        third = "Promised a call back " + ("within %s minutes." % ho.get("minutes") if ho.get("promise") == "minutes" else "first thing tomorrow.")
    elif out == "booked":
        third = "Booking needs staff review before the appointment."
    else:
        third = f"Preferred time: {cap['slot']}."
    return [first, second, third]


_SYSTEM = ("Write a 3-line summary of a dental clinic call for front-desk staff. Use only the facts given; never add "
           "medical advice, prices or phone numbers. Return JSON: {\"lines\": [three short sentences]}.")


def summarise(session: dict) -> dict:
    facts = deterministic(session)
    out = {"lines": facts, "captured": captured(session), "source": "rules"}
    c = llm.client()
    if c is None:
        return out
    transcript = "\n".join(f"{w}: {t}" for w, t, *_ in session.get("transcript", [])[-12:])
    try:
        res = c.json_completion(purpose="summary", model=get_settings().llm_summary_model, prompt_version=PROMPT_VERSION,
                                system=_SYSTEM, user="FACTS:\n" + "\n".join(facts) + "\n\nTRANSCRIPT:\n" + transcript, max_tokens=200)
        lines_ = res.get("lines")
        if (isinstance(lines_, list) and len(lines_) == 3 and all(isinstance(x, str) and 5 < len(x) <= 180 for x in lines_)
                and not any(re.search(r"\d{6,}", x) for x in lines_) and _consistent(session, " ".join(lines_))):
            out.update(lines=lines_, source="groq")
    except Exception:
        pass
    return out


def _consistent(session: dict, text: str) -> bool:
    """Structured fields win (architecture §4.10): the summary must agree on the outcome."""
    t, out = text.lower(), session.get("outcome")
    if out == "booked" and "book" not in t:
        return False
    if out != "booked" and re.search(r"\bbooked\b", t) and "not booked" not in t and "did not book" not in t:
        return False
    ho = session.get("handover") or {}
    if ho.get("urgency") == "urgent" and not re.search(r"urgent|pain|swell|emergency", t):
        return False
    return True
