"""Operations: live metrics, alerts, kill switch, go-live gates (plan P4-08, P4-10; implementation-plan §12-13).

Kill switch (implementation-plan §13):
  stop_assistant   share -> 0 for a clinic or all clinics; new leads go to the standard callback
  pause_booking    the assistant still calls and qualifies but hands over instead of booking
  resume_booking
  drill            records a tested kill switch (required by gate G2)
Automatic triggers (AUTO_KILL_SWITCH=true):
  urgent handover unclaimed at 2x its SLA       -> stop_assistant for that clinic + critical alert
  booking-review rejection > 15% (>= 5 reviews) -> pause_booking for that clinic + critical alert
  handover SLA hit rate < 60% (>= 5 handovers)  -> critical alert only (lowering the share is a human call)

Gates: G2 must pass before any assistant share > 0, G3 before > 20% (enforced in staging/production).
"""

from __future__ import annotations

import os
import statistics
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import httpx
from psycopg import Connection

from . import events
from .config import get_settings
from .db import tx
from .metrics import ist_day_bounds

ATTESTATIONS = {
    "frontdesk_signoff": "Front-desk lead signed off script, tone and handover lines (G1)",
    "hindi_review": "Native Hindi speaker reviewed every Hindi line and template",
    "legal_consent_telecom": "Legal approved consent wording and telecom classification (P0-14)",
    "legal_groq_terms": "Legal accepted Groq data terms, or Groq is not used (P0-13)",
    "whatsapp_templates_approved": "All WhatsApp templates approved by Meta (P0-11)",
    "caller_id_registered": "Registered caller ID live and shown on the form (P0-10)",
    "staff_trained": "Pilot clinic staff trained with the one-page guide (P4-09)",
    "handover_rota": "Handover rota staffed for each pilot clinic (ADR-005)",
    "latency_measured": "p90 turn latency <= 1.2 s measured on real test calls (G1)",
}


def _p(values: list[float], q: int) -> float | None:
    if not values:
        return None
    if len(values) == 1:
        return values[0]
    return statistics.quantiles(values, n=100, method="inclusive")[q - 1]


