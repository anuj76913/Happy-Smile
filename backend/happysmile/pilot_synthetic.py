"""SYNTHETIC pilot data for demonstrating the readout (development only).

Generates about three weeks of pilot-clinic leads: one week at a 20% assistant share,
then 50%, with known built-in effects, so the readout can be shown and checked:
  - standard callback: reached hours later, ~29% book within 7 days, ~72% attend
  - assistant: reached in minutes, ~37% book (incl. staff bookings after handover), ~70% attend
Leads are named "Synthetic NNNN". Refuses to run outside APP_ENV=dev.

Usage:  python -m happysmile.pilot_synthetic [--days 21] [--per-clinic-day 25] [--seed 5]
"""

from __future__ import annotations

import argparse
import math
import random
import secrets
from datetime import date, datetime, time, timedelta, timezone

from psycopg.types.json import Jsonb

from .config import IST, get_settings
from .db import close_pool, tx

REASONS = [("asked_person", 0.28), ("price_emi", 0.24), ("clinical", 0.14), ("pain_swelling", 0.08),
           ("couldnt_understand", 0.12), ("no_suitable_slot", 0.08), ("needs_staff", 0.06)]


def _pick(rng, pairs):
    x, acc = rng.random(), 0.0
    for v, p in pairs:
        acc += p
        if x < acc:
            return v
    return pairs[-1][0]


def _staff_time(t: datetime, rng) -> datetime:
    local = t.astimezone(IST)
    if local.hour < 9:
        local = local.replace(hour=9, minute=rng.randint(0, 50))
    elif local.hour >= 20:
        local = (local + timedelta(days=1)).replace(hour=9, minute=rng.randint(0, 50))
    return local


