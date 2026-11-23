"""Daily call reviews, weekly feedback review, rules change log, attendance
(plan P5-02, P5-03, P5-04; architecture §15.3; implementation-plan §8.2).
"""

from __future__ import annotations

import hashlib
from collections import Counter
from datetime import date, datetime, time, timedelta, timezone

from fastapi import HTTPException
from psycopg import Connection

from . import events
from .auth import Staff
from .config import IST
from .handovers import TAGS
from .voice import RULES_VERSION

SAMPLE_PER_CLINIC = 10
ISSUE_TAGS = ["disclosure", "wrong_booking", "missed_handover", "unneeded_handover", "tone", "hindi_wording",
              "understanding", "slow", "other"]


def _iso(v):
    return v.astimezone(IST).isoformat() if v else None


def _day(d: date) -> tuple[datetime, datetime]:
    t0 = datetime.combine(d, time(0), tzinfo=IST)
    return t0, t0 + timedelta(days=1)


# ---------------------------------------------------------------- daily sample (§15.3)
def daily_sample(conn: Connection, staff: Staff, clinics: list[str], day: date) -> list[dict]:
    """A stable random sample of completed assistant calls: everyone sees the same 10 per clinic per day."""
    t0, t1 = _day(day)
    rows = conn.execute(
        """SELECT a.id, a.started_at, l.id AS lead_id, l.name, l.language, l.clinic_id, c.name AS clinic, cv.outcome,
                  cv.session->'handover'->>'reason' AS reason, cv.prompt_version,
                  (SELECT count(*) FROM call_review r WHERE r.call_attempt_id = a.id) AS reviews,
                  (SELECT count(*) FROM call_review r WHERE r.call_attempt_id = a.id AND r.reviewer_id = %s) AS mine
           FROM call_attempt a JOIN conversation cv ON cv.call_attempt_id = a.id JOIN lead l ON l.id = a.lead_id
           JOIN clinic c ON c.id = l.clinic_id
           WHERE a.made_by = 'assistant' AND a.state = 'completed' AND l.clinic_id = ANY(%s)
             AND a.started_at >= %s AND a.started_at < %s""", (staff.id, clinics, t0, t1)).fetchall()
    key = lambda r: hashlib.sha256(f"{day.isoformat()}:{r['id']}".encode()).hexdigest()  # noqa: E731
    out = []
    for cid in clinics:
        picked = sorted((r for r in rows if r["clinic_id"] == cid), key=key)[:SAMPLE_PER_CLINIC]
        out += [{"call_id": str(r["id"]), "lead_id": str(r["lead_id"]), "name": r["name"], "language": r["language"],
                 "clinic": r["clinic"], "started_at": _iso(r["started_at"]), "outcome": r["outcome"],
                 "handover": TAGS.get(r["reason"], r["reason"]) if r["reason"] else None, "rules_version": r["prompt_version"],
                 "reviews": r["reviews"], "reviewed_by_me": r["mine"] > 0} for r in sorted(picked, key=lambda r: r["started_at"])]
    return out


def call_detail(conn: Connection, staff: Staff, call_id: str) -> dict:
    r = conn.execute(
        """SELECT a.id, a.started_at, l.clinic_id, l.name, l.language, cv.transcript, cv.summary, cv.outcome, cv.guard_events,
                  cv.session->'handover' AS handover, cv.session->'booking' AS booking, cv.prompt_version
           FROM call_attempt a JOIN conversation cv ON cv.call_attempt_id = a.id JOIN lead l ON l.id = a.lead_id WHERE a.id = %s""",
        (call_id,)).fetchone()
    if not r:
        raise HTTPException(404, "Call not found.")
    if not staff.can_see(r["clinic_id"]):
        raise HTTPException(403, "You don't have access to this clinic.")
    events.audit(conn, staff.id, "call_reviewed_opened", detail={"call": str(r["id"])})
    return {"call_id": str(r["id"]), "name": r["name"], "language": r["language"], "started_at": _iso(r["started_at"]),
            "outcome": r["outcome"], "summary": r["summary"] or [], "handover": r["handover"], "booking": r["booking"],
            "rules_version": r["prompt_version"], "guard_events": r["guard_events"] or [],
            "transcript": [{"who": t[0], "text": t[1]} for t in (r["transcript"] or [])]}


