"""Call orchestrator (architecture §4.4; plan P3-07).

- Durable jobs in `call_job`; workers claim with FOR UPDATE SKIP LOCKED and a lease, so
  a crashed worker never causes a double dial (EC-CALL-12, EC-OPS-03).
- Calling window, last-call cutoff, concurrency limit per caller ID.
- Retry policy: attempt 2 after 5 min (3 min if busy), attempt 3 after 2 h, then hand over
  to staff ('not_reached'; WhatsApp follow-up arrives in Phase 4).
- Circuit breaker: repeated LLM/telephony failures open it; while open, new leads go
  straight to the staff queue (system_fallback). No lead is ever left waiting on a dead system.
- Call lifecycle: answered -> agent session in `conversation` -> turns -> finalize + summary.
"""

from __future__ import annotations

import socket
import time as _time
from datetime import datetime, timedelta, timezone

from psycopg.types.json import Jsonb

from . import calling_window, events, handovers
from .config import get_settings
from .db import tx
from .leads import mark_reached
from .telephony import ProviderUnavailable, provider
from .voice import RULES_VERSION
from .voice.agent import Agent, Session
from .voice.nlu import default_nlu
from .voice.summariser import summarise
from .voice.tools import DbBackend, ToolRegistry

LEASE = timedelta(minutes=2)
RETRY_AFTER = {1: timedelta(minutes=5), 2: timedelta(hours=2)}
BREAKER_THRESHOLD, BREAKER_WINDOW, BREAKER_OPEN_FOR = 3, timedelta(minutes=5), timedelta(minutes=2)
WORKER_ID = f"{socket.gethostname()}"


# ---------------------------------------------------------------- scheduling
def schedule_call(conn, lead: dict, due_at: datetime, reason: str) -> None:
    n = conn.execute("SELECT count(*) AS n FROM call_attempt WHERE lead_id = %s AND made_by = 'assistant'", (lead["id"],)).fetchone()["n"]
    open_job = conn.execute("SELECT id FROM call_job WHERE lead_id = %s AND status IN ('pending', 'running') FOR UPDATE",
                            (lead["id"],)).fetchone()
    if open_job:
        conn.execute("UPDATE call_job SET due_at = %s, status = 'pending', updated_at = now() WHERE id = %s", (due_at, open_job["id"]))
    else:
        conn.execute("INSERT INTO call_job (lead_id, attempt_no, due_at) VALUES (%s, %s, %s)", (lead["id"], n + 1, due_at))
    events.append(conn, "call.scheduled", lead_id=lead["id"], clinic_id=lead["clinic_id"], actor="system",
                  payload={"due_at": due_at.isoformat(), "reason": reason, "attempt": n + 1})
    events.status_changed(conn, lead, "queued", actor="system")


def enqueue_new_lead(conn, lead: dict, now: datetime) -> None:
    """Called by intake for assistant-arm leads (architecture §4.4, §5 notes; plan P4-05)."""
    from . import messaging
    if lead["contact_pref"] == "whatsapp":  # greet on WhatsApp; a person replies there (no bot in v1)
        messaging.enqueue(conn, lead, "whatsapp_hello_v1", {"name": messaging.first_name(lead),
                          "treatment": messaging.treatment_word(lead), "clinic": _clinic_name(conn, lead)})
        handovers.create(conn, lead, ["whatsapp_preferred"], "normal", actor="system", note="Prefers WhatsApp: reply there")
        return
    if lead["contact_pref"] == "scheduled" and lead["scheduled_at"]:
        due = lead["scheduled_at"]
        reminder = due - timedelta(minutes=10)
        if reminder > now:
            messaging.enqueue(conn, lead, "call_reminder_v1", {"name": messaging.first_name(lead),
                              "time": messaging.fmt_time(due), "caller_id": get_settings().caller_id},
                              due_at=reminder, dedupe_key=f"reminder:{due.isoformat()}")
    elif calling_window.can_call_now(now):
        due = now
    else:
        due = calling_window.next_opening(now)
        # The form promised "after 9 am tomorrow"; confirm it in writing (EC-TIME-01).
        when = {"en": "after 9:00 am tomorrow", "hi": "कल सुबह 9 बजे के बाद"}[lead["language"] if lead["language"] == "hi" else "en"]
        messaging.enqueue(conn, lead, "enquiry_ack_v1", {"name": messaging.first_name(lead), "treatment": messaging.treatment_word(lead),
                          "clinic": _clinic_name(conn, lead), "when": when, "caller_id": get_settings().caller_id})
    schedule_call(conn, lead, due, "new_lead")


