"""Tools the agent may use (architecture §4.5; plan P3-05; edge cases EC-LLM-05, EC-MAN-01/02/03, EC-BOOK-02/05).

Every call goes through ToolRegistry: name must be on the allowlist, arguments must match
the schema, and the lead is fixed when the call starts (a caller can't reach another
patient's data). Anything else raises DisallowedTool, which the agent turns into a handover.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Protocol

from ..config import IST


class DisallowedTool(Exception):
    pass


SCHEMA: dict[str, dict[str, tuple]] = {
    "get_available_slots": {"clinic_id": (str,), "day_offset": (int, type(None)), "start_min": (int, type(None)),
                            "end_min": (int, type(None)), "limit": (int,)},
    "hold_slot": {"slot_id": (str,)},
    "release_hold": {"slot_id": (str,)},
    "book_consultation": {"slot_id": (str,)},
    "handover": {"reasons": (list,), "urgency": (str,), "note": (str, type(None))},
    "mark_not_interested": {},
    "schedule_callback": {"at": (datetime,)},
    "suppress_contact": {"reason": (str,)},
    "transfer_to_staff": {},  # the backend picks who; the model can't choose a target
}
MAX_BOOKINGS_PER_CALL = 1


class Backend(Protocol):
    def clinics(self) -> list[tuple[str, str]]: ...
    def get_available_slots(self, clinic_id, day_offset, start_min, end_min, limit) -> list[dict]: ...
    def hold_slot(self, slot_id) -> bool: ...
    def release_hold(self, slot_id) -> None: ...
    def book_consultation(self, slot_id) -> dict | None: ...
    def handover(self, reasons, urgency, note) -> dict: ...
    def mark_not_interested(self) -> None: ...
    def schedule_callback(self, at) -> None: ...
    def suppress_contact(self, reason) -> None: ...


@dataclass
class ToolRegistry:
    backend: Backend
    log: list[dict] = field(default_factory=list)
    bookings: int = 0

    def call(self, name: str, **kwargs) -> Any:
        if name not in SCHEMA:
            self.log.append({"tool": name, "allowed": False})
            raise DisallowedTool(f"tool {name!r} is not allowed")
        schema = SCHEMA[name]
        if set(kwargs) != set(schema) or any(not isinstance(kwargs[k], schema[k]) for k in schema):
            self.log.append({"tool": name, "allowed": False})
            raise DisallowedTool(f"bad arguments for {name}")
        if name == "book_consultation" and self.bookings >= MAX_BOOKINGS_PER_CALL:
            self.log.append({"tool": name, "allowed": False})
            raise DisallowedTool("booking limit reached for this call")
        self.log.append({"tool": name, "allowed": True})
        out = getattr(self.backend, name)(**kwargs)
        if name == "book_consultation" and out:
            self.bookings += 1
        return out


# ---------------------------------------------------------------- in-memory backend (eval, unit tests, test calls)
class MemoryBackend:
    """Deterministic slots for the pilot clinics; records what the agent did.

    Used by the evaluation set and the console's test-call screen, so practice calls
    never create real leads, bookings or handovers.
    """

    DENTISTS = {"riverside": ["Dr. Meera Rao", "Dr. Nisha Pillai"], "hillcrest": ["Dr. Karan Bhatia", "Dr. Sana Mirza"],
                "lotus": ["Dr. Leena Das", "Dr. Vivek Menon"]}
    NAMES = {"riverside": "Riverside", "hillcrest": "Hillcrest", "lotus": "Lotus Square"}

    def __init__(self, now: datetime, real_slots: dict[str, list[dict]] | None = None, taken: set[str] | None = None,
                 empty_days: set[int] | None = None, fail_hold: bool = False, booking_paused: bool = False,
                 transfer_staff: str | None = None):
        self.now = now
        self.booking_paused = booking_paused
        self.transfer_staff = transfer_staff
        self.transferred_to: str | None = None
        self.taken = set(taken or ())
        self.empty_days = set(empty_days or ())
        self.fail_hold = fail_hold
        self.held: set[str] = set()
        self.booked: list[dict] = []
        self.handovers: list[dict] = []
        self.flags: list[str] = []
        self.callback_at: datetime | None = None
        self._slots = real_slots or self._generate()

    def _generate(self) -> dict[str, list[dict]]:
        out: dict[str, list[dict]] = {}
        today = self.now.astimezone(IST).date()
        for cid, dentists in self.DENTISTS.items():
            slots = []
            for d in range(8):
                day = today + timedelta(days=d)
                for h0, h1 in ((10, 13), (16, 20)):
                    t = datetime(day.year, day.month, day.day, h0, tzinfo=IST)
                    i = 0
                    while t.hour < h1:
                        dentist = dentists[i % 2]
                        slots.append({"id": f"{cid}-{d}-{t.strftime('%H%M')}-{i % 2}", "start_at": t, "dentist": dentist})
                        t += timedelta(minutes=30)
                        i += 1
            out[cid] = slots
        return out

    def clinics(self):
        return list(self.NAMES.items())

    def booking_allowed(self) -> bool:
        return not self.booking_paused

    def transfer_to_staff(self):
        if not self.transfer_staff:
            return None
        self.transferred_to = self.transfer_staff
        self.handovers.append({"reasons": ["asked_person"], "urgency": "normal", "note": "transferred"})
        return {"name": self.transfer_staff}

    def snapshot(self) -> dict:
        return {"taken": sorted(self.taken), "held": sorted(self.held), "flags": self.flags, "handovers": self.handovers,
                "booked": [{**b, "start_at": b["start_at"].isoformat()} for b in self.booked],
                "callback_at": self.callback_at.isoformat() if self.callback_at else None}

    def restore(self, snap: dict) -> None:
        self.taken, self.held = set(snap.get("taken", [])), set(snap.get("held", []))
        self.flags, self.handovers = list(snap.get("flags", [])), list(snap.get("handovers", []))
        self.booked = [{**b, "start_at": datetime.fromisoformat(b["start_at"])} for b in snap.get("booked", [])]
        self.callback_at = datetime.fromisoformat(snap["callback_at"]) if snap.get("callback_at") else None

    def get_available_slots(self, clinic_id, day_offset, start_min, end_min, limit):
        today = self.now.astimezone(IST).date()
        res = []
        for s in self._slots.get(clinic_id, []):
            local = s["start_at"].astimezone(IST)
            off = (local.date() - today).days
            mins = local.hour * 60 + local.minute
            if s["start_at"] <= self.now + timedelta(minutes=30) or s["id"] in self.taken or s["id"] in self.held:
                continue
            if off in self.empty_days or (day_offset is not None and off != day_offset):
                continue
            if start_min is not None and mins < start_min or end_min is not None and mins > end_min:
                continue
            res.append(dict(s))
            if len(res) >= limit:
                break
        return res

    def hold_slot(self, slot_id):
        if self.fail_hold or slot_id in self.taken or slot_id in self.held:
            self.taken.add(slot_id)
            self.fail_hold = False
            return False
        self.held.add(slot_id)
        return True

    def release_hold(self, slot_id):
        self.held.discard(slot_id)

    def book_consultation(self, slot_id):
        if slot_id not in self.held:
            return None
        s = next(x for v in self._slots.values() for x in v if x["id"] == slot_id)
        cid = next(k for k, v in self._slots.items() if s in v)
        self.held.discard(slot_id)
        self.taken.add(slot_id)
        b = {"booking_id": f"mem-{len(self.booked) + 1}", "start_at": s["start_at"], "dentist": s["dentist"],
             "clinic": self.NAMES[cid]}
        self.booked.append(b)
        return b

    def handover(self, reasons, urgency, note):
        from ..handovers import staffed_promise
        _, kind, minutes = staffed_promise(self.now, urgency if urgency in ("urgent", "normal") else "normal")
        self.handovers.append({"reasons": list(reasons), "urgency": urgency, "note": note})
        return {"promise": kind, "minutes": minutes}

    def mark_not_interested(self):
        self.flags.append("not_interested")

    def schedule_callback(self, at):
        self.callback_at = at

    def suppress_contact(self, reason):
        self.flags.append(f"suppressed:{reason}")


# ---------------------------------------------------------------- database backend (real calls)
class DbBackend:
    """Acts on one lead during one call. Each tool runs in its own short transaction."""

    HOLD_TTL = timedelta(minutes=3)

    def __init__(self, lead_id: str, call_attempt_id: str | None):
        self.lead_id, self.attempt_id = lead_id, call_attempt_id

    def _lead(self, conn, lock=True):
        return conn.execute("SELECT * FROM lead WHERE id = %s" + (" FOR UPDATE" if lock else ""), (self.lead_id,)).fetchone()

    def clinics(self):
        from ..db import tx
        with tx() as conn:
            return [(r["id"], r["name"]) for r in conn.execute("SELECT id, name FROM clinic WHERE is_pilot ORDER BY name")]

    def get_available_slots(self, clinic_id, day_offset, start_min, end_min, limit):
        from ..db import tx
        now = datetime.now(timezone.utc)
        with tx() as conn:
            conn.execute("UPDATE slot SET status = 'open', hold_expires_at = NULL WHERE status = 'held' AND hold_expires_at < now()")
            rows = conn.execute(
                "SELECT s.id, s.start_at, d.name AS dentist FROM slot s JOIN dentist d ON d.id = s.dentist_id "
                "WHERE s.clinic_id = %s AND s.status = 'open' AND s.start_at > %s AND s.start_at < %s "
                "ORDER BY s.start_at, d.name LIMIT 400", (clinic_id, now + timedelta(minutes=30), now + timedelta(days=8))).fetchall()
        today = now.astimezone(IST).date()
        out = []
        for r in rows:
            local = r["start_at"].astimezone(IST)
            mins = local.hour * 60 + local.minute
            if day_offset is not None and (local.date() - today).days != day_offset:
                continue
            if start_min is not None and mins < start_min or end_min is not None and mins > end_min:
                continue
            out.append({"id": str(r["id"]), "start_at": r["start_at"], "dentist": r["dentist"]})
            if len(out) >= limit:
                break
        return out

    def hold_slot(self, slot_id):
        from ..db import tx
        with tx() as conn:
            r = conn.execute("UPDATE slot SET status = 'held', hold_expires_at = now() + %s WHERE id = %s AND status = 'open' "
                             "AND start_at > now() RETURNING id", (self.HOLD_TTL, slot_id)).fetchone()
        return r is not None

    def release_hold(self, slot_id):
        from ..db import tx
        with tx() as conn:
            conn.execute("UPDATE slot SET status = 'open', hold_expires_at = NULL WHERE id = %s AND status = 'held'", (slot_id,))

    def book_consultation(self, slot_id):
        from .. import calendar_sync
        try:
            return self._book(slot_id)
        except calendar_sync.CalendarConflict:  # taken in the clinic's own calendar: block it, offer another
            calendar_sync.block_slot(slot_id)
            return None

    def _book(self, slot_id):
        from .. import calendar_sync, events
        from ..db import tx
        with tx() as conn:
            lead = self._lead(conn)
            slot = conn.execute(
                "UPDATE slot SET status = 'booked', hold_expires_at = NULL WHERE id = %s AND status = 'held' AND clinic_id = %s "
                "RETURNING id, dentist_id, start_at, clinic_id", (slot_id, lead["clinic_id"])).fetchone()
            if slot is None:
                return None
            ext = calendar_sync.confirm_booking(conn, slot["id"], lead, "Booked by the virtual assistant")
            b = conn.execute(
                "INSERT INTO booking (lead_id, slot_id, clinic_id, dentist_id, start_at, created_by, review_status, call_attempt_id, "
                "external_ref) VALUES (%s, %s, %s, %s, %s, 'assistant', 'pending', %s, %s) RETURNING id",
                (lead["id"], slot["id"], slot["clinic_id"], slot["dentist_id"], slot["start_at"], self.attempt_id, ext)).fetchone()
            dentist = conn.execute("SELECT name FROM dentist WHERE id = %s", (slot["dentist_id"],)).fetchone()["name"]
            clinic = conn.execute("SELECT name FROM clinic WHERE id = %s", (slot["clinic_id"],)).fetchone()["name"]
            events.append(conn, "booking.created", lead_id=lead["id"], clinic_id=lead["clinic_id"], actor="assistant",
                          payload={"booking_id": str(b["id"]), "created_by": "assistant", "arm": lead["arm"],
                                   "start_at": slot["start_at"].isoformat()})
            events.status_changed(conn, lead, "booked", actor="assistant")
            from .. import messaging
            messaging.queue_booking_confirmation(conn, lead, b["id"])  # WhatsApp confirmation (plan P4-03)
        return {"booking_id": str(b["id"]), "start_at": slot["start_at"], "dentist": dentist, "clinic": clinic}

    def transfer_to_staff(self):
        """Warm transfer to an available staff member at this clinic, during staffed hours (Phase 6)."""
        from .. import events, handovers, telephony
        from ..db import tx
        from ..handovers import staffed_promise
        if staffed_promise(datetime.now(timezone.utc), "normal")[1] != "minutes":
            return None  # outside staffed hours nobody can pick up live
        with tx() as conn:
            lead = self._lead(conn, lock=False)
            a = conn.execute("SELECT provider_call_id FROM call_attempt WHERE id = %s", (self.attempt_id,)).fetchone()
            staff = conn.execute(
                """SELECT s.id, s.display_name, s.phone_e164 FROM staff s JOIN staff_clinic sc ON sc.staff_id = s.id
                   WHERE sc.clinic_id = %s AND s.active AND s.transfer_available AND s.phone_e164 IS NOT NULL
                     AND (s.transfer_available_until IS NULL OR s.transfer_available_until > now())
                     AND NOT EXISTS (SELECT 1 FROM call_attempt x WHERE x.transferred_to = s.id AND x.transferred_at > now() - interval '10 minutes')
                   ORDER BY random() LIMIT 1""", (lead["clinic_id"],)).fetchone()
        if not staff or not a or not a["provider_call_id"]:
            return None
        try:
            ok = telephony.provider().transfer(a["provider_call_id"], staff["phone_e164"])
        except Exception:
            ok = False
        if not ok:
            return None
        with tx() as conn:
            lead = self._lead(conn)
            conn.execute("UPDATE call_attempt SET transferred_to = %s, transferred_at = now() WHERE id = %s", (staff["id"], self.attempt_id))
            h = handovers.create(conn, lead, ["asked_person", "transferred"], "normal", actor="assistant",
                                 note=f"Transferred live to {staff['display_name']}", call_attempt_id=self.attempt_id)
            conn.execute("UPDATE handover SET claimed_by = %s, claimed_at = now() WHERE id = %s", (staff["id"], h["handover_id"]))
            conn.execute("UPDATE lead SET claimed_by = %s, claimed_at = now() WHERE id = %s", (staff["id"], lead["id"]))
            events.append(conn, "call.transferred", lead_id=lead["id"], clinic_id=lead["clinic_id"], actor="assistant",
                          payload={"to_staff": str(staff["id"])})
        return {"name": staff["display_name"].split()[0]}

    def booking_allowed(self) -> bool:
        """Kill switch 'pause AI booking' (implementation-plan §13): call and qualify, but hand over."""
        from ..db import tx
        with tx() as conn:
            r = conn.execute(
                "SELECT e.booking_paused, c.calendar_adapter, sr.refreshed_at FROM lead l JOIN clinic c ON c.id = l.clinic_id "
                "LEFT JOIN experiment_config e ON e.clinic_id = l.clinic_id LEFT JOIN slot_refresh sr ON sr.clinic_id = l.clinic_id "
                "WHERE l.id = %s", (self.lead_id,)).fetchone()
        if not r or r["booking_paused"]:
            return not r or not r["booking_paused"]
        # Stale slot list -> don't book from it (EC-BOOK-11): 24 h for the manual list, 30 min for a synced calendar.
        max_age = timedelta(minutes=30) if r["calendar_adapter"] == "http" else timedelta(hours=24)
        return r["refreshed_at"] is not None and r["refreshed_at"] > datetime.now(timezone.utc) - max_age

    def handover(self, reasons, urgency, note):
        from .. import handovers
        from ..db import tx
        with tx() as conn:
            lead = self._lead(conn)
            return handovers.create(conn, lead, reasons, urgency, actor="assistant", note=note, call_attempt_id=self.attempt_id)

    def mark_not_interested(self):
        from .. import events
        from ..db import tx
        with tx() as conn:
            events.status_changed(conn, self._lead(conn), "not_interested", actor="assistant")

    def schedule_callback(self, at):
        from .. import orchestrator
        from ..db import tx
        with tx() as conn:
            orchestrator.schedule_call(conn, self._lead(conn), at, reason="callback_requested")

    def suppress_contact(self, reason):
        from .. import events
        from ..db import tx
        with tx() as conn:
            lead = self._lead(conn)
            conn.execute("INSERT INTO suppression (phone_e164, reason, lead_id) VALUES (%s, %s, %s) ON CONFLICT DO NOTHING",
                         (lead["phone_e164"], reason, lead["id"]))
            conn.execute("UPDATE call_job SET status = 'cancelled' WHERE lead_id = %s AND status = 'pending'", (lead["id"],))
            events.append(conn, "lead.suppressed", lead_id=lead["id"], clinic_id=lead["clinic_id"], actor="assistant",
                          payload={"reason": reason})
            from .. import messaging
            messaging.cancel_pending(conn, lead["id"])
            if reason == "stop_calling":  # confirm once (EC-MAN-06); never message someone who says they never enquired
                messaging.enqueue(conn, lead, "opt_out_confirm_v1", {}, dedupe_key="optout")
            events.status_changed(conn, lead, "unreachable" if reason == "never_enquired" else "not_interested", actor="assistant")
