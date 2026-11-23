"""Handover queue (architecture §4.9, §8; plan P3-08).

- One open handover per lead; reason tags + urgency; SLA 5 min urgent, 15 min otherwise.
- Outside staffed hours the SLA starts at the next opening, and the assistant promises
  "first thing tomorrow morning", never "a few minutes" (§8.3, EC-URG-05).
- Escalation sweep: past SLA -> overdue; past 2x SLA -> escalated to the clinic manager.
"""

from __future__ import annotations

from datetime import datetime, time, timedelta, timezone

from psycopg import Connection

from . import events
from .config import IST, get_settings

SLA_MIN = {"urgent": 5, "normal": 15}
TAGS = {
    "asked_person": "Asked for a person", "pain_swelling": "Pain or swelling (urgent)", "emergency": "Emergency symptoms",
    "distress": "Distress", "price_emi": "Price/EMI question", "clinical": "Clinical question",
    "couldnt_understand": "Couldn't understand", "no_suitable_slot": "No suitable slot", "minor": "Under 18",
    "recording_objection": "Didn't want recording", "needs_staff": "Needs staff help", "not_reached": "Not reached (3 calls)",
    "system_fallback": "System fallback", "booking_cancelled": "Booking cancelled", "abusive": "Ended: abusive caller",
    "whatsapp_reply": "WhatsApp reply", "whatsapp_preferred": "Prefers WhatsApp", "whatsapp_failed": "WhatsApp not delivered",
    "booking_paused": "AI booking paused",
    "no_show": "Missed consultation", "transferred": "Transferred live",
}


def _hhmm(s: str) -> time:
    h, m = s.split(":")
    return time(int(h), int(m))


def staffed_promise(now: datetime, urgency: str) -> tuple[datetime, str, int | None]:
    """Returns (sla_due_at, promise kind 'minutes'|'morning', minutes)."""
    s = get_settings()
    start, end = _hhmm(s.staff_hours_start), _hhmm(s.staff_hours_end)
    local = now.astimezone(IST)
    minutes = SLA_MIN[urgency]
    due = local + timedelta(minutes=minutes)
    if start <= local.time() and due.time() <= end and due.date() == local.date():
        return due, "minutes", minutes
    opening = datetime.combine(local.date() + timedelta(days=1 if local.time() >= start else 0), start, tzinfo=IST)
    return opening + timedelta(minutes=minutes), "morning", None


def create(conn: Connection, lead: dict, reasons: list[str], urgency: str, actor: str, note: str | None = None,
           call_attempt_id=None, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    reasons = [r for r in reasons if r in TAGS] or ["needs_staff"]
    urgency = urgency if urgency in SLA_MIN else "normal"
    existing = conn.execute("SELECT * FROM handover WHERE lead_id = %s AND resolved_at IS NULL FOR UPDATE", (lead["id"],)).fetchone()
    due, kind, minutes = staffed_promise(now, urgency)
    if existing:
        tags = sorted(set(existing["reason_tags"]) | set(reasons))
        new_urgency = "urgent" if "urgent" in (urgency, existing["urgency"]) else "normal"
        conn.execute("UPDATE handover SET reason_tags = %s, urgency = %s, sla_due_at = LEAST(sla_due_at, %s) WHERE id = %s",
                     (tags, new_urgency, due, existing["id"]))
        h = existing
    else:
        h = conn.execute(
            "INSERT INTO handover (lead_id, reason_tags, urgency, sla_due_at, call_attempt_id, promised) "
            "VALUES (%s, %s, %s, %s, %s, %s) RETURNING *",
            (lead["id"], reasons, urgency, due, call_attempt_id, kind)).fetchone()
    if note:
        conn.execute("UPDATE lead SET follow_up_note = %s WHERE id = %s", (note[:300], lead["id"]))
    events.append(conn, "handover.created", lead_id=lead["id"], clinic_id=lead["clinic_id"], actor=actor,
                  payload={"reasons": reasons, "urgency": urgency, "sla_due_at": due.isoformat(), "promise": kind,
                           "arm": lead["arm"]})
    events.status_changed(conn, lead, "needs_you", actor=actor)
    return {"handover_id": str(h["id"]), "promise": kind, "minutes": minutes}


def resolve(conn: Connection, lead_id, resolution: str, actor: str) -> None:
    h = conn.execute("UPDATE handover SET resolved_at = now(), resolution = %s WHERE lead_id = %s AND resolved_at IS NULL "
                     "RETURNING id, lead_id", (resolution, lead_id)).fetchone()
    if h:
        clinic = conn.execute("SELECT clinic_id FROM lead WHERE id = %s", (lead_id,)).fetchone()["clinic_id"]
        events.append(conn, "handover.resolved", lead_id=lead_id, clinic_id=clinic, actor=actor,
                      payload={"resolution": resolution})


def sweep(conn: Connection, now: datetime | None = None) -> dict:
    """Mark overdue and escalate (2x SLA). Run by the worker every few seconds."""
    now = now or datetime.now(timezone.utc)
    overdue = conn.execute(
        "UPDATE handover h SET overdue_at = %s FROM lead l WHERE l.id = h.lead_id AND h.resolved_at IS NULL "
        "AND h.overdue_at IS NULL AND h.sla_due_at < %s RETURNING h.id, h.lead_id, l.clinic_id, h.urgency", (now, now)).fetchall()
    for r in overdue:
        events.append(conn, "handover.overdue", lead_id=r["lead_id"], clinic_id=r["clinic_id"], payload={"urgency": r["urgency"]})
    escalated = conn.execute(
        """UPDATE handover h SET escalated_at = %s FROM lead l WHERE l.id = h.lead_id AND h.resolved_at IS NULL
           AND h.escalated_at IS NULL AND h.claimed_at IS NULL
           AND h.sla_due_at + (CASE h.urgency WHEN 'urgent' THEN interval '5 minutes' ELSE interval '15 minutes' END) < %s
           RETURNING h.id, h.lead_id, l.clinic_id, h.urgency""", (now, now)).fetchall()
    for r in escalated:
        # Notification channel to the clinic manager (SMS/WhatsApp) arrives in Phase 4; the event drives alerts.
        events.append(conn, "handover.escalated", lead_id=r["lead_id"], clinic_id=r["clinic_id"], payload={"urgency": r["urgency"]})
    return {"overdue": len(overdue), "escalated": len(escalated)}


def feedback(conn: Connection, handover_id, staff_id, is_correct: bool, reason: str | None) -> None:
    conn.execute("INSERT INTO handover_feedback (handover_id, staff_id, is_correct, reason) VALUES (%s, %s, %s, %s) "
                 "ON CONFLICT (handover_id, staff_id) DO UPDATE SET is_correct = EXCLUDED.is_correct, reason = EXCLUDED.reason, "
                 "created_at = now()", (handover_id, staff_id, is_correct, (reason or "")[:80] or None))
