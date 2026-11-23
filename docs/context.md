# HappySmile — Project Context

> Source: [problemStatement.txt](problemStatement.txt). This file restates the full case faithfully. Sections marked **(derived)** are summaries added for quick reference and are not part of the original brief.

## Overview

- **Case:** HappySmile — AI voice assistant for lead callbacks
- **Type:** Product Manager case exercise, about 2–3 hours. Fictional scenario.
- **Guiding principle:** "We value judgement over polish."

---

## Part 1 — The Problem (as given)

**Headline:** Interested people ask HappySmile to call. The call comes hours later.

```
Enquiry arrives  ---- 4–6 hours ---->  Front desk calls
```

### The situation

| Fact | Detail |
|---|---|
| Business | Chain of **12 dental clinics** in India |
| Lead volume | About **300 people/day** show interest online, enquiring about braces, whitening, implants and similar treatments |
| Current process | Front-desk staff call them back, usually **4–6 hours later** |
| Current conversion | Only about **30%** of enquiries become booked appointments |
| Ask | An **AI voice assistant** that reaches each interested person **within minutes**, **qualifies** them, and either **books an appointment** or **hands over to staff** |

### What three stakeholders said

1. **Operations head** (sharing from their data):
   > "Leads we happen to call within 5 minutes convert 3x better. So the fix is simple: call everyone faster."
2. **Founder:**
   > "The AI should sound so human that nobody realises it's AI."
3. **Front-desk lead:**
   > "Every lead should still go to my team. I don't trust a bot with patients."

---

## Part 2 — What Must Be Submitted (Google Form)

| # | Item | Required? | Constraints |
|---|---|---|---|
| 1 | **Mockup link** | Required | At most two screens or any mockups. **Scenario #1:** the moment a person asks to be contacted. **Scenario #2:** what HappySmile sees afterwards. Any tool works. Link must open **without a login**. |
| 2 | **Brief** | Required | **Maximum 300 words.** Must cover: (a) what you would ship in the first 4 weeks, and what you are explicitly NOT doing; (b) one success metric and one metric you would deliberately ignore, with reasons; (c) how you would handle the founder and the front-desk lead. |
| 3 | **Three questions** | Required | Three questions you'd ask HappySmile before building anything, and why. |
| 4 | **Failure mode** | Required | How is your own solution most likely to fail in the first month? Be specific. |
| 5 | **AI tool usage** | Optional | If you used AI tools: one suggestion you rejected, and why. **Three lines at most.** Leave blank if you did not use AI tools. |

---

## Part 3 — Build Spec for the Mockup

*(Suggested; edit to match your own take.)*

### Goal and constraints

- A small clickable web prototype with **exactly TWO screens**.
- Deployed to a **public URL that opens without login** (e.g. Vercel, Netlify, GitHub Pages, or a public share link from a vibe-coding tool).
- Use **only made-up names, numbers and phone numbers**.
- Do **not** use real HappySmile branding.

### Screen 1 — "Request a call" (mobile, ~390px wide)

The moment a person asks to be contacted, on HappySmile's enquiry page.

- **Fields:** name, mobile number, treatment (braces/aligners, whitening, implants, other), nearest clinic.
- **Contact preference:**
  - "Call me now" (default)
  - "Call me at a time I pick"
  - "WhatsApp me instead"
- **Language:** English / Hindi.
- **Clear disclosure before submit**, e.g.:
  > "HappySmile's virtual assistant will call you in about 2 minutes from +91 XXXXX XXXXX. It can book a consultation or connect you to our team. Say 'talk to a person' at any time."
- **Consent checkbox** for the call and WhatsApp updates.
- **Submit button:** "Request my call".
- **Optional:** after submit, show a confirmation state with the number that will call and a countdown.

### Screen 2 — "Leads" queue for the front desk (desktop, ~1280px wide)

What HappySmile sees afterwards.

- **Top strip for today:**
  - Enquiries received
  - Reached within 5 minutes
  - Consults booked by assistant
  - Waiting for staff
  - No answer (retrying)
- **Tabs or filters, in this order:**
  1. **Needs you** — handed over by assistant, sorted by waiting time, with a timer against a target (e.g. 15 minutes)
  2. **Booked by assistant**
  3. **No answer** — retry scheduled / WhatsApp sent
  4. **Standard callback** — pilot control group; staff call as usual
- **Handover reasons shown as tags:**
  - Asked for a person
  - Pain or swelling (urgent)
  - Price/EMI question
  - Clinical question
  - Couldn't understand
- **Click a lead to open a side panel** containing:
  - Name, treatment, clinic, language, time of enquiry, time first reached
  - 3-line AI call summary
  - Answers captured (treatment, preferred slot, urgency)
  - Transcript snippet + play-recording button
  - Actions: **Call now**, **Book slot**, **Mark not interested**
  - Feedback: "Was this handover right?" thumbs up / thumbs down
- **Booked leads** show slot, dentist, clinic, and "confirmation sent on WhatsApp", with a **Review** link so staff can check every booking.

### Tone and quality bar

- Clean, calm, clinical-but-friendly.
- Real buttons/inputs, readable contrast.
- **No emoji, no lorem ipsum.**

---

## Quick-Reference Checklist (derived)

**Hard constraints**
- [ ] Exactly two screens: mobile request form (~390px) + desktop leads queue (~1280px)
- [ ] Public URL, no login required
- [ ] Fictional names, numbers, phone numbers only; no real HappySmile branding
- [ ] No emoji, no lorem ipsum
- [ ] Brief ≤ 300 words
- [ ] AI-tool rejection note ≤ 3 lines (if used)

**Tensions the solution must address**
- **Ops head:** the 3x conversion stat comes from leads staff *happened* to call within 5 minutes — correlation, possibly selection bias (e.g. eager leads, quieter hours). The pilot control group ("Standard callback" tab) exists to test whether speed itself causes the lift.
- **Founder:** wants the AI to be indistinguishable from a human — conflicts with the required up-front disclosure ("HappySmile's virtual assistant will call you…") and the "talk to a person" escape hatch.
- **Front-desk lead:** wants every lead routed to staff — addressed via handovers, the "Needs you" queue, review links on every booking, and handover-quality feedback, keeping staff in the loop without making them the bottleneck.

**Key numbers**
- 12 clinics · ~300 enquiries/day · 4–6 hr current callback · ~30% booking rate · 3x conversion claim for <5 min calls · ~2 min target call-out · 15 min staff handover target · 4-week first ship