# ---------------------------------------------------------------- metrics
def metrics(conn: Connection, clinics: list[str]) -> dict:
    start, end = ist_day_bounds()
    fd = conn.execute(
        """SELECT extract(epoch FROM a.started_at - l.created_at) AS s FROM call_attempt a JOIN lead l ON l.id = a.lead_id
           WHERE a.made_by = 'assistant' AND a.attempt_no = 1 AND l.clinic_id = ANY(%s) AND l.created_at >= %s AND l.created_at < %s
             AND l.contact_pref = 'now' AND extract(hour FROM l.created_at AT TIME ZONE 'Asia/Kolkata') BETWEEN 9 AND 20""",
        (clinics, start, end)).fetchall()
    first_dial = [float(r["s"]) for r in fd]
    llm = conn.execute(
        "SELECT ok, error, ttft_ms FROM llm_call WHERE at > now() - interval '1 hour'").fetchall()
    ttft = [r["ttft_ms"] for r in llm if r["ok"] and r["ttft_ms"] is not None]
    ho = conn.execute(
        """SELECT h.urgency, h.sla_due_at, h.claimed_at, h.resolved_at, h.escalated_at FROM handover h JOIN lead l ON l.id = h.lead_id
           WHERE l.clinic_id = ANY(%s) AND h.created_at >= %s AND h.created_at < %s""", (clinics, start, end)).fetchall()
    now = datetime.now(timezone.utc)
    decided = [h for h in ho if h["claimed_at"] or h["resolved_at"] or h["sla_due_at"] < now]
    on_time = [h for h in decided if (h["claimed_at"] or h["resolved_at"] or now) <= h["sla_due_at"]]
    urgent_missed = [h for h in ho if h["urgency"] == "urgent" and (h["claimed_at"] or h["resolved_at"] or now) > h["sla_due_at"]]
    msgs = conn.execute(
        """SELECT m.status, count(*) AS n FROM message m JOIN lead l ON l.id = m.lead_id WHERE m.direction = 'outbound'
           AND l.clinic_id = ANY(%s) AND m.created_at >= %s AND m.created_at < %s GROUP BY 1""", (clinics, start, end)).fetchall()
    msg = {r["status"]: r["n"] for r in msgs}
    sent_total = sum(v for k, v in msg.items() if k in ("sent", "delivered", "read", "failed"))
    rev = conn.execute(
        """SELECT review_status, count(*) AS n FROM booking WHERE created_by = 'assistant' AND clinic_id = ANY(%s)
           AND reviewed_at >= %s AND reviewed_at < %s GROUP BY 1""", (clinics, start, end)).fetchall()
    revd = {r["review_status"]: r["n"] for r in rev}
    reviewed = sum(revd.values())
    breakers = {r["name"]: bool(r["open_until"] and r["open_until"] > now)
                for r in conn.execute("SELECT name, open_until FROM breaker")}
    cfg = [dict(r) for r in conn.execute(
        "SELECT clinic_id, assistant_share::float AS share, booking_paused, live_since FROM experiment_config "
        "WHERE clinic_id = ANY(%s) ORDER BY clinic_id", (clinics,))]
    for c in cfg:
        c["live_since"] = c["live_since"].isoformat() if c["live_since"] else None
    return {
        "first_dial_seconds": {"count": len(first_dial), "p50": _p(first_dial, 50), "p90": _p(first_dial, 90), "target_p90": 60},
        "llm": {"calls_last_hour": len(llm), "errors": sum(not r["ok"] for r in llm),
                "rate_limited": sum((r["error"] or "") == "http_429" for r in llm),
                "timeouts": sum((r["error"] or "") == "timeout" for r in llm),
                "ttft_p50_ms": _p(ttft, 50), "ttft_p90_ms": _p(ttft, 90), "enabled": get_settings().llm_enabled},
        "handovers": {"today": len(ho), "decided": len(decided), "on_time": len(on_time),
                      "sla_hit_rate": (len(on_time) / len(decided)) if decided else None,
                      "urgent_missed": len(urgent_missed), "open": sum(1 for h in ho if not h["resolved_at"])},
        "whatsapp": {"queued": msg.get("queued", 0), "sent": sent_total, "failed": msg.get("failed", 0),
                     "failure_rate": (msg.get("failed", 0) / sent_total) if sent_total else None},
        "booking_review": {"reviewed": reviewed, "cancelled": revd.get("cancelled", 0),
                           "rejection_rate": (revd.get("cancelled", 0) / reviewed) if reviewed else None},
        "breakers": breakers,
        "clinics": cfg,
        "voice_agent_enabled": get_settings().voice_agent_enabled,
    }


# ---------------------------------------------------------------- alerts
def _open_alert(conn, key, severity, message, clinic_id=None) -> bool:
    row = conn.execute(
        "INSERT INTO alert (key, severity, clinic_id, message) VALUES (%s, %s, %s, %s) "
        "ON CONFLICT (key, coalesce(clinic_id, '')) WHERE resolved_at IS NULL DO NOTHING RETURNING id",
        (key, severity, clinic_id, message)).fetchone()
    if row:
        events.append(conn, "alert.opened", clinic_id=clinic_id, payload={"key": key, "severity": severity, "message": message})
    return row is not None


def _resolve(conn, key, clinic_id=None):
    conn.execute("UPDATE alert SET resolved_at = now() WHERE key = %s AND coalesce(clinic_id, '') = coalesce(%s, '') "
                 "AND resolved_at IS NULL", (key, clinic_id))


def _toggle(conn, cond: bool, key: str, severity: str, message: str, clinic_id, opened: list) -> None:
    if cond:
        if _open_alert(conn, key, severity, message, clinic_id):
            opened.append(key)
    else:
        _resolve(conn, key, clinic_id)