def record_review(conn: Connection, staff: Staff, call_id: str, body: dict) -> dict:
    a = conn.execute("SELECT l.clinic_id FROM call_attempt a JOIN lead l ON l.id = a.lead_id WHERE a.id = %s", (call_id,)).fetchone()
    if not a:
        raise HTTPException(404, "Call not found.")
    if not staff.can_see(a["clinic_id"]):
        raise HTTPException(403, "You don't have access to this clinic.")
    tags = [t for t in body.get("issue_tags") or [] if t in ISSUE_TAGS]
    conn.execute(
        """INSERT INTO call_review (call_attempt_id, reviewer_id, disclosure_ok, booking_ok, handover_ok, tone_ok, issue_tags, notes)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
           ON CONFLICT (call_attempt_id, reviewer_id) DO UPDATE SET disclosure_ok = EXCLUDED.disclosure_ok,
             booking_ok = EXCLUDED.booking_ok, handover_ok = EXCLUDED.handover_ok, tone_ok = EXCLUDED.tone_ok,
             issue_tags = EXCLUDED.issue_tags, notes = EXCLUDED.notes, created_at = now()""",
        (call_id, staff.id, body["disclosure_ok"], body.get("booking_ok"), body.get("handover_ok"), body["tone_ok"], tags,
         (body.get("notes") or "")[:500] or None))
    events.append(conn, "call.reviewed", clinic_id=a["clinic_id"], actor=f"staff:{staff.id}",
                  payload={"call": call_id, "ok": all(v is not False for v in (body["disclosure_ok"], body.get("booking_ok"),
                                                                                 body.get("handover_ok"), body["tone_ok"])),
                           "tags": tags})
    return {"ok": True}


# ---------------------------------------------------------------- weekly review (plan P5-02/P5-03)
def weekly_report(conn: Connection, clinics: list[str], end: date) -> dict:
    t0, _ = _day(end - timedelta(days=6))
    _, t1 = _day(end)
    reviews = conn.execute(
        """SELECT r.*, a.started_at FROM call_review r JOIN call_attempt a ON a.id = r.call_attempt_id JOIN lead l ON l.id = a.lead_id
           WHERE l.clinic_id = ANY(%s) AND r.created_at >= %s AND r.created_at < %s""", (clinics, t0, t1)).fetchall()
    fails = Counter()
    for r in reviews:
        for k in ("disclosure_ok", "booking_ok", "handover_ok", "tone_ok"):
            if r[k] is False:
                fails[k.replace("_ok", "")] += 1
    downs = conn.execute(
        """SELECT f.reason, h.reason_tags, l.language, l.name, l.id AS lead_id, f.created_at FROM handover_feedback f
           JOIN handover h ON h.id = f.handover_id JOIN lead l ON l.id = h.lead_id
           WHERE NOT f.is_correct AND l.clinic_id = ANY(%s) AND f.created_at >= %s AND f.created_at < %s ORDER BY f.created_at""",
        (clinics, t0, t1)).fetchall()
    mix = conn.execute(
        """SELECT l.language, unnest(h.reason_tags) AS tag, count(*) AS n FROM handover h JOIN lead l ON l.id = h.lead_id
           WHERE l.arm = 'assistant' AND l.clinic_id = ANY(%s) AND h.created_at >= %s AND h.created_at < %s GROUP BY 1, 2
           ORDER BY 3 DESC""", (clinics, t0, t1)).fetchall()
    changes = conn.execute("SELECT version, area, description, created_at FROM rules_change WHERE created_at >= %s AND created_at < %s "
                           "ORDER BY id", (t0, t1)).fetchall()
    return {
        "period": {"from": (end - timedelta(days=6)).isoformat(), "to": end.isoformat()},
        "calls_reviewed": len({r["call_attempt_id"] for r in reviews}), "reviews": len(reviews),
        "checklist_failures": dict(fails), "issue_tags": dict(Counter(t for r in reviews for t in r["issue_tags"]).most_common()),
        "thumbs_down": [{"reason": d["reason"] or "(no reason)", "tags": [TAGS.get(t, t) for t in d["reason_tags"]],
                         "language": d["language"], "lead_id": str(d["lead_id"]), "name": d["name"], "at": _iso(d["created_at"])} for d in downs],
        "thumbs_down_reasons": dict(Counter(d["reason"] or "(no reason)" for d in downs).most_common()),
        "handover_mix": [{"language": m["language"], "reason": TAGS.get(m["tag"], m["tag"]), "count": m["n"]} for m in mix],
        "changes": [{"version": c["version"], "area": c["area"], "description": c["description"], "at": _iso(c["created_at"])} for c in changes],
        "current_rules_version": RULES_VERSION,
    }


