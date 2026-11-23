# P0-10 — Telephony provider and caller ID checklist

**Goal:** an account with an Indian telephony/CPaaS provider and a registered calling number, ready for internal test calls in Phase 3.

## 1. Must-have capabilities

| # | Requirement | Why | Architecture |
|---|---|---|---|
| 1 | Outbound calls to Indian mobiles from a registered Indian number | The number shown on the form | §4.1, §4.4 |
| 2 | **Bidirectional real-time media stream** (WebSocket) | Voice agent pipeline | §4.5 |
| 3 | Call status webhooks (initiated, ringing, answered, completed, failed, busy, no-answer) with signatures | Orchestrator and retries | §4.4, §12 |
| 4 | Answering-machine / voicemail detection | Don't talk to voicemail (EC-CALL-04) | §4.4 |
| 5 | Call recording, with the ability to stop mid-call | Recording, and "don't record me" (EC-AI-07) | §14 |
| 6 | ≥ 10 concurrent channels, with room to grow | Peak capacity | §13 |
| 7 | Inbound handling on the same number (play a message, notify us) | Patients calling back (EC-CALL-07) | — |
| 8 | Click-to-call bridge for staff ("Call now" from the console) | Staff calls show the same number | §12 |
| 9 | Data stored in India; recordings exportable to our storage | Data residency | §13 |
| 10 | Per-call provider ID, idempotent APIs | No double dials (EC-CALL-12) | §4.4 |

## 2. Questions for shortlisted providers

1. Which number types can we use for calls the person asked for (service vs promotional)? What registration does each need?
2. What is the media stream audio format (sample rate, codec), and what latency do you see in India?
3. How accurate is voicemail detection on Indian networks, and how long does it take?
4. Concurrency limits per number and per account? How do we raise them?
5. How do you help keep a number from being labelled as spam?
6. Where are recordings and call logs stored? Retention controls?
7. Pricing per minute (outbound mobile), per number, and for media streaming.
8. Time from sign-up to a live number, including KYC.

## 3. KYC documents usually requested (confirm with the provider)

- Certificate of incorporation / registration
- Company PAN and GST registration
- Registered address proof
- Authorised signatory ID and a letter of authorisation
- Description of the use case (service calls in response to customer enquiries)

## 4. Shortlist and scoring

| Provider | Media stream | Voicemail detection | India data | Concurrency | Time to live | Cost | Score |
|---|---|---|---|---|---|---|---|
| | | | | | | | |
| | | | | | | | |
| | | | | | | | |

## 5. Done when

- [ ] Account approved and KYC complete
- [ ] Calling number provisioned and registered
- [ ] Test outbound call with media stream from staging
- [ ] Webhook signature verification tested
- [ ] Inbound message on the same number configured
- [ ] Number written into the form disclosure ([ADR-003](../decisions/ADR-003-ai-disclosure.md)) and WhatsApp templates
