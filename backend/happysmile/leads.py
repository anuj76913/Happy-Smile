"""Staff work on leads: list, view, claim, record outcomes (architecture §9; plan P2-07).

In Phase 2 every pilot lead is in the standard-callback (control) arm. Staff record each
call's outcome so that time-to-first-reach and booking are measured the same way for
both arms once the assistant goes live.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from psycopg import Connection

from . import events
from .auth import Staff
from .config import IST
from .db import tx
from .phone import display

STANDARD = ("awaiting_call", "no_answer", "follow_up")
TO_CALL = STANDARD + ("needs_you",)   # statuses staff can act on
DONE = ("booked", "not_interested", "unreachable")
CLAIM_TTL = timedelta(minutes=10)  # EC-Q-02: claims auto-release
OUTCOMES = {
    # outcome -> (call result recorded, new status, counts as reached)
    "no_answer": ("no_answer", "no_answer", False),
    "reached_follow_up": ("answered", "follow_up", True),
    "reached_not_interested": ("answered", "not_interested", True),
    "invalid_number": ("invalid", "unreachable", False),
}


def _iso(dt):
    return dt.astimezone(IST).isoformat() if dt else None


def get_lead_for(conn: Connection, staff: Staff, lead_id: str, lock: bool = False) -> dict:
    row = conn.execute("SELECT * FROM lead WHERE id = %s", (lead_id,)).fetchone()
    if row is None:
        raise HTTPException(404, "Lead not found.")
    if not staff.can_see(row["clinic_id"]):
        # Own transaction: the 403 rolls back the request's transaction, and the attempt must still be logged.
        with tx() as audit_conn:
            events.audit(audit_conn, staff.id, "access_denied", lead_id=row["id"], detail={"clinic": row["clinic_id"]})
        raise HTTPException(403, "This lead belongs to a clinic you don't have access to.")
    if lock:  # lock only after the access check, so the audit write above never waits on our own lock
        row = conn.execute("SELECT * FROM lead WHERE id = %s FOR UPDATE", (lead_id,)).fetchone()
    return row


def _summary(r: dict, now: datetime) -> dict:
    claimed = r["claimed_by"] is not None and r["claimed_at"] and now - r["claimed_at"] < CLAIM_TTL
    return {
        "id": str(r["id"]), "ref": r["public_ref"], "name": r["name"], "phone": display(r["phone_e164"]),
        "treatment": r["treatment"], "treatment_other": r["treatment_other_text"],
        "extra_treatments": r["extra_treatments"], "clinic_id": r["clinic_id"], "clinic": r.get("clinic_name"),
        "language": r["language"], "contact_pref": r["contact_pref"], "scheduled_at": _iso(r["scheduled_at"]),
        "arm": r["arm"], "status": r["status"], "created_at": _iso(r["created_at"]),
        "first_reached_at": _iso(r["first_reached_at"]), "follow_up_note": r["follow_up_note"],
        "returning": r["returning_of"] is not None,
        "claimed_by": r.get("claimed_name") if claimed else None,
        "claimed_by_me": bool(claimed and str(r["claimed_by"]) == r.get("_me")),
        "attempts": r.get("attempts", 0),
    }


def list_leads(conn: Connection, staff: Staff, clinics: list[str], view: str) -> list[dict]:
    statuses = STANDARD if view == "to_call" else DONE
    order = ("CASE l.status WHEN 'awaiting_call' THEN 0 WHEN 'no_answer' THEN 1 ELSE 2 END, l.created_at"
             if view == "to_call" else "l.updated_at DESC")
    rows = conn.execute(
        f"""SELECT l.*, c.name AS clinic_name, st.display_name AS claimed_name,
                   (SELECT count(*) FROM call_attempt a WHERE a.lead_id = l.id) AS attempts
            FROM lead l JOIN clinic c ON c.id = l.clinic_id LEFT JOIN staff st ON st.id = l.claimed_by
            WHERE l.clinic_id = ANY(%s) AND l.status = ANY(%s)
              AND l.created_at > now() - interval '30 days'
            ORDER BY {order} LIMIT 300""",
        (clinics, list(statuses))).fetchall()
    now = datetime.now(timezone.utc)
    return [_summary({**r, "_me": staff.id}, now) for r in rows]


def lead_detail(conn: Connection, staff: Staff, lead_id: str) -> dict:
    r = get_lead_for(conn, staff, lead_id)
    full = conn.execute(
        "SELECT l.*, c.name AS clinic_name, st.display_name AS claimed_name FROM lead l JOIN clinic c ON c.id = l.clinic_id "
        "LEFT JOIN staff st ON st.id = l.claimed_by WHERE l.id = %s", (r["id"],)).fetchone()
    attempts = conn.execute(
        "SELECT a.attempt_no, a.made_by, a.outcome, a.occurred_at, s.display_name FROM call_attempt a "
        "LEFT JOIN staff s ON s.id = a.staff_id WHERE a.lead_id = %s ORDER BY a.attempt_no", (r["id"],)).fetchall()
    booking = conn.execute(
        "SELECT b.start_at, d.name AS dentist, b.created_by FROM booking b JOIN dentist d ON d.id = b.dentist_id "
        "WHERE b.lead_id = %s AND b.status = 'active' ORDER BY b.created_at DESC LIMIT 1", (r["id"],)).fetchone()
    events.audit(conn, staff.id, "lead_viewed", lead_id=r["id"])  # who looked at which lead (§13)
    out = _summary({**full, "_me": staff.id, "attempts": len(attempts)}, datetime.now(timezone.utc))
    out["attempt_log"] = [{"no": a["attempt_no"], "by": a["display_name"] or a["made_by"], "outcome": a["outcome"],
                           "at": _iso(a["occurred_at"])} for a in attempts]
    out["booking"] = ({"start_at": _iso(booking["start_at"]), "dentist": booking["dentist"],
                       "created_by": booking["created_by"]} if booking else None)
    return out


def claim(conn: Connection, staff: Staff, lead_id: str) -> dict:
    lead = get_lead_for(conn, staff, lead_id, lock=True)
    now = datetime.now(timezone.utc)
    if lead["status"] not in TO_CALL:
        raise HTTPException(409, "This lead is already closed.")
    if lead["claimed_by"] and str(lead["claimed_by"]) != staff.id and lead["claimed_at"] and now - lead["claimed_at"] < CLAIM_TTL:
        who = conn.execute("SELECT display_name FROM staff WHERE id = %s", (lead["claimed_by"],)).fetchone()["display_name"]
        raise HTTPException(409, f"{who} is already calling this lead.")
    conn.execute("UPDATE lead SET claimed_by = %s, claimed_at = now() WHERE id = %s", (staff.id, lead["id"]))
    conn.execute("UPDATE handover SET claimed_by = %s, claimed_at = coalesce(claimed_at, now()) "
                 "WHERE lead_id = %s AND resolved_at IS NULL", (staff.id, lead["id"]))
    events.append(conn, "lead.claimed", lead_id=lead["id"], clinic_id=lead["clinic_id"], actor=f"staff:{staff.id}")
    events.audit(conn, staff.id, "lead_claimed", lead_id=lead["id"])
    return {"ok": True}


def mark_reached(conn: Connection, lead: dict, actor: str, at: datetime | None = None) -> None:
    """First successful contact. Emits lead.reached once, with minutes since the enquiry."""
    if lead["first_reached_at"] is not None:
        return
    at = at or datetime.now(timezone.utc)
    conn.execute("UPDATE lead SET first_reached_at = %s WHERE id = %s", (at, lead["id"]))
    seconds = (at - lead["created_at"]).total_seconds()
    events.append(conn, "lead.reached", lead_id=lead["id"], clinic_id=lead["clinic_id"], actor=actor,
                  payload={"seconds_after_enquiry": seconds, "minutes_after_enquiry": round(seconds / 60, 1),
                           "arm": lead["arm"]})
    lead["first_reached_at"] = at


def record_attempt(conn: Connection, lead: dict, staff: Staff, result: str) -> None:
    n = conn.execute("SELECT coalesce(max(attempt_no), 0) + 1 AS n FROM call_attempt WHERE lead_id = %s",
                     (lead["id"],)).fetchone()["n"]
    conn.execute("INSERT INTO call_attempt (lead_id, attempt_no, made_by, staff_id, outcome) VALUES (%s, %s, 'staff', %s, %s)",
                 (lead["id"], n, staff.id, result))
    events.append(conn, "call.attempted", lead_id=lead["id"], clinic_id=lead["clinic_id"], actor=f"staff:{staff.id}",
                  payload={"attempt": n, "result": result, "by": "staff"})


def record_outcome(conn: Connection, staff: Staff, lead_id: str, outcome: str, note: str | None) -> dict:
    if outcome not in OUTCOMES:
        raise HTTPException(422, "Unknown outcome.")
    lead = get_lead_for(conn, staff, lead_id, lock=True)
    if lead["status"] not in TO_CALL:
        raise HTTPException(409, "This lead is already closed.")
    result, new_status, reached = OUTCOMES[outcome]
    actor = f"staff:{staff.id}"
    record_attempt(conn, lead, staff, result)
    if reached:
        mark_reached(conn, lead, actor)
    if note is not None:
        conn.execute("UPDATE lead SET follow_up_note = %s WHERE id = %s", ((note or "")[:300] or None, lead["id"]))
    conn.execute("UPDATE lead SET claimed_by = NULL, claimed_at = NULL WHERE id = %s", (lead["id"],))
    from .handovers import resolve
    resolve(conn, lead["id"], outcome, actor)
    events.status_changed(conn, lead, new_status, actor=actor, outcome=outcome)
    events.audit(conn, staff.id, "outcome_recorded", lead_id=lead["id"], detail={"outcome": outcome})
    return {"ok": True, "status": new_status}
