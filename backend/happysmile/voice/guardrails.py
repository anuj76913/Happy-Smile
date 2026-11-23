"""Guardrails (architecture §4.6; edge cases EC-URG, EC-SCOPE, EC-AI, EC-MAN, EC-WHO).

Input side, every caller turn:
  1. Rules (English, Hindi, Hinglish keywords) - high recall, always run, can't be overridden.
  2. Optional Groq classifier for paraphrases - can only ADD triggers, never remove one.
     Timeout or error -> rules-only result stands (EC-LLM-07/08).

Output side, every line before it is spoken:
  blocks claims to be human, medical advice or outcome promises, and prices.
"""

from __future__ import annotations

import re
from concurrent.futures import Future
from dataclasses import dataclass, field

from .. import llm
from ..config import get_settings

PROMPT_VERSION = "guard-v1"

# Triggers that end the conversation with a handover, and their urgency.
HANDOVER = {
    "emergency": "urgent", "pain_swelling": "urgent", "distress": "urgent",
    "asked_person": "normal", "price_emi": "normal", "clinical": "normal",
    "minor": "normal", "recording_objection": "normal",
}
# Triggers the agent handles in-call.
CONTROL = ("stop_calling", "never_enquired", "someone_else", "ask_robot", "where_number", "abusive")


def _rx(*parts: str) -> re.Pattern:
    return re.compile("|".join(parts), re.IGNORECASE)


R = {
    "emergency": _rx(r"\bbreath", r"\bswallow", r"can'?t (open|close) (my )?mouth", r"swell\w* (up )?(to|in|near|around|into) (my |the )?(eye|neck|throat)",
                     r"face is (all )?swollen", r"bleeding (won'?t|will not|doesn'?t|does not|is not|isn'?t) stop", r"heavy bleeding",
                     r"\baccident\b", r"\binjur", r"broken jaw", r"\bfractur", r"\bsaans\b", r"nigal", r"सांस|साँस|निगल",
                     r"khoon (ruk|band) (nahi|nahin|na)", r"खून (रुक|बंद) नहीं"),
    "distress": _rx(r"kill myself", r"\bsuicid", r"end (my|it all|my life)", r"want to die", r"self[- ]?harm",
                    r"marna chaht", r"jeena nahi", r"jaan de"),
    "pain_swelling": _rx(r"\bpain", r"\bpainful\b", r"\bhurt(s|ing)?\b", r"\bach(e|es|ing)\b", r"toothache", r"\bswell", r"\bswollen\b",
                         r"\bbleed", r"\bsore\b", r"\bthrobb", r"\babscess", r"\bpus\b", r"\binfect", r"\bdard\b", r"\bsoojan|\bsujan|\bsooj|\bsoojh",
                         r"\bkhoon\b", r"\btakleef\b", r"दर्द|सूजन|खून|तकलीफ"),
    "asked_person": _rx(r"\b(talk|speak|connect)\w* (to|with|me to) (a |an |some|the )?(real |actual )?(person|human|someone|somebody|staff|receptionist|doctor|dentist|manager|people)",
                        r"\breal (person|human)\b", r"\bhuman\b", r"\binsaan\b", r"kisi (insaan|aadmi|se baat)", r"staff se", r"\breceptionist\b",
                        r"इंसान|किसी से बात"),
    "price_emi": _rx(r"\bprice", r"\bcost", r"how much", r"\bcharges?\b", r"\bfees?\b", r"\brates?\b", r"\bkitn[ae]\b", r"\bkharch",
                     r"\bpaise\b|\bpaisa\b", r"\brupees?\b", r"₹", r"\bemi\b", r"\binstal+ment", r"\bdiscount", r"\binsurance", r"\boffer\b",
                     r"कितना|खर्च|ईएमआई|EMI"),
    "clinical": _rx(r"\bsafe\b", r"\bpregnan", r"breast ?feed", r"\bdiabet", r"blood pressure", r"\bbp\b", r"\bheart\b", r"\bmedicin",
                    r"\bmedication", r"blood thinner", r"side ?effect", r"(will|does|would) (it|this) hurt", r"is it painful",
                    r"which is better", r"do i (really )?need", r"\brecommend", r"\brisks?\b", r"how long (does|will|would) (it|the treatment)",
                    r"\bsurgery\b", r"\banaesthe|\banesthe", r"\ballerg", r"surakshit|सुरक्षित|दवा", r"\bdawai\b",
                    r"\bsugar\b", r"madhumeh|मधुमेह|शुगर", r"\bbp (ki|hai)", r"garbhvati|गर्भवती"),
    "minor": _rx(r"\b(i am|i'm|im|main|mai)\s*(1[0-7]|[5-9])\s*(years?|yrs?|saal)", r"under (18|eighteen)", r"\bminor\b", r"\bnabalig\b",
                 r"school (student|mein)", r"नाबालिग"),
    "recording_objection": _rx(r"(don'?t|do not|stop|no) record", r"record (mat|na) kar", r"recording (band|mat|nahi)", r"रिकॉर्ड मत"),
    "stop_calling": _rx(r"stop calling", r"(don'?t|do not|never) (call|contact|phone|ring)", r"remove my number", r"\bunsubscribe\b",
                        r"(call|phone) mat kar", r"dobara (call|phone) (mat|na)", r"फ़ोन मत|कॉल मत"),
    "never_enquired": _rx(r"(never|didn'?t|did not|haven'?t) (enquire|ask|request|fill|submit|sign)",
                          r"(never|didn'?t|did not|haven'?t) (make|made|send|sent|do|done) (an? |any )?(enquiry|inquiry|request)",
                          r"\bwrong number\b", r"not me\b",
                          r"main?ne (koi )?(enquiry|request|form) nahi", r"galat number", r"गलत नंबर"),
    "someone_else": _rx(r"(he|she)('?s| is) not (here|home|available|in)", r"(not|nahi) (at )?home", r"ghar (pe|par) nahi",
                        r"bahar gaye", r"(she|he)('?s| is) (out|busy|sleeping|at work)", r"this is (his|her) (wife|husband|mother|father|son|daughter|brother|sister)"),
    "ask_robot": _rx(r"are you (a |an )?(robot|bot|machine|computer|ai|human|real|person|recording)", r"is this (a |an )?(robot|bot|recording|machine|ai|computer)",
                     r"(robot|machine|bot) ho", r"insaan ho", r"\bare you ai\b"),
    "where_number": _rx(r"how did you get my number", r"where did you get", r"number (kahan|kaha) se", r"number kaise mila"),
    "abusive": _rx(r"\bf+u+c+k", r"\bbastard\b", r"\bidiot\b", r"\bstupid\b", r"\bchutiya\b", r"\bbewakoof\b", r"\bharami\b", r"\bkutt[ae]\b"),
}

