# P0-15 — Speech-to-text and text-to-speech vendor trial

**Goal:** choose STT and TTS vendors that handle English, Hindi and Hinglish on phone-quality audio, before Hindi support is built in Phase 4. Weak Hindi recognition is a top pilot risk (architecture §16, row 2).

## 1. Test audio set

Record **100 short utterances** from **6–8 staff volunteers** (not patients) with a mix of ages and regional accents. Record on real phones over a phone line (8 kHz narrowband), not studio microphones.

| Category | Count | Examples |
|---|---|---|
| Names | 10 | "Mera naam Priyanka Sharma hai", "This is Venkatesh" |
| Dates and times | 20 | "kal shaam saade paanch baje", "next Tuesday after six", "parson subah", "paune do" |
| Numbers | 10 | Phone digits, "do log", "teen" |
| Treatments | 10 | braces, aligners, implant, whitening, root canal, "daant saaf" |
| **Handover phrases** | 20 | "insaan se baat karni hai", "talk to a person", "dard ho raha hai", "soojan hai", "khoon aa raha hai", "kitna kharcha hoga", "EMI milega?" |
| Yes / no / filler | 10 | "haan ji", "nahi", "hmm theek hai", "one minute" |
| Hinglish free speech | 20 | "Actually mujhe braces ke baare mein puchna tha, weekend pe ho sakta hai?" |

Record each category in **three conditions**: quiet room, street noise, speakerphone.

## 2. STT metrics

| Metric | Target | Why |
|---|---|---|
| Recall on handover phrases (pain, person, bleeding) | **≥ 99%** | Safety (EC-URG-01, EC-AI-06) |
| Date/time entity accuracy | ≥ 95% | Wrong-day bookings (EC-LANG-04/05) |
| Word error rate, Hinglish free speech | Record and compare | Overall understanding |
| Final-transcript latency after end of speech, p90 | ≤ 200 ms | Turn budget (architecture §7.4) |
| Endpointing (detects end of speech without cutting people off) | Qualitative score | Natural turn-taking |
| Mid-utterance language switching | Pass/fail per Hinglish item | Code-switching (EC-LANG-01) |

## 3. TTS evaluation

- Five front-desk staff rate 10 sample lines per voice, from 1 to 5, for naturalness, warmth and clarity on a phone. Include the disclosure line and a date read-back.
- Check pronunciation of names (Indian names in both scripts), clinic names and "₹" amounts.
- First-audio latency p90 ≤ 200 ms.
- Voice gender decision (affects Hindi verb forms in [ADR-003](../decisions/ADR-003-ai-disclosure.md)).

## 4. Scoring sheet

| Vendor | Handover-phrase recall | Date/time accuracy | Hinglish WER | STT p90 latency | TTS rating | TTS p90 latency | India data | Cost / min | Pick? |
|---|---|---|---|---|---|---|---|---|---|
| | | | | | | | | | |
| | | | | | | | | | |
| | | | | | | | | | |

**Rule:** a vendor below 99% recall on handover phrases is out, whatever its other scores.

## 5. Done when

- [ ] Audio set recorded with volunteers' written consent
- [ ] At least 3 STT and 2 TTS options tested
- [ ] Vendor chosen and recorded, with the scoring sheet attached
- [ ] Audio set kept as a regression test for Phase 4 (P4-02)
