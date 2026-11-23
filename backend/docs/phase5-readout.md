# Phase 5: ramp and pilot readout (pilot week 4)

Implements [implementation-plan.md §9](../../docs/implementation-plan.md#9-phase-5--ramp-and-pilot-readout-pilot-week-4) and gate G4.

## P5-01 Ramp 20% → 50%

Console → **Ops** → *Assistant share* (admins). In staging and production the 50% button is refused until **G3** passes for that clinic: ≥ 3 live days, no missed urgent handover, SLA ≥ 80%, review rejection ≤ 5%, no contamination. Ops shows each clinic's G3 status. Ramp clinic by clinic; a clinic that fails G3 stays at 20% while others move.

## P5-02 Daily call reviews and weekly feedback review

- **Daily** (front-desk lead): Console → **Reviews**. Up to 10 completed assistant calls per clinic per day, picked at random but the same for every reviewer. Score each: disclosure, booking correct, handover appropriate, tone. Add issue tags and notes.
- **Weekly** (front-desk lead + Voice/AI, 30 min): Ops → *Weekly review*. It covers checklist failures, issue tags, thumbs-down reasons, the handover mix by language, and the changes shipped that week.

## P5-03 Tuning, with a change log

Every finding becomes:
1. a fix (lines, keywords, understanding, prompt or a threshold),
2. a new scenario in `evaluation/scenarios.py`, then a run of the evaluation set,
3. a bump of `RULES_VERSION` in `happysmile/voice/__init__.py`,
4. an entry in Ops → **Log a change** (version, area, what, why).

Each call stores the rules version it ran on, so the readout can show outcomes **by rules version**. If a metric moves, you can see which change it followed.

## P5-04 Attendance

Console → **Attendance**: mark every consultation from the last 7 days as **Attended** or **No-show**, whoever booked it (both arms). The readout compares attendance between arms, so assistant bookings are checked for being real.

## P5-05 Readout and gate G4

Ops → *Pilot readout*, or download the full Markdown report. From the command line:

```bash
uv run python -m happysmile.readout --from 2026-12-14 --to 2027-01-10 --out readout.md
```

How it's computed:

| Question (§9.2) | Measure |
|---|---|
| Did the assistant raise bookings? | Consultation booked within 7 days (not cancelled at review), **intention-to-treat by assigned arm**, leads with a full 7-day window only; difference with a 95% CI (Newcombe hybrid score) |
| Are the bookings real? | Attended / recorded attendance, by arm, with CI |
| Did speed actually change? | Reach rate, reached within 5 min, time to first contact p50/p90, by arm |
| Can staff keep up? Is it safe? | Handover SLA hit rate, urgent missed, automatic stops, review rejection, opt-outs by arm, thumbs-down rate |
| Where is the agent weak? | Handover reason mix; "couldn't understand" rate by language; outcomes by rules version |
| What does it cost? | Assistant call minutes, LLM tokens; ₹ per lead and per booking once unit prices are set (`COST_*` in `.env`) |

The **recommendation** follows the §9.3 table:

| Condition | Recommendation |
|---|---|
| Any missed urgent handover or automatic stop, or attendance significantly lower in the assistant group | Stop or redesign |
| Booking lift significant (CI above 0), guardrails healthy, attendance not more than 5 points lower | Scale |
| Lift appears but SLA < 80% or review rejection > 5% | Fix first |
| Guardrails healthy, lift not significant | Extend (2–4 more weeks at 50/50) |

It also flags when the pilot is **underpowered**. At a 30% baseline, about 356 matured leads per arm are needed to detect a 10-point lift.

An **admin records the actual G4 decision** with notes (Ops → *Record G4 decision*). The record keeps a snapshot of the readout it was based on and can't be edited. Share the downloaded readout with the founder, ops head and front-desk lead.

## Demo on synthetic data

```bash
uv run python -m happysmile.pilot_synthetic       # development only: ~3 weeks of synthetic pilot leads
uv run python -m happysmile.readout --from <start> --to <today> --synthetic --out eval_reports/pilot-readout-synthetic.md
```

The synthetic data has a built-in lift (≈ 29% → 37%) and equal attendance. The readout recovers it: **+8.9 points, 95% CI +3.0 to +15.0 → Scale**. See [eval_reports/pilot-readout-synthetic.md](../eval_reports/pilot-readout-synthetic.md). These are **not real results**.
