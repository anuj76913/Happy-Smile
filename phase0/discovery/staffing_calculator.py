"""P0-08 — Handover queue staffing calculator (Erlang C).

Estimates how many front-desk people must be free for the "Needs you" queue in
the busiest hour, so handovers are called back within the SLA (architecture §8.1).

Front-desk staff also run the clinic, so only part of each person's time is
available for the queue (--availability). The result is the number of people
on shift, not full-time equivalents.

All defaults are assumptions for a mid-sized pilot clinic. Replace them with
the baseline report (P0-01/P0-04) and the process map (P0-02).

Usage:
    python staffing_calculator.py
    python staffing_calculator.py --leads-per-day 32 --assistant-share 0.5 --handover-rate 0.4
"""

from __future__ import annotations

import argparse
import math


def erlang_c_wait_prob(agents: int, traffic: float) -> float:
    """Probability an arriving task has to wait (Erlang C)."""
    if agents <= traffic:
        return 1.0
    term = 1.0
    total = 1.0  # k = 0
    for k in range(1, agents):
        term *= traffic / k
        total += term
    top = term * traffic / agents * agents / (agents - traffic)  # A^N/N! * N/(N-A)
    return top / (total + top)


def service_level(agents: int, traffic: float, aht_min: float, sla_min: float) -> float:
    """Share of tasks started within sla_min."""
    if agents <= traffic:
        return 0.0
    return 1 - erlang_c_wait_prob(agents, traffic) * math.exp(-(agents - traffic) * sla_min / aht_min)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--leads-per-day", type=float, default=30, help="Enquiries per day at this clinic")
    ap.add_argument("--assistant-share", type=float, default=0.5, help="Share of leads in the assistant arm")
    ap.add_argument("--in-window-share", type=float, default=0.75, help="Share arriving in the calling window")
    ap.add_argument("--contact-rate", type=float, default=0.7, help="Share of assistant calls answered")
    ap.add_argument("--handover-rate", type=float, default=0.35, help="Share of answered calls handed over")
    ap.add_argument("--whatsapp-reply-rate", type=float, default=0.15,
                    help="Share of unreached leads who reply on WhatsApp (also land in Needs you)")
    ap.add_argument("--peak-hour-share", type=float, default=0.12, help="Share of daily volume in the busiest hour")
    ap.add_argument("--aht-min", type=float, default=7, help="Minutes per handover (call + notes + booking)")
    ap.add_argument("--review-min", type=float, default=1.5, help="Minutes to review one AI booking")
    ap.add_argument("--control-aht-min", type=float, default=6, help="Minutes per standard-callback lead")
    ap.add_argument("--sla-min", type=float, default=15, help="Handover SLA in minutes")
    ap.add_argument("--target", type=float, default=0.8, help="Target share within SLA (G3 gate uses 80%%)")
    ap.add_argument("--availability", type=float, default=0.5,
                    help="Share of a front-desk person's time free for the queue")
    a = ap.parse_args()

    assistant = a.leads_per_day * a.assistant_share
    control = a.leads_per_day - assistant
    answered = assistant * a.contact_rate
    handovers = answered * a.handover_rate + assistant * (1 - a.contact_rate) * a.whatsapp_reply_rate
    ai_bookings = answered * (1 - a.handover_rate) * 0.6  # assume 60% of non-handover answered calls book

    peak_handovers = handovers * a.peak_hour_share
    peak_traffic = peak_handovers * a.aht_min / 60  # Erlangs

    agents = max(1, math.ceil(peak_traffic))
    while service_level(agents, peak_traffic, a.aht_min, a.sla_min) < a.target and agents < 50:
        agents += 1
    sl = service_level(agents, peak_traffic, a.aht_min, a.sla_min)
    people = math.ceil(agents / a.availability)

    daily_minutes = handovers * a.aht_min + ai_bookings * a.review_min + control * a.control_aht_min
    baseline_minutes = a.leads_per_day * a.control_aht_min

    urgent_sl = service_level(agents, peak_traffic, a.aht_min, 5)

    print("Handover queue staffing - one clinic (all inputs are assumptions until P0-01/P0-02)")
    print("-" * 78)
    print(f"Leads per day                          {a.leads_per_day:8.1f}")
    print(f"  assistant arm / standard callback    {assistant:8.1f} / {control:.1f}")
    print(f"Handovers per day (Needs you)          {handovers:8.1f}")
    print(f"AI bookings to review per day          {ai_bookings:8.1f}")
    print(f"Handovers in the busiest hour          {peak_handovers:8.2f}")
    print(f"Queue workload in the busiest hour     {peak_traffic:8.2f} Erlangs")
    print("-" * 78)
    print(f"Free people needed at any moment       {agents:8d}  ({sl:.0%} within {a.sla_min:.0f} min, "
          f"{urgent_sl:.0%} within 5 min for urgent)")
    print(f"People on shift at {a.availability:.0%} availability     {people:8d}")
    print("-" * 78)
    print(f"Front-desk minutes per day, pilot      {daily_minutes:8.0f}")
    print(f"Front-desk minutes per day, today      {baseline_minutes:8.0f}  (every lead called by staff)")
    print()
    print(f"Reading: the queue workload is small, but someone must be free when a handover lands.")
    print(f"With each person free {a.availability:.0%} of the time, plan {people} people on the busiest shift")
    print("and name who owns the queue each hour. The total front-desk time spent on leads goes down")
    print("versus today, because the assistant handles the routine calls.")


if __name__ == "__main__":
    main()
