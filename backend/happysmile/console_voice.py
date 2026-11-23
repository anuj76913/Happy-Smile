"""Console support for Phase 3: Needs you queue, assistant bookings + review, handover
feedback, call details, and practice ("test") calls (plan P3-08, P3-09, P3-11/12)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from psycopg import Connection
from psycopg.types.json import Jsonb

from . import calendar_sync, events, handovers, messaging
from .auth import Staff
from .config import IST
from .leads import get_lead_for
from .phone import display
from .voice.agent import Agent, Session
from .voice.nlu import default_nlu
from .voice.summariser import summarise
from .voice.tools import MemoryBackend, ToolRegistry


def _iso(v):
    return v.astimezone(IST).isoformat() if v else None


def latest_conversation(conn: Connection, lead_id) -> dict | None:
    c = conn.execute(
        "SELECT c.summary, c.captured, c.transcript, c.outcome, a.started_at, a.attempt_no FROM conversation c "
        "JOIN call_attempt a ON a.id = c.call_attempt_id WHERE a.lead_id = %s ORDER BY a.started_at DESC LIMIT 1",
        (lead_id,)).fetchone()
    if not c:
        return None
    tr = c["transcript"] or []
    return {"summary": c["summary"] or [], "captured": c["captured"] or {}, "outcome": c["outcome"],
            "transcript": [{"who": t[0], "text": t[1]} for t in tr[-8:]], "started_at": _iso(c["started_at"])}


def needs_you(conn: Connection, clinics: list[str]) -> list[dict]:
    rows = conn.execute(
        """SELECT l.id, l.public_ref, l.name, l.phone_e164, l.treatment, l.language, l.clinic_id, c.name AS clinic, l.arm,
                  h.id AS handover_id, h.reason_tags, h.urgency, h.sla_due_at, h.created_at AS handed_at, h.claimed_at,
                  h.overdue_at, h.escalated_at, s.display_name AS claimed_by
           FROM handover h JOIN lead l ON l.id = h.lead_id JOIN clinic c ON c.id = l.clinic_id
           LEFT JOIN staff s ON s.id = h.claimed_by
           WHERE h.resolved_at IS NULL AND l.clinic_id = ANY(%s)
           ORDER BY (h.claimed_at IS NOT NULL), (h.urgency = 'urgent') DESC, h.created_at""", (clinics,)).fetchall()
    return [{"id": str(r["id"]), "ref": r["public_ref"], "name": r["name"], "phone": display(r["phone_e164"]),
             "treatment": r["treatment"], "language": r["language"], "clinic_id": r["clinic_id"], "clinic": r["clinic"],
             "arm": r["arm"], "handover_id": str(r["handover_id"]), "tags": r["reason_tags"], "urgency": r["urgency"],
             "sla_minutes": handovers.SLA_MIN[r["urgency"]], "sla_due_at": _iso(r["sla_due_at"]), "handed_at": _iso(r["handed_at"]),
             "claimed_at": _iso(r["claimed_at"]), "claimed_by": r["claimed_by"], "escalated": r["escalated_at"] is not None}
            for r in rows]


def assistant_bookings(conn: Connection, clinics: list[str]) -> list[dict]:
    rows = conn.execute(
        """SELECT b.id, b.start_at, b.review_status, b.whatsapp_status, b.created_at, d.name AS dentist,
                  l.id AS lead_id, l.name, l.treatment, l.language, l.clinic_id, c.name AS clinic
           FROM booking b JOIN lead l ON l.id = b.lead_id JOIN dentist d ON d.id = b.dentist_id JOIN clinic c ON c.id = b.clinic_id
           WHERE b.created_by = 'assistant' AND b.status = 'active' AND b.clinic_id = ANY(%s)
             AND b.start_at > now() - interval '1 day'
           ORDER BY (b.review_status = 'pending') DESC, b.start_at""", (clinics,)).fetchall()
    return [{"booking_id": str(r["id"]), "id": str(r["lead_id"]), "name": r["name"], "treatment": r["treatment"],
             "language": r["language"], "clinic_id": r["clinic_id"], "clinic": r["clinic"], "dentist": r["dentist"],
             "start_at": _iso(r["start_at"]), "review_status": r["review_status"], "whatsapp_status": r["whatsapp_status"],
             "created_at": _iso(r["created_at"])} for r in rows]


def no_answer(conn: Connection, clinics: list[str]) -> list[dict]:
    """Assistant-arm leads not yet reached: retrying, or waiting on a WhatsApp reply (plan P4-06)."""
    rows = conn.execute(
        """SELECT l.id, l.name, l.treatment, l.language, l.clinic_id, c.name AS clinic, l.status, l.whatsapp_sent_at, l.created_at,
                  (SELECT count(*) FROM call_attempt a WHERE a.lead_id = l.id AND a.made_by = 'assistant') AS calls,
                  (SELECT a.outcome FROM call_attempt a WHERE a.lead_id = l.id AND a.made_by = 'assistant' ORDER BY a.attempt_no DESC LIMIT 1) AS last_result,
                  (SELECT j.due_at FROM call_job j WHERE j.lead_id = l.id AND j.status = 'pending' LIMIT 1) AS next_call,
                  (SELECT m.status FROM message m WHERE m.lead_id = l.id AND m.template_id = 'no_answer_v1' ORDER BY m.created_at DESC LIMIT 1) AS wa_status
           FROM lead l JOIN clinic c ON c.id = l.clinic_id
           WHERE l.clinic_id = ANY(%s) AND l.arm = 'assistant' AND l.first_reached_at IS NULL
             AND (l.status = 'whatsapp_sent' OR (l.status = 'queued' AND EXISTS
                  (SELECT 1 FROM call_attempt a WHERE a.lead_id = l.id AND a.made_by = 'assistant')))
           ORDER BY coalesce((SELECT j.due_at FROM call_job j WHERE j.lead_id = l.id AND j.status = 'pending' LIMIT 1), 'infinity'),
                    l.created_at""", (clinics,)).fetchall()
    return [{"id": str(r["id"]), "name": r["name"], "treatment": r["treatment"], "language": r["language"], "clinic_id": r["clinic_id"],
             "clinic": r["clinic"], "status": r["status"], "calls": r["calls"], "last_result": r["last_result"],
             "next_call": _iso(r["next_call"]), "whatsapp_sent_at": _iso(r["whatsapp_sent_at"]), "whatsapp_status": r["wa_status"],
             "created_at": _iso(r["created_at"])} for r in rows]


def messages_for(conn: Connection, lead_id) -> list[dict]:
    return [{"direction": r["direction"], "template": r["template_id"], "body": r["body"], "status": r["status"],
             "at": _iso(r["created_at"]), "due_at": _iso(r["due_at"]), "error": r["error"]}
            for r in conn.execute("SELECT * FROM message WHERE lead_id = %s ORDER BY created_at", (lead_id,))]


def lead_extras(conn: Connection, lead_id) -> dict:
    h = conn.execute("SELECT id, reason_tags, urgency, sla_due_at, created_at, claimed_at, promised FROM handover "
                     "WHERE lead_id = %s AND resolved_at IS NULL", (lead_id,)).fetchone()
    b = conn.execute("SELECT b.id, b.review_status, b.created_by FROM booking b WHERE b.lead_id = %s AND b.status = 'active' "
                     "ORDER BY b.created_at DESC LIMIT 1", (lead_id,)).fetchone()
    return {
        "messages": messages_for(conn, lead_id),
        "conversation": latest_conversation(conn, lead_id),
        "handover": ({"id": str(h["id"]), "tags": h["reason_tags"], "urgency": h["urgency"], "sla_due_at": _iso(h["sla_due_at"]),
                      "handed_at": _iso(h["created_at"]), "claimed_at": _iso(h["claimed_at"]), "promised": h["promised"],
                      "sla_minutes": handovers.SLA_MIN[h["urgency"]]} if h else None),
        "booking_review": ({"booking_id": str(b["id"]), "review_status": b["review_status"], "created_by": b["created_by"]}
                           if b else None),
    }


def feedback(conn: Connection, staff: Staff, handover_id: str, is_correct: bool, reason: str | None) -> dict:
    h = conn.execute("SELECT h.id, l.clinic_id, l.id AS lead_id FROM handover h JOIN lead l ON l.id = h.lead_id WHERE h.id = %s",
                     (handover_id,)).fetchone()
    if not h:
        raise HTTPException(404, "Handover not found.")
    if not staff.can_see(h["clinic_id"]):
        raise HTTPException(403, "You don't have access to this clinic.")
    handovers.feedback(conn, h["id"], staff.id, is_correct, reason)
    events.append(conn, "handover.feedback", lead_id=h["lead_id"], clinic_id=h["clinic_id"], actor=f"staff:{staff.id}",
                  payload={"correct": is_correct, "reason": reason})
    return {"ok": True}


def review_booking(conn: Connection, staff: Staff, booking_id: str, action: str, slot_id: str | None, reason: str | None) -> dict:
    b = conn.execute("SELECT * FROM booking WHERE id = %s FOR UPDATE", (booking_id,)).fetchone()
    if not b or b["status"] != "active":
        raise HTTPException(404, "Booking not found or already cancelled.")
    lead = get_lead_for(conn, staff, str(b["lead_id"]), lock=True)
    actor = f"staff:{staff.id}"
    if action == "approve":
        conn.execute("UPDATE booking SET review_status = 'approved', reviewed_by = %s, reviewed_at = now() WHERE id = %s",
                     (staff.id, b["id"]))
    elif action == "change":
        if not slot_id:
            raise HTTPException(422, "Choose a new slot.")
        new = conn.execute("UPDATE slot SET status = 'booked' WHERE id = %s AND clinic_id = %s AND status = 'open' AND start_at > now() "
                           "RETURNING id, dentist_id, start_at", (slot_id, b["clinic_id"])).fetchone()
        if not new:
            raise HTTPException(409, "That slot was just taken or is no longer available.")
        try:  # external calendar: book the new slot there first, then release the old one (Phase 6)
            ext = calendar_sync.confirm_booking(conn, new["id"], lead, f"Moved at review by {staff.display_name}")
        except calendar_sync.CalendarConflict:
            raise HTTPException(409, "The clinic calendar says that slot was just taken. Please pick another.")
        calendar_sync.cancel_external(conn, b["id"])
        conn.execute("UPDATE slot SET status = 'open' WHERE id = %s", (b["slot_id"],))
        conn.execute("UPDATE booking SET slot_id = %s, dentist_id = %s, start_at = %s, review_status = 'changed', reviewed_by = %s, "
                     "reviewed_at = now(), external_ref = %s WHERE id = %s",
                     (new["id"], new["dentist_id"], new["start_at"], staff.id, ext, b["id"]))
        messaging.cancel_pending(conn, lead["id"], "appointment_reminder_v1")
        messaging.queue_appointment_reminder(conn, lead, b["id"])
        dentist = conn.execute("SELECT name FROM dentist WHERE id = %s", (new["dentist_id"],)).fetchone()["name"]
        hi = lead["language"] == "hi"
        messaging.queue_booking_update(conn, lead, b["id"], "समय बदला गया है" if hi else "the time has changed",
                                       f"{messaging.fmt_date(new['start_at'], lead['language'])}, {messaging.fmt_time(new['start_at'])}, {dentist}")
    elif action == "cancel":
        if not reason:
            raise HTTPException(422, "Give a reason for cancelling.")
        calendar_sync.cancel_external(conn, b["id"])
        conn.execute("UPDATE slot SET status = 'open' WHERE id = %s", (b["slot_id"],))
        conn.execute("UPDATE booking SET status = 'cancelled', review_status = 'cancelled', cancel_reason = %s, reviewed_by = %s, "
                     "reviewed_at = now() WHERE id = %s", (reason[:120], staff.id, b["id"]))
        # The patient must hear about it from a person (EC-POST-02), and in writing.
        messaging.cancel_pending(conn, lead["id"], "booking_confirm_v1")
        messaging.cancel_pending(conn, lead["id"], "appointment_reminder_v1")
        hi = lead["language"] == "hi"
        messaging.queue_booking_update(conn, lead, b["id"], "बुकिंग रद्द कर दी गई है" if hi else "this booking has been cancelled",
                                       "हमारी टीम आपको नया समय तय करने के लिए कॉल करेगी" if hi else "our team will call you to arrange a new time")
        handovers.create(conn, lead, ["booking_cancelled"], "normal", actor=actor, note=f"Booking cancelled at review: {reason}")
    else:
        raise HTTPException(422, "Unknown review action.")
    events.append(conn, f"booking.review_{action}", lead_id=lead["id"], clinic_id=lead["clinic_id"], actor=actor,
                  payload={"booking_id": str(b["id"]), "reason": reason})
    events.audit(conn, staff.id, f"booking_{action}", lead_id=lead["id"], detail={"booking": str(b["id"])})
    return {"ok": True}


# ---------------------------------------------------------------- practice calls
def _real_slots(conn: Connection) -> dict:
    rows = conn.execute(
        "SELECT s.id, s.clinic_id, s.start_at, d.name AS dentist FROM slot s JOIN dentist d ON d.id = s.dentist_id "
        "WHERE s.status = 'open' AND s.start_at > now() AND s.start_at < now() + interval '8 days' ORDER BY s.start_at").fetchall()
    out: dict = {}
    for r in rows:
        out.setdefault(r["clinic_id"], []).append({"id": str(r["id"]), "start_at": r["start_at"], "dentist": r["dentist"]})
    return out


def _test_agent(conn, session: Session, snap: dict) -> tuple[Agent, MemoryBackend]:
    backend = MemoryBackend(datetime.now(timezone.utc), real_slots=_real_slots(conn))
    names = {r["id"]: r["name"] for r in conn.execute("SELECT id, name FROM clinic WHERE is_pilot")}
    backend.NAMES = names
    backend.restore(snap)
    return Agent(session, ToolRegistry(backend), nlu=default_nlu()), backend


def start_test_call(conn: Connection, staff: Staff, name: str, treatment: str, clinic_id: str, language: str) -> dict:
    clinic = conn.execute("SELECT id, name FROM clinic WHERE id = %s AND is_pilot", (clinic_id,)).fetchone()
    if not clinic:
        raise HTTPException(422, "Pick a pilot clinic.")
    session = Session(name=(name or "Test").strip()[:30] or "Test", treatment=treatment if treatment in
                      ("braces", "whitening", "implants", "other") else "braces", clinic_id=clinic["id"],
                      clinic_name=clinic["name"], lang=language if language in ("en", "hi") else "en")
    agent, backend = _test_agent(conn, session, {})
    turn = agent.start()
    row = conn.execute("INSERT INTO test_call (staff_id, session, backend) VALUES (%s, %s, %s) RETURNING id",
                       (staff.id, Jsonb(agent.s.to_dict()), Jsonb(backend.snapshot()))).fetchone()
    events.audit(conn, staff.id, "test_call_started", detail={"clinic": clinic_id, "language": language})
    return {"id": str(row["id"]), "say": turn.say, "end": False, "lang": agent.s.lang}


def test_call_turn(conn: Connection, staff: Staff, call_id: str, text: str | None, silence: bool, hangup: bool,
                   confidence: float) -> dict:
    row = conn.execute("SELECT * FROM test_call WHERE id = %s AND staff_id = %s FOR UPDATE", (call_id, staff.id)).fetchone()
    if not row:
        raise HTTPException(404, "Test call not found.")
    session = Session.from_dict(row["session"])
    agent, backend = _test_agent(conn, session, row["backend"])
    if session.ended:
        turn_say, end = "", True
    elif hangup:
        agent.hangup()
        turn_say, end = "", True
    elif silence:
        t = agent.silence()
        turn_say, end = t.say, t.end
    else:
        t = agent.handle(text or "", confidence)
        turn_say, end = t.say, t.end
    s = agent.s
    conn.execute("UPDATE test_call SET session = %s, backend = %s, updated_at = now() WHERE id = %s",
                 (Jsonb(s.to_dict()), Jsonb(backend.snapshot()), row["id"]))
    out = {"say": turn_say, "end": end, "stage": s.stage, "outcome": s.outcome, "handover": s.handover, "lang": s.lang,
           "guard_events": s.guard_events[-3:],
           "booking": ({"start_at": _iso(s.booking["start_at"]), "dentist": s.booking["dentist"], "clinic": s.booking["clinic"]}
                       if s.booking else None)}
    if end:
        out["summary"] = summarise(s.to_dict())
    return out
