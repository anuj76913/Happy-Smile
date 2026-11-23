"""Everything the assistant can say, in English and Hindi (ADR-007).

The assistant speaks only these approved lines. The LLM is used to *understand* the
caller, not to write replies, so disclosure, tone and safety wording can't drift and
the Hindi can be reviewed line by line. The opening line carries the disclosure and
the recording notice and is the same on every call (architecture §7.2).

Hindi uses feminine verb forms for the assistant (ADR-003). Needs native-speaker review.
"""

from __future__ import annotations

from datetime import datetime

from ..config import IST

LINES: dict[str, dict[str, str]] = {
    # ---- opening (stage 1); first sentence always names the virtual assistant
    "greeting": {
        "en": "Hi {name}, this is HappySmile's virtual assistant, calling about the {treatment} enquiry you just made. "
              "This call is recorded for quality. Is now a good time to talk?",
        "hi": "नमस्ते {name} जी, मैं HappySmile की वर्चुअल असिस्टेंट बोल रही हूँ। आपने अभी {treatment} के बारे में जो पूछताछ की थी, "
              "उसी के लिए कॉल कर रही हूँ। यह कॉल क्वालिटी के लिए रिकॉर्ड की जा रही है। क्या अभी बात कर सकते हैं?",
    },
    "good_time": {"en": "Is now a good time to talk?", "hi": "क्या अभी बात कर सकते हैं?"},
    "ask_callback_time": {"en": "No problem. When would be a better time to call you, today or tomorrow?",
                          "hi": "कोई बात नहीं। आपको कब कॉल करना ठीक रहेगा, आज या कल?"},
    "callback_confirm": {"en": "Thank you. We'll call you back {when}. Goodbye.",
                         "hi": "धन्यवाद। हम आपको {when} फिर से कॉल करेंगे। नमस्ते।"},
    "callback_default": {"en": "No problem. We'll try again a little later today. Goodbye.",
                         "hi": "कोई बात नहीं। हम आज थोड़ी देर बाद फिर कोशिश करेंगे। नमस्ते।"},
    "someone_else": {"en": "Sorry to bother you. We'll try {name} again later. Goodbye.",
                     "hi": "परेशानी के लिए माफ़ कीजिए। हम {name} जी को बाद में फिर कॉल करेंगे। नमस्ते।"},
    "never_enquired": {"en": "I'm sorry for the trouble. We won't call this number again. Goodbye.",
                       "hi": "परेशानी के लिए माफ़ी चाहती हूँ। हम इस नंबर पर दोबारा कॉल नहीं करेंगे। नमस्ते।"},
    # ---- stage 2: confirm need
    "confirm_need": {"en": "You asked about {treatment}. Is that what you'd like a consultation for?",
                     "hi": "आपने {treatment} के बारे में पूछा था। क्या आप इसी के लिए कंसल्टेशन चाहते हैं?"},
    "ask_treatment": {"en": "Which treatment would you like to discuss: braces or aligners, whitening, implants, or something else?",
                      "hi": "आप किस इलाज के बारे में बात करना चाहेंगे: ब्रेसेस या अलाइनर, दाँतों की सफ़ेदी, इम्प्लांट, या कुछ और?"},
    # ---- stage 3: urgency screen
    "urgency": {"en": "Before we look at times, are you in any pain, or do you have any swelling right now?",
                "hi": "समय देखने से पहले, क्या आपको अभी कोई दर्द या सूजन है?"},
    # ---- stage 4: clinic and timing
    "clinic_confirm": {"en": "Is our {clinic} clinic the most convenient for you?",
                       "hi": "क्या हमारा {clinic} क्लिनिक आपके लिए सबसे सुविधाजनक है?"},
    "ask_clinic": {"en": "Which of our clinics would suit you best: {clinics}?",
                   "hi": "आपके लिए कौन-सा क्लिनिक सबसे ठीक रहेगा: {clinics}?"},
    "ask_time": {"en": "Which day and time of day suit you best? For example, tomorrow evening or Saturday morning.",
                 "hi": "आपके लिए कौन-सा दिन और समय ठीक रहेगा? जैसे, कल शाम या शनिवार सुबह।"},
    # ---- stage 5: offer slots
    "filler": {"en": "One moment, let me check the times.", "hi": "एक पल, मैं समय देख रही हूँ।"},
    "offer_two": {"en": "I can offer {s1} with {d1}, or {s2} with {d2}. Which would you prefer?",
                  "hi": "मेरे पास {s1} {d1} के साथ, या {s2} {d2} के साथ समय है। आपको कौन-सा ठीक रहेगा?"},
    "offer_one": {"en": "I can offer {s1} with {d1}. Does that work for you?",
                  "hi": "मेरे पास {s1} {d1} के साथ समय है। क्या यह ठीक रहेगा?"},
    "which_one": {"en": "Sorry, which one would you like: {s1}, or {s2}?",
                  "hi": "माफ़ कीजिए, आपको कौन-सा चाहिए: {s1}, या {s2}?"},
    "no_slots_alt": {"en": "I don't have anything free then. Would another day or time work for you?",
                     "hi": "उस समय कोई स्लॉट खाली नहीं है। क्या कोई और दिन या समय ठीक रहेगा?"},
    "slot_taken": {"en": "Sorry, that time was just taken.", "hi": "माफ़ कीजिए, वह समय अभी-अभी बुक हो गया।"},
    "ask_other_time": {"en": "No problem. Which other day or time would suit you?",
                       "hi": "कोई बात नहीं। कौन-सा दूसरा दिन या समय आपके लिए ठीक रहेगा?"},
    "go_ahead": {"en": "Sure, what would you like to know?", "hi": "ज़रूर, आप क्या जानना चाहेंगे?"},
    # ---- stage 6: book and confirm (read-back uses the booking result only, EC-BOOK-05)
    "booked": {"en": "Done. You're booked for {slot} with {dentist} at our {clinic} clinic. "
                     "You'll get a confirmation on WhatsApp.",
               "hi": "हो गया। आपकी कंसल्टेशन {slot} {dentist} के साथ हमारे {clinic} क्लिनिक में बुक है। "
                     "आपको WhatsApp पर पुष्टि मिल जाएगी।"},
    # ---- stage 7: close
    "anything_else": {"en": "Is there anything else I can help with?", "hi": "क्या मैं और किसी चीज़ में मदद कर सकती हूँ?"},
    "goodbye": {"en": "Thank you, {name}. Goodbye.", "hi": "धन्यवाद {name} जी। नमस्ते।"},
    "not_interested": {"en": "No problem at all. Thank you for your time. Goodbye.",
                       "hi": "कोई बात नहीं। समय देने के लिए धन्यवाद। नमस्ते।"},
    "stop_calling": {"en": "Understood. We won't contact you again about this enquiry. Goodbye.",
                     "hi": "समझ गई। इस पूछताछ के बारे में हम आपसे दोबारा संपर्क नहीं करेंगे। नमस्ते।"},
    # ---- identity, recovery, scope
    "robot": {"en": "Yes, I'm HappySmile's virtual assistant. I can book your consultation, or I can ask someone "
                    "from our team to call you. Which would you prefer?",
              "hi": "जी हाँ, मैं HappySmile की वर्चुअल असिस्टेंट हूँ। मैं आपकी कंसल्टेशन बुक कर सकती हूँ, या हमारी टीम से "
                    "किसी को आपको कॉल करने के लिए कह सकती हूँ। आप क्या चाहेंगे?"},
    "where_number": {"en": "You asked for a call on our website a few minutes ago. If you'd rather not be contacted, just say so.",
                     "hi": "आपने कुछ मिनट पहले हमारी वेबसाइट पर कॉल का अनुरोध किया था। अगर आप संपर्क नहीं चाहते, तो बस बता दीजिए।"},
    "off_topic": {"en": "I can help you book a dental consultation.", "hi": "मैं आपकी डेंटल कंसल्टेशन बुक करने में मदद कर सकती हूँ।"},
    "reprompt": {"en": "Sorry, could you say that again?", "hi": "माफ़ कीजिए, क्या आप फिर से बोल सकते हैं?"},
    "silence": {"en": "Are you still there?", "hi": "क्या आप लाइन पर हैं?"},
    "abuse_warning": {"en": "I'd like to help, but I'll have to end the call if that language continues.",
                      "hi": "मैं मदद करना चाहती हूँ, लेकिन ऐसी भाषा जारी रही तो मुझे कॉल खत्म करनी होगी।"},
    "abuse_end": {"en": "I'm ending the call now. Goodbye.", "hi": "मैं अब कॉल खत्म कर रही हूँ। नमस्ते।"},
    "dropped_line": {"en": "Sorry, I'm having trouble with the line. Our team will call you shortly.",
                     "hi": "माफ़ कीजिए, लाइन में दिक्कत है। हमारी टीम जल्द ही आपको कॉल करेगी।"},
    # ---- handovers: lead-in by reason, then a promise the queue can keep (architecture §8.3)
    "ho_asked_person": {"en": "Of course.", "hi": "ज़रूर।"},
    "ho_price_emi": {"en": "Our team can go through costs and payment options with you.",
                     "hi": "हमारी टीम आपको खर्च और भुगतान के विकल्पों के बारे में बताएगी।"},
    "ho_clinical": {"en": "That's a good question for the dentist, so I won't guess.",
                    "hi": "यह सवाल डेंटिस्ट से पूछना सबसे अच्छा रहेगा, इसलिए मैं अंदाज़ा नहीं लगाऊँगी।"},
    "ho_couldnt_understand": {"en": "Sorry, I'm having trouble understanding.", "hi": "माफ़ कीजिए, मुझे ठीक से समझ नहीं आ रहा।"},
    "ho_no_suitable_slot": {"en": "I'll ask our team to find a time that works for you.",
                            "hi": "मैं हमारी टीम से आपके लिए सही समय ढूँढने को कहूँगी।"},
    "ho_needs_staff": {"en": "I'll ask our team to help you with that.", "hi": "मैं इसके लिए हमारी टीम से मदद करवाऊँगी।"},
    "ho_minor": {"en": "Thank you for telling me. Our team will call to speak with a parent or guardian.",
                 "hi": "बताने के लिए धन्यवाद। हमारी टीम माता-पिता या अभिभावक से बात करने के लिए कॉल करेगी।"},
    "ho_recording_objection": {"en": "I understand, and I've stopped recording. I'll ask our team to call you instead.",
                               "hi": "मैं समझती हूँ, मैंने रिकॉर्डिंग बंद कर दी है। मैं हमारी टीम से आपको कॉल करवाऊँगी।"},
    "ho_system_fallback": {"en": "Sorry, I'm having a technical problem.", "hi": "माफ़ कीजिए, कुछ तकनीकी दिक्कत आ रही है।"},
    "ho_booking_paused": {"en": "I'll ask our team to book a time that works for you.",
                          "hi": "मैं हमारी टीम से आपके लिए सही समय बुक करवाऊँगी।"},
    "transferring": {"en": "Of course. I'm connecting you to {staff} at our {clinic} clinic now. If the line drops, they'll call you straight back.",
                     "hi": "ज़रूर। मैं आपको अभी हमारे {clinic} क्लिनिक में {staff} से जोड़ रही हूँ। अगर लाइन कट जाए, तो वे तुरंत आपको वापस कॉल करेंगे।"},
    "lang_switched": {"en": "Sure, let's continue in English.", "hi": "ज़रूर, हम हिंदी में बात करते हैं।"},
    "ho_pain_swelling": {"en": "I'm sorry to hear that. I'm passing this to our clinic team now.",
                         "hi": "यह सुनकर दुख हुआ। मैं अभी यह बात हमारी क्लिनिक टीम को बता रही हूँ।"},
    "ho_emergency": {"en": "That sounds serious. Please go to the nearest emergency department, or call 112 or 108, now. "
                           "I'm also alerting our clinic team.",
                     "hi": "यह गंभीर लग रहा है। कृपया अभी नज़दीकी इमरजेंसी में जाएँ, या 112 या 108 पर कॉल करें। "
                           "मैं हमारी क्लिनिक टीम को भी बता रही हूँ।"},
    "ho_distress": {"en": "I'm really sorry you're going through this. If you feel unsafe, please call the Tele-MANAS "
                          "helpline on 14416, or 112.",
                    "hi": "मुझे बहुत दुख है कि आप इससे गुज़र रहे हैं। अगर आप सुरक्षित महसूस नहीं कर रहे, तो कृपया Tele-MANAS "
                          "हेल्पलाइन 14416 या 112 पर कॉल करें।"},
    "promise_minutes": {"en": "Someone from our {clinic} team will call you within {minutes} minutes. Thank you, goodbye.",
                        "hi": "हमारी {clinic} टीम से कोई {minutes} मिनट के अंदर आपको कॉल करेगा। धन्यवाद, नमस्ते।"},
    "promise_morning": {"en": "Someone from our {clinic} team will call you first thing tomorrow morning. Thank you, goodbye.",
                        "hi": "हमारी {clinic} टीम से कोई कल सुबह सबसे पहले आपको कॉल करेगा। धन्यवाद, नमस्ते।"},
    "safe_care_tonight": {"en": "If it gets worse tonight, please go to the nearest emergency department.",
                          "hi": "अगर आज रात तकलीफ़ बढ़े, तो कृपया नज़दीकी इमरजेंसी में जाएँ।"},
    "safe_care": {"en": "If it gets worse, please visit the clinic or emergency care.",
                  "hi": "अगर तकलीफ़ बढ़े, तो कृपया क्लिनिक या इमरजेंसी में जाएँ।"},
}

