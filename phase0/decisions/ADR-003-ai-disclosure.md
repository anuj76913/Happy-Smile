# ADR-003 — The assistant says it is a virtual assistant

| | |
|---|---|
| **Status** | Proposed — needs founder sign-off before build |
| **Plan item** | P0-06 |
| **Deciders** | Founder, PM; legal reviews the wording (P0-14) |
| **Architecture** | §2 principle 2, §7.2, §14; edge cases EC-AI-01 to 07 |

## Context

The founder said: *"The AI should sound so human that nobody realises it's AI."* The case brief's own form copy says the opposite: "HappySmile's virtual assistant will call you…". We need one policy before any script is written.

## Decision

The assistant **sounds as natural and warm as we can make it**, and **always says it is a virtual assistant**:
- on the form, before the person submits,
- in the first sentence of every call (pre-recorded, fixed in code),
- truthfully, whenever someone asks,
- with "talk to a person" always available.

## Why (talking points for the founder)

**What we keep from your ask:**
- A natural voice, the patient's name, short warm sentences, no robotic menus.
- Speed: the call comes in about 2 minutes, which no human team can match all day.
- We will test voice and tone variants in the pilot to make it feel as human as possible.

**What we won't do, and why:**
1. **Patients find out anyway.** Pauses and unusual answers give it away. Being caught pretending costs more trust than saying it up front, and trust is what a dental chain sells.
2. **It's a health conversation.** People share pain and medical worries. They have a right to know who, or what, they are talking to.
3. **Legal exposure.** Consent under India's data protection law must be informed. A hidden AI undermines that, and AI-disclosure rules are tightening in many markets.
4. **The front desk will only back it if it's honest.** The front-desk lead's trust is a launch requirement.
5. **We'll measure it.** The pilot tracks opt-outs and "asked for a person" handovers. If disclosure really hurts bookings, the data will show it, and we can discuss it with evidence.

## Approved wording (draft — needs native-speaker review for Hindi)

### Enquiry form disclosure (above the submit button)

**English:**
> HappySmile's virtual assistant will call you in about 2 minutes from +91 XXXXX XXXXX. It can book a consultation or connect you to our team. Say "talk to a person" at any time.

**Hindi:**
> HappySmile की वर्चुअल असिस्टेंट लगभग 2 मिनट में +91 XXXXX XXXXX से आपको कॉल करेगी। वह आपकी कंसल्टेशन बुक कर सकती है या आपको हमारी टीम से जोड़ सकती है। किसी भी समय "किसी इंसान से बात करनी है" कहें।

Outside the calling window, "in about 2 minutes" becomes "after 9:00 tomorrow" / "कल सुबह 9 बजे के बाद" (EC-TIME-01).

### Consent checkbox

**English:**
> I agree to a call from HappySmile's virtual assistant about this enquiry, and to WhatsApp updates about my appointment. The call may be recorded. I can ask it to stop at any time.

**Hindi:**
> मैं इस पूछताछ के बारे में HappySmile की वर्चुअल असिस्टेंट से कॉल और अपनी अपॉइंटमेंट के बारे में WhatsApp अपडेट पाने के लिए सहमत हूँ। कॉल रिकॉर्ड की जा सकती है। मैं किसी भी समय इसे रोकने के लिए कह सकता/सकती हूँ।

### Call opening (pre-recorded, first sentence)

**English:**
> Hi {first_name}, this is HappySmile's virtual assistant, calling about the {treatment} enquiry you just made. This call is recorded for quality. Is now a good time?

**Hindi:**
> नमस्ते {first_name} जी, मैं HappySmile की वर्चुअल असिस्टेंट बोल रही हूँ। आपने अभी {treatment} के बारे में जो पूछताछ की थी, उसी के लिए कॉल कर रही हूँ। यह कॉल क्वालिटी के लिए रिकॉर्ड की जा रही है। क्या अभी बात कर सकते हैं?

### "Are you a robot / AI?"

**English:**
> Yes, I'm HappySmile's virtual assistant. I can book your consultation, or I can ask someone from our team to call you. Which would you prefer?

**Hindi:**
> जी हाँ, मैं HappySmile की वर्चुअल असिस्टेंट हूँ। मैं आपकी कंसल्टेशन बुक कर सकती हूँ, या हमारी टीम से किसी को आपको कॉल करने के लिए कह सकती हूँ। आप क्या चाहेंगे?

The Hindi uses feminine verb forms ("करेगी", "बोल रही हूँ"). If a male voice is chosen, switch to masculine forms.

## Consequences

- The disclosure line is a fixed audio file. Prompt changes cannot remove it (G1 checks 100% disclosure).
- The output guardrail blocks any claim to be human (EC-AI-05).
- Wording changes create a new consent version (EC-PRIV-02).

## Sign-off

| Name | Role | Date |
|---|---|---|
| | Founder | |
| | Legal | |
| | Front-desk lead | |