def _clinic_name(conn, lead) -> str:
    return conn.execute("SELECT name FROM clinic WHERE id = %s", (lead["clinic_id"],)).fetchone()["name"]


def no_answer_exhausted(conn, lead: dict) -> None:
    """Three calls unanswered: WhatsApp them and wait for a reply; staff if we can't (architecture §5)."""
    from . import messaging
    sent = messaging.enqueue(conn, lead, "no_answer_v1", {"name": messaging.first_name(lead), "treatment": messaging.treatment_word(lead)},
                             dedupe_key="no_answer")
    if sent:
        conn.execute("UPDATE lead SET whatsapp_sent_at = now() WHERE id = %s", (lead["id"],))
        events.status_changed(conn, lead, "whatsapp_sent", actor="system")
    else:
        handovers.create(conn, lead, ["not_reached"], "normal", actor="system", note="No answer after 3 calls; no WhatsApp consent")


# ---------------------------------------------------------------- circuit breaker
def breaker_record(name: str, ok: bool) -> None:
    with tx() as conn:
        conn.execute("INSERT INTO breaker (name) VALUES (%s) ON CONFLICT DO NOTHING", (name,))
        b = conn.execute("SELECT * FROM breaker WHERE name = %s FOR UPDATE", (name,)).fetchone()
        now = datetime.now(timezone.utc)
        if ok:
            if b["failures"]:
                conn.execute("UPDATE breaker SET failures = 0, window_start = now() WHERE name = %s", (name,))
            return
        failures = 1 if now - b["window_start"] > BREAKER_WINDOW else b["failures"] + 1
        opened = now + BREAKER_OPEN_FOR if failures >= BREAKER_THRESHOLD else b["open_until"]
        conn.execute("UPDATE breaker SET failures = %s, window_start = CASE WHEN %s = 1 THEN now() ELSE window_start END, "
                     "open_until = %s WHERE name = %s", (failures, failures, opened, name))
        if failures == BREAKER_THRESHOLD:
            events.append(conn, "breaker.opened", payload={"name": name, "until": opened.isoformat()})


def breaker_open(name: str) -> bool:
    with tx() as conn:
        b = conn.execute("SELECT open_until FROM breaker WHERE name = %s", (name,)).fetchone()
    return bool(b and b["open_until"] and b["open_until"] > datetime.now(timezone.utc))


def _llm_failures_recent() -> bool:
    """Opens the 'llm' breaker if most recent Groq calls failed (only when Groq is configured)."""
    if not get_settings().llm_enabled:
        return False
    with tx() as conn:
        rows = conn.execute("SELECT ok FROM llm_call WHERE at > now() - interval '2 minutes' ORDER BY id DESC LIMIT 10").fetchall()
    return len(rows) >= 5 and sum(not r["ok"] for r in rows) >= 4


# ---------------------------------------------------------------- worker
def claim_due(limit: int = 5) -> list[str]:
    with tx() as conn:
        rows = conn.execute(
            "UPDATE call_job SET status = 'running', locked_until = now() + %s, updated_at = now() WHERE id IN ("
            "  SELECT id FROM call_job WHERE (status = 'pending' AND due_at <= now()) "
            "     OR (status = 'running' AND locked_until < now()) "
            "  ORDER BY due_at LIMIT %s FOR UPDATE SKIP LOCKED) RETURNING id", (LEASE, limit)).fetchall()
    return [str(r["id"]) for r in rows]


def _finish_job(conn, job_id, status="done", error=None):
    conn.execute("UPDATE call_job SET status = %s, last_error = %s, locked_until = NULL, updated_at = now() WHERE id = %s",
                 (status, error, job_id))


def _fallback(conn, lead, job_id, why: str) -> None:
    handovers.create(conn, lead, ["system_fallback"], "normal", actor="system", note=f"Assistant unavailable: {why}")
    _finish_job(conn, job_id, "done", why)


