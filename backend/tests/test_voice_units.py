"""Voice agent units: guardrails, tools allowlist, lines, Groq client, evaluation gate."""

import json
import os
from datetime import datetime

import httpx
import pytest

from happysmile import config, llm
from happysmile.config import IST
from happysmile.handovers import staffed_promise
from happysmile.voice import guardrails, lines
from happysmile.voice.agent import Agent, Session
from happysmile.voice.nlu import GroqNLU, RuleNLU, parse_day, parse_time
from happysmile.voice.tools import DisallowedTool, MemoryBackend, ToolRegistry

NOW = datetime(2026, 11, 24, 14, 20, tzinfo=IST)


# ---------------------------------------------------------------- guardrails
@pytest.mark.parametrize("text,trigger", [
    ("my gum is swollen", "pain_swelling"), ("thoda dard hai", "pain_swelling"), ("बहुत दर्द है", "pain_swelling"),
    ("I can't breathe properly and my face is swollen", "emergency"), ("bleeding won't stop", "emergency"),
    ("I want to end my life", "distress"), ("can I talk to a real person", "asked_person"),
    ("how much will it cost", "price_emi"), ("is it safe in pregnancy", "clinical"), ("will it hurt?", "clinical"),
    ("I'm 15 years old", "minor"), ("don't record this", "recording_objection"),
])
def test_rules_detect(text, trigger):
    g = guardrails.rules(text)
    assert trigger in g.triggers
    assert g.handover is not None


@pytest.mark.parametrize("text", ["no pain at all", "No, no pain", "nahi, koi dard nahi", "painless, thanks", "will it hurt?"])
def test_negated_pain_is_not_urgent(text):
    assert "pain_swelling" not in guardrails.rules(text).triggers


def test_classifier_can_add_but_never_remove():
    from concurrent.futures import Future
    f = Future()
    f.set_result({"triggers": ["price_emi"], "confidence": 0.9})
    g = guardrails.merge(guardrails.rules("it hurts"), f)
    assert set(g.triggers) == {"pain_swelling", "price_emi"}
    f2 = Future()
    f2.set_exception(TimeoutError())
    assert guardrails.merge(guardrails.rules("it hurts"), f2).triggers == ["pain_swelling"]  # rules stand (EC-LLM-07)


def _classifier(triggers, conf):
    from concurrent.futures import Future
    f = Future()
    f.set_result({"triggers": triggers, "confidence": conf})
    return f


def test_classifier_is_strict_for_non_urgent_triggers():
    # Found in the Groq evaluation: these ended calls with needless handovers.
    assert "asked_person" not in guardrails.merge(guardrails.rules("Are you a robot?"), _classifier(["asked_person"], 0.99)).triggers
    assert guardrails.merge(guardrails.rules("mujhe braces hi chahiye"), _classifier(["clinical"], 0.8)).triggers == []
    # Urgent paraphrases still get through at modest confidence.
    assert guardrails.merge(guardrails.rules("my cheek has blown up like a balloon"), _classifier(["pain_swelling"], 0.7)).handover == "pain_swelling"


def test_rules_win_over_llm_for_dates_and_times():
    from happysmile.voice.nlu import Understanding
    rules = RuleNLU().understand("time", "kal saade paanch baje", "hi", {"weekday_today": 1})
    llm_guess = Understanding(intent="provide", day_offset=1, start_min=600, end_min=660, source="groq")  # the 10 am mistake
    m = GroqNLU.merge(rules, llm_guess)
    assert (m.day_offset, m.start_min) == (1, 16 * 60 + 30)
    # Where the rules understood nothing, the LLM fills in.
    unclear = RuleNLU().understand("open", "that would be grand, carry on", "en", {"weekday_today": 1})
    assert unclear.intent == "unclear"
    assert GroqNLU.merge(unclear, Understanding(intent="yes", source="groq")).intent == "yes"


@pytest.mark.parametrize("text", ["I'm a real person, don't worry", "It's completely safe", "That will cost ₹ 5,000",
                                  "You should take a painkiller", "main insaan hoon"])
def test_output_check_blocks(text):
    assert guardrails.check_output(text)