def evaluate_alerts() -> dict:
    """Run every minute by the worker. Opens/resolves alerts and fires automatic kill-switch actions."""
    s = get_settings()
    opened, actions = [], []
    with tx() as conn:
        clinics = [r["clinic_id"] for r in conn.execute("SELECT clinic_id FROM experiment_config ORDER BY clinic_id")]
        for cid in clinics:
            m = metrics(conn, [cid])
            # First dial too slow (target p90 <= 60 s; alert at 2 min, implementation-plan §15.2)
            p90 = m["first_dial_seconds"]["p90"]
            _toggle(conn, p90 is not None and m["first_dial_seconds"]["count"] >= 3 and p90 > 120, "first_dial_slow", "warning",
                    f"First-dial p90 is {p90 or 0:.0f}s (target 60s)", cid, opened)
            ho = m["handovers"]
            _toggle(conn, ho["sla_hit_rate"] is not None and ho["decided"] >= 5 and ho["sla_hit_rate"] < 0.6, "sla_below_60", "critical",
                    f"Handover SLA hit rate {ho['sla_hit_rate'] or 0:.0%} today; consider lowering the assistant share", cid, opened)
            late = conn.execute("SELECT count(*) AS n FROM handover h JOIN lead l ON l.id = h.lead_id WHERE l.clinic_id = %s "
                                "AND h.urgency = 'urgent' AND h.resolved_at IS NULL AND h.claimed_at IS NULL AND h.sla_due_at < now()",
                                (cid,)).fetchone()["n"]
            _toggle(conn, late > 0, "urgent_overdue", "critical", f"{late} urgent handover(s) past the 5-minute target", cid, opened)
            escalated = conn.execute("SELECT count(*) AS n FROM handover h JOIN lead l ON l.id = h.lead_id WHERE l.clinic_id = %s "
                                     "AND h.urgency = 'urgent' AND h.escalated_at IS NOT NULL AND h.claimed_at IS NULL "
                                     "AND h.resolved_at IS NULL", (cid,)).fetchone()["n"]
            share = conn.execute("SELECT assistant_share, booking_paused FROM experiment_config WHERE clinic_id = %s", (cid,)).fetchone()
            if escalated and s.auto_kill_switch and share["assistant_share"] > 0:
                kill_switch(conn, "stop_assistant", cid, None, reason="urgent handover missed (2x SLA)")
                actions.append(f"stop_assistant:{cid}")
            # Booking review rejection
            br = m["booking_review"]
            if br["rejection_rate"] is not None and br["reviewed"] >= 5 and br["rejection_rate"] > 0.15:
                _open_alert(conn, "review_rejection_high", "critical", f"{br['rejection_rate']:.0%} of assistant bookings cancelled at review today", cid)
                if s.auto_kill_switch and not share["booking_paused"]:
                    kill_switch(conn, "pause_booking", cid, None, reason="booking review rejection > 15%")
                    actions.append(f"pause_booking:{cid}")
            else:
                _resolve(conn, "review_rejection_high", cid)
        # System-wide
        failed = conn.execute("SELECT count(*) AS n FROM message WHERE status = 'failed' AND updated_at > now() - interval '1 hour'").fetchone()["n"]
        _toggle(conn, failed > 0, "whatsapp_failures", "warning", f"{failed} WhatsApp message(s) failed in the last hour", None, opened)
        if clinics:
            m = metrics(conn, clinics)
            llm = m["llm"]
            _toggle(conn, llm["calls_last_hour"] >= 20 and llm["errors"] / llm["calls_last_hour"] > 0.02, "llm_errors", "warning",
                    f"Groq errors {llm['errors']}/{llm['calls_last_hour']} in the last hour ({llm['rate_limited']} rate-limited)", None, opened)
            for name, is_open in m["breakers"].items():
                _toggle(conn, is_open, f"breaker_{name}", "critical", f"Circuit breaker '{name}' is open: new leads go to staff", None, opened)
    notify()
    return {"opened": opened, "actions": actions}


def notify() -> int:
    """Send unsent alerts to ALERT_WEBHOOK_URL (e.g. a Slack or Teams incoming webhook). No personal data."""
    url = get_settings().alert_webhook_url
    if not url:
        return 0
    with tx() as conn:
        rows = conn.execute("SELECT id, key, severity, clinic_id, message FROM alert WHERE notified_at IS NULL AND resolved_at IS NULL").fetchall()
    sent = 0
    for r in rows:
        try:
            httpx.post(url, json={"text": f"[{r['severity'].upper()}] {r['clinic_id'] or 'all clinics'}: {r['message']}"}, timeout=5)
            with tx() as conn:
                conn.execute("UPDATE alert SET notified_at = now() WHERE id = %s", (r["id"],))
            sent += 1
        except httpx.HTTPError:
            pass
    return sent


