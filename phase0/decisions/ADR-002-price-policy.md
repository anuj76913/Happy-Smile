# ADR-002 — What the assistant may say about price

| | |
|---|---|
| **Status** | Proposed — needs founder approval |
| **Plan item** | P0-05 |
| **Deciders** | Founder, PM, front-desk lead |
| **Architecture** | §7.3, §8.1 (Price/EMI handover), edge cases EC-SCOPE-01 to 03 |

## Context

Price is one of the first questions patients ask. If the assistant can say nothing, every price question becomes a handover, which adds load to the front desk (the biggest pilot risk). If it says too much, it can quote wrongly or appear to promise a price before the dentist has seen the patient.

## Options

| Option | What the assistant says | Handover load | Risk |
|---|---|---|---|
| **1. No prices** | "Our team will go through costs with you." Hand over, and offer to book a consultation meanwhile | Highest | Lowest |
| **2. "Starting from" card** | Approved starting prices only, always with "the dentist confirms the exact cost at the consultation". EMI, discounts and insurance → handover | Medium | Low, if the card is kept current |
| **3. Full price list** | Detailed prices and EMI terms | Lowest | High: misquotes, implied promises, frequent updates |

## Proposed decision

**Option 2 if the founder approves a price card; otherwise option 1.** Option 3 is out of scope for the pilot.

In every option, the assistant never:
- negotiates or offers a discount,
- quotes EMI terms or interest,
- says whether insurance covers a treatment,
- gives a price for a specific patient's case.

## Price card template (to be filled by HappySmile)

| Treatment | Consultation fee | "Starting from" price | Wording the assistant uses |
|---|---|---|---|
| Braces / aligners | ₹ TBD | ₹ TBD | "Braces start from about ₹__. The dentist will confirm the exact cost after the consultation." |
| Whitening | ₹ TBD | ₹ TBD | |
| Implants | ₹ TBD | ₹ TBD | |
| Consultation only | ₹ TBD | — | |

Owner of the card: ______ · Review frequency: monthly · Version: ______

## Consequences

- With option 1, expect "Price/EMI question" to be one of the top handover reasons. Plan staffing for it.
- The card is versioned; a change means re-running the price scenarios in the evaluation set.
- The pilot readout reports the price/EMI handover rate. If it is high under option 1, revisit this decision.