def generate(days: int = 21, per_clinic_day: int = 25, seed: int = 5, now: datetime | None = None) -> dict:
    rng = random.Random(seed)
    now = now or datetime.now(timezone.utc)
    today = now.astimezone(IST).date()
    start = today - timedelta(days=days - 1)
    counts = {"leads": 0, "assistant": 0, "control": 0, "bookings": 0, "handovers": 0}
    with tx() as conn:
        clinics = [r["id"] for r in conn.execute("SELECT id FROM clinic WHERE is_pilot ORDER BY id")]
        dentists = {c: [r["id"] for r in conn.execute("SELECT id FROM dentist WHERE clinic_id = %s", (c,))] for c in clinics}
        staff = conn.execute("SELECT id FROM staff WHERE role = 'front_desk' LIMIT 1").fetchone()["id"]
        n = 0
        for d in range(days):
            day = start + timedelta(days=d)
            share = 0.2 if d < 7 else 0.5
            version = "r4.0" if d < 10 else "r5.0"
            for cid in clinics:
                for _ in range(max(0, int(rng.gauss(per_clinic_day, 3)))):
                    n += 1
                    hour = rng.choices(range(8, 23), [1, 2, 3, 3, 3, 3, 2, 2, 3, 4, 5, 5, 4, 2, 1])[0]
                    created = datetime.combine(day, time(hour, rng.randint(0, 59), rng.randint(0, 59)), tzinfo=IST)
                    if created > now:
                        continue
                    arm = "assistant" if rng.random() < share else "control"
                    lang = "hi" if rng.random() < 0.42 else "en"
                    treatment = rng.choices(["braces", "whitening", "implants", "other"], [0.38, 0.27, 0.2, 0.15])[0]
                    lead = conn.execute(
                        "INSERT INTO lead (public_ref, name, phone_e164, treatment, clinic_id, language, contact_pref, arm, "
                        "arm_assigned_at, status, created_at) VALUES (%s, %s, %s, %s, %s, %s, 'now', %s, %s, 'new', %s) RETURNING id",
                        ("SY-" + secrets.token_hex(4).upper(), f"Synthetic {n:04d}", f"+919{rng.randint(100000000, 999999999)}",
                         treatment, cid, lang, arm, created, created)).fetchone()["id"]
                    conn.execute("INSERT INTO consent (lead_id, disclosure_version, call_consent, whatsapp_consent, language, created_at) "
                                 "VALUES (%s, %s, true, true, %s, %s)", (lead, ("mixed-" if arm == "assistant" else "team-") + lang + "-v1", lang, created))
                    counts["leads"] += 1
                    counts[arm] += 1
                    status, reached, booking_by, ho = "awaiting_call", None, None, None
                    if arm == "control":
                        if rng.random() < 0.76:
                            reached = _staff_time(created + timedelta(minutes=rng.lognormvariate(math.log(270), 0.6)), rng)
                            if rng.random() < 0.38:
                                booking_by, status = "staff", "booked"
                            else:
                                status = rng.choice(["follow_up", "not_interested", "not_interested"])
                        else:
                            status = "no_answer"
                    else:
                        in_window = 9 <= created.astimezone(IST).hour < 21
                        answered = rng.random() < 0.8
                        call_at = created + timedelta(seconds=rng.randint(30, 75)) if in_window else _staff_time(created, rng)
                        attempt = conn.execute(
                            "INSERT INTO call_attempt (lead_id, attempt_no, made_by, provider, state, outcome, started_at, ended_at, occurred_at) "
                            "VALUES (%s, 1, 'assistant', 'sim', 'completed', %s, %s, %s, %s) RETURNING id",
                            (lead, "answered" if answered else "no_answer", call_at, call_at + timedelta(seconds=rng.randint(60, 240)),
                             call_at)).fetchone()["id"]
                        if answered:
                            reached = call_at + timedelta(seconds=10)
                            x = rng.random()
                            outcome = "booked" if x < 0.33 else "handover" if x < 0.68 else "not_interested" if x < 0.86 else "callback"
                            reason = _pick(rng, REASONS) if outcome == "handover" else None
                            if lang == "hi" and outcome == "handover" and rng.random() < 0.1:
                                reason = "couldnt_understand"
                            conn.execute("INSERT INTO conversation (call_attempt_id, session, transcript, outcome, prompt_version, summary) "
                                         "VALUES (%s, %s, '[]', %s, %s, %s)",
                                         (attempt, Jsonb({"handover": {"reason": reason}} if reason else {}), outcome, version,
                                          ["Synthetic call.", f"Outcome: {outcome}.", "No transcript."]))
                            if outcome == "booked":
                                booking_by, status = "assistant", "booked"
                            elif outcome == "handover":
                                ho = reason
                                status = "needs_you"
                                if rng.random() < 0.42:
                                    booking_by, status = "staff", "booked"
                            elif outcome == "not_interested":
                                status = "not_interested"
                            else:
                                status = "queued"
                        else:
                            status = "whatsapp_sent" if rng.random() < 0.5 else "unreachable"
                    if ho:
                        urgency = "urgent" if ho == "pain_swelling" else "normal"
                        sla = 5 if urgency == "urgent" else 15
                        handed = reached + timedelta(minutes=2)
                        claim_after = rng.uniform(1, sla * (1.6 if rng.random() < 0.12 else 0.9))
                        claimed = handed + timedelta(minutes=claim_after)
                        h = conn.execute(
                            "INSERT INTO handover (lead_id, reason_tags, urgency, sla_due_at, created_at, claimed_by, claimed_at, resolved_at, resolution) "
                            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id",
                            (lead, [ho], urgency, handed + timedelta(minutes=sla), handed, staff, claimed,
                             claimed + timedelta(minutes=5) if claimed < now else None, "synthetic")).fetchone()["id"]
                        counts["handovers"] += 1
                        if rng.random() < 0.6:
                            ok = rng.random() > 0.15
                            conn.execute("INSERT INTO handover_feedback (handover_id, staff_id, is_correct, reason, created_at) "
                                         "VALUES (%s, %s, %s, %s, %s)",
                                         (h, staff, ok, None if ok else rng.choice(["Assistant could have handled this", "Wrong reason tag"]),
                                          claimed))
                    if booking_by:
                        made = (reached or created) + timedelta(minutes=rng.randint(1, 30))
                        start_at = datetime.combine((made + timedelta(days=rng.randint(1, 5))).astimezone(IST).date(),
                                                    time(rng.choice([10, 11, 12, 16, 17, 18, 19]), rng.choice([0, 30])), tzinfo=IST) \
                            + timedelta(microseconds=rng.randint(1, 999999))
                        dentist = rng.choice(dentists[cid])
                        slot = conn.execute("INSERT INTO slot (clinic_id, dentist_id, start_at, duration_min, status) VALUES (%s, %s, %s, 30, 'booked') "
                                            "RETURNING id", (cid, dentist, start_at)).fetchone()["id"]
                        cancelled = booking_by == "assistant" and rng.random() < 0.03
                        attended = None
                        if start_at < now and not cancelled and rng.random() < 0.9:
                            attended = rng.random() < (0.70 if arm == "assistant" else 0.72)
                        conn.execute(
                            "INSERT INTO booking (lead_id, slot_id, clinic_id, dentist_id, start_at, created_by, review_status, status, "
                            "attended, created_at, reviewed_at) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                            (lead, slot, cid, dentist, start_at, booking_by,
                             ("cancelled" if cancelled else "approved"), "cancelled" if cancelled else "active", attended, made,
                             made + timedelta(hours=2) if booking_by == "assistant" else None))
                        counts["bookings"] += 1
                    if rng.random() < (0.012 if arm == "assistant" else 0.008):
                        conn.execute("INSERT INTO suppression (phone_e164, reason, lead_id) SELECT phone_e164, 'stop_calling', id FROM lead "
                                     "WHERE id = %s ON CONFLICT DO NOTHING", (lead,))
                    conn.execute("UPDATE lead SET status = %s, first_reached_at = %s WHERE id = %s",
                                 (status, reached, lead))
        for cid in clinics:
            conn.execute("UPDATE experiment_config SET live_since = %s WHERE clinic_id = %s",
                         (datetime.combine(start, time(9), tzinfo=IST), cid))
    return {"from": start.isoformat(), "to": today.isoformat(), **counts}


if __name__ == "__main__":
    if get_settings().env != "dev":
        raise SystemExit("pilot_synthetic is for development only.")
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=21)
    ap.add_argument("--per-clinic-day", type=int, default=25)
    ap.add_argument("--seed", type=int, default=5)
    a = ap.parse_args()
    print(generate(a.days, a.per_clinic_day, a.seed))
    close_pool()
