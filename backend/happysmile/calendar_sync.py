"""Calendar adapters (ADR-001 option A; Phase 6 "calendar API integration").

The local `slot` table stays the working copy the assistant and staff book from. A clinic is
either:
  local  - staff maintain slots in the console (pilot slot store, ADR-001 option B), or
  http   - slots are synced from the clinic's calendar system, and every booking, change and
           cancellation is confirmed there first. If the calendar says the slot is gone, the
           local booking is refused and the slot is blocked (no double booking, EC-BOOK-02).

The HTTP adapter speaks the small JSON contract below. The real practice-management
vendor (P0-03, still open) is mapped onto it by a thin shim or by changing this adapter:

  GET    {base}/clinics/{clinic}/slots?from=ISO&to=ISO
         -> {"slots": [{"id", "dentist_id", "dentist_name", "start", "duration_min"}]}
  POST   {base}/bookings  {"slot_id", "clinic", "patient": {"name", "phone"}, "note"}
         -> 201 {"id"}   |  409 slot no longer available
  DELETE {base}/bookings/{id}  -> 204
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import httpx
from psycopg import Connection

from . import events
from .config import get_settings


class CalendarConflict(Exception):
    """The external calendar says the slot is no longer available."""


class CalendarUnavailable(Exception):
    pass


class HttpCalendar:
    def __init__(self, transport: httpx.BaseTransport | None = None):
        s = get_settings()
        if not s.calendar_api_url:
            raise CalendarUnavailable("CALENDAR_API_URL is not set")
        self._c = httpx.Client(base_url=s.calendar_api_url, transport=transport, timeout=8,
                               headers={"Authorization": f"Bearer {s.calendar_api_token}"})

    def list_open(self, clinic_id: str, start: datetime, end: datetime) -> list[dict]:
        r = self._c.get(f"/clinics/{clinic_id}/slots", params={"from": start.isoformat(), "to": end.isoformat()})
        r.raise_for_status()
        return r.json()["slots"]

    def book(self, external_slot: str, clinic_id: str, name: str, phone: str, note: str) -> str:
        r = self._c.post("/bookings", json={"slot_id": external_slot, "clinic": clinic_id,
                                            "patient": {"name": name, "phone": phone}, "note": note})
        if r.status_code == 409:
            raise CalendarConflict(external_slot)
        r.raise_for_status()
        return str(r.json()["id"])

    def cancel(self, external_booking: str) -> None:
        r = self._c.delete(f"/bookings/{external_booking}")
        if r.status_code not in (200, 204, 404):
            r.raise_for_status()


_adapter = None


def adapter():
    global _adapter
    if _adapter is None:
        _adapter = HttpCalendar()
    return _adapter


def set_adapter(a) -> None:  # tests
    global _adapter
    _adapter = a


def is_external(conn: Connection, clinic_id: str) -> bool:
    return conn.execute("SELECT calendar_adapter FROM clinic WHERE id = %s", (clinic_id,)).fetchone()["calendar_adapter"] == "http"


def sync(conn: Connection, clinic_id: str, days: int = 8) -> dict:
    """Mirror the external calendar's open slots into the local slot table."""
    now = datetime.now(timezone.utc)
    remote = adapter().list_open(clinic_id, now, now + timedelta(days=days))
    seen, created = set(), 0
    for s in remote:
        d = conn.execute("SELECT id FROM dentist WHERE clinic_id = %s AND external_ref = %s", (clinic_id, str(s["dentist_id"]))).fetchone()
        if d is None:
            d = conn.execute("INSERT INTO dentist (clinic_id, name, external_ref) VALUES (%s, %s, %s) RETURNING id",
                             (clinic_id, s["dentist_name"], str(s["dentist_id"]))).fetchone()
        start = datetime.fromisoformat(s["start"])
        row = conn.execute(
            "INSERT INTO slot (clinic_id, dentist_id, start_at, duration_min, status, source, external_ref) "
            "VALUES (%s, %s, %s, %s, 'open', 'external', %s) ON CONFLICT (clinic_id, external_ref) WHERE external_ref IS NOT NULL "
            "DO UPDATE SET status = CASE WHEN slot.status = 'blocked' THEN 'open' ELSE slot.status END RETURNING (xmax = 0) AS inserted",
            (clinic_id, d["id"], start, int(s.get("duration_min", 30)), str(s["id"]))).fetchone()
        created += 1 if row and row["inserted"] else 0
        seen.add(str(s["id"]))
    # Open slots the calendar no longer offers were taken elsewhere (walk-in, phone): block them.
    gone = conn.execute(
        "UPDATE slot SET status = 'blocked' WHERE clinic_id = %s AND source = 'external' AND status = 'open' "
        "AND start_at > now() AND NOT (external_ref = ANY(%s)) RETURNING id", (clinic_id, list(seen))).fetchall()
    conn.execute("UPDATE clinic SET calendar_synced_at = now() WHERE id = %s", (clinic_id,))
    conn.execute("INSERT INTO slot_refresh (clinic_id, refreshed_at) VALUES (%s, now()) "
                 "ON CONFLICT (clinic_id) DO UPDATE SET refreshed_at = now()", (clinic_id,))
    events.append(conn, "calendar.synced", clinic_id=clinic_id, payload={"remote": len(remote), "created": created, "blocked": len(gone)})
    return {"remote": len(remote), "created": created, "blocked": len(gone)}


def confirm_booking(conn: Connection, slot_id, lead: dict, note: str) -> str | None:
    """Book in the external calendar before the local booking commits. Returns its reference.

    Raises CalendarConflict if the slot is gone there; the caller refuses the booking.
    """
    if not is_external(conn, lead["clinic_id"]):
        return None
    ext = conn.execute("SELECT external_ref FROM slot WHERE id = %s", (slot_id,)).fetchone()["external_ref"]
    if ext is None:
        return None
    return adapter().book(ext, lead["clinic_id"], lead["name"], lead["phone_e164"], note)


def block_slot(slot_id) -> None:
    """Separate transaction: the slot stays blocked even though the booking transaction rolls back."""
    from .db import tx
    with tx() as conn:
        conn.execute("UPDATE slot SET status = 'blocked', hold_expires_at = NULL WHERE id = %s", (slot_id,))


def cancel_external(conn: Connection, booking_id) -> None:
    b = conn.execute("SELECT external_ref, clinic_id FROM booking WHERE id = %s", (booking_id,)).fetchone()
    if b and b["external_ref"]:
        adapter().cancel(b["external_ref"])
        events.append(conn, "calendar.cancelled", clinic_id=b["clinic_id"], payload={"booking": str(booking_id)})


def sync_due(max_age_minutes: int = 10) -> list[str]:
    """Worker hook: refresh external calendars every few minutes."""
    from .db import tx
    with tx() as conn:
        clinics = [r["id"] for r in conn.execute(
            "SELECT id FROM clinic WHERE is_pilot AND calendar_adapter = 'http' AND "
            "(calendar_synced_at IS NULL OR calendar_synced_at < now() - %s)", (timedelta(minutes=max_age_minutes),))]
    done = []
    for cid in clinics:
        try:
            with tx() as conn:
                sync(conn, cid)
            done.append(cid)
        except (httpx.HTTPError, CalendarUnavailable):
            pass  # stale-slot protection (EC-BOOK-11) pauses AI booking until a sync succeeds
    return done