def process_job(job_id: str, now: datetime | None = None) -> str:
    """Returns what happened (for logs and tests)."""
    s = get_settings()
    now = now or datetime.now(timezone.utc)
    with tx() as conn:
        job = conn.execute("SELECT * FROM call_job WHERE id = %s FOR UPDATE", (job_id,)).fetchone()
        if job is None or job["status"] != "running":
            return "skipped"
        lead = conn.execute("SELECT * FROM lead WHERE id = %s FOR UPDATE", (job["lead_id"],)).fetchone()
        if lead["status"] != "queued":
            _finish_job(conn, job_id, "cancelled", f"lead is {lead['status']}")
            return "cancelled"
        if conn.execute("SELECT 1 FROM suppression WHERE phone_e164 = %s", (lead["phone_e164"],)).fetchone():
            _finish_job(conn, job_id, "cancelled", "suppressed")
            events.status_changed(conn, lead, "not_interested", actor="system", reason="suppressed")
            return "suppressed"
        if not calling_window.can_call_now(now):
            conn.execute("UPDATE call_job SET status = 'pending', due_at = %s, locked_until = NULL WHERE id = %s",
                         (calling_window.next_opening(now), job_id))
            return "rescheduled_window"
        if not s.voice_agent_enabled:
            _fallback(conn, lead, job_id, "voice agent disabled")
            return "fallback"
        if breaker_open("telephony") or breaker_open("llm") or _llm_failures_recent():
            _fallback(conn, lead, job_id, "circuit breaker open")
            return "fallback"
        active = conn.execute("SELECT count(*) AS n FROM call_attempt WHERE made_by = 'assistant' "
                              "AND state IN ('dialing', 'ringing', 'in_progress')").fetchone()["n"]
        if active >= s.max_concurrent_calls:
            conn.execute("UPDATE call_job SET status = 'pending', due_at = now() + interval '30 seconds', locked_until = NULL "
                         "WHERE id = %s", (job_id,))
            return "rescheduled_busy"
        n = conn.execute("SELECT coalesce(max(attempt_no), 0) + 1 AS n FROM call_attempt WHERE lead_id = %s",
                         (lead["id"],)).fetchone()["n"]
        attempt = conn.execute(
            "INSERT INTO call_attempt (lead_id, attempt_no, made_by, provider, state, started_at) "
            "VALUES (%s, %s, 'assistant', %s, 'dialing', now()) RETURNING id", (lead["id"], n, s.telephony_provider)).fetchone()
        _finish_job(conn, job_id)
    try:
        pid = provider().place_call(str(attempt["id"]), lead["phone_e164"], s.caller_id)
        breaker_record("telephony", True)
    except (ProviderUnavailable, Exception) as e:
        breaker_record("telephony", False)
        with tx() as conn:
            conn.execute("UPDATE call_attempt SET state = 'failed', outcome = 'failed', ended_at = now() WHERE id = %s", (attempt["id"],))
            lead = conn.execute("SELECT * FROM lead WHERE id = %s FOR UPDATE", (lead["id"],)).fetchone()
            handovers.create(conn, lead, ["system_fallback"], "normal", actor="system", note=f"Call failed: {type(e).__name__}")
        return "fallback"
    with tx() as conn:
        conn.execute("UPDATE call_attempt SET provider_call_id = %s, state = 'ringing' WHERE id = %s", (pid, attempt["id"]))
        events.append(conn, "call.placed", lead_id=lead["id"], clinic_id=lead["clinic_id"], actor="system",
                      payload={"attempt": n, "provider": s.telephony_provider})
    return f"placed:{attempt['id']}"


# ---------------------------------------------------------------- call lifecycle
def _load(conn, attempt_id, lock=True):
    a = conn.execute("SELECT * FROM call_attempt WHERE id = %s" + (" FOR UPDATE" if lock else ""), (attempt_id,)).fetchone()
    if a is None:
        raise KeyError("unknown call attempt")
    lead = conn.execute("SELECT l.*, c.name AS clinic_name FROM lead l JOIN clinic c ON c.id = l.clinic_id WHERE l.id = %s",
                        (a["lead_id"],)).fetchone()
    return a, lead


def _agent(attempt, lead, session: Session) -> Agent:
    return Agent(session, ToolRegistry(DbBackend(str(lead["id"]), str(attempt["id"]))), nlu=default_nlu())


