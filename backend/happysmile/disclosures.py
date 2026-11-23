"""Versioned disclosure and consent wording shown on the enquiry form.

The form fetches the wording for the chosen clinic and language, shows it, and sends
the version back. The consent record stores that version, so we always know the exact
text a person agreed to (architecture §14, EC-PRIV-02).

Which wording applies depends on the clinic's assistant share (ADR-003, architecture §4.3):
  share = 0      -> "team"       (no AI call possible; Phase 2)
  0 < share < 1  -> "mixed"      (the arm is decided after submit, so both are disclosed)
  share = 1      -> "assistant"

Never edit a text in place. Add a new version (bump the suffix); the database refuses
changes to a registered version.
"""

from __future__ import annotations

import hashlib

from psycopg import Connection

_TEAM_DISC_EN = ("A member of our team at your chosen HappySmile clinic will call you back during clinic "
                 "hours (9 am to 9 pm). If you choose WhatsApp, we will message you instead.")
_TEAM_CONS_EN = ("I agree to a call from HappySmile's team about this enquiry, and to WhatsApp updates "
                 "about my appointment. I can ask you to stop at any time.")
_TEAM_DISC_HI = ("आपके चुने हुए HappySmile क्लिनिक की टीम का सदस्य क्लिनिक के समय (सुबह 9 से रात 9 बजे) में "
                 "आपको कॉल करेगा। अगर आप WhatsApp चुनते हैं, तो हम आपको मैसेज करेंगे।")
_TEAM_CONS_HI = ("मैं इस पूछताछ के बारे में HappySmile की टीम से कॉल और अपनी अपॉइंटमेंट के बारे में WhatsApp "
                 "अपडेट पाने के लिए सहमत हूँ। मैं किसी भी समय इसे रोकने के लिए कह सकता/सकती हूँ।")

_MIXED_DISC_EN = ("You will get a call from HappySmile: either our virtual assistant, usually within about "
                  "2 minutes from {caller_id}, or a member of our team during clinic hours. The assistant can "
                  "book a consultation or connect you to our team. Say “talk to a person” at any time.")
_MIXED_CONS_EN = ("I agree to a call from HappySmile (our team or our virtual assistant) about this enquiry, "
                  "and to WhatsApp updates about my appointment. Calls from the virtual assistant may be "
                  "recorded. I can ask you to stop at any time.")
_MIXED_DISC_HI = ("आपको HappySmile से कॉल आएगी: या तो हमारी वर्चुअल असिस्टेंट से, आमतौर पर लगभग 2 मिनट में "
                  "{caller_id} से, या क्लिनिक के समय में हमारी टीम के किसी सदस्य से। असिस्टेंट आपकी कंसल्टेशन "
                  "बुक कर सकती है या आपको हमारी टीम से जोड़ सकती है। किसी भी समय “किसी इंसान से बात करनी "
                  "है” कहें।")
_MIXED_CONS_HI = ("मैं इस पूछताछ के बारे में HappySmile (हमारी टीम या वर्चुअल असिस्टेंट) से कॉल और अपनी "
                  "अपॉइंटमेंट के बारे में WhatsApp अपडेट पाने के लिए सहमत हूँ। वर्चुअल असिस्टेंट की कॉल रिकॉर्ड "
                  "की जा सकती है। मैं किसी भी समय इसे रोकने के लिए कह सकता/सकती हूँ।")

_ASSIST_DISC_EN = ("HappySmile's virtual assistant will call you in about 2 minutes from {caller_id}. It can "
                   "book a consultation or connect you to our team. Say “talk to a person” at any time.")
_ASSIST_CONS_EN = ("I agree to a call from HappySmile's virtual assistant about this enquiry, and to WhatsApp "
                   "updates about my appointment. The call may be recorded. I can ask it to stop at any time.")
_ASSIST_DISC_HI = ("HappySmile की वर्चुअल असिस्टेंट लगभग 2 मिनट में {caller_id} से आपको कॉल करेगी। वह आपकी "
                   "कंसल्टेशन बुक कर सकती है या आपको हमारी टीम से जोड़ सकती है। किसी भी समय “किसी इंसान से "
                   "बात करनी है” कहें।")
_ASSIST_CONS_HI = ("मैं इस पूछताछ के बारे में HappySmile की वर्चुअल असिस्टेंट से कॉल और अपनी अपॉइंटमेंट के बारे "
                   "में WhatsApp अपडेट पाने के लिए सहमत हूँ। कॉल रिकॉर्ड की जा सकती है। मैं किसी भी समय इसे रोकने "
                   "के लिए कह सकता/सकती हूँ।")

# version -> (variant, language, disclosure template, consent text)
VERSIONS: dict[str, tuple[str, str, str, str]] = {
    "team-en-v1": ("team", "en", _TEAM_DISC_EN, _TEAM_CONS_EN),
    "team-hi-v1": ("team", "hi", _TEAM_DISC_HI, _TEAM_CONS_HI),
    "mixed-en-v1": ("mixed", "en", _MIXED_DISC_EN, _MIXED_CONS_EN),
    "mixed-hi-v1": ("mixed", "hi", _MIXED_DISC_HI, _MIXED_CONS_HI),
    "assistant-en-v1": ("assistant", "en", _ASSIST_DISC_EN, _ASSIST_CONS_EN),
    "assistant-hi-v1": ("assistant", "hi", _ASSIST_DISC_HI, _ASSIST_CONS_HI),
}

# The version the form should use today for each (variant, language).
CURRENT = {(v[0], v[1]): k for k, v in VERSIONS.items()}


def variant_for_share(share: float, is_pilot: bool) -> str:
    if not is_pilot or share <= 0:
        return "team"
    return "assistant" if share >= 1 else "mixed"


def _sha(disclosure: str, consent: str) -> str:
    return hashlib.sha256((disclosure + "\n---\n" + consent).encode("utf-8")).hexdigest()


def render(version: str, caller_id: str) -> dict:
    variant, lang, disc, cons = VERSIONS[version]
    return {"version": version, "variant": variant, "language": lang,
            "disclosure": disc.format(caller_id=caller_id), "consent": cons}


def register_all(conn: Connection) -> None:
    """Insert any new versions. Fails loudly if a registered version's text was edited."""
    for version, (variant, lang, disc, cons) in VERSIONS.items():
        sha = _sha(disc, cons)
        row = conn.execute("SELECT sha256 FROM disclosure_version WHERE version = %s", (version,)).fetchone()
        if row is None:
            conn.execute(
                "INSERT INTO disclosure_version (version, variant, language, disclosure, consent, sha256) "
                "VALUES (%s, %s, %s, %s, %s, %s)", (version, variant, lang, disc, cons, sha))
        elif row["sha256"] != sha:
            raise RuntimeError(f"Disclosure {version} was edited after release. Add a new version instead.")
