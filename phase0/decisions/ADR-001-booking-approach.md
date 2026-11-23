# ADR-001 — How the assistant books consultations

| | |
|---|---|
| **Status** | Proposed — waiting on calendar discovery (P0-03) |
| **Plan item** | P0-03 |
| **Deciders** | PM, backend engineer, ops head |
| **Architecture** | §4.7 Booking Service |

## Context

The assistant must offer real slots and book them during the call. We don't yet know what calendar system the clinics use or whether it has an API. The pilot runs in 2–3 clinics for about 2 weeks of live traffic.

## Options

See [calendar-discovery.md §2](../discovery/calendar-discovery.md#2-options): **A** API adapter, **B** pilot slot store, **C** read-only sync with manual entry.

## Proposed decision

**Default to option B (pilot slot store)** unless discovery shows that the calendar API supports listing and booking slots, with sandbox access within a week.

Reasons:
- The pilot's job is to test whether fast AI contact raises bookings, not to integrate with a calendar vendor.
- Option B can be built in Phase 2 without external dependencies.
- The Booking Service uses an adapter interface either way (`listSlots`, `holdSlot`, `confirmBooking`, `cancelBooking`), so moving to option A in Phase 6 does not change the agent.

## Consequences

- A named person per pilot clinic must refresh slots daily by 09:00. This becomes part of the front-desk rota ([ADR-005](ADR-005-handover-sla-staffing.md)).
- Bookings made outside the assistant must also be marked in the store.
- AI booking pauses automatically if a clinic's store is stale (EC-BOOK-11).
- The risk register entry "Booking errors from a stale pilot slot store" stays at Medium likelihood until option A is live.

## Update (Phase 6)

The adapter now exists: `backend/happysmile/calendar_sync.py`. Clinics are `local` (option B) or `http` (option A). With `http`, slots are synced every ~10 minutes, and each booking, change and cancellation is confirmed in the external calendar first. Mapping the real vendor's API onto the documented contract is the remaining work once P0-03 names the system.

## To record once decided

- Chosen option:
- Calendar system and vendor:
- API capabilities confirmed (list / hold / book / cancel):
- Slot refresh owner per clinic:
- Date decided:
