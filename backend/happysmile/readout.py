"""Pilot readout and gate G4 recommendation (plan P5-05; implementation-plan §9.2-9.3; architecture §10).

Analysis is intention-to-treat by the arm assigned at intake (assistant vs control);
'not_in_pilot' leads are excluded. Primary outcome: a consultation booked within 7 days
of the enquiry and not cancelled at review, counted only for leads whose 7 days have
passed ("matured"). Differences between arms come with 95% confidence intervals
(Newcombe hybrid score method). The recommendation follows the §9.3 table; a person
records the actual G4 decision.

CLI:  python -m happysmile.readout --from 2026-12-14 --to 2026-12-21 [--out readout.md]
"""

from __future__ import annotations

import argparse
import math
import os
from collections import Counter, defaultdict
from datetime import date, datetime, time, timedelta, timezone

from psycopg import Connection

from .config import IST
from .handovers import TAGS

Z = 1.959964
ARMS = ("assistant", "control")
DECISIONS = {
    "scale": "Scale: add clinics in waves (Phase 6)",
    "extend": "Extend: run 2-4 more weeks at 50/50 for statistical power; fix the weakest handover reasons",
    "fix_first": "Fix first: staffing or agent quality before adding clinics",
    "stop_or_redesign": "Stop or redesign: assistant share back to 0%; review the approach",
}


# ---------------------------------------------------------------- statistics
def wilson(k: int, n: int) -> tuple[float, float]:
    if n == 0:
        return (float("nan"), float("nan"))
    p = k / n
    d = 1 + Z * Z / n
    c = (p + Z * Z / (2 * n)) / d
    h = Z * math.sqrt(p * (1 - p) / n + Z * Z / (4 * n * n)) / d
    return (max(0.0, c - h), min(1.0, c + h))


def diff_ci(k1: int, n1: int, k2: int, n2: int) -> dict:
    """Difference p1 - p2 with the Newcombe (method 10) 95% interval."""
    if not n1 or not n2:
        return {"diff": None, "lo": None, "hi": None}
    p1, p2 = k1 / n1, k2 / n2
    l1, u1 = wilson(k1, n1)
    l2, u2 = wilson(k2, n2)
    d = p1 - p2
    lo = d - math.sqrt((p1 - l1) ** 2 + (u2 - p2) ** 2)
    hi = d + math.sqrt((u1 - p1) ** 2 + (p2 - l2) ** 2)
    return {"diff": d, "lo": lo, "hi": hi}


def n_per_arm(p_control: float, lift: float = 0.10, power_z: float = 0.8416) -> int:
    """Leads per arm needed to detect an absolute lift at 80% power, alpha 0.05 two-sided."""
    p1, p2 = p_control, min(0.99, p_control + lift)
    pbar = (p1 + p2) / 2
    num = (Z * math.sqrt(2 * pbar * (1 - pbar)) + power_z * math.sqrt(p1 * (1 - p1) + p2 * (1 - p2))) ** 2
    return math.ceil(num / (lift ** 2))


def pctl(values: list[float], q: float) -> float | None:
    if not values:
        return None
    s = sorted(values)
    i = (len(s) - 1) * q
    lo, hi = math.floor(i), math.ceil(i)
    return s[lo] + (s[hi] - s[lo]) * (i - lo)


# ---------------------------------------------------------------- data
def _bounds(start: date, end: date) -> tuple[datetime, datetime]:
    return datetime.combine(start, time(0), tzinfo=IST), datetime.combine(end, time(0), tzinfo=IST) + timedelta(days=1)


