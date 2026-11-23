# P0-03 — Clinic calendar discovery

**Goal:** find out where consultation slots live today and whether the assistant can read and book them by API. The result decides [ADR-001](../decisions/ADR-001-booking-approach.md): booking adapter or pilot slot store (architecture §4.7).

**Who:** backend engineer, with the ops head (for vendor contacts) and one front-desk person per pilot clinic.

---

## 1. Questions

**The system**
1. What holds clinic appointments (practice-management software, Google Calendar, paper, spreadsheet)? Same in all 12 clinics?
2. Who is the vendor? Is there a support or partner contact?
3. Is the system cloud-hosted or on a clinic PC?

**API access**
4. Is there an API? REST, SOAP, database access, or export only?
5. Can it **list free slots** by clinic, dentist, date and appointment type?
6. Can it **hold** a slot for a few minutes, or only book outright?
7. Can it **create, change and cancel** a booking, and tag it as created by the assistant?
8. Does it send its own reminders or confirmations? (Avoid double messages.)
9. Rate limits, sandbox environment, costs, contract changes needed?
10. How long would the vendor take to give access?

**How slots work**
11. How long is a consultation? Does it differ by treatment?
12. Can any dentist do any consultation, or are some treatment-specific (e.g. implants)?
13. How far ahead are slots open? Who blocks time for leave or emergencies?
14. How often do walk-ins or phone bookings change availability during the day?

## 2. Options

| Option | When it fits | Pros | Cons |
|---|---|---|---|
| **A. API adapter** | API supports list + book (+ hold) and access is quick | Always current; no manual upkeep | Vendor dependency; may not be ready in 4 weeks |
| **B. Pilot slot store** | No API, or access will take longer than the pilot | Fully under our control; fast to build | Manual daily upkeep; stale-slot risk (edge case EC-BOOK-11) |
| **C. Read-only sync + manual entry** | API can read slots but not book | Current availability | Staff must enter every AI booking; review step becomes mandatory |

## 3. Decision criteria

Choose **A** only if all are true: list and book are supported, sandbox access within 1 week, and no contract change is needed. Otherwise choose **B** for the pilot and plan A for Phase 6.

## 4. Pilot slot store (option B) — operating model

| Item | Proposal |
|---|---|
| What is stored | Consultation slots per clinic and dentist: start time, duration, status (open / held / booked) |
| Who updates it | A named front-desk person per pilot clinic, **by 09:00 every day**, for the next 7 days |
| How | Simple admin screen in the Leads console, or a CSV/Google Sheet import |
| Conflict rule | Any booking made outside the assistant (walk-in, phone) must also be marked in the store; otherwise the slot can be double-booked |
| Safety | If the store hasn't been refreshed in 24 h, AI booking pauses for that clinic and leads are handed over (EC-BOOK-11) |
| Review | Every AI booking appears in **Booked by assistant** for review before the appointment day |

## 5. Output

Record in ADR-001: chosen option, vendor and API notes, owner of the slot refresh, and the date access was confirmed.
