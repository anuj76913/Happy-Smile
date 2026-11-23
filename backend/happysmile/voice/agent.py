"""Conversation state machine (architecture §7.1; plan P3-04).

Stages: open -> confirm_need (-> ask_treatment) -> urgency -> clinic (-> choose_clinic)
        -> time -> offer -> close (-> close_q); side paths: callback_time.

Each caller turn:
  1. Guardrails (rules, plus the Groq classifier in parallel) -> handover triggers win.
  2. Control intents: stop calling, never enquired, someone else answered, "are you a robot?",
     "where did you get my number?", abuse.
  3. Understanding for the current stage (Groq, falling back to rules) -> next stage.
The assistant only says approved lines (lines.py); each passes the output check first.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field
from datetime import datetime, time, timedelta, timezone
from typing import Callable

from ..config import IST
from . import guardrails, language, lines
from .nlu import RuleNLU, Understanding
from .tools import DisallowedTool, ToolRegistry

MAX_TURNS = 24
WINDOW_START, WINDOW_LAST = time(9, 0), time(20, 45)
_POOL = ThreadPoolExecutor(max_workers=8, thread_name_prefix="agent")


@dataclass
class Session:
    name: str
    treatment: str
    clinic_id: str
    clinic_name: str
    lang: str = "en"
    stage: str = "open"
    day_offset: int | None = None
    start_min: int | None = None
    end_min: int | None = None
    offered: list[dict] = field(default_factory=list)
    asked_alt: bool = False
    robot_pending: bool = False
    silences: int = 0
    unclear: int = 0
    low_conf: int = 0
    abusive: int = 0
    turns: int = 0
    hold_failures: int = 0
    held: str | None = None
    booking: dict | None = None
    outcome: str | None = None
    handover: dict | None = None
    ended: bool = False
    transcript: list[list] = field(default_factory=list)
    guard_events: list[dict] = field(default_factory=list)
    understood: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        d = asdict(self)
        if self.booking:
            d["booking"] = {**self.booking, "start_at": _iso(self.booking["start_at"])}
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "Session":
        s = cls(**d)
        if s.booking and isinstance(s.booking.get("start_at"), str):
            s.booking["start_at"] = datetime.fromisoformat(s.booking["start_at"])
        return s


def _iso(v):
    return v.isoformat() if isinstance(v, datetime) else v


@dataclass
class Turn:
    say: str
    end: bool = False


class Agent:
    def __init__(self, session: Session, tools: ToolRegistry, nlu=None, now: Callable[[], datetime] | None = None):
        self.s, self.tools, self.nlu = session, tools, nlu or RuleNLU()
        self.now = now or (lambda: datetime.now(timezone.utc))

    # ------------------------------------------------------------------ public
    def start(self) -> Turn:
        text = lines.say("greeting", self.s.lang, name=self.s.name, treatment=lines.treatment_word(self.s.treatment, self.s.lang))
        return self._say(text)

    def handle(self, text: str, confidence: float = 1.0) -> Turn:
        s = self.s
        if s.ended:
            return Turn("", True)
        s.turns += 1
        text = (text or "").strip()
        if not text:
            return self.silence()
        s.silences = 0
        s.transcript.append(["Caller", text, self._ts()])
        try:
            return self._handle(text, confidence)
        except DisallowedTool as e:
            s.guard_events.append({"type": "disallowed_tool", "detail": str(e)})
            return self._handover("system_fallback")
        except Exception as e:  # any dependency failure fails toward a human (§2 principle 4)
            s.guard_events.append({"type": "error", "detail": type(e).__name__})
            return self._handover("system_fallback")

    def silence(self) -> Turn:
        s = self.s
        s.silences += 1
        s.transcript.append(["Caller", "(silence)", self._ts()])
        if s.silences == 1:
            return self._say(lines.say("silence", s.lang))
        if s.stage == "open":  # never engaged: try again later (EC-LANG-07)
            self._safe_tool("schedule_callback", at=self._callback_time(None, None))
            return self._end(lines.say("callback_default", s.lang), "callback")
        return self._handover("system_fallback", lead_in="dropped_line", quiet=False)

    def hangup(self) -> None:
        """Caller hung up. Make sure nobody is left without a next step."""
        s = self.s
        if s.ended:
            return
        s.transcript.append(["System", "Caller hung up", self._ts()])
        if s.held:
            self._safe_tool("release_hold", slot_id=s.held)
        if s.booking:
            s.outcome = "booked"
        elif s.stage == "open":
            self._safe_tool("schedule_callback", at=self._callback_time(None, None))
            s.outcome = "callback"
        else:
            self._handover("system_fallback", quiet=True)
            s.outcome = "dropped"
        s.ended = True

    # ------------------------------------------------------------------ turn handling
    def _handle(self, text: str, confidence: float) -> Turn:
        s = self.s
        if s.turns > MAX_TURNS:
            return self._handover("needs_staff")
        if confidence < 0.5:
            s.low_conf += 1
            s.guard_events.append({"type": "low_confidence", "value": confidence})
            if s.low_conf >= 2:
                return self._handover("couldnt_understand")
            return self._say(lines.say("reprompt", s.lang))
        s.low_conf = 0

        new_lang, explicit = language.detect(text, s.lang)
        if new_lang:
            s.guard_events.append({"type": "language_switch", "from": s.lang, "to": new_lang, "explicit": explicit})
            s.lang = new_lang
            if s.offered:  # re-phrase offered slots in the new language
                for o in s.offered:
                    o["phrase"] = lines.slot_phrase(datetime.fromisoformat(o["start_at"]), self.now(), s.lang)

        ctx = {"weekday_today": self.now().astimezone(IST).weekday(), "offered": s.offered}
        guard_fut = guardrails.classify_async(_POOL, text)
        nlu_fut = _POOL.submit(self.nlu.understand, s.stage, text, s.lang, ctx)
        g = guardrails.merge(guardrails.rules(text), guard_fut)
        try:
            u: Understanding = nlu_fut.result(timeout=2.5)
        except Exception:
            u = RuleNLU().understand(s.stage, text, s.lang, ctx)
        if g.triggers:
            s.guard_events.append({"type": "triggers", "triggers": list(g.triggers), "source": dict(g.source)})
        s.understood.append({"stage": s.stage, "intent": u.intent, "source": u.source})

        # "Are you in pain?" -> "yes" is a pain report even without pain words.
        if s.stage == "urgency" and not g.handover and u.intent == "yes":
            g.triggers.append("pain_swelling")
        if g.handover:  # safety first, even in a "switch language" turn
            return self._handover(g.handover)
        if explicit:
            return self._say(lines.say("lang_switched", s.lang) + " " + self._stage_prompt())

        ctl = g.control()
        if ctl == "stop_calling":
            self.tools.call("suppress_contact", reason="stop_calling")
            return self._end(lines.say("stop_calling", s.lang), "suppressed")
        if ctl == "never_enquired":
            self.tools.call("suppress_contact", reason="never_enquired")
            return self._end(lines.say("never_enquired", s.lang), "wrong_person")
        if ctl == "someone_else" and s.stage == "open":
            self.tools.call("schedule_callback", at=self._callback_time(None, None))
            return self._end(lines.say("someone_else", s.lang, name=s.name), "callback")
        if ctl == "ask_robot":
            s.robot_pending = True
            return self._say(lines.say("robot", s.lang))
        if ctl == "where_number":
            return self._say(lines.say("where_number", s.lang) + " " + self._stage_prompt())
        if ctl == "abusive":
            s.abusive += 1
            if s.abusive >= 2:
                self.tools.call("handover", reasons=["abusive"], urgency="normal", note="Call ended after abusive language")
                return self._end(lines.say("abuse_end", s.lang), "ended_abusive")
            return self._say(lines.say("abuse_warning", s.lang) + " " + self._stage_prompt())

        if u.intent == "not_interested" and s.stage in ("close", "close_q"):  # "no thanks" after booking = goodbye
            return self._end(lines.say("goodbye", s.lang, name=s.name), "booked")
        if u.intent == "not_interested":
            self.tools.call("mark_not_interested")
            return self._end(lines.say("not_interested", s.lang), "not_interested")
        s.robot_pending = False
        return getattr(self, f"_stage_{s.stage}")(u)

    # ------------------------------------------------------------------ stages
    def _stage_open(self, u: Understanding) -> Turn:
        s = self.s
        if u.intent in ("yes", "provide", "choose"):
            s.unclear = 0
            if u.treatment and u.treatment != s.treatment:
                s.treatment = u.treatment
            s.stage = "confirm_need"
            return self._say(self._stage_prompt())
        if u.intent in ("no", "not_now"):
            s.stage = "callback_time"
            return self._say(lines.say("ask_callback_time", s.lang))
        return self._unclear()

    def _stage_callback_time(self, u: Understanding) -> Turn:
        s = self.s
        if u.day_offset is not None or u.start_min is not None:
            at = self._callback_time(u.day_offset, u.start_min)
            self.tools.call("schedule_callback", at=at)
            return self._end(lines.say("callback_confirm", s.lang, when=lines.slot_phrase(at, self.now(), s.lang)), "callback")
        self.tools.call("schedule_callback", at=self._callback_time(None, None))
        return self._end(lines.say("callback_default", s.lang), "callback")

    def _stage_confirm_need(self, u: Understanding) -> Turn:
        s = self.s
        if u.treatment:
            s.treatment = u.treatment
            return self._goto("urgency")
        if u.intent == "yes":
            return self._goto("urgency")
        if u.intent == "no":
            return self._goto("ask_treatment")
        return self._unclear()

    def _stage_ask_treatment(self, u: Understanding) -> Turn:
        if u.treatment:
            self.s.treatment = u.treatment
            return self._goto("urgency")
        if self.s.unclear >= 1:  # don't block the booking on this: the dentist will ask anyway
            self.s.treatment = "other"
            return self._goto("urgency")
        return self._unclear()

    def _stage_urgency(self, u: Understanding) -> Turn:
        self._remember(u)
        if u.intent in ("no", "provide", "choose") or u.day_offset is not None:
            return self._goto("clinic")
        if self.s.unclear >= 1:  # unsure whether they're in pain: a person should check (fail safe)
            return self._handover("couldnt_understand")
        return self._unclear()

    def _stage_clinic(self, u: Understanding) -> Turn:
        s = self.s
        self._remember(u)
        if u.clinic and u.clinic != s.clinic_id:
            return self._switch_clinic(u.clinic)
        if u.intent in ("yes", "provide", "choose"):
            return self._after_clinic()
        if u.intent == "no":
            return self._goto("choose_clinic")
        return self._unclear()

    def _stage_choose_clinic(self, u: Understanding) -> Turn:
        if u.clinic:
            return self._switch_clinic(u.clinic)
        return self._handover("needs_staff", note="Wants a clinic outside the pilot or didn't name one")

    def _stage_time(self, u: Understanding) -> Turn:
        s = self.s
        self._remember(u)
        if u.intent == "no" and s.asked_alt and u.day_offset is None and u.start_min is None:
            return self._handover("no_suitable_slot")
        if u.day_offset is not None or u.start_min is not None or u.intent in ("yes", "provide") or s.unclear >= 1:
            return self._offer()
        return self._unclear()

    def _stage_offer(self, u: Understanding) -> Turn:
        s = self.s
        if u.intent == "choose" and u.choice is not None and u.choice < len(s.offered):
            return self._book(u.choice)
        if u.day_offset is not None or u.start_min is not None:
            self._remember(u, replace=True)
            return self._offer()
        if u.intent == "no":
            if s.asked_alt:
                return self._handover("no_suitable_slot")
            s.asked_alt = True
            s.stage = "time"
            return self._say(lines.say("ask_other_time", s.lang))
        if u.intent == "yes" and len(s.offered) == 1:
            return self._book(0)
        if len(s.offered) == 2:
            if s.unclear >= 2:
                return self._handover("couldnt_understand")
            s.unclear += 1
            return self._say(lines.say("which_one", s.lang, s1=s.offered[0]["phrase"], s2=s.offered[1]["phrase"]))
        return self._unclear()

    def _stage_close(self, u: Understanding) -> Turn:
        s = self.s
        if u.intent == "yes":
            s.stage = "close_q"
            return self._say(lines.say("go_ahead", s.lang))
        return self._end(lines.say("goodbye", s.lang, name=s.name), "booked")

    def _stage_close_q(self, u: Understanding) -> Turn:
        if u.intent in ("no",):
            return self._end(lines.say("goodbye", self.s.lang, name=self.s.name), "booked")
        return self._handover("needs_staff", note="Had a question after booking")

    # ------------------------------------------------------------------ helpers
    def _stage_prompt(self) -> str:
        s, L = self.s, self.s.lang
        return {
            "open": lines.say("good_time", L),
            "callback_time": lines.say("ask_callback_time", L),
            "confirm_need": lines.say("confirm_need", L, treatment=lines.treatment_word(s.treatment, L)),
            "ask_treatment": lines.say("ask_treatment", L),
            "urgency": lines.say("urgency", L),
            "clinic": lines.say("clinic_confirm", L, clinic=s.clinic_name),
            "choose_clinic": lines.say("ask_clinic", L, clinics=", ".join(n for _, n in self.tools.backend.clinics())),
            "time": lines.say("ask_time", L),
            "offer": self._offer_line(),
            "close": lines.say("anything_else", L),
            "close_q": lines.say("go_ahead", L),
        }[s.stage]

    def _goto(self, stage: str) -> Turn:
        self.s.stage, self.s.unclear = stage, 0
        return self._say(self._stage_prompt())

    def _unclear(self) -> Turn:
        s = self.s
        s.unclear += 1
        if s.unclear >= 3:
            return self._handover("couldnt_understand")
        return self._say(lines.say("reprompt", s.lang) + " " + self._stage_prompt())

    def _remember(self, u: Understanding, replace: bool = False) -> None:
        s = self.s
        if replace or u.day_offset is not None:
            s.day_offset = u.day_offset if u.day_offset is not None else (None if replace else s.day_offset)
        if replace or u.start_min is not None:
            s.start_min, s.end_min = u.start_min, u.end_min

    def _switch_clinic(self, clinic_id: str) -> Turn:
        names = dict(self.tools.backend.clinics())
        if clinic_id not in names:
            return self._handover("needs_staff", note="Asked for a clinic outside the pilot")
        self.s.clinic_id, self.s.clinic_name = clinic_id, names[clinic_id]
        return self._after_clinic()

    def _after_clinic(self) -> Turn:
        s = self.s
        if s.day_offset is not None or s.start_min is not None:
            return self._offer()
        return self._goto("time")

    def _offer(self) -> Turn:
        s = self.s
        s.unclear = 0
        allowed = getattr(self.tools.backend, "booking_allowed", lambda: True)
        if not allowed():  # kill switch: AI booking paused for this clinic (implementation-plan §13)
            return self._handover("booking_paused", note=self._pref_note())
        slots = self.tools.call("get_available_slots", clinic_id=s.clinic_id, day_offset=s.day_offset,
                                start_min=s.start_min, end_min=s.end_min, limit=12)
        picked: list[dict] = []
        for sl in slots:  # two options at least an hour apart where possible
            if not picked or abs((sl["start_at"] - picked[0]["start_at"]).total_seconds()) >= 3600:
                picked.append(sl)
            if len(picked) == 2:
                break
        if not picked:
            if s.asked_alt:
                return self._handover("no_suitable_slot")
            s.asked_alt, s.stage = True, "time"
            s.day_offset = s.start_min = s.end_min = None
            return self._say(lines.say("no_slots_alt", s.lang))
        now = self.now()
        s.offered = [{"id": p["id"], "start_at": p["start_at"].isoformat(), "dentist": p["dentist"],
                      "phrase": lines.slot_phrase(p["start_at"], now, s.lang),
                      "minute_of_day": p["start_at"].astimezone(IST).hour * 60 + p["start_at"].astimezone(IST).minute,
                      "weekday_word": p["start_at"].astimezone(IST).strftime("%A").lower()} for p in picked]
        s.stage = "offer"
        return self._say(self._offer_line())

    def _pref_note(self) -> str:
        s = self.s
        day = {None: "any day", 0: "today", 1: "tomorrow"}.get(s.day_offset, f"in {s.day_offset} days")
        band = "" if s.start_min is None else f", around {s.start_min // 60:02d}:{s.start_min % 60:02d}-{s.end_min // 60:02d}:{s.end_min % 60:02d}"
        return f"Wants a consultation {day}{band} at {s.clinic_name}"

    def _offer_line(self) -> str:
        s, o = self.s, self.s.offered
        if len(o) >= 2:
            return lines.say("offer_two", s.lang, s1=o[0]["phrase"], d1=o[0]["dentist"], s2=o[1]["phrase"], d2=o[1]["dentist"])
        if o:
            return lines.say("offer_one", s.lang, s1=o[0]["phrase"], d1=o[0]["dentist"])
        return lines.say("ask_time", s.lang)

    def _book(self, i: int) -> Turn:
        s = self.s
        slot = s.offered[i]
        if not self.tools.call("hold_slot", slot_id=slot["id"]):
            return self._slot_lost()
        s.held = slot["id"]
        b = self.tools.call("book_consultation", slot_id=slot["id"])
        s.held = None
        if not b:
            return self._slot_lost()
        s.booking = b
        s.stage = "close"
        # Read back only what the booking returned (EC-BOOK-05).
        text = lines.say("booked", s.lang, slot=lines.slot_phrase(b["start_at"], self.now(), s.lang), dentist=b["dentist"],
                         clinic=b["clinic"]) + " " + lines.say("anything_else", s.lang)
        return self._say(text)

    def _slot_lost(self) -> Turn:
        s = self.s
        s.hold_failures += 1
        if s.hold_failures >= 2:
            return self._handover("no_suitable_slot")
        lost = lines.say("slot_taken", s.lang)
        turn = self._offer()
        turn.say = lost + " " + turn.say
        s.transcript[-1][1] = turn.say
        return turn

    def _handover(self, reason: str, lead_in: str | None = None, note: str | None = None, quiet: bool = False) -> Turn:
        s = self.s
        if s.held:
            self._safe_tool("release_hold", slot_id=s.held)
            s.held = None
        urgency = guardrails.HANDOVER.get(reason, "normal")
        if reason == "asked_person" and not quiet:  # live warm transfer when someone is free (Phase 6)
            try:
                t = self.tools.call("transfer_to_staff")
            except Exception:
                t = None
            if t:
                s.handover = {"reason": reason, "urgency": urgency, "promise": "transfer", "staff": t["name"]}
                return self._end(lines.say("transferring", s.lang, staff=t["name"], clinic=s.clinic_name), "transferred")
        tag = "pain_swelling" if reason == "emergency" else reason
        reasons = [tag] + (["emergency"] if reason == "emergency" else [])
        try:
            res = self.tools.call("handover", reasons=reasons, urgency=urgency, note=note)
        except Exception:
            res = {"promise": "minutes", "minutes": 15}
        s.handover = {"reason": reason, "urgency": urgency, **res}
        if quiet:
            s.outcome, s.ended = "handover", True
            return Turn("", True)
        L = s.lang
        parts = [lines.say(lead_in or f"ho_{reason}", L)]
        if res.get("promise") == "minutes":
            parts.append(lines.say("promise_minutes", L, clinic=s.clinic_name, minutes=res.get("minutes") or 15))
        else:
            parts.append(lines.say("promise_morning", L, clinic=s.clinic_name))
        if reason == "pain_swelling":
            parts.insert(-1, lines.say("safe_care" if res.get("promise") == "minutes" else "safe_care_tonight", L))
        return self._end(" ".join(parts), "handover")

    def _end(self, text: str, outcome: str) -> Turn:
        self.s.outcome, self.s.ended = outcome, True
        t = self._say(text)
        t.end = True
        return t

    def _say(self, text: str) -> Turn:
        bad = guardrails.check_output(text)
        if bad:  # never speak it; fail toward a human (architecture §4.6)
            self.s.guard_events.append({"type": "output_blocked", "violations": bad})
            if not self.s.ended:
                return self._handover("system_fallback")
            text = lines.say("ho_system_fallback", self.s.lang)
        self.s.transcript.append(["Assistant", text, self._ts()])
        return Turn(text, self.s.ended)

    def _safe_tool(self, name: str, **kw):
        try:
            return self.tools.call(name, **kw)
        except Exception:
            return None

    def _callback_time(self, day_offset: int | None, start_min: int | None) -> datetime:
        now = self.now().astimezone(IST)
        if day_offset is None and start_min is None:
            at = now + timedelta(hours=2)
        else:
            day = now.date() + timedelta(days=day_offset or 0)
            mins = start_min if start_min is not None else (now.hour * 60 + now.minute + 120 if not day_offset else 10 * 60)
            at = datetime(day.year, day.month, day.day, tzinfo=IST) + timedelta(minutes=mins)
        if at <= now:
            at = now + timedelta(hours=2)
        if at.time() < WINDOW_START:
            at = datetime.combine(at.date(), WINDOW_START, tzinfo=IST)
        elif at.time() > WINDOW_LAST:
            nxt = at.date() + timedelta(days=1)
            at = datetime.combine(nxt, time(10, 0), tzinfo=IST)
        return at

    def _ts(self) -> str:
        return self.now().isoformat()