TREATMENT = {
    "braces": {"en": "braces or aligners", "hi": "ब्रेसेस या अलाइनर"},
    "whitening": {"en": "teeth whitening", "hi": "दाँतों की सफ़ेदी"},
    "implants": {"en": "dental implants", "hi": "डेंटल इम्प्लांट"},
    "other": {"en": "dental", "hi": "दाँतों के इलाज"},
}

_WEEKDAY_HI = ["सोमवार", "मंगलवार", "बुधवार", "गुरुवार", "शुक्रवार", "शनिवार", "रविवार"]
_MONTH_HI = ["जनवरी", "फ़रवरी", "मार्च", "अप्रैल", "मई", "जून", "जुलाई", "अगस्त", "सितंबर", "अक्टूबर", "नवंबर", "दिसंबर"]


def say(key: str, lang: str, **kw) -> str:
    return LINES[key][lang if lang in ("en", "hi") else "en"].format(**kw)


def treatment_word(t: str, lang: str) -> str:
    return TREATMENT.get(t, TREATMENT["other"])[lang]


def slot_phrase(start: datetime, now: datetime, lang: str) -> str:
    """Always an explicit date, never just 'kal' (EC-LANG-04/05/06)."""
    local, today = start.astimezone(IST), now.astimezone(IST).date()
    offset = (local.date() - today).days
    h, m = local.hour, local.minute
    hm = f"{h % 12 or 12}:{m:02d}"
    if lang == "hi":
        rel = "आज, " if offset == 0 else "कल, " if offset == 1 else ""
        part = "सुबह" if h < 12 else "दोपहर" if h < 16 else "शाम" if h < 19 else "रात"
        return f"{rel}{_WEEKDAY_HI[local.weekday()]} {local.day} {_MONTH_HI[local.month - 1]}, {part} {hm} बजे"
    rel = "today, " if offset == 0 else "tomorrow, " if offset == 1 else ""
    return f"{rel}{local.strftime('%A')} {local.day} {local.strftime('%B')}, at {hm} {'am' if h < 12 else 'pm'}"


def fixed_audio_manifest() -> list[dict]:
    """Lines to pre-generate as audio once the TTS vendor is chosen (plan P3-03).

    The disclosure sentence is the same on every call, so it's recorded once per
    language and treatment; only the caller's name is synthesised live.
    """
    out = []
    for lang in ("en", "hi"):
        for t in TREATMENT:
            text = say("greeting", lang, name="{name}", treatment=treatment_word(t, lang))
            out.append({"id": f"greeting.{t}.{lang}", "lang": lang, "text": text, "live_part": "{name}"})
        for key in ("filler", "silence", "reprompt", "dropped_line", "ho_emergency", "ho_distress", "stop_calling"):
            out.append({"id": f"{key}.{lang}", "lang": lang, "text": LINES[key][lang], "live_part": None})
    return out
