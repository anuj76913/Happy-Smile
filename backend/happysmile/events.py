"""Append-only domain events (architecture §4.12) and the staff audit log (§13).

Events are written in the same transaction as the state change they describe, so
the log and the tables can't drift apart. Writers take a transaction-scoped advisory
lock, which makes event ids commit in order: the live stream can then safely read
"everything after id N" without missing a late commit.
"""

from __future__ import annotations

from typing import Any

from psycopg import Connection
from psycopg.types.json import Jsonb

_EVENT_LOCK = 7002


def append(conn: Connection, type_: str, *, lead_id=None, clinic_id: str | None = None,
           actor: str = "system", payload: dict[str, Any] | None = None) -> int:
    conn.execute("SELECT pg_advisory_xact_lock(%s)", (_EVENT_LOCK,))
    row = conn.execute(
        "INSERT INTO event (lead_id, clinic_id, type, payload, actor) VALUES (%s, %s, %s, %s, %s) RETURNING id",
        (lead_id, clinic_id, type_, Jsonb(payload or {}), actor)).fetchone()
    return row["id"]


def status_changed(conn: Connection, lead: dict, new_status: str, actor: str, **extra) -> None:
    if lead["status"] == new_status:
        return
    conn.execute("UPDATE lead SET status = %s WHERE id = %s", (new_status, lead["id"]))
    append(conn, "lead.status_changed", lead_id=lead["id"], clinic_id=lead["clinic_id"], actor=actor,
           payload={"from": lead["status"], "to": new_status, "arm": lead["arm"], **extra})
    lead["status"] = new_status


def audit(conn: Connection, staff_id, action: str, *, lead_id=None, detail: dict | None = None,
          ip_hash: str | None = None) -> None:
    conn.execute("INSERT INTO audit_log (staff_id, action, lead_id, detail, ip_hash) VALUES (%s, %s, %s, %s, %s)",
                 (staff_id, action, lead_id, Jsonb(detail or {}), ip_hash))
