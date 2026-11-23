# P0-02 — Current callback process: mapping guide

**Goal:** document how leads are handled today at 2–3 clinics, and measure front-desk capacity. The outputs feed the staffing calculator (`staffing_calculator.py`), the handover SLA decision ([ADR-005](../decisions/ADR-005-handover-sla-staffing.md)), and the pilot clinic choice ([ADR-004](../decisions/ADR-004-pilot-clinic-selection.md)).

**Who:** PM, with the front-desk lead introducing the PM to each clinic team.
**Time:** about half a day per clinic (1 h interview + 2 h observation + 30 min wrap-up).

---

## 1. Before the visit

- [ ] The front-desk lead tells clinic staff why the PM is visiting: to learn how they work, not to assess them.
- [ ] Ask for a copy of any callback script, lead sheet or CRM view in use.
- [ ] Pick a visit slot that includes a busy period (evening, if the baseline shows evening peaks).

## 2. Interview questions (front-desk staff)

**Where leads come from**
1. How do online enquiries reach you (email, CRM, sheet, WhatsApp, phone)?
2. How do you know a new one has arrived? How often do you check?
3. Who decides the order in which you call them back?

**The callback**
4. Walk me through your last callback, start to finish.
5. What do you say first? Is there a script?
6. What questions do patients ask most? Which are hardest to answer?
7. How often do people ask about price or EMI? What do you tell them?
8. How do you book: which system, how long does it take, who can change slots?
9. What happens when nobody answers? How many times do you try?

**Capacity**
10. How many people are at the front desk per shift? What else do they do?
11. In a typical hour, how much time is free for calling leads?
12. When are you busiest? When is it quiet?

**Trust and concerns**
13. What would worry you about an assistant calling patients first?
14. Which kinds of patient would you never want a bot to handle?
15. If the assistant handed a lead to you, what would you need to see so you don't have to re-ask?

## 3. Observation sheet (2 hours)

Record every lead-related action:

| Time | Action (check inbox / dial / talk / book / note) | Lead source | Duration (min) | Outcome | Interruptions |
|---|---|---|---|---|---|
| | | | | | |

Also note: walk-in and phone interruptions per hour, and how long a booking takes in the calendar system.

## 4. Capacity worksheet (per clinic)

| Measure | Value | How measured |
|---|---|---|
| Front-desk people per shift (morning / evening) | | Interview |
| Share of time free for leads (busy hour / quiet hour) | | Observation |
| Average minutes per callback (answered) | | Observation |
| Average minutes per booking in the calendar | | Observation |
| Attempts before giving up on a no-answer | | Interview |
| Leads per day (from the baseline report) | | P0-01 |

Feed these into `staffing_calculator.py` as `--availability`, `--aht-min` and `--leads-per-day`.

## 5. Output (one page per clinic)

```
Clinic: C__        Visited: ____-__-__        By: ______

Lead flow today:      [source] -> [where it lands] -> [who calls] -> [booking system]
Typical first call:   __ h after enquiry (observed) / __ h (baseline report)
Script / opening:     ...
Top patient questions: 1. ...  2. ...  3. ...
Price/EMI handling:   ...
Capacity:             __ people/shift, __% free in busy hour, __ min per callback
Concerns raised:      ...
Must-see items for a handover: ...
Willingness to pilot (1-5): __   Notes: ...
```