def test_every_approved_line_passes_output_check():
    for key, langs in lines.LINES.items():
        for lang, text in langs.items():
            filled = text.format(name="Asha", treatment="braces", clinic="Riverside", clinics="Riverside", when="tomorrow",
                                 s1="tomorrow at 6 pm", d1="Dr. A", s2="Friday at 10 am", d2="Dr. B", slot="tomorrow at 6 pm",
                                 dentist="Dr. A", minutes=15, staff="Kavya")
            assert guardrails.check_output(filled) == [], (key, lang)
    assert all("virtual assistant" in lines.say("greeting", "en", name="A", treatment=t) for t in ("braces", "whitening"))


def test_fixed_audio_manifest_has_disclosure_per_language_and_treatment():
    m = lines.fixed_audio_manifest()
    greetings = [x for x in m if x["id"].startswith("greeting.")]
    assert len(greetings) == 8 and all("{name}" in g["text"] for g in greetings)


# ---------------------------------------------------------------- understanding
def test_dates_and_times():
    assert parse_day("kal shaam", 1) == 1                 # EC-LANG-04: kal = tomorrow when booking
    assert parse_day("parson", 1) == 2
    assert parse_day("Saturday morning", 1) == 4          # Tuesday -> Saturday
    assert parse_time("saade paanch baje") == (16 * 60 + 30, 18 * 60 + 30)
    assert parse_time("after 6 pm") == (18 * 60, 21 * 60)
    assert parse_time("subah") == (9 * 60, 12 * 60)


def test_groq_nlu_falls_back_to_rules_on_error(monkeypatch):
    class Broken:
        def json_completion(self, **kw):
            raise llm.LlmError("timeout")
    monkeypatch.setattr(llm, "client", lambda: Broken())
    u = GroqNLU().understand("time", "tomorrow evening", "en", {"weekday_today": 1})
    assert u.source == "rules" and u.day_offset == 1


def test_groq_nlu_output_is_validated(monkeypatch):
    class Odd:
        def json_completion(self, **kw):
            return {"intent": "choose", "choice": 7, "day_offset": 99, "clinic": "mars"}
    monkeypatch.setattr(llm, "client", lambda: Odd())
    u = GroqNLU().understand("offer", "the third", "en", {"weekday_today": 1, "offered": [{"phrase": "x"}]})
    assert u.choice is None and u.intent == "unclear" and u.day_offset is None and u.clinic is None


# ---------------------------------------------------------------- tools
def test_registry_allowlist_and_schema():
    reg = ToolRegistry(MemoryBackend(NOW))
    with pytest.raises(DisallowedTool):
        reg.call("cancel_all_bookings")
    with pytest.raises(DisallowedTool):
        reg.call("hold_slot", slot_id=123)
    with pytest.raises(DisallowedTool):
        reg.call("get_available_slots", clinic_id="riverside", lead_id="someone-else", day_offset=None,
                 start_min=None, end_min=None, limit=2)
    s = reg.call("get_available_slots", clinic_id="riverside", day_offset=1, start_min=None, end_min=None, limit=2)
    assert reg.call("hold_slot", slot_id=s[0]["id"]) and reg.call("book_consultation", slot_id=s[0]["id"])
    reg.call("hold_slot", slot_id=s[1]["id"])
    with pytest.raises(DisallowedTool):
        reg.call("book_consultation", slot_id=s[1]["id"])  # one booking per call (EC-BOOK-09)


def test_backend_failure_fails_toward_a_human():
    backend = MemoryBackend(NOW)
    backend.get_available_slots = lambda **kw: (_ for _ in ()).throw(RuntimeError("db down"))
    sess = Session(name="A", treatment="braces", clinic_id="riverside", clinic_name="Riverside")
    agent = Agent(sess, ToolRegistry(backend), now=lambda: NOW)
    agent.start()
    for t in ("yes", "yes", "no", "yes"):
        agent.handle(t)
    turn = agent.handle("tomorrow evening")
    assert turn.end and sess.outcome == "handover" and sess.handover["reason"] == "system_fallback"


