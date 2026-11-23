"""P0-01 / P0-04 baseline analysis of historical enquiries.

Answers, from an export of past enquiries (schema in README.md):

  1. What is today's baseline? (volume, booking rate, time to first call)
  2. Does the "3x better within 5 minutes" claim hold, and how much of it is
     selection rather than speed?
       - raw ratio using time to first REACHED (likely how the claim was made)
       - raw ratio using time to first DIAL (removes "eager people answer first")
       - Mantel-Haenszel adjusted ratios, stratified by observable confounders
       - who gets fast calls (is "fast" random? if not, the raw ratio is biased)
  3. P0-04: what share of enquiries arrive outside the calling window, and
     what is the language mix (if the column exists)?
  4. Volume per clinic (input for pilot clinic selection, P0-07, and staffing, P0-08).

Only the standard library is used. Output is a Markdown report.

Usage:
    python baseline_analysis.py --input sample_data/enquiries_synthetic.csv \
        --out reports/baseline_report_synthetic.md --synthetic
"""

from __future__ import annotations

import argparse
import csv
import statistics
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

FAST_MIN = 5.0
WINDOW_START, WINDOW_END = 9, 21  # proposed AI calling window (architecture §4.4)
DELAY_BUCKETS = [(5, "<= 5 min"), (30, "5-30 min"), (120, "30 min-2 h"),
                 (360, "2-6 h"), (float("inf"), "> 6 h")]


@dataclass
class Lead:
    created: datetime
    clinic: str
    treatment: str
    source: str
    language: str
    dial_min: float | None
    reach_min: float | None
    booked: bool
    attended: bool | None


def _parse_dt(s: str) -> datetime | None:
    s = (s or "").strip()
    return datetime.fromisoformat(s) if s else None


def _minutes(a: datetime | None, b: datetime) -> float | None:
    return None if a is None else max(0.0, (a - b).total_seconds() / 60)


def load(path: Path) -> list[Lead]:
    leads: list[Lead] = []
    with path.open(encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            created = _parse_dt(r["created_at"])
            if created is None:
                continue
            att = (r.get("attended") or "").strip()
            leads.append(Lead(
                created=created,
                clinic=r.get("clinic_id", "") or "unknown",
                treatment=r.get("treatment", "") or "unknown",
                source=r.get("source", "") or "unknown",
                language=r.get("language", "") or "",
                dial_min=_minutes(_parse_dt(r.get("first_call_at", "")), created),
                reach_min=_minutes(_parse_dt(r.get("first_reached_at", "")), created),
                booked=str(r.get("booked", "0")).strip() in {"1", "true", "True", "yes"},
                attended=None if att == "" else att in {"1", "true", "True", "yes"},
            ))
    return leads


# ---------- helpers ----------

def pct(x: float) -> str:
    return f"{100 * x:.1f}%"


def rate(group: list[Lead]) -> float:
    return sum(l.booked for l in group) / len(group) if group else float("nan")


def bucket(minutes: float | None) -> str:
    if minutes is None:
        return "never"
    for limit, label in DELAY_BUCKETS:
        if minutes <= limit:
            return label
    return DELAY_BUCKETS[-1][1]


def hour_band(h: int) -> str:
    if h < WINDOW_START or h >= WINDOW_END:
        return "out of window"
    if h < 12:
        return "09-12"
    if h < 15:
        return "12-15"
    if h < 18:
        return "15-18"
    return "18-21"


def raw_ratio(leads: list[Lead], attr: str) -> tuple[float, float, float, int, int]:
    fast = [l for l in leads if getattr(l, attr) is not None and getattr(l, attr) <= FAST_MIN]
    slow = [l for l in leads if getattr(l, attr) is not None and getattr(l, attr) > FAST_MIN]
    rf, rs = rate(fast), rate(slow)
    return rf, rs, (rf / rs if rs else float("nan")), len(fast), len(slow)


def mantel_haenszel_rr(leads: list[Lead], attr: str, key) -> tuple[float, int]:
    """MH risk ratio of booking, fast (<= 5 min) vs slow, across strata defined by key(lead)."""
    strata: dict = defaultdict(lambda: [0, 0, 0, 0])  # a, n1, c, n0
    for l in leads:
        m = getattr(l, attr)
        if m is None:
            continue
        s = strata[key(l)]
        if m <= FAST_MIN:
            s[0] += l.booked
            s[1] += 1
        else:
            s[2] += l.booked
            s[3] += 1
    num = den = 0.0
    used = 0
    for a, n1, c, n0 in strata.values():
        if n1 == 0 or n0 == 0:
            continue
        N = n1 + n0
        num += a * n0 / N
        den += c * n1 / N
        used += 1
    return (num / den if den else float("nan")), used


def table(headers: list[str], rows: list[list]) -> str:
    out = ["| " + " | ".join(headers) + " |", "|" + "---|" * len(headers)]
    out += ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]
    return "\n".join(out)


# ---------- report ----------

