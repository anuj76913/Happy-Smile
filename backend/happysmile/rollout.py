"""Scaling after the pilot (implementation-plan §10, Phase 6).

Rules:
  - Nothing beyond the pilot happens unless the latest recorded G4 decision is 'scale'
    (enforced in staging/production; reported in development).
  - Clinics join in waves of three. A wave can start when every clinic in the previous
    wave has been at steady state for 7 days with no open critical alert, and each new
    clinic's onboarding is complete.
  - A permanent control group stays: the assistant share never exceeds
    1 - PERMANENT_CONTROL_SHARE (default 90%), in every environment, so lift keeps
    being measured (§10 "keep a small permanent control share").
  - Ramp per clinic: 0 -> 20% (onboarding + G2) -> 50% (G3) -> steady 90% (G3 + G4 scale).
"""

from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from psycopg import Connection

from . import events
from .config import get_settings

ONBOARDING = {
    "rota_staffed": "Handover rota staffed for this clinic (ADR-005)",
    "staff_trained": "Front-desk staff trained with the staff guide",
    "languages_confirmed": "Patient languages checked against the assistant's supported languages",
    "address_confirmed": "Clinic address and dentist list checked for confirmations",
}
STEADY_DAYS = 7


def latest_g4(conn: Connection) -> str | None:
    r = conn.execute("SELECT decision FROM pilot_decision ORDER BY id DESC LIMIT 1").fetchone()
    return r["decision"] if r else None


def max_share() -> Decimal:
    return Decimal(1) - Decimal(str(get_settings().permanent_control_share))


def onboarding_checks(conn: Connection, clinic_id: str) -> list[dict]:
    c = conn.execute("SELECT * FROM clinic WHERE id = %s", (clinic_id,)).fetchone()
    dentists = conn.execute("SELECT count(*) AS n FROM dentist WHERE clinic_id = %s AND active", (clinic_id,)).fetchone()["n"]
    staff = conn.execute("SELECT count(*) AS n FROM staff s JOIN staff_clinic sc ON sc.staff_id = s.id "
                         "WHERE sc.clinic_id = %s AND s.active AND s.role = 'front_desk'", (clinic_id,)).fetchone()["n"]
    fresh = conn.execute("SELECT refreshed_at > now() - interval '24 hours' AS ok FROM slot_refresh WHERE clinic_id = %s",
                         (clinic_id,)).fetchone()
    calendar_ok = (c["calendar_adapter"] == "http" and c["calendar_synced_at"] is not None) or bool(fresh and fresh["ok"])
    done = {r["item"]: r for r in conn.execute(
        "SELECT o.item, o.done_at, s.display_name FROM clinic_onboarding o JOIN staff s ON s.id = o.done_by WHERE o.clinic_id = %s",
        (clinic_id,))}
    checks = [
        {"id": "dentists", "label": "At least one dentist configured", "ok": dentists > 0},
        {"id": "staff_accounts", "label": "Front-desk accounts created for this clinic", "ok": staff > 0},
        {"id": "slots", "label": "Calendar synced or slot list updated in the last 24 h", "ok": calendar_ok},
        {"id": "address", "label": "Clinic address on file", "ok": bool(c["address"])},
    ]
    for item, label in ONBOARDING.items():
        d = done.get(item)
        checks.append({"id": item, "label": label, "ok": d is not None, "attestation": True,
                       "by": d["display_name"] if d else None})
    return checks


def wave_status(conn: Connection) -> list[dict]:
    rows = conn.execute(
        """SELECT c.id, c.name, c.rollout_wave, c.is_pilot, c.activated_at, c.calendar_adapter, c.calendar_synced_at,
                  e.assistant_share::float AS share, e.steady_since, e.booking_paused
           FROM clinic c LEFT JOIN experiment_config e ON e.clinic_id = c.id ORDER BY c.rollout_wave NULLS LAST, c.name""").fetchall()
    out = []
    for r in rows:
        out.append({"id": r["id"], "name": r["name"], "wave": r["rollout_wave"], "active": r["is_pilot"],
                    "activated_at": r["activated_at"].isoformat() if r["activated_at"] else None,
                    "share": r["share"], "steady_since": r["steady_since"].isoformat() if r["steady_since"] else None,
                    "calendar": r["calendar_adapter"], "calendar_synced_at": r["calendar_synced_at"].isoformat() if r["calendar_synced_at"] else None,
                    "onboarding": onboarding_checks(conn, r["id"]) if not r["is_pilot"] else None})
    return out