def test_handover_promise_matches_staffed_hours():
    assert staffed_promise(datetime(2026, 11, 24, 14, 20, tzinfo=IST), "normal")[1:] == ("minutes", 15)
    assert staffed_promise(datetime(2026, 11, 24, 23, 0, tzinfo=IST), "urgent")[1] == "morning"      # EC-URG-05
    assert staffed_promise(datetime(2026, 11, 24, 20, 58, tzinfo=IST), "urgent")[1] == "morning"


# ---------------------------------------------------------------- evaluation set (gate G1 behaviour checks)
def test_evaluation_set_meets_g1():
    from happysmile.evaluation.runner import run_all
    from happysmile.evaluation.scenarios import S
    assert len(S) >= 60
    res = run_all(RuleNLU())
    failed = [(r["id"], r["fails"]) for r in res["results"] if not r["ok"]]
    assert all(res["metrics"]["g1"].values()), (res["metrics"], failed)


# ---------------------------------------------------------------- Groq client
def _settings(**env):
    os.environ.update({"GROQ_API_KEY": "test-key", "LLM_DIALOGUE_MODEL": "m-nlu", "LLM_GUARD_MODEL": "m-guard",
                       "LLM_SUMMARY_MODEL": "m-sum", **env})
    config.get_settings.cache_clear()


def test_groq_client_json_retry_and_redaction():
    _settings()
    seen = []

    def handler(req: httpx.Request):
        body = json.loads(req.content)
        seen.append(body)
        if len(seen) == 1:
            return httpx.Response(429, json={"error": "rate"})
        return httpx.Response(200, json={"choices": [{"message": {"content": '{"intent": "yes"}'}}], "usage": {"prompt_tokens": 9}})

    c = llm.GroqClient(transport=httpx.MockTransport(handler))
    out = c.json_completion(purpose="nlu", model="m-nlu", prompt_version="v1", system="s", user="call me on 98765 43210 ok")
    assert out == {"intent": "yes"} and len(seen) == 2                       # one retry after 429
    assert "98765" not in seen[0]["messages"][1]["content"]                  # phone redacted (EC-LLM-13)
    assert seen[0]["model"] == "m-nlu" and seen[0]["response_format"] == {"type": "json_object"}


def test_groq_client_raises_on_timeout_and_bad_json():
    _settings()
    c = llm.GroqClient(transport=httpx.MockTransport(lambda r: (_ for _ in ()).throw(httpx.ReadTimeout("slow"))))
    with pytest.raises(llm.LlmError):
        c.json_completion(purpose="nlu", model="m", prompt_version="v", system="s", user="u")
    c2 = llm.GroqClient(transport=httpx.MockTransport(
        lambda r: httpx.Response(200, json={"choices": [{"message": {"content": "not json"}}]})))
    with pytest.raises(llm.LlmError):
        c2.json_completion(purpose="nlu", model="m", prompt_version="v", system="s", user="u")


def test_groq_streaming_measures_first_token():
    _settings()
    sse = "".join(f'data: {json.dumps({"choices": [{"delta": {"content": w}}]})}\n\n' for w in ("Hel", "lo")) + "data: [DONE]\n\n"
    c = llm.GroqClient(transport=httpx.MockTransport(lambda r: httpx.Response(200, text=sse)))
    res = c.stream_text(purpose="nlu", model="m", prompt_version="v", system="s", user="u")
    assert res.content == "Hello" and res.ttft_ms is not None


def test_summary_from_groq_is_rejected_if_it_contradicts_facts(monkeypatch):
    from happysmile.voice import summariser
    session = {"outcome": "handover", "handover": {"reason": "pain_swelling", "urgency": "urgent", "promise": "minutes", "minutes": 5},
               "treatment": "braces", "lang": "en", "stage": "urgency", "transcript": []}

    class Liar:
        def json_completion(self, **kw):
            return {"lines": ["Patient booked a whitening slot.", "Booked for tomorrow.", "All good."]}
    monkeypatch.setattr(llm, "client", lambda: Liar())
    out = summariser.summarise(session)
    assert out["source"] == "rules" and "Pain or swelling" in out["lines"][1]
