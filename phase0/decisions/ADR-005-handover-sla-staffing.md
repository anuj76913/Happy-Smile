# ADR-005 — Handover SLAs and queue staffing

| | |
|---|---|
| **Status** | Proposed — needs front-desk lead agreement and named people |
| **Plan item** | P0-08 |
| **Deciders** | Front-desk lead, ops head, PM |
| **Architecture** | §4.9, §8.1, §8.3; implementation-plan §12 (G3), §13 (kill switch) |

## Context

The most likely way the pilot fails is that handovers wait too long (architecture §16, row 1). The assistant reaches people in minutes, but a slow human follow-up wastes that. Staffing has to be agreed **before** go-live, not discovered after.

## Proposed SLAs

| Handover type | Target | Applies |
|---|---|---|
| Urgent (pain, swelling, bleeding) | **5 minutes** | During staffed hours |
| All other handovers | **15 minutes** | During staffed hours |
| Any handover outside staffed hours | First thing next opening | The assistant promises "tomorrow morning", never "a few minutes" (§8.3) |
| AI booking review | Before the end of the same day | Always before the appointment day (EC-POST-03) |

**G3 gate:** ≥ 80% of handovers within SLA. **Kill switch:** < 60% for a day → reduce the assistant share.

## Staffing model

Running `staffing_calculator.py` with default assumptions (30 leads/day, 50% assistant share, 35% handover rate, staff free 50% of the time) gives:

- about **4 handovers a day** per clinic, about 0.5 in the busiest hour,
- **1 person free at any moment** is enough (99% within 15 min, 97% within 5 min),
- so **2 people on the busiest shift**, with one named as queue owner each hour,
- total front-desk minutes on leads go **down** (about 127 vs 180 a day today), because routine calls move to the assistant.

Rerun with real inputs from P0-01 and P0-02 before deciding.

## Rota template (per pilot clinic)

| Hour block | Queue owner | Back-up | Slot store refresh (by 09:00) |
|---|---|---|---|
| 09:00–12:00 | | | ✔ owner: |
| 12:00–15:00 | | | |
| 15:00–18:00 | | | |
| 18:00–21:00 | | | |

The queue owner keeps the Leads console open and takes **Needs you** items first. The back-up covers breaks and walk-in rushes.

## Escalation

1. Past SLA → lead highlighted in the console.
2. Past 2× SLA → clinic manager notified.
3. Urgent lead past 5 minutes → clinic manager **and** on-call PM alerted (EC-URG-07).

## Decision (to fill)

- SLAs agreed: yes / changed to: ______
- Rota filled for each pilot clinic: yes / no
- Escalation contacts: ______
- Date decided:
