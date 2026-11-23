"""Pilot slot store and staff booking (ADR-001 option B; plan P2-08; EC-BOOK-02/11/12)."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone

from fastapi import HTTPException
from psycopg import Connection, errors

from . import events
from .auth import Staff
from .config import IST
from .leads import TO_CALL, get_lead_for, mark_reached, record_attempt

STALE_AFTER = timedelta(hours=24)


def _parse_hhmm(s: str) -> time:
    try:
        h, m = s.split(":")
        return time(int(h), int(m))
    except (ValueError, AttributeError):
        raise HTTPException(422, f"Invalid time {s!r}; use HH:MM.")


def list_dentists(conn: Connection, clinics: list[str]) -> list[dict]:
    return [{"id": str(r["id"]), "name": r["name"], "clinic_id": r["clinic_id"]} for r in conn.execute(
        "SELECT id, name, clinic_id FROM dentist WHERE clinic_id = ANY(%s) AND active ORDER BY clinic_id, name", (clinics,))]


def open_slots(conn: Connection, clinic_id: str, days: int = 7) -> dict:
    now = datetime.now(timezone.utc)
    rows = conn.execute(
        "SELECT s.id, s.start_at, s.duration_min, d.name AS dentist FROM slot s JOIN dentist d ON d.id = s.dentist_id "
        "WHERE s.clinic_id = %s AND s.status = 'open' AND s.start_at > %s AND s.start_at < %s ORDER BY s.start_at, d.name",
        (clinic_id, now + timedelta(minutes=30), now + timedelta(days=days))).fetchall()
    refresh = conn.execute("SELECT refreshed_at FROM slot_refresh WHERE clinic_id = %s", (clinic_id,)).fetchone()
    stale = refresh is None or now - refresh["refreshed_at"] > STALE_AFTER
    return {
        "slots": [{"id": str(r["id"]), "start_at": r["start_at"].astimezone(IST).isoformat(),
                   "duration_min": r["duration_min"], "dentist": r["dentist"]} for r in rows],
        "refreshed_at": refresh["refreshed_at"].astimezone(IST).isoformat() if refresh else None,
        "stale": stale,
    }


def add_slots(conn: Connection, staff: Staff, clinic_id: str, dentist_id: str, day: date,
              start: str, end: str, duration_min: int) -> dict:
    if not staff.can_see(clinic_id):
        raise HTTPException(403, "You don't have access to this clinic.")
    d = conn.execute("SELECT id FROM dentist WHERE id = %s AND clinic_id = %s", (dentist_id, clinic_id)).fetchone()
    if d is None:
        raise HTTPException(422, "That dentist doesn't work at this clinic.")
    if not 10 <= duration_min <= 120:
        raise HTTPException(422, "Slot length must be 10 to 120 minutes.")
    t0, t1 = _parse_hhmm(start), _parse_hhmm(end)
    cur = datetime.combine(day, t0, tzinfo=IST)
    stop = datetime.combine(day, t1, tzinfo=IST)
    if stop <= cur:
        raise HTTPException(422, "End time must be after start time.")
    if stop < datetime.now(IST):
        raise HTTPException(422, "These slots are in the past.")
    created = 0
    while cur + timedelta(minutes=duration_min) <= stop:
        r = conn.execute(
            "INSERT INTO slot (clinic_id, dentist_id, start_at, duration_min, created_by) VALUES (%s, %s, %s, %s, %s) "
            "ON CONFLICT (dentist_id, start_at) DO NOTHING RETURNING id",
            (clinic_id, dentist_id, cur, duration_min, staff.id)).fetchone()
        created += 1 if r else 0
        cur += timedelta(minutes=duration_min)
    conn.execute("INSERT INTO slot_refresh (clinic_id, refreshed_at, refreshed_by) VALUES (%s, now(), %s) "
                 "ON CONFLICT (clinic_id) DO UPDATE SET refreshed_at = now(), refreshed_by = EXCLUDED.refreshed_by",
                 (clinic_id, staff.id))
    events.audit(conn, staff.id, "slots_added", detail={"clinic": clinic_id, "day": day.isoformat(), "created": created})
    return {"created": created}


def book(conn: Connection, staff: Staff, lead_id: str, slot_id: str) -> dict:
    lead = get_lead_for(conn, staff, lead_id, lock=True)
    if lead["status"] not in TO_CALL:
        raise HTTPException(409, "This lead is already closed.")
    # Take the slot only if it is still open: two people can't book the same slot (EC-BOOK-02).
    try:
        slot = conn.execute(
            "UPDATE slot SET status = 'booked' WHERE id = %s AND clinic_id = %s AND status = 'open' AND start_at > now() "
            "RETURNING id, dentist_id, start_at", (slot_id, lead["clinic_id"])).fetchone()
    except errors.InvalidTextRepresentation:
        slot = None
    if slot is None:
        raise HTTPException(409, "That slot was just taken or is no longer available. Please pick another.")
    actor = f"staff:{staff.id}"
    from . import calendar_sync
    try:  # clinics on an external calendar: confirm there first (Phase 6)
        ext = calendar_sync.confirm_booking(conn, slot["id"], lead, f"Booked by {staff.display_name}")
    except calendar_sync.CalendarConflict:
        conn.execute("UPDATE slot SET status = 'blocked' WHERE id = %s", (slot["id"],))  # commits; nothing else changed
        return {"conflict": True, "message": "The clinic calendar says that slot was just taken. Please pick another."}
    if lead["first_reached_at"] is None:
        record_attempt(conn, lead, staff, "answered")
    mark_reached(conn, lead, actor)
    b = conn.execute(
        "INSERT INTO booking (lead_id, slot_id, clinic_id, dentist_id, start_at, created_by, created_by_staff, review_status, external_ref) "
        "VALUES (%s, %s, %s, %s, %s, 'staff', %s, 'approved', %s) RETURNING id",
        (lead["id"], slot["id"], lead["clinic_id"], slot["dentist_id"], slot["start_at"], staff.id, ext)).fetchone()
    conn.execute("UPDATE lead SET claimed_by = NULL, claimed_at = NULL WHERE id = %s", (lead["id"],))
    from .handovers import resolve
    resolve(conn, lead["id"], "booked_by_staff", actor)
    events.append(conn, "booking.created", lead_id=lead["id"], clinic_id=lead["clinic_id"], actor=actor,
                  payload={"booking_id": str(b["id"]), "created_by": "staff", "arm": lead["arm"],
                           "start_at": slot["start_at"].isoformat()})
    events.status_changed(conn, lead, "booked", actor=actor, outcome="reached_booked")
    if lead["arm"] == "assistant":  # control arm keeps today's process: no automated messages
        from . import messaging
        messaging.queue_booking_confirmation(conn, lead, b["id"])
    events.audit(conn, staff.id, "booking_created", lead_id=lead["id"], detail={"slot": str(slot["id"])})
    return {"ok": True, "booking_id": str(b["id"]), "start_at": slot["start_at"].astimezone(IST).isoformat()}
