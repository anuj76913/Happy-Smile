"""Generate a SYNTHETIC enquiry dataset for demonstrating the P0-01 baseline analysis.

This is NOT HappySmile data. It exists so the analysis can be built and tested
before the real export arrives. The generator deliberately builds in the two
confounders we suspect behind the ops head's "3x within 5 minutes" claim:

  1. Latent intent: eager leads answer the first call, so their *first reached*
     time is short. They also book more, whatever the speed.
  2. Staff behaviour: staff call fast in quiet hours and favour website leads,
     which also differ in intent.

The *true* causal effect of speed is set by SPEED_EFFECT below (modest). The
analysis should show a much larger raw ratio than this, which shrinks when
measured by first dial or adjusted for observable confounders.

Usage:
    python generate_sample_data.py --days 90 --seed 7 --out sample_data/enquiries_synthetic.csv
"""

from __future__ import annotations

import argparse
import csv
import math
import random
from datetime import datetime, timedelta
from pathlib import Path

CLINICS = [f"C{n:02d}" for n in range(1, 13)]
CLINIC_WEIGHTS = [1.6, 1.4, 1.3, 1.2, 1.1, 1.0, 1.0, 0.9, 0.8, 0.7, 0.6, 0.4]
TREATMENTS = ["braces_aligners", "whitening", "implants", "other"]
TREATMENT_WEIGHTS = [0.38, 0.27, 0.2, 0.15]
TREATMENT_BOOK_MULT = {"braces_aligners": 1.0, "whitening": 0.9, "implants": 1.15, "other": 0.85}
LANGS = ["en", "hi"]

# Enquiry arrivals by hour of day (IST), relative weights. Evening-heavy, some late night.
HOUR_WEIGHTS = [0.4, 0.2, 0.1, 0.1, 0.1, 0.2, 0.5, 1.0, 1.6, 2.2, 2.8, 3.0,
                3.4, 3.6, 3.0, 2.8, 2.9, 3.2, 3.8, 4.4, 5.0, 4.6, 3.2, 1.4]

STAFF_START, STAFF_END = 9, 20           # front desk makes callbacks 09:00-20:00
QUIET_HOURS = {10, 11, 15, 16}            # front desk less busy -> more fast calls
HIGH_INTENT_SHARE = 0.25

# True causal effect of time-to-reach on booking (the thing we want to recover).
SPEED_EFFECT = [(5, 1.30), (30, 1.20), (120, 1.10), (float("inf"), 1.00)]


def speed_mult(minutes: float) -> float:
    for limit, mult in SPEED_EFFECT:
        if minutes <= limit:
            return mult
    return 1.0


def next_staff_time(t: datetime, rng: random.Random) -> datetime:
    """First moment staff could plausibly call, at or after t."""
    if t.hour < STAFF_START:
        base = t.replace(hour=STAFF_START, minute=0, second=0)
    elif t.hour >= STAFF_END:
        base = (t + timedelta(days=1)).replace(hour=STAFF_START, minute=0, second=0)
    else:
        return t
    return base + timedelta(minutes=rng.expovariate(1 / 90))


def generate(days: int, per_day: int, seed: int) -> list[dict]:
    rng = random.Random(seed)
    start = datetime(2026, 8, 1)
    rows: list[dict] = []
    n = 0
    for d in range(days):
        day = start + timedelta(days=d)
        count = max(0, int(rng.gauss(per_day, per_day * 0.12)))
        for _ in range(count):
            n += 1
            hour = rng.choices(range(24), HOUR_WEIGHTS)[0]
            created = day + timedelta(hours=hour, minutes=rng.randint(0, 59), seconds=rng.randint(0, 59))
            high = rng.random() < HIGH_INTENT_SHARE
            source = rng.choices(["website", "ads", "aggregator"],
                                 [0.6, 0.3, 0.1] if high else [0.3, 0.5, 0.2])[0]
            treatment = rng.choices(TREATMENTS, TREATMENT_WEIGHTS)[0]
            clinic = rng.choices(CLINICS, CLINIC_WEIGHTS)[0]
            language = rng.choices(LANGS, [0.55, 0.45])[0]

            # --- first dial ---
            in_staff_hours = STAFF_START <= created.hour < STAFF_END
            p_fast = (0.30 if created.hour in QUIET_HOURS else 0.08) if in_staff_hours else 0.0
            if source == "website":
                p_fast *= 1.5
            roll = rng.random()
            if roll < p_fast:
                first_dial = created + timedelta(minutes=rng.uniform(0.5, 5))
            elif in_staff_hours and roll < p_fast + 0.12:
                first_dial = next_staff_time(created + timedelta(minutes=rng.uniform(5, 120)), rng)
            else:
                delay = rng.lognormvariate(math.log(200), 0.5)
                first_dial = next_staff_time(created + timedelta(minutes=delay), rng)

            # --- attempts until reached (max 3) ---
            p_answer = 0.90 if high else 0.30
            attempts, reached_at, t = 0, None, first_dial
            while attempts < 3:
                attempts += 1
                if rng.random() < p_answer:
                    reached_at = t
                    break
                t = next_staff_time(t + timedelta(minutes=rng.uniform(60, 300)), rng)

            # --- booking ---
            if reached_at is None:
                p_book = 0.03
            else:
                mins = (reached_at - created).total_seconds() / 60
                p_book = (0.75 if high else 0.15) * speed_mult(mins) * TREATMENT_BOOK_MULT[treatment]
                if created.hour in QUIET_HOURS:
                    p_book *= 1.10
                p_book = min(p_book, 0.95)
            booked = rng.random() < p_book
            booked_at = (reached_at or first_dial) + timedelta(minutes=rng.uniform(2, 60)) if booked else None
            attended = (rng.random() < (0.8 if high else 0.6)) if booked else None

            rows.append({
                "enquiry_id": f"E{n:06d}",
                "created_at": created.isoformat(timespec="seconds"),
                "clinic_id": clinic,
                "treatment": treatment,
                "source": source,
                "language": language,
                "first_call_at": first_dial.isoformat(timespec="seconds"),
                "first_reached_at": reached_at.isoformat(timespec="seconds") if reached_at else "",
                "call_attempts": attempts,
                "booked": int(booked),
                "booked_at": booked_at.isoformat(timespec="seconds") if booked_at else "",
                "attended": "" if attended is None else int(attended),
            })
    return rows


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--days", type=int, default=90)
    ap.add_argument("--per-day", type=int, default=300)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--out", type=Path, default=Path(__file__).parent / "sample_data" / "enquiries_synthetic.csv")
    args = ap.parse_args()

    rows = generate(args.days, args.per_day, args.seed)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print(f"Wrote {len(rows):,} synthetic enquiries to {args.out}")


if __name__ == "__main__":
    main()
