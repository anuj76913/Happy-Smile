"""Top-strip metrics (architecture §9.2), computed from the event log only.

Plan P2 exit criterion: "the event log reproduces the top-strip numbers exactly".
`from_events` is what the console shows; `from_state` derives the same numbers from the
tables, and `consistency` compares them (used by tests and the admin endpoint).
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta

from psycopg import Connection

from .config import IST

WAITING = ("awaiting_call", "needs_you")


def ist_day_bounds(day: date | None = None) -> tuple[datetime, datetime]:
    day = day or datetime.now(IST).date()
    start = datetime.combine(day, time(0, 0), tzinfo=IST)
    return start, start + timedelta(days=1)


def from_events(conn: Connection, clinics: list[str], day: date | None = None) -> dict:
    start, end = ist_day_bounds(day)
    q = lambda sql, *a: conn.execute(sql, a).fetchone()  # noqa: E731

    enquiries = q("SELECT count(*) AS n FROM event WHERE type = 'lead.created' AND clinic_id = ANY(%s) "
                  "AND occurred_at >= %s AND occurred_at < %s", clinics, start, end)["n"]

    reach = conn.execute(
        """WITH created AS (
             SELECT lead_id FROM event WHERE type = 'lead.created' AND clinic_id = ANY(%s)
               AND occurred_at >= %s AND occurred_at < %s),
           arm AS (SELECT DISTINCT ON (lead_id) lead_id, payload->>'arm' AS arm FROM event
                   WHERE type = 'lead.assigned' AND lead_id IN (SELECT lead_id FROM created) ORDER BY lead_id, id),
           reached AS (SELECT DISTINCT ON (lead_id) lead_id, (payload->>'seconds_after_enquiry')::float8 AS s FROM event
                       WHERE type = 'lead.reached' AND lead_id IN (SELECT lead_id FROM created) ORDER BY lead_id, id)
           SELECT arm.arm, count(*) AS leads, count(*) FILTER (WHERE reached.s <= 300) AS within5,
                  count(reached.lead_id) AS reached
           FROM arm LEFT JOIN reached USING (lead_id) GROUP BY arm.arm""", (clinics, start, end)).fetchall()
    by_arm = {r["arm"]: {"leads": r["leads"], "reached_within_5": r["within5"], "reached": r["reached"]} for r in reach}

    bookings = conn.execute(
        "SELECT payload->>'created_by' AS by, count(*) AS n FROM event WHERE type = 'booking.created' "
        "AND clinic_id = ANY(%s) AND occurred_at >= %s AND occurred_at < %s GROUP BY 1", (clinics, start, end)).fetchall()
    booked = {r["by"]: r["n"] for r in bookings}

    latest = conn.execute(
        """SELECT payload->>'to' AS status, count(*) AS n FROM (
             SELECT DISTINCT ON (lead_id) lead_id, payload FROM event
             WHERE type = 'lead.status_changed' AND clinic_id = ANY(%s)
               AND lead_id IN (SELECT lead_id FROM event WHERE type = 'lead.created'
                               AND occurred_at > now() - interval '30 days')
             ORDER BY lead_id, id DESC) s GROUP BY 1""", (clinics,)).fetchall()
    current = {r["status"]: r["n"] for r in latest}

    return _shape(enquiries, by_arm, booked, current)


def from_state(conn: Connection, clinics: list[str], day: date | None = None) -> dict:
    start, end = ist_day_bounds(day)
    enquiries = conn.execute("SELECT count(*) AS n FROM lead WHERE clinic_id = ANY(%s) AND created_at >= %s AND created_at < %s",
                             (clinics, start, end)).fetchone()["n"]
    reach = conn.execute(
        "SELECT arm, count(*) AS leads, "
        "count(*) FILTER (WHERE extract(epoch FROM first_reached_at - created_at) <= 300) AS within5, "
        "count(first_reached_at) AS reached FROM lead WHERE clinic_id = ANY(%s) AND created_at >= %s AND created_at < %s "
        "GROUP BY arm", (clinics, start, end)).fetchall()
    by_arm = {r["arm"]: {"leads": r["leads"], "reached_within_5": r["within5"], "reached": r["reached"]} for r in reach}
    booked = {r["created_by"]: r["n"] for r in conn.execute(
        "SELECT created_by, count(*) AS n FROM booking WHERE clinic_id = ANY(%s) AND created_at >= %s AND created_at < %s "
        "GROUP BY 1", (clinics, start, end))}
    current = {r["status"]: r["n"] for r in conn.execute(
        "SELECT status, count(*) AS n FROM lead WHERE clinic_id = ANY(%s) AND created_at > now() - interval '30 days' "
        "AND status <> 'new' GROUP BY 1", (clinics,))}
    return _shape(enquiries, by_arm, booked, current)


def _shape(enquiries: int, by_arm: dict, booked: dict, current: dict) -> dict:
    empty = {"leads": 0, "reached_within_5": 0, "reached": 0}
    return {
        "enquiries_received": enquiries,
        "reached_within_5": {arm: by_arm.get(arm, empty) for arm in ("assistant", "control", "not_in_pilot")},
        "booked_by_assistant": booked.get("assistant", 0),
        "booked_by_staff": booked.get("staff", 0),
        "waiting_for_staff": sum(current.get(s, 0) for s in WAITING),
        "no_answer": current.get("no_answer", 0),
    }


def consistency(conn: Connection, clinics: list[str]) -> dict:
    a, b = from_events(conn, clinics), from_state(conn, clinics)
    return {"match": a == b, "from_events": a, "from_state": b}
