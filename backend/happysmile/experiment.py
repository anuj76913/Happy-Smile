"""Experiment assigner (architecture §4.3, §10; edge cases EC-EXP-01 to 08).

- Pilot clinics only; other clinics get 'not_in_pilot' and are excluded from analysis.
- Deterministic: sha256(clinic salt + lead id) mapped to [0, 1) and compared with the
  clinic's assistant share. Each clinic has its own share and salt (stratified by clinic),
  so staff can't predict or influence the arm.
- Returning patients keep the arm of their first pilot lead (EC-EXP-02).
- Written once; the database refuses any later change.
"""

from __future__ import annotations

import hashlib
from decimal import Decimal

from psycopg import Connection

from . import events
from .config import get_settings


def bucket(salt: str, lead_id) -> float:
    h = hashlib.sha256(f"{salt}:{lead_id}".encode()).hexdigest()
    return int(h[:13], 16) / float(16 ** 13)


def clinic_share(conn: Connection, clinic_id: str) -> tuple[bool, float, str | None]:
    row = conn.execute(
        "SELECT c.is_pilot, e.assistant_share, e.salt FROM clinic c "
        "LEFT JOIN experiment_config e ON e.clinic_id = c.id WHERE c.id = %s", (clinic_id,)).fetchone()
    if row is None:
        raise ValueError(f"unknown clinic {clinic_id}")
    share = float(row["assistant_share"] or 0) if row["is_pilot"] else 0.0
    return bool(row["is_pilot"]), share, row["salt"]


def assign(conn: Connection, lead: dict) -> str:
    """Assign and persist the arm for a new lead. Returns the arm."""
    is_pilot, share, salt = clinic_share(conn, lead["clinic_id"])
    reason, b = "hash", None
    if not is_pilot or salt is None:
        arm, reason = "not_in_pilot", "clinic_not_in_pilot"
    else:
        # A returning patient keeps their first arm (fair comparison). The dev browser voice demo skips
        # this so you can test repeatedly with your own number, which may already sit in control.
        prior = None if get_settings().browser_calls else conn.execute(
            "SELECT arm FROM lead WHERE phone_e164 = %s AND id <> %s AND arm IN ('assistant', 'control') "
            "ORDER BY created_at LIMIT 1", (lead["phone_e164"], lead["id"])).fetchone()
        if prior:
            arm, reason = prior["arm"], "returning_patient"
        else:
            b = bucket(salt, lead["id"])
            arm = "assistant" if b < share else "control"

    conn.execute("UPDATE lead SET arm = %s, arm_assigned_at = now() WHERE id = %s", (arm, lead["id"]))
    events.append(conn, "lead.assigned", lead_id=lead["id"], clinic_id=lead["clinic_id"], actor="system",
                  payload={"arm": arm, "share": share, "bucket": b, "reason": reason})
    lead["arm"] = arm
    return arm


def set_share(conn: Connection, clinic_id: str, share: Decimal, staff_id) -> None:
    """Change a clinic's assistant share. Only affects new leads (assignment is write-once)."""
    if not (Decimal(0) <= share <= Decimal(1)):
        raise ValueError("assistant_share must be between 0 and 1")
    if share > 0 and not get_settings().voice_agent_enabled:
        raise PermissionError("The voice agent is not enabled yet, so the assistant share must stay at 0.")
    row = conn.execute("SELECT is_pilot FROM clinic WHERE id = %s", (clinic_id,)).fetchone()
    if not row or not row["is_pilot"]:
        raise ValueError("Only pilot clinics have an experiment configuration.")
    from . import ops, rollout
    rollout.check_share(conn, clinic_id, share)     # permanent control cap; G4 'scale' above 50%; onboarding (Phase 6)
    ops.check_share_change(conn, clinic_id, share)  # gates G2 (any share) and G3 (above 20%)
    old = conn.execute("SELECT assistant_share FROM experiment_config WHERE clinic_id = %s", (clinic_id,)).fetchone()
    conn.execute("UPDATE experiment_config SET assistant_share = %s, updated_at = now(), updated_by = %s, "
                 "live_since = CASE WHEN %s > 0 THEN coalesce(live_since, now()) ELSE NULL END "
                 "WHERE clinic_id = %s", (share, staff_id, share, clinic_id))
    rollout.mark_steady(conn, clinic_id, share)
    events.append(conn, "experiment.share_changed", clinic_id=clinic_id, actor=f"staff:{staff_id}",
                  payload={"from": float(old["assistant_share"]) if old else None, "to": float(share)})
