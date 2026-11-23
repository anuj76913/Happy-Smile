# Phase 0 — Discovery and long-lead setup

Implements Phase 0 of [implementation-plan.md](../docs/implementation-plan.md#4-phase-0--discovery-and-long-lead-setup).

Phase 0 is mostly decisions, data and approvals that only HappySmile and outside parties can provide. This folder holds everything needed to **run** Phase 0: analysis tools, discovery guides, decision records with recommendations, draft templates, and briefs. Each item below says what is ready and what still needs a person.

---

## Tracker

**Status key:** **Ready** = tool or draft complete, needs input or sign-off · **Blocked** = needs HappySmile or an external party before anything can happen · **Done** = exit criteria met.

### Discovery (P0-01 to P0-08)

| ID | Task | Artifact | Status | Needs |
|---|---|---|---|---|
| P0-01 | Baseline: time to call vs booking, selection-bias check | [discovery/baseline/](discovery/baseline/) — `baseline_analysis.py`, worked example on synthetic data | **Ready** | 90-day enquiry export from HappySmile ([data request](discovery/baseline/README.md#data-request-to-happysmile)) |
| P0-02 | Map current callback process and capacity | [discovery/process-mapping-guide.md](discovery/process-mapping-guide.md) | **Ready** | Visits to 2–3 clinics |
| P0-03 | Calendar system and API | [discovery/calendar-discovery.md](discovery/calendar-discovery.md), [ADR-001](decisions/ADR-001-booking-approach.md) | **Ready** | Answers from ops head / calendar vendor |
| P0-04 | Out-of-hours share and language mix | Included in `baseline_analysis.py` (report §4) | **Ready** | Same export as P0-01; language may need clinic sampling |
| P0-05 | Price policy | [ADR-002](decisions/ADR-002-price-policy.md) — recommends a "starting from" card, else no prices | **Ready** | Founder decision; price card values |
| P0-06 | AI disclosure policy and wording | [ADR-003](decisions/ADR-003-ai-disclosure.md) — EN/HI wording and founder talking points | **Ready** | Founder sign-off; Hindi native-speaker review |
| P0-07 | Pilot clinic selection | [ADR-004](decisions/ADR-004-pilot-clinic-selection.md) — weighted scoring sheet | **Ready** | Baseline volumes + visit scores |
| P0-08 | Handover SLAs and staffing | [ADR-005](decisions/ADR-005-handover-sla-staffing.md), [discovery/staffing_calculator.py](discovery/staffing_calculator.py) | **Ready** | Front-desk lead agreement; named people on the rota |

### Long-lead setup (P0-10 to P0-16)

| ID | Item | Artifact | Status | Needs | Needed by |
|---|---|---|---|---|---|
| P0-10 | Telephony account, KYC, caller ID | [long-lead/telephony-checklist.md](long-lead/telephony-checklist.md) | **Blocked** | Company KYC documents; provider choice | Phase 3 |
| P0-11 | WhatsApp Business account + templates | [long-lead/whatsapp-templates.md](long-lead/whatsapp-templates.md) — 6 templates, EN + HI | **Ready** to submit | WhatsApp Business account; Hindi review | Phase 4 |
| P0-12 | Groq account, models, rate limits | [long-lead/groq/](long-lead/groq/) — `groq_check.py` + capacity maths | **Blocked** | HappySmile-owned Groq org account and API key | Phase 3 |
| P0-13 | Groq data processing terms | [long-lead/groq/README.md](long-lead/groq/README.md#p0-13--data-processing-questions-for-groq-for-legal) — 7 questions | **Ready** to send | Groq's written answers; legal review | **G2** |
| P0-14 | DPDP consent and telecom classification | [long-lead/legal-review-brief.md](long-lead/legal-review-brief.md) — 12 items with proposed positions | **Ready** to send | Legal adviser | **G2** |
| P0-15 | STT/TTS vendor trial (Hindi/Hinglish) | [long-lead/stt-tts-trial-plan.md](long-lead/stt-tts-trial-plan.md) | **Ready** | Staff volunteers to record; vendor trial accounts | Phase 4 |
| P0-16 | *New:* SMS sender + template registration (DLT) | Noted in [whatsapp-templates.md](long-lead/whatsapp-templates.md#sms-fallback) | Only if SMS fallback (EC-WA-01) is accepted | Decision on SMS fallback | Phase 4 |

P0-16 is not in the implementation plan yet. It comes from the SMS fallback proposed in [edge-case.md](../docs/edge-case.md) (EC-WA-01). Add it to the plan if the fallback is accepted.

---

## What to do this week

| Day | Action | Owner |
|---|---|---|
| 1 | Send the data request (P0-01/04), the legal brief (P0-14) and the Groq questions (P0-13) | PM |
| 1 | Start telephony KYC (P0-10) and the WhatsApp Business account (P0-11) | Backend + ops head |
| 1–2 | Founder meeting: disclosure (ADR-003) and price policy (ADR-002) | PM |
| 2–3 | Clinic visits with the process-mapping guide (P0-02); calendar questions (P0-03) | PM + backend |
| 3 | Run `baseline_analysis.py` on the real export; share section 6 with the ops head | PM |
| 3–4 | Record the STT/TTS audio set; start vendor trials (P0-15) | Voice/AI |
| 4 | Score clinics (ADR-004); run `staffing_calculator.py` with real inputs; fill the rota (ADR-005) | PM + front-desk lead |
| 5 | Phase 0 exit review | PM |

---

## Exit criteria (implementation-plan §4.3)

- [ ] Baseline report on **real** data exists, and the selection-bias question has a written answer
- [ ] Booking approach decided ([ADR-001](decisions/ADR-001-booking-approach.md))
- [ ] Disclosure wording ([ADR-003](decisions/ADR-003-ai-disclosure.md)) and price policy ([ADR-002](decisions/ADR-002-price-policy.md)) signed off
- [ ] Pilot clinics ([ADR-004](decisions/ADR-004-pilot-clinic-selection.md)) and handover staffing ([ADR-005](decisions/ADR-005-handover-sla-staffing.md)) confirmed
- [ ] All long-lead items (P0-10 to P0-15) submitted, with owners and expected dates

---

## Tools

All scripts need Python 3.10+ and the standard library only.

```bash
# P0-01 / P0-04: baseline on synthetic data (worked example)
cd discovery/baseline
python generate_sample_data.py
python baseline_analysis.py --input sample_data/enquiries_synthetic.csv \
    --out reports/baseline_report_synthetic.md --synthetic

# P0-08: staffing for one clinic
cd ../
python staffing_calculator.py --leads-per-day 30 --assistant-share 0.5 --availability 0.5

# P0-12: Groq check (needs GROQ_API_KEY in the environment)
cd ../long-lead/groq
python groq_check.py --list-models
```

### What the synthetic worked example shows

The report at [discovery/baseline/reports/baseline_report_synthetic.md](discovery/baseline/reports/baseline_report_synthetic.md) uses **made-up data** with a known true effect of 1.3x. The naive "fast versus everyone else" comparison shows **2.3x**. Comparing reached leads only gives **1.7x**. Measuring by first dial gives **1.3x**, and adjusting for hour, source and treatment gives **1.1x**. This is the argument to take to the ops head: the historical figure mixes speed with who answers and who gets called first, so the pilot needs its randomised control group.

## Folder layout

```
phase0/
  README.md                         this tracker
  discovery/
    baseline/                       P0-01, P0-04 analysis + synthetic worked example
    process-mapping-guide.md        P0-02
    calendar-discovery.md           P0-03
    staffing_calculator.py          P0-08
  decisions/
    ADR-001-booking-approach.md     P0-03
    ADR-002-price-policy.md         P0-05
    ADR-003-ai-disclosure.md        P0-06
    ADR-004-pilot-clinic-selection.md  P0-07
    ADR-005-handover-sla-staffing.md   P0-08
  long-lead/
    telephony-checklist.md          P0-10
    whatsapp-templates.md           P0-11 (+ P0-16 note)
    groq/                           P0-12, P0-13
    legal-review-brief.md           P0-13, P0-14
    stt-tts-trial-plan.md           P0-15
```