def compute(conn: Connection, start: date, end: date, clinics: list[str], now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    t0, t1 = _bounds(start, end)
    leads = conn.execute(
        """SELECT l.id, l.arm, l.clinic_id, l.treatment, l.language, l.created_at, l.first_reached_at,
                  EXISTS (SELECT 1 FROM booking b WHERE b.lead_id = l.id AND b.review_status <> 'cancelled'
                          AND b.created_at <= l.created_at + interval '7 days') AS booked7,
                  EXISTS (SELECT 1 FROM suppression s WHERE s.lead_id = l.id) AS opted_out
           FROM lead l WHERE l.arm IN ('assistant', 'control') AND l.clinic_id = ANY(%s)
             AND l.created_at >= %s AND l.created_at < %s""", (clinics, t0, t1)).fetchall()
    matured = [l for l in leads if l["created_at"] + timedelta(days=7) <= now]

    def by_arm(rows, pred):
        out = {}
        for arm in ARMS:
            g = [r for r in rows if r["arm"] == arm]
            k = sum(1 for r in g if pred(r))
            out[arm] = {"n": len(g), "k": k, "rate": k / len(g) if g else None, "ci": wilson(k, len(g)) if g else None}
        return out

    primary = by_arm(matured, lambda r: r["booked7"])
    primary["diff"] = diff_ci(primary["assistant"]["k"], primary["assistant"]["n"], primary["control"]["k"], primary["control"]["n"])
    all_booked = by_arm(leads, lambda r: r["booked7"])

    # Attendance (bookings whose appointment time has passed)
    att_rows = conn.execute(
        """SELECT l.arm, b.attended FROM booking b JOIN lead l ON l.id = b.lead_id
           WHERE l.arm IN ('assistant', 'control') AND l.clinic_id = ANY(%s) AND l.created_at >= %s AND l.created_at < %s
             AND b.review_status <> 'cancelled' AND b.start_at < %s""", (clinics, t0, t1, now)).fetchall()
    attendance = {}
    for arm in ARMS:
        g = [r for r in att_rows if r["arm"] == arm]
        known = [r for r in g if r["attended"] is not None]
        k = sum(1 for r in known if r["attended"])
        attendance[arm] = {"appointments": len(g), "recorded": len(known), "attended": k,
                           "rate": k / len(known) if known else None}
    attendance["diff"] = diff_ci(attendance["assistant"]["attended"], attendance["assistant"]["recorded"],
                                 attendance["control"]["attended"], attendance["control"]["recorded"])

    # Speed of first contact
    speed = {}
    for arm in ARMS:
        g = [l for l in leads if l["arm"] == arm]
        mins = [(l["first_reached_at"] - l["created_at"]).total_seconds() / 60 for l in g if l["first_reached_at"]]
        speed[arm] = {"leads": len(g), "reached": len(mins), "reach_rate": len(mins) / len(g) if g else None,
                      "p50_min": pctl(mins, 0.5), "p90_min": pctl(mins, 0.9),
                      "within_5_min": sum(m <= 5 for m in mins) / len(g) if g else None}

    # Handovers, safety and trust (assistant arm)
    ho = conn.execute(
        """SELECT h.reason_tags, h.urgency, h.sla_due_at, h.claimed_at, h.resolved_at, l.language
           FROM handover h JOIN lead l ON l.id = h.lead_id
           WHERE l.arm = 'assistant' AND l.clinic_id = ANY(%s) AND l.created_at >= %s AND l.created_at < %s""",
        (clinics, t0, t1)).fetchall()
    decided = [h for h in ho if h["claimed_at"] or h["resolved_at"] or h["sla_due_at"] < now]
    on_time = [h for h in decided if (h["claimed_at"] or h["resolved_at"] or now) <= h["sla_due_at"]]
    urgent = [h for h in ho if h["urgency"] == "urgent"]
    urgent_missed = [h for h in urgent if (h["claimed_at"] or h["resolved_at"] or now) > h["sla_due_at"]]
    mix = Counter(t for h in ho for t in h["reason_tags"])
    rev = conn.execute(
        """SELECT b.review_status FROM booking b JOIN lead l ON l.id = b.lead_id WHERE b.created_by = 'assistant'
           AND l.clinic_id = ANY(%s) AND l.created_at >= %s AND l.created_at < %s AND b.reviewed_at IS NOT NULL""",
        (clinics, t0, t1)).fetchall()
    fb = conn.execute(
        """SELECT f.is_correct FROM handover_feedback f JOIN handover h ON h.id = f.handover_id JOIN lead l ON l.id = h.lead_id
           WHERE l.clinic_id = ANY(%s) AND l.created_at >= %s AND l.created_at < %s""", (clinics, t0, t1)).fetchall()
    calls = conn.execute(
        """SELECT l.language, c.outcome, c.session->'handover'->>'reason' AS reason, a.started_at, a.ended_at, c.prompt_version
           FROM conversation c JOIN call_attempt a ON a.id = c.call_attempt_id JOIN lead l ON l.id = a.lead_id
           WHERE l.clinic_id = ANY(%s) AND l.created_at >= %s AND l.created_at < %s""", (clinics, t0, t1)).fetchall()
    by_lang = defaultdict(lambda: [0, 0])
    for c in calls:
        by_lang[c["language"]][0] += 1
        by_lang[c["language"]][1] += c["reason"] == "couldnt_understand"
    by_version = defaultdict(lambda: Counter())
    for c in calls:
        by_version[c["prompt_version"] or "unknown"][c["outcome"] or "none"] += 1
    safety = {
        "handovers": len(ho), "sla_decided": len(decided), "sla_on_time": len(on_time),
        "sla_hit_rate": len(on_time) / len(decided) if decided else None,
        "urgent": len(urgent), "urgent_missed": len(urgent_missed),
        "reviewed_bookings": len(rev), "review_cancelled": sum(r["review_status"] == "cancelled" for r in rev),
        "review_rejection_rate": (sum(r["review_status"] == "cancelled" for r in rev) / len(rev)) if rev else None,
        "feedback": len(fb), "thumbs_down": sum(not f["is_correct"] for f in fb),
        "thumbs_down_rate": (sum(not f["is_correct"] for f in fb) / len(fb)) if fb else None,
        "opt_out": by_arm(leads, lambda r: r["opted_out"]),
        "auto_stops": conn.execute("SELECT count(*) AS n FROM event WHERE type = 'killswitch.stop_assistant' AND actor = 'system' "
                                   "AND occurred_at >= %s AND occurred_at < %s", (t0, t1)).fetchone()["n"],
    }
    weak = {"handover_mix": dict(mix.most_common()),
            "couldnt_understand_by_language": {lang: {"calls": v[0], "rate": v[1] / v[0] if v[0] else None} for lang, v in by_lang.items()},
            "outcomes_by_rules_version": {k: dict(v) for k, v in by_version.items()}}

    # Cost (only if unit prices are configured; INR)
    minutes = sum(((c["ended_at"] or c["started_at"]) - c["started_at"]).total_seconds() / 60 for c in calls if c["started_at"])
    tokens = conn.execute("SELECT coalesce(sum(coalesce(prompt_tokens, 0) + coalesce(output_tokens, 0)), 0) AS t FROM llm_call "
                          "WHERE at >= %s AND at < %s", (t0, t1)).fetchone()["t"]
    prices = {k: float(os.environ[k]) for k in ("COST_TELEPHONY_INR_PER_MIN", "COST_SPEECH_INR_PER_MIN", "COST_LLM_INR_PER_1K_TOKENS")
              if os.environ.get(k)}
    a_leads = speed["assistant"]["leads"]
    cost = {"call_minutes": round(minutes, 1), "llm_tokens": int(tokens), "prices_configured": len(prices) == 3}
    if len(prices) == 3:
        total = minutes * (prices["COST_TELEPHONY_INR_PER_MIN"] + prices["COST_SPEECH_INR_PER_MIN"]) + tokens / 1000 * prices["COST_LLM_INR_PER_1K_TOKENS"]
        cost.update(total_inr=round(total, 2), per_assistant_lead_inr=round(total / a_leads, 2) if a_leads else None,
                    per_assistant_booking_inr=round(total / primary["assistant"]["k"], 2) if primary["assistant"]["k"] else None)

    # Segments (matured leads)
    def seg(key):
        groups = defaultdict(list)
        for l in matured:
            groups[key(l)].append(l)
        out = {}
        for g, rows in sorted(groups.items()):
            b = by_arm(rows, lambda r: r["booked7"])
            out[g] = {"assistant": [b["assistant"]["k"], b["assistant"]["n"]], "control": [b["control"]["k"], b["control"]["n"]],
                      "diff": diff_ci(b["assistant"]["k"], b["assistant"]["n"], b["control"]["k"], b["control"]["n"])["diff"]}
        return out

    def band(l):
        h = l["created_at"].astimezone(IST).hour
        for lo, hi, name in ((9, 12, "09-12"), (12, 15, "12-15"), (15, 18, "15-18"), (18, 21, "18-21")):
            if lo <= h < hi:
                return name
        return "out of hours"

    segments = {"clinic": seg(lambda l: l["clinic_id"]), "treatment": seg(lambda l: l["treatment"]),
                "language": seg(lambda l: l["language"]), "hour": seg(band)}
    cr = primary["control"]["rate"]
    power = {"needed_per_arm_for_10pt_lift": n_per_arm(cr) if cr not in (None, 0) else None,
             "have_per_arm": min(primary["assistant"]["n"], primary["control"]["n"])}
    out = {"period": {"from": start.isoformat(), "to": end.isoformat(), "clinics": clinics, "generated_at": now.isoformat()},
           "leads": {"total": len(leads), "matured": len(matured)}, "primary": primary, "all_leads_booked": all_booked,
           "attendance": attendance, "speed": speed, "safety": safety, "weak_spots": weak, "cost": cost,
           "segments": segments, "power": power}
    out["recommendation"] = decide(out)
    return out


# ---------------------------------------------------------------- G4 recommendation (§9.3)
def decide(r: dict) -> dict:
    p, a, s = r["primary"]["diff"], r["attendance"]["diff"], r["safety"]
    reasons = []
    lift_sig = p["lo"] is not None and p["lo"] > 0
    lift_appears = p["diff"] is not None and p["diff"] > 0
    att_drop = a["hi"] is not None and a["hi"] < 0
    att_worse = a["lo"] is not None and a["diff"] is not None and a["diff"] < -0.05
    safety_incident = s["urgent_missed"] > 0 or s["auto_stops"] > 0
    sla_ok = s["sla_hit_rate"] is None or s["sla_hit_rate"] >= 0.8
    rev_ok = s["review_rejection_rate"] is None or s["review_rejection_rate"] <= 0.05
    oo = s["opt_out"]
    optout_ok = not (oo["assistant"]["rate"] and oo["control"]["rate"] is not None and oo["assistant"]["rate"] > oo["control"]["rate"] + 0.02)
    guardrails = sla_ok and rev_ok and optout_ok and not safety_incident

    if safety_incident:
        reasons.append(f"Safety: {s['urgent_missed']} urgent handover(s) missed, {s['auto_stops']} automatic stop(s).")
    if att_drop:
        reasons.append("Attendance is significantly lower in the assistant group.")
    if not sla_ok:
        reasons.append(f"Handover SLA hit rate {s['sla_hit_rate']:.0%} is below 80%.")
    if not rev_ok:
        reasons.append(f"Booking review rejection {s['review_rejection_rate']:.0%} is above 5%.")
    if not optout_ok:
        reasons.append("Opt-outs are more than 2 points higher in the assistant group.")
    if p["diff"] is not None:
        reasons.append(f"Booking-rate difference {p['diff']:+.1%} (95% CI {p['lo']:+.1%} to {p['hi']:+.1%}).")
    if r["power"]["needed_per_arm_for_10pt_lift"] and r["power"]["have_per_arm"] < r["power"]["needed_per_arm_for_10pt_lift"]:
        reasons.append(f"Underpowered: {r['power']['have_per_arm']} matured leads per arm; about "
                       f"{r['power']['needed_per_arm_for_10pt_lift']} needed to detect a 10-point lift.")

    if safety_incident or att_drop:
        d = "stop_or_redesign"
    elif lift_sig and guardrails and not att_worse:
        d = "scale"
    elif lift_appears and not (sla_ok and rev_ok):
        d = "fix_first"
    elif guardrails:
        d = "extend"
    else:
        d = "fix_first"
    return {"decision": d, "label": DECISIONS[d], "reasons": reasons}


# ---------------------------------------------------------------- markdown
def _pct(x):
    return "–" if x is None else f"{x:.1%}"


def _ci(ci):
    return "" if not ci or ci[0] != ci[0] else f" ({ci[0]:.0%}–{ci[1]:.0%})"


def _diff(d: dict) -> str:
    if d.get("diff") is None:
        return "–"
    return "{:+.1%} (95% CI {:+.1%} to {:+.1%})".format(d["diff"], d["lo"], d["hi"])


def _signed(x) -> str:
    return "–" if x is None else "{:+.1%}".format(x)


def render_markdown(r: dict, synthetic: bool = False) -> str:
    p, a, sp, s, w = r["primary"], r["attendance"], r["speed"], r["safety"], r["weak_spots"]
    rec = r["recommendation"]
    L = [f"# Pilot readout: {r['period']['from']} to {r['period']['to']}", ""]
    if synthetic:
        L += ["> **SYNTHETIC DATA.** Generated by `happysmile.pilot_synthetic` to demonstrate the readout. Not real results.", ""]
    L += [f"Clinics: {', '.join(r['period']['clinics'])} · leads: {r['leads']['total']} ({r['leads']['matured']} with a full 7-day window) · "
          "intention-to-treat by assigned arm.", "",
          f"## Recommendation (gate G4): {rec['label']}", ""] + [f"- {x}" for x in rec["reasons"]] + [
          "", "A person records the final decision in the console (Ops → Readout).", "",
          "## Did the assistant raise bookings?", "",
          "| | Assistant | Standard callback | Difference |", "|---|---|---|---|",
          f"| Booked within 7 days (matured leads) | {p['assistant']['k']}/{p['assistant']['n']} = {_pct(p['assistant']['rate'])}{_ci(p['assistant']['ci'])} "
          f"| {p['control']['k']}/{p['control']['n']} = {_pct(p['control']['rate'])}{_ci(p['control']['ci'])} "
          f"| {_diff(p['diff'])} |",
          "", "## Are the bookings real?", "", "| | Assistant | Standard callback | Difference |", "|---|---|---|---|",
          f"| Attended (recorded / past appointments) | {a['assistant']['attended']}/{a['assistant']['recorded']} = {_pct(a['assistant']['rate'])} "
          f"(of {a['assistant']['appointments']}) | {a['control']['attended']}/{a['control']['recorded']} = {_pct(a['control']['rate'])} "
          f"(of {a['control']['appointments']}) | {_diff(a['diff'])} |",
          "", "## Did speed actually change?", "", "| | Assistant | Standard callback |", "|---|---|---|",
          f"| Reached at all | {_pct(sp['assistant']['reach_rate'])} | {_pct(sp['control']['reach_rate'])} |",
          f"| Reached within 5 minutes | {_pct(sp['assistant']['within_5_min'])} | {_pct(sp['control']['within_5_min'])} |",
          "| Time to first contact p50 / p90 | " + " | ".join(
              "–" if sp[x]["p50_min"] is None else f"{sp[x]['p50_min']:.0f} / {sp[x]['p90_min']:.0f} min" for x in ARMS) + " |",
          "", "## Can staff keep up? Is it safe and trusted?", "",
          f"- Handover SLA hit rate: **{_pct(s['sla_hit_rate'])}** ({s['sla_on_time']}/{s['sla_decided']}); target ≥ 80%",
          f"- Urgent handovers: {s['urgent']}, missed: **{s['urgent_missed']}**; automatic stops: {s['auto_stops']}",
          f"- Booking review rejections: **{_pct(s['review_rejection_rate'])}** ({s['review_cancelled']}/{s['reviewed_bookings']}); target ≤ 5%",
          f"- Opt-outs: assistant {_pct(s['opt_out']['assistant']['rate'])}, standard {_pct(s['opt_out']['control']['rate'])}",
          f"- Handover thumbs-down: {_pct(s['thumbs_down_rate'])} ({s['thumbs_down']}/{s['feedback']})",
          "", "## Where is the agent weak?", "", "| Handover reason | Count |", "|---|---|"]
    L += [f"| {TAGS.get(k, k)} | {v} |" for k, v in w["handover_mix"].items()] or ["| – | 0 |"]
    L += ["", "| Language | Assistant calls | Couldn't understand |", "|---|---|---|"]
    L += [f"| {lang} | {v['calls']} | {_pct(v['rate'])} |" for lang, v in w["couldnt_understand_by_language"].items()]
    L += ["", "Outcomes by rules version: " + "; ".join(f"`{k}` {dict(v)}" for k, v in w["outcomes_by_rules_version"].items()), "",
          "## What does it cost?", "",
          f"- Assistant call minutes: {r['cost']['call_minutes']} · LLM tokens: {r['cost']['llm_tokens']}"]
    if r["cost"].get("prices_configured"):
        L.append(f"- Total ₹{r['cost']['total_inr']} · per assistant lead ₹{r['cost']['per_assistant_lead_inr']} · "
                 f"per assistant booking ₹{r['cost']['per_assistant_booking_inr']}")
    else:
        L.append("- Unit prices not configured (COST_TELEPHONY_INR_PER_MIN, COST_SPEECH_INR_PER_MIN, COST_LLM_INR_PER_1K_TOKENS).")
    L += ["", "## Segments (booked within 7 days: assistant vs standard)", ""]
    for name, rows in r["segments"].items():
        L += [f"**By {name}**", "", "| Segment | Assistant | Standard | Difference |", "|---|---|---|---|"]
        L += [f"| {g} | {v['assistant'][0]}/{v['assistant'][1]} | {v['control'][0]}/{v['control'][1]} | {_signed(v['diff'])} |"
              for g, v in rows.items()]
        L.append("")
    L += ["Segments are descriptive; with pilot sample sizes, differences within segments are not reliable on their own.",
          "", "Not measured by design: call duration and \"sounds human\" ratings (architecture §15.1)."]
    return "\n".join(L) + "\n"


if __name__ == "__main__":  # pragma: no cover
    from .db import close_pool, tx
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="start", required=True)
    ap.add_argument("--to", dest="end", required=True)
    ap.add_argument("--out")
    ap.add_argument("--synthetic", action="store_true")
    a = ap.parse_args()
    with tx() as conn:
        clinics = [r["id"] for r in conn.execute("SELECT id FROM clinic WHERE is_pilot ORDER BY id")]
        res = compute(conn, date.fromisoformat(a.start), date.fromisoformat(a.end), clinics)
    text = render_markdown(res, a.synthetic)
    if a.out:
        open(a.out, "w", encoding="utf-8").write(text)
    print(res["recommendation"]["label"])
    for x in res["recommendation"]["reasons"]:
        print(" -", x)
    close_pool()