# ---------------------------------------------------------------- rules change log
def log_change(conn: Connection, staff: Staff, version: str, area: str, description: str, reason: str | None) -> dict:
    row = conn.execute("INSERT INTO rules_change (version, area, description, reason, author_id) VALUES (%s, %s, %s, %s, %s) RETURNING id",
                       (version.strip()[:20], area, description.strip()[:500], (reason or "").strip()[:300] or None, staff.id)).fetchone()
    events.audit(conn, staff.id, "rules_change_logged", detail={"version": version, "area": area})
    return {"id": row["id"]}


def list_changes(conn: Connection, limit: int = 50) -> list[dict]:
    return [{"version": r["version"], "area": r["area"], "description": r["description"], "reason": r["reason"],
             "by": r["display_name"], "at": _iso(r["created_at"])} for r in conn.execute(
        "SELECT c.*, s.display_name FROM rules_change c LEFT JOIN staff s ON s.id = c.author_id ORDER BY c.id DESC LIMIT %s", (limit,))]


# ---------------------------------------------------------------- attendance (plan P5-04)
def attendance_list(conn: Connection, clinics: list[str], days: int = 7) -> list[dict]:
    now = datetime.now(timezone.utc)
    rows = conn.execute(
        """SELECT b.id, b.start_at, b.attended, b.created_by, l.name, l.arm, l.language, c.name AS clinic, d.name AS dentist
           FROM booking b JOIN lead l ON l.id = b.lead_id JOIN clinic c ON c.id = b.clinic_id JOIN dentist d ON d.id = b.dentist_id
           WHERE b.status = 'active' AND b.clinic_id = ANY(%s) AND b.start_at < %s AND b.start_at > %s
           ORDER BY (b.attended IS NULL) DESC, b.start_at DESC""", (clinics, now, now - timedelta(days=days))).fetchall()
    return [{"booking_id": str(r["id"]), "start_at": _iso(r["start_at"]), "attended": r["attended"], "name": r["name"],
             "clinic": r["clinic"], "dentist": r["dentist"], "booked_by": r["created_by"]} for r in rows]


def record_attendance(conn: Connection, staff: Staff, booking_id: str, attended: bool) -> dict:
    b = conn.execute("SELECT b.*, l.arm FROM booking b JOIN lead l ON l.id = b.lead_id WHERE b.id = %s FOR UPDATE", (booking_id,)).fetchone()
    if not b:
        raise HTTPException(404, "Booking not found.")
    if not staff.can_see(b["clinic_id"]):
        raise HTTPException(403, "You don't have access to this clinic.")
    if b["start_at"] > datetime.now(timezone.utc):
        raise HTTPException(409, "This appointment hasn't happened yet.")
    conn.execute("UPDATE booking SET attended = %s, attendance_recorded_by = %s, attendance_recorded_at = now() WHERE id = %s",
                 (attended, staff.id, booking_id))
    events.append(conn, "booking.attendance", lead_id=b["lead_id"], clinic_id=b["clinic_id"], actor=f"staff:{staff.id}",
                  payload={"booking_id": booking_id, "attended": attended, "arm": b["arm"], "created_by": b["created_by"]})
    if not attended and b["arm"] == "assistant" and b["attended"] is not False:
        # No-show recovery (Phase 6): WhatsApp offer to rebook + a person follows up. Control arm keeps today's process.
        from . import handovers, messaging
        lead = conn.execute("SELECT * FROM lead WHERE id = %s FOR UPDATE", (b["lead_id"],)).fetchone()
        messaging.queue_no_show(conn, lead, booking_id)
        handovers.create(conn, lead, ["no_show"], "normal", actor=f"staff:{staff.id}", note="Missed the consultation: offer a new time")
    return {"ok": True}