_PAIN_NEGATED = _rx(r"\b(no|not|without|never|koi|zero)\b[^.?!]{0,20}\b(pain|dard|swelling|soojan|sujan|bleeding|ache|hurt)",
                    r"\b(pain|dard|swelling|soojan|sujan|ache)\b[^.?!]{0,15}\b(nahi|nahin|nhi|no)\b", r"\bpainless\b",
                    r"(कोई )?(दर्द|सूजन)[^।?!]{0,10}नहीं")
_PAIN_ABOUT_TREATMENT = _rx(r"(will|does|would|is) (it|this|the treatment|braces|implant)\w* (hurt|be painful|painful)")


@dataclass
class GuardResult:
    triggers: list[str] = field(default_factory=list)
    source: dict[str, str] = field(default_factory=dict)  # trigger -> 'rules' | 'classifier'

    @property
    def handover(self) -> str | None:
        """The most serious handover trigger, if any."""
        for t in ("emergency", "distress", "pain_swelling", "minor", "recording_objection", "asked_person", "clinical", "price_emi"):
            if t in self.triggers:
                return t
        return None

    def control(self) -> str | None:
        for t in CONTROL:
            if t in self.triggers:
                return t
        return None


def rules(text: str) -> GuardResult:
    t = (text or "").strip()
    res = GuardResult()
    if not t:
        return res
    for name, rx in R.items():
        if rx.search(t):
            res.triggers.append(name)
            res.source[name] = "rules"
    if "pain_swelling" in res.triggers:
        # "No pain" is not pain; "will it hurt?" is a clinical question, not pain (EC-URG-08 accepted: cautious otherwise).
        if _PAIN_ABOUT_TREATMENT.search(t) or (_PAIN_NEGATED.search(t) and not re.search(r"\b(but|lekin|par)\b", t, re.I)):
            res.triggers.remove("pain_swelling")
            res.source.pop("pain_swelling")
            if _PAIN_ABOUT_TREATMENT.search(t) and "clinical" not in res.triggers:
                res.triggers.append("clinical")
                res.source["clinical"] = "rules"
    # "real person?" asked as identity question is ask_robot, not a request for a person.
    if "ask_robot" in res.triggers and "asked_person" in res.triggers and not re.search(r"\b(talk|speak|connect|want|chahiye)\b", t, re.I):
        res.triggers.remove("asked_person")
    return res