# ---------------------------------------------------------------- kill switch
def kill_switch(conn: Connection, action: str, clinic_id: str | None, staff_id, reason: str) -> dict:
    where = "WHERE clinic_id = %s" if clinic_id else ""
    args = (clinic_id,) if clinic_id else ()
    actor = f"staff:{staff_id}" if staff_id else "system"
    before = [dict(r) for r in conn.execute(f"SELECT clinic_id, assistant_share::float AS share, booking_paused FROM experiment_config {where}", args)]
    if action == "stop_assistant":
        conn.execute(f"UPDATE experiment_config SET assistant_share = 0, live_since = NULL, updated_at = now() {where}", args)
        # Leads already queued for an assistant call go to staff, keeping their arm (EC-EXP-04, intention-to-treat).
        queued = conn.execute(
            "SELECT * FROM lead WHERE status = 'queued' AND arm = 'assistant'" + (" AND clinic_id = %s" if clinic_id else "") + " FOR UPDATE",
            args).fetchall()
        from . import handovers
        for lead in queued:
            conn.execute("UPDATE call_job SET status = 'cancelled' WHERE lead_id = %s AND status = 'pending'", (lead["id"],))
            handovers.create(conn, lead, ["system_fallback"], "normal", actor=actor, note="Assistant stopped by kill switch")
    elif action == "pause_booking":
        conn.execute(f"UPDATE experiment_config SET booking_paused = true, updated_at = now() {where}", args)
    elif action == "resume_booking":
        conn.execute(f"UPDATE experiment_config SET booking_paused = false, updated_at = now() {where}", args)
    elif action != "drill":
        raise ValueError("unknown kill-switch action")
    events.append(conn, "killswitch." + action, clinic_id=clinic_id, actor=actor,
                  payload={"reason": reason, "before": before})
    if action in ("stop_assistant", "pause_booking"):
        _open_alert(conn, f"killswitch_{action}", "critical", f"Kill switch: {action.replace('_', ' ')} ({reason})", clinic_id)
    if action == "resume_booking":
        _resolve(conn, "killswitch_pause_booking", clinic_id)
    if staff_id:
        events.audit(conn, staff_id, f"killswitch_{action}", detail={"clinic": clinic_id, "reason": reason})
    return {"ok": True, "action": action, "before": before}


# ---------------------------------------------------------------- go-live gates
def g2_checks(conn: Connection) -> list[dict]:
    s = get_settings()
    from .evaluation.runner import run_all
    eval_ok = all(run_all()["metrics"]["g1"].values())
    drill = conn.execute("SELECT max(occurred_at) AS t FROM event WHERE type = 'killswitch.drill'").fetchone()["t"]
    att = {r["item"]: r for r in conn.execute(
        "SELECT a.item, a.attested_at, a.note, st.display_name FROM golive_attestation a JOIN staff st ON st.id = a.attested_by")}
    checks = [
        {"id": "voice_enabled", "label": "Voice agent enabled", "ok": s.voice_agent_enabled},
        {"id": "telephony_real", "label": "Real telephony provider configured", "ok": s.telephony_provider != "sim"},
        {"id": "whatsapp_real", "label": "Real WhatsApp provider configured", "ok": s.whatsapp_provider != "sim"},
        {"id": "webhook_secrets", "label": "Webhook secrets set (telephony, WhatsApp)",
         "ok": bool(s.telephony_webhook_secret and (s.whatsapp_provider == "sim" or s.whatsapp_app_secret))},
        {"id": "alerts_delivered", "label": "Alerts delivered outside the app (ALERT_WEBHOOK_URL)", "ok": bool(s.alert_webhook_url)},
        {"id": "eval_g1", "label": "Evaluation set passes all G1 behaviour checks", "ok": eval_ok},
        {"id": "kill_switch_drill", "label": "Kill switch drilled in the last 14 days",
         "ok": bool(drill and drill > datetime.now(timezone.utc) - timedelta(days=14))},
    ]
    for item, label in ATTESTATIONS.items():
        a = att.get(item)
        checks.append({"id": item, "label": label, "ok": a is not None, "attestation": True,
                       "by": a["display_name"] if a else None, "at": a["attested_at"].isoformat() if a else None,
                       "note": a["note"] if a else None})
    return checks