def build_report(leads: list[Lead], synthetic: bool, source_name: str) -> str:
    days = (max(l.created for l in leads).date() - min(l.created for l in leads).date()).days + 1
    reached = [l for l in leads if l.reach_min is not None]
    md: list[str] = []

    md.append("# Baseline report — enquiries and time to first call")
    md.append("")
    if synthetic:
        md.append("> **SYNTHETIC DATA.** These numbers come from `generate_sample_data.py`, not from "
                  "HappySmile. They demonstrate the method only. Rerun on the real export before "
                  "drawing any conclusion.")
        md.append("")
    md.append(f"Source: `{source_name}` · {len(leads):,} enquiries over {days} days · "
              f"fast = first contact within {FAST_MIN:.0f} minutes.")
    md.append("")

    # 1. Baseline
    md.append("## 1. Baseline")
    md.append("")
    dial = [l.dial_min for l in leads if l.dial_min is not None]
    reach = [l.reach_min for l in reached]
    attended = [l for l in leads if l.booked and l.attended is not None]
    rows = [
        ["Enquiries per day (mean)", f"{len(leads) / days:.0f}"],
        ["Booking rate", pct(rate(leads))],
        ["Reached at all", pct(len(reached) / len(leads))],
        ["Median time to first dial", f"{statistics.median(dial) / 60:.1f} h" if dial else "n/a"],
        ["Median time to first reached", f"{statistics.median(reach) / 60:.1f} h" if reach else "n/a"],
        ["Dialled within 5 min", pct(sum(m <= FAST_MIN for m in dial) / len(leads)) if dial else "n/a"],
        ["Reached within 5 min", pct(sum(m <= FAST_MIN for m in reach) / len(leads)) if reach else "n/a"],
    ]
    if attended:
        rows.append(["Attendance rate of bookings", pct(sum(l.attended for l in attended) / len(attended))])
    md.append(table(["Metric", "Value"], rows))
    md.append("")

    # 2. Booking by delay bucket
    md.append("## 2. Booking rate by time to first contact")
    md.append("")
    order = [b[1] for b in DELAY_BUCKETS] + ["never"]
    rows = []
    for label in order:
        g_reach = [l for l in leads if bucket(l.reach_min) == label]
        g_dial = [l for l in leads if bucket(l.dial_min) == label]
        rows.append([label,
                     f"{len(g_reach):,}", pct(rate(g_reach)) if g_reach else "–",
                     f"{len(g_dial):,}", pct(rate(g_dial)) if g_dial else "–"])
    md.append(table(["Delay", "Leads (by reached)", "Booked (by reached)",
                     "Leads (by dial)", "Booked (by dial)"], rows))
    md.append("")

    # 3. The 3x claim
    md.append("## 3. Testing the \"3x within 5 minutes\" claim")
    md.append("")
    rf, rs, rr_reach, nf, ns = raw_ratio(leads, "reach_min")
    df, ds, rr_dial, ndf, nds = raw_ratio(leads, "dial_min")
    fast_reached = [l for l in leads if l.reach_min is not None and l.reach_min <= FAST_MIN]
    everyone_else = [l for l in leads if not (l.reach_min is not None and l.reach_min <= FAST_MIN)]
    rr_naive = rate(fast_reached) / rate(everyone_else) if everyone_else else float("nan")
    rows = [
        ["Reached within 5 min vs **all other leads** (incl. never reached)", pct(rate(fast_reached)),
         pct(rate(everyone_else)), f"**{rr_naive:.2f}x**", f"{len(fast_reached):,} / {len(everyone_else):,}"],
        ["Raw, by first **reached** (reached leads only)", pct(rf), pct(rs), f"**{rr_reach:.2f}x**", f"{nf:,} / {ns:,}"],
        ["Raw, by first **dial**", pct(df), pct(ds), f"**{rr_dial:.2f}x**", f"{ndf:,} / {nds:,}"],
    ]
    md.append(table(["Measure", "Booked if fast", "Booked if slow", "Ratio", "Fast / slow leads"], rows))
    md.append("")
    md.append("Read the rows top to bottom:")
    md.append("")
    md.append("- **Row 1** is the likely way a \"3x\" figure gets made: people reached fast versus everyone "
              "else, including people never reached (who almost never book).")
    md.append("- **Row 2** compares reached leads only. A drop from row 1 means part of the claim comes "
              "from counting unreachable leads as \"slow\".")
    md.append("- **Row 3** measures speed by first *dial*. A further drop means eager people answering "
              "the first call explains part of the effect, not the speed of calling.")
    md.append("")

    md.append("### Adjusted for observable confounders (Mantel–Haenszel risk ratio, by first dial)")
    md.append("")
    keys = {
        "Hour band": lambda l: hour_band(l.created.hour),
        "Lead source": lambda l: l.source,
        "Treatment": lambda l: l.treatment,
        "Clinic": lambda l: l.clinic,
        "Hour band × source × treatment": lambda l: (hour_band(l.created.hour), l.source, l.treatment),
    }
    rows = []
    for name, fn in keys.items():
        rr, used = mantel_haenszel_rr(leads, "dial_min", fn)
        rows.append([name, f"{rr:.2f}x", used])
    md.append(table(["Stratified by", "Adjusted ratio", "Strata used"], rows))
    md.append("")
    md.append("Adjustment only removes bias from *recorded* factors. Intent (how keen someone is) is "
              "not recorded, so the adjusted figure can still be biased in either direction. Only the "
              "randomised pilot (architecture §10) measures the true effect of speed.")
    md.append("")

    md.append("### Who gets fast calls? (is \"fast\" random?)")
    md.append("")
    for name, fn in [("Hour band", lambda l: hour_band(l.created.hour)),
                     ("Lead source", lambda l: l.source)]:
        groups: dict = defaultdict(list)
        for l in leads:
            groups[fn(l)].append(l)
        rows = []
        for k in sorted(groups):
            g = groups[k]
            fast_share = sum(1 for l in g if l.dial_min is not None and l.dial_min <= FAST_MIN) / len(g)
            rows.append([k, f"{len(g):,}", pct(fast_share), pct(rate(g))])
        md.append(f"**By {name.lower()}**")
        md.append("")
        md.append(table([name, "Leads", "Dialled within 5 min", "Booking rate"], rows))
        md.append("")
    md.append("If some groups get fast calls far more often *and* book more anyway, the raw ratio "
              "overstates the effect of speed.")
    md.append("")

    # 4. P0-04 timing and language mix
    md.append("## 4. When enquiries arrive (P0-04)")
    md.append("")
    out_window = sum(1 for l in leads if not (WINDOW_START <= l.created.hour < WINDOW_END))
    md.append(f"- Outside the proposed calling window ({WINDOW_START:02d}:00–{WINDOW_END:02d}:00): "
              f"**{pct(out_window / len(leads))}** of enquiries. These cannot get an AI call in "
              f"minutes and need the overnight path (architecture §4.4).")
    by_hour = Counter(l.created.hour for l in leads)
    peak_hour, peak_n = by_hour.most_common(1)[0]
    md.append(f"- Busiest hour: **{peak_hour:02d}:00–{peak_hour + 1:02d}:00** with "
              f"{pct(peak_n / len(leads))} of daily volume (used for capacity, architecture §13).")
    langs = Counter(l.language for l in leads if l.language)
    if langs:
        mix = ", ".join(f"{k}: {pct(v / sum(langs.values()))}" for k, v in langs.most_common())
        md.append(f"- Language mix: {mix}.")
    else:
        md.append("- Language mix: not in the export. Needs sampling at clinics.")
    md.append("")
    rows = [[f"{h:02d}:00", f"{by_hour.get(h, 0) / days:.1f}", pct(by_hour.get(h, 0) / len(leads))]
            for h in range(24)]
    md.append(table(["Hour", "Enquiries per day", "Share"], rows))
    md.append("")

    # 5. Clinic volumes
    md.append("## 5. Volume by clinic (input for P0-07 and P0-08)")
    md.append("")
    by_clinic: dict = defaultdict(list)
    for l in leads:
        by_clinic[l.clinic].append(l)
    rows = []
    for c in sorted(by_clinic, key=lambda c: -len(by_clinic[c])):
        g = by_clinic[c]
        med_dial = statistics.median([l.dial_min for l in g if l.dial_min is not None] or [float("nan")])
        hi = Counter(l.language for l in g if l.language)
        hi_share = pct(hi.get("hi", 0) / sum(hi.values())) if hi else "–"
        rows.append([c, f"{len(g) / days:.1f}", pct(rate(g)), f"{med_dial / 60:.1f} h", hi_share])
    md.append(table(["Clinic", "Enquiries per day", "Booking rate", "Median time to dial", "Hindi share"], rows))
    md.append("")

    # 6. Conclusion template
    md.append("## 6. What to take to the ops head")
    md.append("")
    md.append(f"- Fast-reached versus everyone else: **{rr_naive:.1f}x**.")
    md.append(f"- Among reached leads only: **{rr_reach:.1f}x**.")
    md.append(f"- Measured by first dial instead: **{rr_dial:.1f}x**.")
    adj, _ = mantel_haenszel_rr(leads, "dial_min", keys["Hour band × source × treatment"])
    md.append(f"- After adjusting for hour, source and treatment: **{adj:.1f}x** (unrecorded factors such "
              f"as intent can still bias this).")
    md.append("- Conclusion: speed probably helps, but the historical data cannot say by how much. "
              "The pilot keeps a randomised standard-callback group to measure it.")
    md.append("")
    return "\n".join(md)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--input", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--synthetic", action="store_true", help="Label the report as synthetic data")
    args = ap.parse_args()

    leads = load(args.input)
    if not leads:
        raise SystemExit("No rows loaded. Check the input file and schema (README.md).")
    report = build_report(leads, args.synthetic, args.input.name)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(report, encoding="utf-8")
    print(f"Analysed {len(leads):,} enquiries -> {args.out}")


if __name__ == "__main__":
    main()