# ---------------------------------------------------------------- Groq classifier (paraphrases)
_SYSTEM = (
    "You classify one caller utterance from a dental clinic phone call. Return JSON: "
    '{"triggers": [...], "confidence": 0-1}. Allowed triggers: emergency (trouble breathing or swallowing, swelling '
    "spreading to eye or neck, bleeding that won't stop, injury), distress (self-harm), pain_swelling (current pain, "
    "swelling, bleeding), asked_person (wants a human), price_emi (cost, EMI, discount, insurance), clinical "
    "(medical or treatment suitability question), minor (caller under 18), recording_objection, stop_calling. "
    "Use [] if none apply. Do not include anything else. Not triggers: asking whether they are talking to a bot, "
    "robot or AI (that is not asked_person); simply saying which treatment they want, e.g. 'I want braces' "
    "(that is not clinical); agreeing, declining or giving a day or time."
)
# The classifier is there to catch paraphrased safety cases. It may add urgent triggers at modest
# confidence; non-urgent ones need high confidence, because a false positive ends the call with a
# handover (Groq evaluation: "Are you a robot?" -> asked_person, "mujhe braces chahiye" -> clinical).
_URGENT = {"emergency", "distress", "pain_swelling", "minor"}
_MIN_CONF_URGENT, _MIN_CONF_OTHER = 0.6, 0.9


def classify_async(executor, text: str) -> Future | None:
    c = llm.client()
    if c is None or not text.strip():
        return None
    s = get_settings()
    return executor.submit(c.json_completion, purpose="guard", model=s.llm_guard_model, prompt_version=PROMPT_VERSION,
                           system=_SYSTEM, user=text, max_tokens=60, budget_ms=s.llm_first_token_timeout_ms)


def merge(base: GuardResult, fut: Future | None, timeout_s: float = 0.9) -> GuardResult:
    if fut is None:
        return base
    try:
        out = fut.result(timeout=timeout_s)
    except Exception:
        return base  # rules-only result stands
    allowed = set(HANDOVER) | {"stop_calling"}
    try:
        conf = float(out.get("confidence") or 0)
    except (TypeError, ValueError):
        conf = 0.0
    for t in out.get("triggers") or []:
        if t not in allowed or t in base.triggers:
            continue
        if t == "asked_person" and "ask_robot" in base.triggers:
            continue  # "are you a robot?" is an identity question, answered truthfully in-call
        if conf >= (_MIN_CONF_URGENT if t in _URGENT else _MIN_CONF_OTHER):
            base.triggers.append(t)
            base.source[t] = "classifier"
    return base


# ---------------------------------------------------------------- output checks
_OUT = {
    "claims_human": _rx(r"\bi('?m| am) (a |an )?(real |actual )?(person|human|woman|man)\b", r"\bnot (a |an )?(bot|robot|machine|ai|computer)\b",
                        r"main insaan hoon", r"मैं इंसान हूँ", r"मैं (कोई )?रोबोट नहीं"),
    "medical_advice": _rx(r"\b(it is|it's|that is|that's|this is) (completely |totally |very )?(safe|not safe|harmless|dangerous)\b",
                          r"\byou (should|must|need to) (take|use|apply|stop|start|avoid|rinse)\b", r"\b(won'?t|will not|doesn'?t|does not) hurt\b",
                          r"\bguarantee", r"\bwill (fix|cure|heal|solve)\b", r"\bno risk\b", r"\b(take|use) (a |an )?(painkiller|antibiotic|ibuprofen|paracetamol)"),
    "price": _rx(r"(₹|\brs\.?|\binr\b)\s*\d", r"\d[\d,]*\s*(rupees|rupaye|रुपये)"),
}


def check_output(text: str) -> list[str]:
    return [name for name, rx in _OUT.items() if rx.search(text or "")]
