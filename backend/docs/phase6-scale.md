# Phase 6: after the pilot (scale or stop)

Implements the candidates in [implementation-plan.md §10](../../docs/implementation-plan.md#10-phase-6--after-the-pilot-scale-or-stop). **Precondition:** the latest recorded G4 decision is **Scale**. In staging and production the system enforces this: no assistant share above 50% and no new wave without it. In development the checks are shown but not enforced.

## Status by candidate

| # | Candidate (plan order) | Status | Where |
|---|---|---|---|
| 1 | Roll out to the remaining clinics in waves of 3 | **Built** | `rollout.py`; Ops → Rollout |
| 2 | Calendar API integration | **Built as an adapter**; the vendor mapping waits on P0-03 / ADR-001 | `calendar_sync.py` |
| 3 | Live warm transfer for "asked for a person" | **Built**; needs telephony transfer support (P0-10) | `voice/tools.py::transfer_to_staff`; topbar toggle |
| 4 | Reminder and no-show recovery | **Built** (WhatsApp + staff follow-up); two new templates need Meta approval | `messaging.py`, `reviews.record_attendance` |
| 5 | More languages per clinic | **Readiness checker only**: no language added without P0-04 data and native wording | `python -m happysmile.languages mr` |
| 6 | India-hosted LLM option | **Built as config**: any OpenAI-compatible endpoint | `LLM_BASE_URL`, `LLM_API_KEY`, `LLM_PROVIDER` |
| 7 | Permanent control share | **Built and always enforced** (default 10%) | `PERMANENT_CONTROL_SHARE` |

## 1 + 7. Rollout waves and the permanent control group

- Waves: 1 = the pilot clinics; 2 = Maple Road, Palm Grove, Banyan Park; 3 = Cedar Avenue, Harbour View, Orchid Lane; 4 = Sunrise Plaza, Willow Street, Lake Gate. Admins can change these in the database.
- **A wave can start when** the latest G4 decision is *scale*; every clinic in the previous wave has been at steady state (share above 50%) for 7 days with no open critical alert; and each new clinic's onboarding is complete. Onboarding means:
  - checked automatically: dentists, front-desk accounts, slots or calendar synced, address;
  - signed off: rota, training, languages, address and dentist list.
- Starting a wave brings its clinics in at **0%**. They then ramp like the pilot: 20% (G2 + onboarding) → 50% (G3) → steady.
- **The assistant share never goes above 90%**, in every environment. The remaining 10% stay on the standard callback, so the lift keeps being measured. The pilot readout (Ops → Pilot readout, any date range) becomes the ongoing lift report.

## 2. Calendar adapter

Each clinic is `local` (staff keep the slot list, as in the pilot) or `http` (synced from the clinic's calendar system). With `http`:
- the worker syncs open slots every ~10 minutes; slots taken elsewhere are blocked;
- every booking (assistant or staff) and every change or cancellation at review is **confirmed in the calendar first**. If the calendar says the slot is gone, the booking is refused, the slot is blocked, and the assistant offers another time;
- if syncing stops, the slot list goes stale and **AI booking pauses automatically** for that clinic (30 minutes for a synced calendar, 24 hours for a manual list; EC-BOOK-11). The assistant then hands over instead of booking.

The HTTP contract is documented in `calendar_sync.py`. To connect the real practice-management system, either put a thin shim in front of it that speaks this contract, or replace `HttpCalendar` with a vendor adapter of the same shape. Set `CALENDAR_API_URL` / `CALENDAR_API_TOKEN`, then switch a clinic with `PUT /v1/admin/clinics/{id}/calendar {"adapter": "http"}`.

## 3. Live warm transfer

- Front-desk staff switch on **Live transfers** in the console topbar (first time: the phone that should ring). It lasts 4 hours.
- When a caller asks for a person **during staffed hours**, and someone at that clinic is available and not already on a transfer, the assistant says *"I'm connecting you to Kavya…"* and the telephony provider bridges the call. The handover is recorded as picked up by that person, so they record the outcome as usual.
- If nobody is available, or the transfer fails, the normal handover and promise apply (it falls back to a person).
- Pain or swelling still goes to the urgent queue rather than a live transfer, as the plan scoped transfers to "asked for a person". **Worth considering next:** live transfer for urgent cases too.
- Needs the telephony vendor's transfer/bridge API (`Provider.transfer`); the simulator implements it.

## 4. Reminders and no-show recovery (assistant group only)

- **Appointment reminder** 24 h before (3 h if booked for the next day), re-planned when staff move a booking and cancelled when they cancel it.
- **No-show:** marking *No-show* in Attendance sends a "sorry we missed you, reply to rebook" WhatsApp and puts the lead in Needs you ("Missed consultation") for a call.
- The control group keeps today's process (no automated messages), so attendance stays comparable.
- New templates `appointment_reminder_v1` and `no_show_v1` must be approved by Meta before use (added to the submission list).

## 5. Adding a language

`python -m happysmile.languages <code>` lists everything missing. That covers the assistant lines, treatment words, form disclosures, WhatsApp templates, understanding and guardrail keywords, language detection, the DB constraints, the form, the speech vendor, 30+ evaluation scenarios and a native-speaker review. Start only when P0-04 data shows a clinic needs it.

## 6. India-hosted LLM

Set `LLM_BASE_URL` and `LLM_API_KEY` to any OpenAI-compatible endpoint, `LLM_PROVIDER` to a label, and pin the three model IDs. Telemetry records the provider with each call. Re-run the evaluation set with the new endpoint (`--groq` flag uses whatever endpoint is configured) before switching production.

## Decisions taken here (flagged for review)

- **Permanent control at 10%:** a trade-off. About 10% of leads keep the slower process, in exchange for continuously knowing the effect. Revisit once the effect is stable over several months.
- **Transfers only for "asked for a person"**, as the plan scoped; urgent cases still use the 5-minute queue.
- **No-show recovery uses WhatsApp and a person**, not an AI call. An AI "rebook" call would need a new conversation flow and evaluation set.
- **No new language added** without data and native-speaker wording.
