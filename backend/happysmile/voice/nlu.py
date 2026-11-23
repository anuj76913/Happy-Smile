"""Understanding what the caller said, per conversation stage.

Two implementations with the same output:
  RuleNLU  - deterministic English/Hindi/Hinglish patterns. Always available; also the
             fallback whenever Groq is slow or fails.
  GroqNLU  - Groq JSON mode for paraphrases; validated, falls back to rules on any problem.

Output is structured only (intent + entities). The agent decides what to do and says
approved lines (ADR-007), so the model never writes what the caller hears.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass

from .. import llm
from ..config import get_settings

PROMPT_VERSION = "nlu-v1"

INTENTS = ("yes", "no", "not_now", "not_interested", "provide", "choose", "unclear")


@dataclass
class Understanding:
    intent: str = "unclear"
    treatment: str | None = None
    clinic: str | None = None
    day_offset: int | None = None
    start_min: int | None = None   # earliest acceptable time of day, minutes from midnight
    end_min: int | None = None     # latest acceptable time of day
    choice: int | None = None      # 0 or 1 when picking an offered slot
    source: str = "rules"


def _rx(*p: str) -> re.Pattern:
    return re.compile("|".join(p), re.IGNORECASE)


YES = _rx(r"\b(yes|yeah|yea|yep|yup|sure|ok|okay|fine|go ahead|good|haan|haa|han|hanji|ji haan|jee|ji|theek|thik|bilkul|zaroor|correct|right|perfect|works|sounds good|book it|that one|chalega|done)\b",
          r"हाँ|हां|जी|ठीक|बिल्कुल|ज़रूर|चलेगा")
NO = _rx(r"\b(no|nope|nah|nahi|nahin|nhi|na|not really|mat)\b", r"नहीं|ना\b")
# Clear refusals that contain loose "yes" words ("neither works", "that doesn't suit me").
NO_STRONG = _rx(r"\bneither\b", r"\bnone of\b", r"(doesn'?t|don'?t|won'?t|does not|do not|will not|not) (work|suit|fit)",
                r"not (good|possible|convenient)", r"\bkoi bhi nahi\b", r"dono nahi", r"नहीं चलेगा|दोनों नहीं")
NOT_NOW = _rx(r"\bbusy\b", r"not (a good|the right) time", r"not now", r"\blater\b", r"call (me )?back", r"\bmeeting\b", r"\bdriving\b",
              r"abhi nahi", r"baad mein", r"thodi der", r"बाद में|अभी नहीं")
NOT_INTERESTED = _rx(r"not interested", r"no thanks", r"no thank you", r"(don'?t|do not) (want|need)", r"nahi chahiye", r"interest nahi",
                     r"changed my mind", r"नहीं चाहिए")

TREATMENTS = [
    ("braces", _rx(r"brace", r"align", r"invisalign", r"straighten", r"crooked", r"ब्रेस", r"अलाइनर")),
    ("whitening", _rx(r"whit", r"bleach", r"\bsafed\b", r"yellow", r"सफ़ेद|सफेद")),
    ("implants", _rx(r"implant", r"missing (tooth|teeth)", r"daant lagwa", r"इम्प्लांट")),
    ("other", _rx(r"root canal", r"clean", r"filling", r"crown", r"extract", r"check ?up", r"\bsaaf\b", r"something else", r"kuch aur")),
]

CLINICS = {"riverside": _rx(r"river ?side"), "hillcrest": _rx(r"hill ?crest"), "lotus": _rx(r"lotus")}

_WEEKDAYS = [  # Monday = 0
    _rx(r"\bmon(day)?\b", r"som ?var", r"सोमवार"), _rx(r"\btue(s|sday)?\b", r"mangal", r"मंगलवार"),
    _rx(r"\bwed(nesday)?\b", r"budh", r"बुधवार"), _rx(r"\bthu(rs|rsday)?\b", r"guru ?var", r"brihaspat", r"गुरुवार"),
    _rx(r"\bfri(day)?\b", r"shukra", r"शुक्रवार"), _rx(r"\bsat(urday)?\b", r"shani", r"शनिवार"),
    _rx(r"\bsun(day)?\b", r"ravi ?var", r"itvar", r"इतवार|रविवार"),
]
_HI_NUM = {"ek": 1, "do": 2, "teen": 3, "char": 4, "chaar": 4, "paanch": 5, "panch": 5, "chhe": 6, "che": 6, "chheh": 6,
           "saat": 7, "aath": 8, "nau": 9, "das": 10, "gyarah": 11, "barah": 12, "baarah": 12}


_DEV_DIGITS = str.maketrans("०१२३४५६७८९", "0123456789")
_DEV_WORDS = {"साढ़े": "saade", "साढे": "saade", "सवा": "sawa", "पौने": "paune", "डेढ़": "dedh", "डेढ": "dedh",
              "ढाई": "dhai", "बजे": "baje", "एक": "ek", "दो": "do", "तीन": "teen", "चार": "char", "पांच": "paanch",
              "पाँच": "paanch", "छह": "chhe", "छः": "chhe", "सात": "saat", "आठ": "aath", "नौ": "nau", "दस": "das",
              "ग्यारह": "gyarah", "बारह": "barah", "शाम": "shaam", "सुबह": "subah", "दोपहर": "dopahar", "रात": "raat"}
_DEV_RX = re.compile("(?<![ऀ-ॿ])(" + "|".join(sorted(map(re.escape, _DEV_WORDS), key=len, reverse=True))
                     + ")(?![ऀ-ॿ])")


def normalise_spoken(text: str) -> str:
    """Speech recognisers write times their own way: "साढ़े पांच बजे", "६:३० बजे", "6 p.m.".
    Map these onto the forms the time parser reads (romanised Hindi numbers, am/pm)."""
    t = (text or "").translate(_DEV_DIGITS)
    t = re.sub(r"\b([ap])\.\s?m\.?", r"\1m", t, flags=re.IGNORECASE)
    t = _DEV_RX.sub(lambda m: _DEV_WORDS[m.group(1)], t)
    return t.replace("के बाद", "ke baad").replace("से पहले", "se pehle")


def parse_day(text: str, weekday_today: int) -> int | None:
    t = text.lower()
    if re.search(r"day after tomorrow|\bparso[n]?\b|परसों", t):
        return 2
    if re.search(r"\btoday\b|\baaj\b|आज", t):
        return 0
    if re.search(r"\btomorrow\b|\bkal\b|कल", t):  # booking context: "kal" means tomorrow (EC-LANG-04)
        return 1
    if re.search(r"\bweekend\b", t):
        return (5 - weekday_today) % 7  # the coming Saturday (today if it is Saturday)
    if re.search(r"next week|agle hafte|अगले हफ्ते", t):
        return 7 - weekday_today
    for i, rx in enumerate(_WEEKDAYS):
        if rx.search(t):
            return (i - weekday_today) % 7
    return None


def _hour(h: int, t: str) -> int:
    if re.search(r"\bam\b|subah|morning|सुबह", t) and h < 12:
        return h
    if re.search(r"\bpm\b|shaam|sham|evening|raat|night|dopahar|afternoon|शाम|रात|दोपहर", t) and h < 12:
        return h + 12
    return h + 12 if 1 <= h <= 8 else h  # clinic hours: "at 6" means 6 pm


def parse_time(text: str) -> tuple[int | None, int | None]:
    """Returns (start_min, end_min) of the acceptable window."""
    t = text.lower()
    m = re.search(r"\b(saade|sade|sawa|paune|dedh|dhai)\s+(\w+)", t)
    exact = None
    if m:
        word, num = m.group(1), m.group(2)
        n = _HI_NUM.get(num, int(num) if num.isdigit() else None)
        if word in ("dedh",):
            exact = (13, 30)
        elif word == "dhai":
            exact = (14, 30)
        elif n:
            h = _hour(n, t)
            exact = {"saade": (h, 30), "sade": (h, 30), "sawa": (h, 15), "paune": (h - 1, 45)}[word]
    if exact is None:
        m = re.search(r"\b(\d{1,2})(?:[:.](\d{2}))?\s*(am|pm|baje|o'?clock)?\b", t)
        if m and (m.group(2) or m.group(3)) and 1 <= int(m.group(1)) <= 12:
            exact = (_hour(int(m.group(1)), t), int(m.group(2) or 0))
        else:
            m = re.search(r"\b(" + "|".join(_HI_NUM) + r")\s+baje", t)
            if m:
                exact = (_hour(_HI_NUM[m.group(1)], t), 0)
    if exact:
        mins = exact[0] * 60 + exact[1]
        if re.search(r"\bafter\b|ke baad|baad|के बाद", t):
            return mins, 21 * 60
        if re.search(r"\bbefore\b|se pehle|पहले", t):
            return 9 * 60, mins
        return mins - 60, mins + 60
    if re.search(r"morning|subah|सुबह", t):
        return 9 * 60, 12 * 60
    if re.search(r"afternoon|dopahar|lunch|दोपहर", t):
        return 12 * 60, 16 * 60
    if re.search(r"evening|shaam|sham|after work|शाम", t):
        return 16 * 60, 21 * 60
    if re.search(r"night|raat|रात", t):
        return 19 * 60, 21 * 60
    return None, None


def parse_choice(text: str, offered: list[dict]) -> int | None:
    t = text.lower()
    if re.search(r"\b(first|1st|earlier|pehl[ae]|pahla)\b", t) or re.search(r"पहला|पहले वाला", t):
        return 0
    if len(offered) > 1 and (re.search(r"\b(second|2nd|later one|latter|dusr[ae]|doosr[ae])\b", t) or re.search(r"दूसरा", t)):
        return 1
    s, e = parse_time(text)
    if s is not None and (e - s) <= 120:  # a specific time: pick the closest offered slot
        centre = (s + e) // 2
        best = min(range(len(offered)), key=lambda i: abs(offered[i]["minute_of_day"] - centre), default=None)
        if best is not None and abs(offered[best]["minute_of_day"] - centre) <= 45:
            return best
    for i, o in enumerate(offered):
        if o.get("weekday_word") and o["weekday_word"] in t:
            return i
    return None


class RuleNLU:
    def understand(self, stage: str, text: str, lang: str, ctx: dict) -> Understanding:
        t = (text or "").strip()
        u = Understanding()
        if not t:
            return u
        hits = [(m.start(), name) for name, rx in TREATMENTS for m in [rx.search(t)] if m]
        if hits:  # "whitening, not braces": the first one mentioned is what they want
            u.treatment = min(hits)[1]
        for cid, rx in CLINICS.items():
            if rx.search(t):
                u.clinic = cid
        u.day_offset = parse_day(t, ctx.get("weekday_today", 0))
        spoken = normalise_spoken(t)
        u.start_min, u.end_min = parse_time(spoken)
        if stage == "offer" and ctx.get("offered"):
            u.choice = parse_choice(spoken, ctx["offered"])
            if u.choice is None and len(ctx["offered"]) == 1 and YES.search(t) and not NO.search(t):
                u.choice = 0

        if NOT_INTERESTED.search(t):
            u.intent = "not_interested"
        elif stage == "open" and NOT_NOW.search(t):
            u.intent = "not_now"
        elif NO_STRONG.search(t):
            u.intent, u.choice = "no", None
        elif u.choice is not None:
            u.intent = "choose"
        elif NO.search(t) and not YES.search(t.replace("nahi", "").replace("no", "")):
            u.intent = "no"
        elif YES.search(t):
            u.intent = "yes"
        elif NO.search(t):
            u.intent = "no"
        elif NOT_NOW.search(t):
            u.intent = "not_now"
        if any(v is not None for v in (u.treatment, u.clinic, u.day_offset, u.start_min)) and u.intent in ("unclear", "yes"):
            u.intent = "provide" if u.intent == "unclear" else u.intent
        return u


_SYSTEM = (
    "You extract structured meaning from one caller utterance in a dental clinic booking call (English, Hindi or "
    "Hinglish). The current conversation stage and context are given. Return JSON only with keys: intent (one of "
    "yes, no, not_now, not_interested, provide, choose, unclear), treatment (braces, whitening, implants, other or "
    "null), clinic (riverside, hillcrest, lotus or null), day_offset (days from today, 0-13, or null; 'kal' means "
    "tomorrow), start_min and end_min (acceptable time-of-day window in minutes from midnight, or null), choice "
    "(index of the offered slot the caller picked, or null)."
)


class GroqNLU:
    """Rules first, LLM fills the gaps.

    The Groq evaluation (eval_reports/g1-groq-subset.md) showed the LLM is unreliable at
    turning dates and times into numbers ("Thursday at 6:30 pm" -> Friday 10 am;
    "kal saade paanch" -> 10 am), while the rules get them exactly right. So every field the
    rules understood is kept; the LLM only supplies what the rules missed, mainly the intent
    of unusual phrasings.
    """

    def __init__(self, fallback: RuleNLU | None = None):
        self.fallback = fallback or RuleNLU()

    def understand(self, stage: str, text: str, lang: str, ctx: dict) -> Understanding:
        rules = self.fallback.understand(stage, text, lang, ctx)
        c = llm.client()
        if c is None or not (text or "").strip():
            return rules
        s = get_settings()
        offered = [{"index": i, "when": o["phrase"]} for i, o in enumerate(ctx.get("offered") or [])]
        user = f"stage: {stage}\nweekday_today: {ctx.get('weekday_today')}\noffered: {offered}\nutterance: {text}"
        try:
            out = c.json_completion(purpose="nlu", model=s.llm_nlu_model, prompt_version=PROMPT_VERSION,
                                    system=_SYSTEM, user=user, max_tokens=120)
            return self.merge(rules, self._validate(out, ctx))
        except Exception:
            return rules

    @staticmethod
    def merge(rules: Understanding, g: Understanding) -> Understanding:
        m = Understanding(source="hybrid")
        for f in ("treatment", "clinic", "day_offset", "choice"):
            setattr(m, f, getattr(rules, f) if getattr(rules, f) is not None else getattr(g, f))
        if rules.start_min is not None:
            m.start_min, m.end_min = rules.start_min, rules.end_min
        else:
            m.start_min, m.end_min = g.start_min, g.end_min
        m.intent = rules.intent if rules.intent != "unclear" else g.intent
        if m.intent == "choose" and m.choice is None:
            m.intent = "unclear"
        if m.intent in ("unclear", "yes") and any(v is not None for v in (m.treatment, m.clinic, m.day_offset, m.start_min)):
            m.intent = "provide" if m.intent == "unclear" else m.intent
        if rules.intent != "unclear" and all(getattr(rules, f) == getattr(m, f) for f in ("treatment", "clinic", "day_offset", "start_min", "choice")):
            m.source = "rules"  # the LLM added nothing this turn
        return m

    @staticmethod
    def _validate(out: dict, ctx: dict) -> Understanding:
        u = Understanding(source="groq")
        u.intent = out.get("intent") if out.get("intent") in INTENTS else "unclear"
        u.treatment = out.get("treatment") if out.get("treatment") in ("braces", "whitening", "implants", "other") else None
        u.clinic = out.get("clinic") if out.get("clinic") in CLINICS else None
        d = out.get("day_offset")
        u.day_offset = d if isinstance(d, int) and 0 <= d <= 13 else None
        s, e = out.get("start_min"), out.get("end_min")
        if isinstance(s, int) and isinstance(e, int) and 0 <= s < e <= 24 * 60:
            u.start_min, u.end_min = s, e
        ch = out.get("choice")
        u.choice = ch if isinstance(ch, int) and 0 <= ch < len(ctx.get("offered") or []) else None
        if u.intent == "choose" and u.choice is None:
            u.intent = "unclear"
        return u


def default_nlu():
    return GroqNLU() if get_settings().llm_enabled else RuleNLU()


def as_dict(u: Understanding) -> dict:
    return asdict(u)