def on_status(attempt_id: str, status: str) -> str | None:
    """Normalised status from the provider. Returns the agent's first line when answered."""
    with tx() as conn:
        a, lead = _load(conn, attempt_id)
        if a["state"] in ("completed", "failed"):
            return None  # duplicate or late webhook (EC-CALL-11)
        if status == "answered":
            if a["state"] == "in_progress":
                return None
            conn.execute("UPDATE call_attempt SET state = 'in_progress', outcome = 'answered' WHERE id = %s", (attempt_id,))
            lead_row = conn.execute("SELECT * FROM lead WHERE id = %s FOR UPDATE", (lead["id"],)).fetchone()
            mark_reached(conn, lead_row, "assistant")
            events.append(conn, "call.attempted", lead_id=lead["id"], clinic_id=lead["clinic_id"], actor="assistant",
                          payload={"attempt": a["attempt_no"], "result": "answered", "by": "assistant"})
            session = Session(name=lead["name"].split()[0], treatment=lead["treatment"], clinic_id=lead["clinic_id"],
                              clinic_name=lead["clinic_name"], lang=lead["language"])
            conn.execute("INSERT INTO conversation (call_attempt_id, session, transcript) VALUES (%s, %s, '[]')",
                         (attempt_id, Jsonb({})))
        else:
            result = {"no_answer": "no_answer", "busy": "busy", "voicemail": "voicemail", "invalid": "invalid"}.get(status, "failed")
            conn.execute("UPDATE call_attempt SET state = 'completed', outcome = %s, ended_at = now() WHERE id = %s",
                         (result, attempt_id))
            events.append(conn, "call.attempted", lead_id=lead["id"], clinic_id=lead["clinic_id"], actor="assistant",
                          payload={"attempt": a["attempt_no"], "result": result, "by": "assistant"})
            lead_row = conn.execute("SELECT * FROM lead WHERE id = %s FOR UPDATE", (lead["id"],)).fetchone()
            tries = conn.execute("SELECT count(*) AS n FROM call_attempt WHERE lead_id = %s AND made_by = 'assistant'",
                                 (lead["id"],)).fetchone()["n"]
            if result == "invalid" or tries >= 3:  # invalid number: retrying won't help (EC-CALL-03)
                no_answer_exhausted(conn, lead_row)
            else:
                wait = timedelta(minutes=3) if result == "busy" and tries == 1 else RETRY_AFTER[tries]
                schedule_call(conn, lead_row, datetime.now(timezone.utc) + wait, f"retry_after_{result}")
            return None
    agent = _agent(a, lead, session)
    turn = agent.start()
    _save(attempt_id, agent.s)
    return turn.say


def _save(attempt_id, session: Session) -> None:
    with tx() as conn:
        conn.execute("UPDATE conversation SET session = %s, transcript = %s, guard_events = %s, updated_at = now() "
                     "WHERE call_attempt_id = %s",
                     (Jsonb(session.to_dict()), Jsonb(session.transcript), Jsonb(session.guard_events), attempt_id))


def _session_for(attempt_id):
    with tx() as conn:
        a, lead = _load(conn, attempt_id, lock=False)
        c = conn.execute("SELECT session FROM conversation WHERE call_attempt_id = %s", (attempt_id,)).fetchone()
    if a["state"] != "in_progress" or c is None:
        raise KeyError("call is not in progress")
    return a, lead, Session.from_dict(c["session"])


def on_caller_turn(attempt_id: str, text: str, confidence: float = 1.0) -> dict:
    a, lead, session = _session_for(attempt_id)
    agent = _agent(a, lead, session)
    t0 = _time.perf_counter()
    turn = agent.handle(text, confidence)
    _save(attempt_id, agent.s)
    if turn.end:
        finalize(attempt_id, agent.s)
    return {"say": turn.say, "end": turn.end, "ms": int((_time.perf_counter() - t0) * 1000),
            "lang": agent.s.lang, "outcome": agent.s.outcome}


def on_silence(attempt_id: str) -> dict:
    a, lead, session = _session_for(attempt_id)
    agent = _agent(a, lead, session)
    turn = agent.silence()
    _save(attempt_id, agent.s)
    if turn.end:
        finalize(attempt_id, agent.s)
    return {"say": turn.say, "end": turn.end, "lang": agent.s.lang, "outcome": agent.s.outcome}


def on_hangup(attempt_id: str) -> None:
    try:
        a, lead, session = _session_for(attempt_id)
    except KeyError:
        return
    agent = _agent(a, lead, session)
    agent.hangup()
    _save(attempt_id, agent.s)
    finalize(attempt_id, agent.s)


