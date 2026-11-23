# P0-13 / P0-14 — Legal and compliance review brief

**For:** HappySmile's legal / compliance adviser
**From:** pilot PM
**Needed by:** go-live gate G2 (pilot week 3)

We plan a 4-week pilot in 2–3 clinics. When someone requests a call on the website, an AI voice assistant calls them within minutes, says it is a virtual assistant, asks a few questions, and either books a consultation or passes them to clinic staff. Calls are recorded. Booking confirmations go by WhatsApp. The language model is provided by Groq, which processes data outside India.

For each item below, we give our proposed position. We need you to confirm it or tell us what to change.

| # | Topic | Our proposed position | Decision needed |
|---|---|---|---|
| 1 | **Consent (DPDP Act, 2023)** | A single, unticked checkbox covers the AI call and WhatsApp updates for this enquiry. The wording names the virtual assistant and recording ([ADR-003](../decisions/ADR-003-ai-disclosure.md)). Consent records are versioned and kept. | Is one checkbox enough, or do call and WhatsApp need separate consent? Is the wording adequate? |
| 2 | **Withdrawal** | "Stop", "don't call me", or replying STOP removes the person from all calls and messages for this enquiry. | Any other required withdrawal routes? |
| 3 | **Telecom classification** | These are service calls the person asked for, made within 09:00–21:00 from a registered number. No promotion. | Which number series and registrations apply? Does the DND registry restrict these calls given explicit consent (EC-CALL-14)? |
| 4 | **Call recording** | Announced in the first sentence. Kept 90 days, then deleted. If the person objects, recording stops and staff call back instead (EC-AI-07). | Retention period? Is an announcement enough? |
| 5 | **Health information** | The assistant does not ask for medical history. Anything clinical goes to staff. Health details the caller volunteers stay in the transcript and are redacted from analytics. | Is this adequate? Any extra safeguards for health data? |
| 6 | **Cross-border processing (Groq)** | Transcripts are sent to Groq for processing, with phone numbers removed and names minimised. Groq's answers on location, retention and training use will be attached ([groq/README.md](groq/README.md)). | Is transfer acceptable? Is a DPA required? Do we need extra redaction or an India-hosted alternative? |
| 7 | **AI disclosure** | Disclosed on the form, in the first sentence, and whenever asked. Never claims to be human. | Any requirement beyond this? |
| 8 | **Minors** | If the caller says they are under 18, staff take over and no booking is made without a guardian. | Is that the right policy? |
| 9 | **Emergencies** | For severe symptoms, the assistant advises calling 112 / 108 or going to an emergency department, then hands over urgently. It never diagnoses. | Approve the wording? |
| 10 | **Data rights** | Deletion requests are handled by staff: the lead, recordings and transcripts are deleted, with a minimal audit record kept (EC-PRIV-01). | Response time? What must the audit record keep? |
| 11 | **Vendors** | Telephony, speech-to-text, text-to-speech, WhatsApp and Groq act as processors. | Which contracts/DPAs are needed before go-live? |
| 12 | **SMS fallback** (if adopted) | Sent only for booking confirmations when WhatsApp fails. | DLT registration required? Template approval? |

## Attachments to include

- Form and consent wording (English and Hindi): [ADR-003](../decisions/ADR-003-ai-disclosure.md)
- WhatsApp templates: [whatsapp-templates.md](whatsapp-templates.md)
- Data model and retention: architecture §11, §14
- Groq answers: [groq/README.md](groq/README.md) (P0-13 section)

## Sign-off

| Item | Approved / changed | By | Date |
|---|---|---|---|
| 1–12 | | | |
