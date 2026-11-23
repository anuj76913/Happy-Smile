# P0-11 — WhatsApp message templates (drafts for Meta approval)

Submit these through the WhatsApp Business account as soon as it exists. Approval can take days, and rejections need rewording. All are **Utility** templates (transactional, triggered by the person's own request). None are marketing.

**Rules followed** (common rejection causes):
- No template starts or ends with a variable.
- No two variables next to each other.
- No promotional language, offers or discounts.
- Every message says how to stop messages.
- Sample values are fictional.

Hindi drafts need native-speaker review before submission. Each language is a separate submission under the same template name.

---

## 1. `enquiry_ack_v1` — acknowledgement (sent immediately; required for out-of-hours enquiries)

Used by: architecture §4.4 (calling window), EC-TIME-01.

**English**
```
Hi {{1}}, thank you for your enquiry about {{2}} at HappySmile {{3}}. Our virtual assistant will call you {{4}} from {{5}}. Reply STOP if you do not want to be contacted.
```
Samples: {{1}} Asha · {{2}} braces · {{3}} Sector 9 · {{4}} after 9:00 tomorrow · {{5}} +91 90000 00000

**Hindi**
```
नमस्ते {{1}} जी, HappySmile {{3}} में {{2}} के बारे में पूछताछ के लिए धन्यवाद। हमारी वर्चुअल असिस्टेंट आपको {{4}} {{5}} से कॉल करेगी। संपर्क नहीं चाहते तो STOP लिखकर भेजें।
```

## 1b. `whatsapp_hello_v1` — "WhatsApp me instead" (added in Phase 4)

Used by: assistant-group leads who choose WhatsApp on the form; a person replies in the chat.

**English**
```
Hi {{1}}, thank you for your enquiry about {{2}} at HappySmile {{3}}. Our team will reply here during clinic hours, 9 am to 9 pm. Reply STOP if you do not want to be contacted.
```

**Hindi**
```
नमस्ते {{1}} जी, HappySmile {{3}} में {{2}} के बारे में पूछताछ के लिए धन्यवाद। हमारी टीम क्लिनिक के समय, सुबह 9 से रात 9 बजे, यहीं जवाब देगी। संपर्क नहीं चाहते तो STOP लिखें।
```

## 2. `booking_confirm_v1` — consultation booked

Used by: architecture §4.7, §6.1.

**English**
```
Your consultation is booked.
Date: {{1}}
Time: {{2}}
Clinic: HappySmile {{3}}
Dentist: {{4}}
Address: {{5}}
To change the time, reply to this message. Reply STOP to stop messages.
```
Samples: {{1}} Tue, 3 Dec · {{2}} 6:30 pm · {{3}} Sector 9 · {{4}} Dr. Meera Rao · {{5}} 12 Lake Road, Sector 9
Quick-reply buttons: `Change time` · `Cancel`

**Hindi**
```
आपकी कंसल्टेशन बुक हो गई है।
तारीख: {{1}}
समय: {{2}}
क्लिनिक: HappySmile {{3}}
डेंटिस्ट: {{4}}
पता: {{5}}
समय बदलने के लिए इस मैसेज का जवाब दें। मैसेज बंद करने के लिए STOP लिखें।
```
Buttons: `समय बदलें` · `रद्द करें`

## 3. `no_answer_v1` — after retries are exhausted

Used by: architecture §4.4 retry policy, §6.3.

**English**
```
Hi {{1}}, we tried calling you about your {{2}} enquiry but could not reach you. Reply here with a good time to call, and our team will get back to you. Reply STOP if you do not want to be contacted.
```

**Hindi**
```
नमस्ते {{1}} जी, हमने आपकी {{2}} संबंधी पूछताछ के लिए कॉल किया, पर बात नहीं हो पाई। कॉल के लिए सही समय यहाँ लिखकर भेजें, हमारी टीम आपसे संपर्क करेगी। संपर्क नहीं चाहते तो STOP लिखें।
```

## 4. `call_reminder_v1` — scheduled call reminder (10 minutes before)

Used by: "Call me at a time I pick" (architecture §5 notes).

**English**
```
Hi {{1}}, as you asked, HappySmile's virtual assistant will call you at {{2}} from {{3}}. Reply CHANGE to pick another time, or STOP to cancel.
```

**Hindi**
```
नमस्ते {{1}} जी, आपके कहे अनुसार HappySmile की वर्चुअल असिस्टेंट आपको {{2}} बजे {{3}} से कॉल करेगी। समय बदलने के लिए CHANGE और रद्द करने के लिए STOP लिखें।
```

## 5. `booking_update_v1` — booking changed or cancelled by staff

Used by: booking review (EC-POST-01, EC-POST-02).

**English**
```
Update on your HappySmile consultation: {{1}}. New details: {{2}}. Reply to this message if you have any questions.
```
Samples: {{1}} the time has changed · {{2}} Wed, 4 Dec at 5:00 pm with Dr. Meera Rao

**Hindi**
```
आपकी HappySmile कंसल्टेशन के बारे में अपडेट: {{1}}। नई जानकारी: {{2}}। कोई सवाल हो तो इस मैसेज का जवाब दें।
```

## 5b. `appointment_reminder_v1` — 24 h before the consultation (added in Phase 6)

**English**
```
Hi {{1}}, a reminder of your HappySmile consultation {{2}} at our {{3}} clinic, {{4}}. To change the time, reply to this message. Reply STOP to stop messages.
```
**Hindi**
```
नमस्ते {{1}} जी, याद दिला दें कि आपकी HappySmile कंसल्टेशन {{2}} हमारे {{3}} क्लिनिक ({{4}}) में है। समय बदलने के लिए इस मैसेज का जवाब दें। मैसेज बंद करने के लिए STOP लिखें।
```

## 5c. `no_show_v1` — missed consultation (added in Phase 6)

**English**
```
Hi {{1}}, we missed you at HappySmile {{2}} today. Reply here if you would like a new time, and our team will help. Reply STOP to stop messages.
```
**Hindi**
```
नमस्ते {{1}} जी, आज HappySmile {{2}} में आपसे मुलाकात नहीं हो पाई। नया समय चाहिए तो यहाँ जवाब दें, हमारी टीम मदद करेगी। मैसेज बंद करने के लिए STOP लिखें।
```

## 6. `opt_out_confirm_v1` — after STOP or "don't call me"

Used by: EC-MAN-06, EC-WA-06.

**English**
```
You will not receive further calls or messages from HappySmile about this enquiry. If you change your mind, you can request a call on our website at any time.
```

**Hindi**
```
अब आपको इस पूछताछ के बारे में HappySmile से कोई कॉल या मैसेज नहीं आएगा। अगर आप फिर से बात करना चाहें, तो कभी भी हमारी वेबसाइट पर कॉल का अनुरोध कर सकते हैं।
```

---

## Submission tracker

| Template | Language | Submitted | Status | Notes |
|---|---|---|---|---|
| enquiry_ack_v1 | en / hi | | | |
| whatsapp_hello_v1 | en / hi | | | Added in Phase 4 |
| appointment_reminder_v1 | en / hi | | | Added in Phase 6 |
| no_show_v1 | en / hi | | | Added in Phase 6 |
| booking_confirm_v1 | en / hi | | | |
| no_answer_v1 | en / hi | | | |
| call_reminder_v1 | en / hi | | | |
| booking_update_v1 | en / hi | | | |
| opt_out_confirm_v1 | en / hi | | | |

## SMS fallback

Edge case EC-WA-01 proposes SMS when WhatsApp fails. Sending SMS in India needs the sender and its message templates registered on the telecom operators' DLT platform, which also takes time. If the SMS fallback is accepted, start that registration now (P0-16 in the [Phase 0 tracker](../README.md)).