def finalize(attempt_id, session: Session) -> None:
    d = session.to_dict()
    summ = summarise(d)
    with tx() as conn:
        a, lead = _load(conn, attempt_id)
        if a["state"] == "completed":
            return
        conn.execute("UPDATE call_attempt SET state = 'completed', ended_at = now() WHERE id = %s", (attempt_id,))
        conn.execute("UPDATE conversation SET outcome = %s, summary = %s, captured = %s, final_stage = %s, prompt_version = %s, "
                     "session = %s, transcript = %s, guard_events = %s, updated_at = now() WHERE call_attempt_id = %s",
                     (session.outcome, summ["lines"], Jsonb(summ["captured"]),
                      ["open", "confirm_need", "urgency", "clinic", "time", "offer", "close"].index(session.stage) + 1
                      if session.stage in ("open", "confirm_need", "urgency", "clinic", "time", "offer", "close") else None,
                      RULES_VERSION, Jsonb(d), Jsonb(session.transcript), Jsonb(session.guard_events), attempt_id))
        events.append(conn, "call.completed", lead_id=lead["id"], clinic_id=lead["clinic_id"], actor="assistant",
                      payload={"outcome": session.outcome, "turns": session.turns, "summary_source": summ["source"]})


# ---------------------------------------------------------------- browser demo line
BROWSER_RING_FOR, BROWSER_IDLE_FOR = timedelta(seconds=90), timedelta(minutes=5)


def sweep_browser_calls() -> int:
    """The browser demo line has no provider webhooks: if the tab never answers, or is closed
    mid-call, close the attempt the way a phone network would (no answer / hang-up)."""
    with tx() as conn:
        ringing = conn.execute("SELECT id FROM call_attempt WHERE provider = 'browser' AND state IN ('dialing', 'ringing') "
                               "AND started_at < now() - %s", (BROWSER_RING_FOR,)).fetchall()
        idle = conn.execute("SELECT a.id FROM call_attempt a JOIN conversation c ON c.call_attempt_id = a.id "
                            "WHERE a.provider = 'browser' AND a.state = 'in_progress' AND c.updated_at < now() - %s",
                            (BROWSER_IDLE_FOR,)).fetchall()
    for r in ringing:
        on_status(str(r["id"]), "no_answer")
    for r in idle:
        on_hangup(str(r["id"]))
    return len(ringing) + len(idle)


# ---------------------------------------------------------------- loop
_last_ops = 0.0


def tick() -> dict:
    global _last_ops
    from . import messaging, ops
    out = {"jobs": [], "sweep": None, "messages": []}
    for job in claim_due():
        out["jobs"].append(process_job(job))
    if get_settings().browser_calls:
        out["browser_swept"] = sweep_browser_calls()
    out["messages"] = messaging.dispatch_due()
    from . import calendar_sync
    out["calendars"] = calendar_sync.sync_due()  # external calendars every ~10 minutes (Phase 6)
    with tx() as conn:
        conn.execute("UPDATE slot SET status = 'open', hold_expires_at = NULL WHERE status = 'held' AND hold_expires_at < now()")
        out["sweep"] = handovers.sweep(conn)
        out["expired"] = messaging.expire_unanswered(conn)
    if _time.monotonic() - _last_ops > 60:  # alert rules + automatic kill switch, once a minute
        _last_ops = _time.monotonic()
        out["alerts"] = ops.evaluate_alerts()
    return out


SLOT_TOP_UP_EVERY = 6 * 3600  # public demo site: keep a rolling week of open slots


def run_forever(interval: float = 2.0, stop=None) -> None:  # pragma: no cover - process entry point
    """Worker loop. `stop` (a threading.Event) ends it when the worker runs inside the web process."""
    print(f"Orchestrator worker {WORKER_ID} started.", flush=True)
    last_top_up = 0.0
    while not (stop and stop.is_set()):
        try:
            r = tick()
            if r["jobs"]:
                print(r, flush=True)
            if get_settings().env == "demo" and _time.monotonic() - last_top_up > SLOT_TOP_UP_EVERY:
                from .seed import seed
                seed(with_staff=False)
                last_top_up = _time.monotonic()
        except Exception as e:
            print("worker error:", type(e).__name__, e, flush=True)
        if stop:
            stop.wait(interval)
        else:
            _time.sleep(interval)


if __name__ == "__main__":  # python -m happysmile.orchestrator
    from .db import init_pool
    init_pool()
    run_forever()