def g3_checks(conn: Connection, clinic_id: str) -> list[dict]:
    c = conn.execute("SELECT live_since FROM experiment_config WHERE clinic_id = %s", (clinic_id,)).fetchone()
    since = c["live_since"] if c else None
    ok_days = bool(since and since < datetime.now(timezone.utc) - timedelta(days=3))
    if since is None:
        return [{"id": "live_3_days", "label": "At least 3 live days at 20%", "ok": False}]
    ho = conn.execute("""SELECT h.urgency, h.sla_due_at, h.claimed_at, h.resolved_at FROM handover h JOIN lead l ON l.id = h.lead_id
                         WHERE l.clinic_id = %s AND h.created_at >= %s""", (clinic_id, since)).fetchall()
    now = datetime.now(timezone.utc)
    decided = [h for h in ho if h["claimed_at"] or h["resolved_at"] or h["sla_due_at"] < now]
    hit = sum((h["claimed_at"] or h["resolved_at"] or now) <= h["sla_due_at"] for h in decided) / len(decided) if decided else 1.0
    missed = sum(h["urgency"] == "urgent" and (h["claimed_at"] or h["resolved_at"] or now) > h["sla_due_at"] for h in ho)
    rev = conn.execute("SELECT count(*) FILTER (WHERE review_status = 'cancelled') AS c, count(*) FILTER (WHERE reviewed_at IS NOT NULL) AS n "
                       "FROM booking WHERE created_by = 'assistant' AND clinic_id = %s AND created_at >= %s", (clinic_id, since)).fetchone()
    rejection = rev["c"] / rev["n"] if rev["n"] else 0.0
    contamination = conn.execute(
        """SELECT count(*) AS n FROM call_attempt a JOIN lead l ON l.id = a.lead_id WHERE a.made_by = 'staff' AND l.arm = 'assistant'
           AND l.clinic_id = %s AND a.occurred_at >= %s
           AND NOT EXISTS (SELECT 1 FROM handover h WHERE h.lead_id = l.id AND h.created_at <= a.occurred_at)""",
        (clinic_id, since)).fetchone()["n"]
    return [
        {"id": "live_3_days", "label": "At least 3 live days at 20%", "ok": ok_days},
        {"id": "no_missed_urgent", "label": "No missed urgent handover", "ok": missed == 0, "value": missed},
        {"id": "sla_80", "label": "Handover SLA hit rate >= 80%", "ok": hit >= 0.8, "value": round(hit, 3)},
        {"id": "rejection_5", "label": "Booking review rejection <= 5%", "ok": rejection <= 0.05, "value": round(rejection, 3)},
        {"id": "no_contamination", "label": "No staff calls to assistant-group leads before handover", "ok": contamination == 0,
         "value": contamination},
    ]


def check_share_change(conn: Connection, clinic_id: str, new_share: Decimal) -> None:
    """Gate enforcement for experiment.set_share (staging/production only; reported in dev)."""
    if not get_settings().is_production_like or new_share <= 0:
        return
    failing = [c["label"] for c in g2_checks(conn) if not c["ok"]]
    if failing:
        raise PermissionError("Gate G2 not passed: " + "; ".join(failing))
    if new_share > Decimal("0.2"):
        failing = [c["label"] for c in g3_checks(conn, clinic_id) if not c["ok"]]
        if failing:
            raise PermissionError("Gate G3 not passed for ramp above 20%: " + "; ".join(failing))


def attest(conn: Connection, item: str, staff_id, note: str | None) -> None:
    if item not in ATTESTATIONS:
        raise ValueError("unknown go-live item")
    conn.execute("INSERT INTO golive_attestation (item, attested_by, note) VALUES (%s, %s, %s) ON CONFLICT (item) DO UPDATE "
                 "SET attested_by = EXCLUDED.attested_by, note = EXCLUDED.note, attested_at = now()", (item, staff_id, (note or "")[:300]))
    events.audit(conn, staff_id, "golive_attested", detail={"item": item})


def open_alerts(conn: Connection, clinics: list[str]) -> list[dict]:
    return [{"id": r["id"], "key": r["key"], "severity": r["severity"], "clinic_id": r["clinic_id"], "message": r["message"],
             "opened_at": r["opened_at"].isoformat()} for r in conn.execute(
        "SELECT * FROM alert WHERE resolved_at IS NULL AND (clinic_id IS NULL OR clinic_id = ANY(%s)) "
        "ORDER BY severity, opened_at DESC", (clinics,))]