def wave_checks(conn: Connection, wave: int) -> list[dict]:
    g4 = latest_g4(conn)
    checks = [{"id": "g4_scale", "label": "Latest G4 decision is 'scale'", "ok": g4 == "scale", "value": g4}]
    prev = conn.execute("SELECT c.id, e.steady_since FROM clinic c LEFT JOIN experiment_config e ON e.clinic_id = c.id "
                        "WHERE c.rollout_wave = %s", (wave - 1,)).fetchall()
    now = datetime.now(timezone.utc)
    if wave > 1:
        not_steady = [p["id"] for p in prev if not (p["steady_since"] and p["steady_since"] < now - timedelta(days=STEADY_DAYS))]
        checks.append({"id": "previous_wave_steady", "label": f"Wave {wave - 1} at steady state for {STEADY_DAYS} days",
                       "ok": not not_steady and bool(prev), "value": not_steady})
        alerts = conn.execute("SELECT count(*) AS n FROM alert WHERE resolved_at IS NULL AND severity = 'critical' "
                              "AND clinic_id = ANY(%s)", ([p["id"] for p in prev],)).fetchone()["n"]
        checks.append({"id": "no_critical_alerts", "label": f"No open critical alerts in wave {wave - 1}", "ok": alerts == 0, "value": alerts})
    for c in conn.execute("SELECT id FROM clinic WHERE rollout_wave = %s AND NOT is_pilot ORDER BY id", (wave,)):
        missing = [x["label"] for x in onboarding_checks(conn, c["id"]) if not x["ok"]]
        checks.append({"id": f"onboarding_{c['id']}", "label": f"{c['id']}: onboarding complete", "ok": not missing, "value": missing})
    return checks


def activate_wave(conn: Connection, wave: int, staff_id) -> dict:
    """Bring a wave's clinics into the programme at 0% assistant share (they ramp like the pilot did)."""
    if wave < 2:
        raise ValueError("Wave 1 is the pilot.")
    failing = [c["label"] for c in wave_checks(conn, wave) if not c["ok"]]
    if failing and get_settings().is_production_like:
        raise PermissionError("Wave can't start: " + "; ".join(failing))
    clinics = [r["id"] for r in conn.execute("SELECT id FROM clinic WHERE rollout_wave = %s AND NOT is_pilot", (wave,))]
    for cid in clinics:
        conn.execute("UPDATE clinic SET is_pilot = true, activated_at = now() WHERE id = %s", (cid,))
        conn.execute("INSERT INTO experiment_config (clinic_id, assistant_share, salt) VALUES (%s, 0, %s) ON CONFLICT (clinic_id) DO NOTHING",
                     (cid, secrets.token_hex(16)))
        events.append(conn, "rollout.clinic_activated", clinic_id=cid, actor=f"staff:{staff_id}", payload={"wave": wave})
    events.audit(conn, staff_id, "rollout_wave_activated", detail={"wave": wave, "clinics": clinics, "unmet_in_dev": failing})
    return {"activated": clinics, "unmet_checks_reported_only": failing if not get_settings().is_production_like else []}


def attest_onboarding(conn: Connection, clinic_id: str, item: str, staff_id, note: str | None) -> None:
    if item not in ONBOARDING:
        raise ValueError("unknown onboarding item")
    conn.execute("INSERT INTO clinic_onboarding (clinic_id, item, done_by, note) VALUES (%s, %s, %s, %s) "
                 "ON CONFLICT (clinic_id, item) DO UPDATE SET done_by = EXCLUDED.done_by, note = EXCLUDED.note, done_at = now()",
                 (clinic_id, item, staff_id, (note or "")[:300]))
    events.audit(conn, staff_id, "onboarding_attested", detail={"clinic": clinic_id, "item": item})


def check_share(conn: Connection, clinic_id: str, share: Decimal) -> None:
    """Phase 6 share rules, applied on top of gates G2/G3 (ops.check_share_change)."""
    cap = max_share()
    if share > cap:  # always enforced: the permanent control group keeps measurement honest
        raise PermissionError(f"The assistant share can't exceed {cap:.0%}: {get_settings().permanent_control_share:.0%} of leads "
                              "stay on the standard callback so the effect keeps being measured.")
    if not get_settings().is_production_like or share <= 0:
        return
    if share > Decimal("0.5") and latest_g4(conn) != "scale":
        raise PermissionError("Above 50% needs a recorded G4 decision of 'scale'.")
    wave = conn.execute("SELECT rollout_wave FROM clinic WHERE id = %s", (clinic_id,)).fetchone()["rollout_wave"]
    if wave and wave > 1:
        missing = [c["label"] for c in onboarding_checks(conn, clinic_id) if not c["ok"]]
        if missing:
            raise PermissionError("Onboarding incomplete: " + "; ".join(missing))


def mark_steady(conn: Connection, clinic_id: str, share: Decimal) -> None:
    conn.execute("UPDATE experiment_config SET steady_since = CASE WHEN %s > 0.5 THEN coalesce(steady_since, now()) ELSE NULL END "
                 "WHERE clinic_id = %s", (share, clinic_id))
