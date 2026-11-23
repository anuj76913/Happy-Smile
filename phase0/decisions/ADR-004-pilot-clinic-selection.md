# ADR-004 — Pilot clinic selection

| | |
|---|---|
| **Status** | Proposed — scoring needs real data |
| **Plan item** | P0-07 |
| **Deciders** | Ops head, front-desk lead, PM |
| **Architecture** | §10 Pilot experiment design |

## Context

The pilot runs in **2–3 of the 12 clinics**. They need enough leads for a readable result, teams willing to try it, and a language mix that tests Hindi.

## Selection criteria

| # | Criterion | Weight | How to score (1–5) | Source |
|---|---|---|---|---|
| 1 | Lead volume | 30% | 5 = ≥ 35/day · 3 = 20–35 · 1 = < 20 | Baseline report §5 |
| 2 | Front-desk willingness | 25% | From the process-mapping visit (1–5) | P0-02 |
| 3 | Staff capacity for the queue | 15% | 5 = calculator shows comfortable slack · 1 = already stretched | P0-02 + staffing calculator |
| 4 | Language mix | 10% | 5 = ≥ 40% Hindi · 3 = 20–40% · 1 = < 20% | Baseline report §5 |
| 5 | Calendar / slot readiness | 10% | 5 = clean calendar, one owner · 1 = messy or shared | P0-03 |
| 6 | Stability | 10% | 1 if there are staff changes, renovations or new-dentist ramp-ups during the pilot | Ops head |

**Hard rules:**
- At least one selected clinic must have a high Hindi share.
- Exclude any clinic whose front-desk team scores willingness ≤ 2. Forcing it would test resistance, not the assistant.
- Selected clinics together should give **≥ 70 leads/day**, so a 50/50 split gives about 35 per arm per day (implementation-plan §10 power check).

## Scoring sheet

| Clinic | Volume | Willingness | Capacity | Language | Calendar | Stability | **Weighted score** | Notes |
|---|---|---|---|---|---|---|---|---|
| C01 | | | | | | | | |
| C02 | | | | | | | | |
| C03 | | | | | | | | |
| C04 | | | | | | | | |
| C05 | | | | | | | | |
| C06 | | | | | | | | |
| C07 | | | | | | | | |
| C08 | | | | | | | | |
| C09 | | | | | | | | |
| C10 | | | | | | | | |
| C11 | | | | | | | | |
| C12 | | | | | | | | |

Weighted score = 0.30·Volume + 0.25·Willingness + 0.15·Capacity + 0.10·Language + 0.10·Calendar + 0.10·Stability.

## Decision (to fill)

- Selected clinics:
- Combined leads/day:
- Hindi-heavy clinic included: yes / no
- Front-desk owner per clinic:
- Date decided:
