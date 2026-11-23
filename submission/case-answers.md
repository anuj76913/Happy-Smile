# HappySmile case — submission answers

Draft answers for the Google Form ([context.md Part 2](../docs/context.md#part-2--what-must-be-submitted-google-form)). Paste each section into its form field.

---

## 1. Mockup link

`<public URL — see prototype/README.md, "Deploy">`

Two screens: **Request a call** (mobile) and **Leads** (front desk, desktop). Each links to the other.

---

## 2. Brief (max 300 words)

<!-- brief:start -->
**Ship in 4 weeks (pilot in 3 clinics)**
- Enquiry form that says up front a virtual assistant will call within about 2 minutes, with consent.
- The assistant calls in English or Hindi, asks about treatment, urgency, clinic and timing, then books a consultation or hands over with a reason, summary and recording.
- Front-desk "Needs you" queue: 15-minute target (5 for pain), review of every assistant booking, thumbs up/down on each handover.
- Retries, then WhatsApp, for people who don't answer.
- Half of leads randomly stay on today's staff callback as a control group.

**Not doing:** hiding that it's AI; clinical advice; quoting final prices or EMI; booking treatments or payments; live transfer mid-call; all 12 clinics at once.

**Success metric:** enquiry to consultation booked within 7 days, assistant group versus control. It is what HappySmile earns from, and the control shows whether speed causes the lift. The ops head's "3x" compares leads staff *happened* to reach fast, often the eager people who answer first. I'll also check attendance, so bookings are real.

**Metric I'd ignore:** call duration and "sounds human" ratings. Neither predicts bookings, and chasing human-likeness pushes toward deceiving patients.

**Founder:** keep what matters in the ask (a warm, natural voice, the patient's name, speed no team can match) but disclose in the first sentence. People notice anyway, it's a health conversation, consent must be informed, and the front desk won't back a deceptive bot. We'll track opt-outs and revisit with data.

**Front-desk lead:** every lead stays visible to the team, even if not every lead reaches them first. They get full context on handovers, review every assistant booking, co-own the script and handover triggers, and can pause the assistant. Routine calls leave their day; judgement calls stay with them.
<!-- brief:end -->

---

## 3. Three questions before building anything

1. **How was "3x within 5 minutes" measured: from enquiry to the first dial or the first answered call, and compared with which leads?**
   If it compares people reached fast with everyone else, it mostly measures who is eager and who answers, not the effect of speed. The answer sets how big the control group must be and what lift is realistic. On synthetic data with a true effect of 1.3x, the same comparison shows 2.3x.

2. **Who will call back handovers, during which hours, and how much free time do front-desk staff really have?**
   The assistant reaches people in two minutes, but a handover that waits an hour wastes that and breaks the promise just made to the patient. The answer sets the handover targets, the share of leads given to the assistant, and what the assistant is allowed to promise.

3. **Where do clinic appointments live today, and can we read and book slots by API?**
   It decides whether the assistant can book real slots within 4 weeks or needs a slot list the front desk updates every morning. A wrong or double booking loses patient and staff trust faster than anything else.

---

## 4. How my solution is most likely to fail in the first month

**The front desk can't keep up with handovers, so fast first contact turns into a slow human follow-up.**

About a third of answered calls will need a person (price and EMI, clinical questions, "talk to a person", pain), plus WhatsApp replies from people we couldn't reach. These cluster in the 6–9 pm enquiry peak, which is also when the front desk is busiest with walk-ins and billing. The assistant tells a patient with a swollen gum that someone will call within minutes; the call comes 40 minutes later. That is worse than today, because we set the expectation. Staff then see the queue as extra work from "the bot", and the front-desk lead's doubts are confirmed.

**How I'd spot it:** under 80% of handovers called back on time, rising wait times in "Needs you", or any urgent case past 5 minutes.

**What I'd do:** name one queue owner per hour in each pilot clinic before launch, start the assistant on 20% of leads rather than 50%, only promise call-back times the queue can meet, lower the assistant's share if targets slip, and cut avoidable handovers with an approved "starting from" price card.

A related risk: weak Hindi/Hinglish recognition on noisy phone lines would push "couldn't understand" handovers up and feed the same failure.

---

## 5. If you used AI tools: one suggestion you rejected, and why (max 3 lines, optional)

Claude suggested letting the LLM (Groq) interpret every caller reply, including dates, slot choice and "pain or swelling". I rejected that after our test calls passed only 11 of 16: it got dates wrong and flagged pain that wasn't there. Now tested rules decide first, and the LLM only fills gaps they can't read: 16 of 16 passed.
