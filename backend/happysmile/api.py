"""HTTP API (architecture §12)."""

from __future__ import annotations

import asyncio
import json
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import anyio
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from . import enquiries, events, experiment, leads, metrics, slots
from .auth import Staff, current_staff, login, logout, require_role, staff_writer
from .db import tx
from .security import hash_ip

router = APIRouter(prefix="/v1")


def client_ip(request: Request) -> str | None:
    # Behind the production load balancer, trust only its X-Forwarded-For (configured at the proxy).
    fwd = request.headers.get("x-forwarded-for")
    return fwd.split(",")[0].strip() if fwd else (request.client.host if request.client else None)


# ---------------------------------------------------------------- public
@router.get("/enquiry-config")
def enquiry_config(lang: str = "en"):
    with tx() as conn:
        return enquiries.form_config(conn, lang)


class EnquiryIn(BaseModel):
    client_token: uuid.UUID
    name: str = Field(max_length=200)
    mobile: str = Field(max_length=30)
    treatment: str
    treatment_other: str | None = Field(default=None, max_length=200)
    clinic_id: str = Field(max_length=40)
    language: str
    contact_pref: str
    scheduled_at: datetime | None = None
    consent: bool
    disclosure_version: str = Field(max_length=40)


@router.post("/enquiries")
def create_enquiry(body: EnquiryIn, request: Request):
    sub = enquiries.Submission(
        client_token=body.client_token, name=body.name, mobile=body.mobile, treatment=body.treatment,
        treatment_other=(body.treatment_other or "").strip() or None, clinic_id=body.clinic_id, language=body.language,
        contact_pref=body.contact_pref, scheduled_at=body.scheduled_at, consent=body.consent,
        disclosure_version=body.disclosure_version)
    try:
        with tx() as conn:
            status, out = enquiries.submit(conn, sub, client_ip(request), request.headers.get("user-agent"))
    except enquiries.IntakeError as e:
        return JSONResponse({"error": e.code, "message": e.message, "fields": e.fields, **e.extra}, status_code=e.status)
    return JSONResponse(out, status_code=status)


# ---------------------------------------------------------------- auth
class LoginIn(BaseModel):
    username: str = Field(max_length=80)
    password: str = Field(max_length=200)


def _me(s: Staff) -> dict:
    with tx() as conn:
        clinics = [dict(r) for r in conn.execute(
            "SELECT id, name FROM clinic WHERE id = ANY(%s) ORDER BY name", (s.scope(None, conn),))]
    return {"username": s.username, "name": s.display_name, "role": s.role, "clinics": clinics}


@router.post("/auth/login")
def do_login(body: LoginIn, request: Request, response: Response):
    return _me(login(body.username.strip().lower(), body.password, client_ip(request), response))


@router.post("/auth/logout")
def do_logout(request: Request, response: Response):
    logout(request, response)
    return {"ok": True}


@router.get("/auth/me")
def me(staff: Staff = Depends(current_staff)):
    return _me(staff)


# ---------------------------------------------------------------- console
@router.get("/leads")
def get_leads(clinic: str | None = None, view: str = Query("to_call", pattern="^(to_call|done)$"),
              staff: Staff = Depends(current_staff)):
    with tx() as conn:
        return {"leads": leads.list_leads(conn, staff, staff.scope(clinic, conn), view)}


@router.get("/leads/{lead_id}")
def get_lead(lead_id: uuid.UUID, staff: Staff = Depends(current_staff)):
    with tx() as conn:
        return leads.lead_detail(conn, staff, str(lead_id))


@router.post("/leads/{lead_id}/claim")
def claim_lead(lead_id: uuid.UUID, staff: Staff = Depends(staff_writer)):
    with tx() as conn:
        return leads.claim(conn, staff, str(lead_id))


class OutcomeIn(BaseModel):
    outcome: str
    note: str | None = Field(default=None, max_length=300)


@router.post("/leads/{lead_id}/outcome")
def lead_outcome(lead_id: uuid.UUID, body: OutcomeIn, staff: Staff = Depends(staff_writer)):
    with tx() as conn:
        return leads.record_outcome(conn, staff, str(lead_id), body.outcome, body.note)


class BookIn(BaseModel):
    slot_id: uuid.UUID


@router.post("/leads/{lead_id}/bookings")
def book_lead(lead_id: uuid.UUID, body: BookIn, staff: Staff = Depends(staff_writer)):
    with tx() as conn:
        out = slots.book(conn, staff, str(lead_id), str(body.slot_id))
    if out.get("conflict"):
        return JSONResponse({"detail": out["message"]}, status_code=409)
    return out


@router.get("/metrics/today")
def metrics_today(clinic: str | None = None, staff: Staff = Depends(current_staff)):
    with tx() as conn:
        return metrics.from_events(conn, staff.scope(clinic, conn))


@router.get("/dentists")
def dentists(clinic: str | None = None, staff: Staff = Depends(current_staff)):
    with tx() as conn:
        return {"dentists": slots.list_dentists(conn, staff.scope(clinic, conn))}


@router.get("/slots")
def get_slots(clinic: str, days: int = Query(7, ge=1, le=14), staff: Staff = Depends(current_staff)):
    with tx() as conn:
        staff.scope(clinic, conn)
        return slots.open_slots(conn, clinic, days)


class SlotsIn(BaseModel):
    clinic_id: str
    dentist_id: uuid.UUID
    day: date
    start: str = "09:00"
    end: str = "13:00"
    duration_min: int = 30


@router.post("/slots/bulk")
def add_slots(body: SlotsIn, staff: Staff = Depends(staff_writer)):
    with tx() as conn:
        return slots.add_slots(conn, staff, body.clinic_id, str(body.dentist_id), body.day, body.start, body.end, body.duration_min)


# ---------------------------------------------------------------- live updates (Server-Sent Events)
@router.get("/stream")
async def stream(request: Request, staff: Staff = Depends(current_staff)):
    """Pushes lightweight change notices (no personal data); the console refetches.

    Resumes from Last-Event-ID after a reconnect (EC-Q-09). Polls the append-only event
    table, which is safe across several app instances.
    """
    def scope():
        with tx() as conn:
            return staff.scope(None, conn)

    def max_id():
        with tx() as conn:
            return conn.execute("SELECT coalesce(max(id), 0) AS m FROM event").fetchone()["m"]

    def fetch(after: int, clinics: list[str]):
        with tx() as conn:
            return conn.execute("SELECT id, type, lead_id, clinic_id FROM event WHERE id > %s AND clinic_id = ANY(%s) "
                                "ORDER BY id LIMIT 200", (after, clinics)).fetchall()

    clinics = await anyio.to_thread.run_sync(scope)
    last = request.headers.get("last-event-id")
    cursor = int(last) if last and last.isdigit() else await anyio.to_thread.run_sync(max_id)

    async def gen():
        nonlocal cursor
        yield "retry: 3000\n\n"
        idle = 0
        while not await request.is_disconnected():
            rows = await anyio.to_thread.run_sync(fetch, cursor, clinics)
            for r in rows:
                cursor = r["id"]
                data = json.dumps({"type": r["type"], "lead_id": str(r["lead_id"]) if r["lead_id"] else None,
                                   "clinic_id": r["clinic_id"]})
                yield f"id: {r['id']}\nevent: change\ndata: {data}\n\n"
            idle = 0 if rows else idle + 1
            if idle and idle % 15 == 0:
                yield ": keep-alive\n\n"
            await asyncio.sleep(1)

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


# ---------------------------------------------------------------- Phase 3: assistant queues, review, feedback, test calls
from . import console_voice  # noqa: E402


@router.get("/queue")
def queue(tab: str = Query(pattern="^(needs_you|booked|no_answer)$"), clinic: str | None = None, staff: Staff = Depends(current_staff)):
    with tx() as conn:
        clinics = staff.scope(clinic, conn)
        fn = {"needs_you": console_voice.needs_you, "booked": console_voice.assistant_bookings, "no_answer": console_voice.no_answer}[tab]
        return {"items": fn(conn, clinics)}


@router.get("/leads/{lead_id}/assistant")
def lead_assistant(lead_id: uuid.UUID, staff: Staff = Depends(current_staff)):
    with tx() as conn:
        leads.get_lead_for(conn, staff, str(lead_id))
        return console_voice.lead_extras(conn, lead_id)


class FeedbackIn(BaseModel):
    is_correct: bool
    reason: str | None = Field(default=None, max_length=80)


@router.post("/handovers/{handover_id}/feedback")
def handover_feedback(handover_id: uuid.UUID, body: FeedbackIn, staff: Staff = Depends(staff_writer)):
    with tx() as conn:
        return console_voice.feedback(conn, staff, str(handover_id), body.is_correct, body.reason)


class ReviewIn(BaseModel):
    action: str = Field(pattern="^(approve|change|cancel)$")
    slot_id: uuid.UUID | None = None
    reason: str | None = Field(default=None, max_length=120)


@router.post("/bookings/{booking_id}/review")
def review_booking(booking_id: uuid.UUID, body: ReviewIn, staff: Staff = Depends(staff_writer)):
    with tx() as conn:
        return console_voice.review_booking(conn, staff, str(booking_id), body.action,
                                            str(body.slot_id) if body.slot_id else None, body.reason)


class TestCallIn(BaseModel):
    name: str = Field(default="Test", max_length=30)
    treatment: str = "braces"
    clinic_id: str
    language: str = "en"


class TestTurnIn(BaseModel):
    text: str | None = Field(default=None, max_length=500)
    silence: bool = False
    hangup: bool = False
    confidence: float = Field(default=1.0, ge=0, le=1)


@router.post("/test-calls")
def start_test_call(body: TestCallIn, staff: Staff = Depends(staff_writer)):
    with tx() as conn:
        return console_voice.start_test_call(conn, staff, body.name, body.treatment, body.clinic_id, body.language)


@router.post("/test-calls/{call_id}/turn")
def test_call_turn(call_id: uuid.UUID, body: TestTurnIn, staff: Staff = Depends(staff_writer)):
    def run():
        with tx() as conn:
            return console_voice.test_call_turn(conn, staff, str(call_id), body.text, body.silence, body.hangup, body.confidence)
    return run()


# ---------------------------------------------------------------- browser demo line (development only)
# With TELEPHONY_PROVIDER=browser the worker "dials" the patient's own browser tab. The page that
# submitted the form polls here with its submission token (a random UUID only that tab knows),
# shows an incoming call, and the conversation runs through the real call path (orchestrator).
def _demo_call(client_token: uuid.UUID) -> dict:
    from .config import get_settings
    if not get_settings().browser_calls:
        raise HTTPException(404, "Not found")
    with tx() as conn:
        sub = conn.execute("SELECT lead_id, kind FROM enquiry_submission WHERE client_token = %s", (client_token,)).fetchone()
        if sub is None or sub["kind"] != "created":
            raise HTTPException(404, "Not found")
        lead = conn.execute("SELECT id, status, arm, language FROM lead WHERE id = %s", (sub["lead_id"],)).fetchone()
        a = conn.execute("SELECT a.id, a.state, a.provider, c.outcome FROM call_attempt a "
                         "LEFT JOIN conversation c ON c.call_attempt_id = a.id "
                         "WHERE a.lead_id = %s AND a.made_by = 'assistant' ORDER BY a.attempt_no DESC LIMIT 1",
                         (lead["id"],)).fetchone()
        job = conn.execute("SELECT due_at FROM call_job WHERE lead_id = %s AND status IN ('pending', 'running') "
                           "ORDER BY due_at LIMIT 1", (lead["id"],)).fetchone()
    return {"lead": lead, "attempt": a if a and a["provider"] == "browser" else None, "job": job}


def _demo_state(d: dict) -> dict:
    lead, a, job = d["lead"], d["attempt"], d["job"]
    if a and a["state"] in ("dialing", "ringing"):
        return {"state": "ringing", "lang": lead["language"]}
    if a and a["state"] == "in_progress":
        return {"state": "in_call", "lang": lead["language"]}
    if job and lead["status"] == "queued":
        return {"state": "queued", "due_at": job["due_at"].isoformat(), "retry": a is not None}
    if a:
        return {"state": "ended", "outcome": a["outcome"]}
    # Never dialled: control group, WhatsApp/scheduled preference, or handed to staff (kill switch, fallback).
    return {"state": "staff", "arm": lead["arm"]}


@router.get("/demo-call/{client_token}")
def demo_call_status(client_token: uuid.UUID):
    return _demo_state(_demo_call(client_token))


@router.post("/demo-call/{client_token}/answer")
def demo_call_answer(client_token: uuid.UUID):
    from . import orchestrator
    d = _demo_call(client_token)
    if not d["attempt"] or d["attempt"]["state"] not in ("dialing", "ringing"):
        raise HTTPException(409, "There is no incoming call to answer.")
    say = orchestrator.on_status(str(d["attempt"]["id"]), "answered")
    if say is None:
        raise HTTPException(409, "The call has already ended.")
    return {"say": say, "end": False, "lang": d["lead"]["language"]}


@router.post("/demo-call/{client_token}/decline")
def demo_call_decline(client_token: uuid.UUID):
    from . import orchestrator
    d = _demo_call(client_token)
    if d["attempt"] and d["attempt"]["state"] in ("dialing", "ringing"):
        orchestrator.on_status(str(d["attempt"]["id"]), "no_answer")  # retried later, like a missed phone call
    return _demo_state(_demo_call(client_token))


class DemoTurnIn(BaseModel):
    text: str | None = Field(default=None, max_length=500)
    silence: bool = False
    hangup: bool = False
    confidence: float = Field(default=1.0, ge=0, le=1)


@router.post("/demo-call/{client_token}/turn")
def demo_call_turn(client_token: uuid.UUID, body: DemoTurnIn):
    from . import orchestrator
    d = _demo_call(client_token)
    if not d["attempt"] or d["attempt"]["state"] != "in_progress":
        raise HTTPException(409, "The call has ended.")
    aid = str(d["attempt"]["id"])
    if body.hangup:
        orchestrator.on_hangup(aid)
        with tx() as conn:
            c = conn.execute("SELECT outcome FROM conversation WHERE call_attempt_id = %s", (aid,)).fetchone()
        out = {"say": None, "end": True, "outcome": c["outcome"] if c else None}
    elif body.silence or not (body.text or "").strip():
        out = orchestrator.on_silence(aid)
    else:
        out = orchestrator.on_caller_turn(aid, body.text.strip(), body.confidence)
    if out.get("end"):
        out["result"] = _demo_state(_demo_call(client_token))
    return out


# ---------------------------------------------------------------- telephony webhooks (vendor adapters map onto this)
class TelephonyStatusIn(BaseModel):
    event_id: str = Field(max_length=100)
    provider_call_id: str = Field(max_length=100)
    status: str = Field(max_length=30)


@router.post("/hooks/telephony/status", include_in_schema=False)
async def telephony_status(request: Request):
    from . import orchestrator, telephony
    from .config import get_settings
    raw = await request.body()
    if not telephony.verify_signature(raw, request.headers.get("x-signature"), get_settings().telephony_webhook_secret):
        raise HTTPException(401, "bad signature")
    body = TelephonyStatusIn.model_validate_json(raw)
    status = telephony.STATUS_MAP.get(body.status)
    if status is None:
        return {"ok": True, "ignored": body.status}

    def apply():
        with tx() as conn:
            a = conn.execute("SELECT id FROM call_attempt WHERE provider_call_id = %s", (body.provider_call_id,)).fetchone()
        if not a:
            return {"ok": True, "unknown_call": True}
        if status == "completed":
            orchestrator.on_hangup(str(a["id"]))
        else:
            orchestrator.on_status(str(a["id"]), status)  # idempotent: duplicates/late events are ignored
        return {"ok": True}
    return await anyio.to_thread.run_sync(apply)


# ---------------------------------------------------------------- Phase 4: WhatsApp webhook (Meta Cloud API format)
@router.get("/hooks/whatsapp", include_in_schema=False)
def whatsapp_verify(request: Request):
    from fastapi.responses import PlainTextResponse
    from .config import get_settings
    q = request.query_params
    token = get_settings().whatsapp_verify_token
    if q.get("hub.mode") == "subscribe" and token and q.get("hub.verify_token") == token:
        return PlainTextResponse(q.get("hub.challenge", ""))
    raise HTTPException(403, "verification failed")


@router.post("/hooks/whatsapp", include_in_schema=False)
async def whatsapp_webhook(request: Request):
    from . import messaging
    raw = await request.body()
    if not messaging.verify_meta_signature(raw, request.headers.get("x-hub-signature-256")):
        raise HTTPException(401, "bad signature")
    try:
        items = messaging.parse_meta_webhook(json.loads(raw))
    except (ValueError, AttributeError):
        raise HTTPException(400, "bad payload")

    def apply():
        done = []
        for it in items:
            with tx() as conn:
                fresh = conn.execute("INSERT INTO webhook_event (provider, event_id) VALUES ('whatsapp', %s) ON CONFLICT DO NOTHING "
                                     "RETURNING event_id", (it["event_id"],)).fetchone()
                if not fresh:
                    continue  # duplicate delivery
                if it["kind"] == "status":
                    messaging.handle_status(conn, it["message_id"], it["status"], it.get("error"))
                else:
                    done.append(messaging.handle_inbound(conn, it["from"], it["text"], it["message_id"]))
        return {"ok": True, "handled": len(items), "inbound": done}
    return await anyio.to_thread.run_sync(apply)


# ---------------------------------------------------------------- Phase 4: ops, kill switch, go-live gates
from . import ops  # noqa: E402


@router.get("/admin/ops")
def ops_view(clinic: str | None = None, staff: Staff = Depends(require_role("manager", "admin"))):
    with tx() as conn:
        clinics = staff.scope(clinic, conn)
        return {"metrics": ops.metrics(conn, clinics), "alerts": ops.open_alerts(conn, clinics)}


class KillIn(BaseModel):
    action: str = Field(pattern="^(stop_assistant|pause_booking|resume_booking|drill)$")
    clinic_id: str | None = None
    reason: str = Field(min_length=3, max_length=200)


@router.post("/admin/kill-switch")
def kill_switch(body: KillIn, request: Request, staff: Staff = Depends(require_role("manager", "admin"))):
    from .auth import require_csrf
    require_csrf(request)
    with tx() as conn:
        if body.clinic_id:
            staff.scope(body.clinic_id, conn)
        return ops.kill_switch(conn, body.action, body.clinic_id, staff.id, body.reason)


@router.get("/admin/go-live")
def go_live(clinic: str | None = None, staff: Staff = Depends(require_role("manager", "admin"))):
    with tx() as conn:
        clinics = staff.scope(clinic, conn)
        g2 = ops.g2_checks(conn)
        return {"g2": g2, "g2_passed": all(c["ok"] for c in g2),
                "g3": {c: ops.g3_checks(conn, c) for c in clinics},
                "enforced": __import__("happysmile.config", fromlist=["x"]).get_settings().is_production_like}


class AttestIn(BaseModel):
    item: str
    note: str | None = Field(default=None, max_length=300)


@router.post("/admin/go-live/attest")
def go_live_attest(body: AttestIn, request: Request, staff: Staff = Depends(require_role("admin"))):
    from .auth import require_csrf
    require_csrf(request)
    try:
        with tx() as conn:
            ops.attest(conn, body.item, staff.id, body.note)
    except ValueError as e:
        raise HTTPException(422, str(e))
    return {"ok": True}


# ---------------------------------------------------------------- Phase 5: reviews, attendance, change log, readout, G4
from . import readout, reviews  # noqa: E402


@router.get("/reviews/sample")
def review_sample(day: date | None = None, clinic: str | None = None, staff: Staff = Depends(current_staff)):
    from .config import IST
    with tx() as conn:
        return {"calls": reviews.daily_sample(conn, staff, staff.scope(clinic, conn), day or datetime.now(IST).date()),
                "issue_tags": reviews.ISSUE_TAGS}


@router.get("/reviews/calls/{call_id}")
def review_call(call_id: uuid.UUID, staff: Staff = Depends(current_staff)):
    with tx() as conn:
        return reviews.call_detail(conn, staff, str(call_id))


class ReviewScoreIn(BaseModel):
    disclosure_ok: bool
    booking_ok: bool | None = None
    handover_ok: bool | None = None
    tone_ok: bool
    issue_tags: list[str] = []
    notes: str | None = Field(default=None, max_length=500)


@router.post("/reviews/calls/{call_id}")
def review_score(call_id: uuid.UUID, body: ReviewScoreIn, staff: Staff = Depends(staff_writer)):
    with tx() as conn:
        return reviews.record_review(conn, staff, str(call_id), body.model_dump())


@router.get("/attendance")
def attendance(clinic: str | None = None, days: int = Query(7, ge=1, le=31), staff: Staff = Depends(current_staff)):
    with tx() as conn:
        return {"appointments": reviews.attendance_list(conn, staff.scope(clinic, conn), days)}


class AttendanceIn(BaseModel):
    attended: bool


@router.post("/bookings/{booking_id}/attendance")
def mark_attendance(booking_id: uuid.UUID, body: AttendanceIn, staff: Staff = Depends(staff_writer)):
    with tx() as conn:
        return reviews.record_attendance(conn, staff, str(booking_id), body.attended)


@router.get("/admin/weekly-review")
def weekly_review(end: date | None = None, clinic: str | None = None, staff: Staff = Depends(require_role("manager", "admin"))):
    from .config import IST
    with tx() as conn:
        return reviews.weekly_report(conn, staff.scope(clinic, conn), end or datetime.now(IST).date())


class ChangeIn(BaseModel):
    version: str = Field(min_length=1, max_length=20)
    area: str = Field(pattern="^(lines|keywords|understanding|prompt|thresholds|other)$")
    description: str = Field(min_length=5, max_length=500)
    reason: str | None = Field(default=None, max_length=300)


@router.get("/admin/rules-changes")
def rules_changes(staff: Staff = Depends(require_role("manager", "admin"))):
    from .voice import RULES_VERSION
    with tx() as conn:
        return {"current_version": RULES_VERSION, "changes": reviews.list_changes(conn)}


@router.post("/admin/rules-changes")
def add_rules_change(body: ChangeIn, staff: Staff = Depends(staff_writer)):
    if staff.role not in ("manager", "admin"):
        raise HTTPException(403, "You don't have permission to do this.")
    with tx() as conn:
        return reviews.log_change(conn, staff, body.version, body.area, body.description, body.reason)


def _readout(conn, staff: Staff, start: date | None, end: date | None, clinic: str | None):
    from .config import IST
    end = end or datetime.now(IST).date()
    if start is None:
        first = conn.execute("SELECT min(live_since) AS t FROM experiment_config").fetchone()["t"]
        start = first.astimezone(IST).date() if first else end - timedelta(days=27)
    if start > end:
        raise HTTPException(422, "'from' must be on or before 'to'.")
    return readout.compute(conn, start, end, staff.scope(clinic, conn))


@router.get("/admin/readout")
def get_readout(start: date | None = Query(None, alias="from"), end: date | None = Query(None, alias="to"), clinic: str | None = None,
                staff: Staff = Depends(require_role("manager", "admin"))):
    with tx() as conn:
        r = _readout(conn, staff, start, end, clinic)
        r["decisions"] = [{"decision": d["decision"], "recommended": d["recommended"], "notes": d["notes"], "by": d["display_name"],
                           "at": d["decided_at"].isoformat()} for d in conn.execute(
            "SELECT p.*, s.display_name FROM pilot_decision p JOIN staff s ON s.id = p.decided_by ORDER BY p.id DESC LIMIT 10")]
    return r


@router.get("/admin/readout.md")
def get_readout_md(start: date | None = Query(None, alias="from"), end: date | None = Query(None, alias="to"), clinic: str | None = None,
                   synthetic: bool = False, staff: Staff = Depends(require_role("manager", "admin"))):
    from fastapi.responses import PlainTextResponse
    with tx() as conn:
        r = _readout(conn, staff, start, end, clinic)
    return PlainTextResponse(readout.render_markdown(r, synthetic), media_type="text/markdown; charset=utf-8",
                             headers={"Content-Disposition": f'attachment; filename="pilot-readout-{r["period"]["to"]}.md"'})


class DecisionIn(BaseModel):
    decision: str = Field(pattern="^(scale|extend|fix_first|stop_or_redesign)$")
    notes: str = Field(min_length=10, max_length=2000)
    start: date | None = Field(default=None, alias="from")
    end: date | None = Field(default=None, alias="to")


@router.post("/admin/readout/decision")
def record_decision(body: DecisionIn, request: Request, staff: Staff = Depends(require_role("admin"))):
    from psycopg.types.json import Jsonb
    from .auth import require_csrf
    require_csrf(request)
    with tx() as conn:
        r = _readout(conn, staff, body.start, body.end, None)
        conn.execute("INSERT INTO pilot_decision (decision, recommended, notes, decided_by, readout) VALUES (%s, %s, %s, %s, %s)",
                     (body.decision, r["recommendation"]["decision"], body.notes, staff.id, Jsonb(json.loads(json.dumps(r, default=str)))))
        events.append(conn, "pilot.decision", actor=f"staff:{staff.id}",
                      payload={"decision": body.decision, "recommended": r["recommendation"]["decision"]})
        events.audit(conn, staff.id, "pilot_decision_recorded", detail={"decision": body.decision})
    return {"ok": True, "recommended": r["recommendation"]["decision"]}


# ---------------------------------------------------------------- Phase 6: rollout, calendar, live transfer
from . import calendar_sync, rollout  # noqa: E402


@router.get("/admin/rollout")
def rollout_view(staff: Staff = Depends(require_role("manager", "admin"))):
    from .config import get_settings
    with tx() as conn:
        clinics = rollout.wave_status(conn)
        waves = sorted({c["wave"] for c in clinics if c["wave"] and c["wave"] > 1})
        return {"clinics": clinics, "latest_g4": rollout.latest_g4(conn), "max_share": float(rollout.max_share()),
                "permanent_control_share": get_settings().permanent_control_share,
                "waves": {w: rollout.wave_checks(conn, w) for w in waves},
                "enforced": get_settings().is_production_like}


@router.post("/admin/rollout/waves/{wave}/activate")
def rollout_activate(wave: int, request: Request, staff: Staff = Depends(require_role("admin"))):
    from .auth import require_csrf
    require_csrf(request)
    try:
        with tx() as conn:
            return rollout.activate_wave(conn, wave, staff.id)
    except PermissionError as e:
        raise HTTPException(409, str(e))
    except ValueError as e:
        raise HTTPException(422, str(e))


class OnboardIn(BaseModel):
    clinic_id: str
    item: str
    note: str | None = Field(default=None, max_length=300)


@router.post("/admin/rollout/onboarding")
def rollout_onboard(body: OnboardIn, request: Request, staff: Staff = Depends(require_role("admin"))):
    from .auth import require_csrf
    require_csrf(request)
    try:
        with tx() as conn:
            rollout.attest_onboarding(conn, body.clinic_id, body.item, staff.id, body.note)
    except ValueError as e:
        raise HTTPException(422, str(e))
    return {"ok": True}


class CalendarIn(BaseModel):
    adapter: str = Field(pattern="^(local|http)$")


@router.put("/admin/clinics/{clinic_id}/calendar")
def set_calendar(clinic_id: str, body: CalendarIn, request: Request, staff: Staff = Depends(require_role("admin"))):
    from .auth import require_csrf
    from .config import get_settings
    require_csrf(request)
    if body.adapter == "http" and not get_settings().calendar_api_url:
        raise HTTPException(409, "Set CALENDAR_API_URL and CALENDAR_API_TOKEN first.")
    with tx() as conn:
        conn.execute("UPDATE clinic SET calendar_adapter = %s WHERE id = %s", (body.adapter, clinic_id))
        events.audit(conn, staff.id, "calendar_adapter_set", detail={"clinic": clinic_id, "adapter": body.adapter})
    return {"ok": True}


@router.post("/admin/clinics/{clinic_id}/calendar/sync")
def sync_calendar(clinic_id: str, request: Request, staff: Staff = Depends(require_role("admin", "manager"))):
    from .auth import require_csrf
    require_csrf(request)
    try:
        with tx() as conn:
            if not calendar_sync.is_external(conn, clinic_id):
                raise HTTPException(409, "This clinic uses the manual slot list.")
            return calendar_sync.sync(conn, clinic_id)
    except calendar_sync.CalendarUnavailable as e:
        raise HTTPException(409, str(e))


class TransferIn(BaseModel):
    available: bool
    phone: str | None = Field(default=None, max_length=30)
    hours: float = Field(default=4, gt=0, le=12)


@router.get("/me/transfer")
def my_transfer(staff: Staff = Depends(current_staff)):
    with tx() as conn:
        r = conn.execute("SELECT phone_e164, transfer_available, transfer_available_until FROM staff WHERE id = %s", (staff.id,)).fetchone()
    until = r["transfer_available_until"]
    on = r["transfer_available"] and (until is None or until > datetime.now(timezone.utc))
    return {"available": bool(on), "phone": r["phone_e164"],
            "until": r["transfer_available_until"].isoformat() if on and r["transfer_available_until"] else None}


@router.post("/me/transfer")
def set_my_transfer(body: TransferIn, staff: Staff = Depends(staff_writer)):
    from .phone import normalise_mobile
    with tx() as conn:
        phone = conn.execute("SELECT phone_e164 FROM staff WHERE id = %s", (staff.id,)).fetchone()["phone_e164"]
        if body.phone:
            phone = normalise_mobile(body.phone)
            if not phone:
                raise HTTPException(422, "Enter a 10-digit mobile number for live transfers.")
        if body.available and not phone:
            raise HTTPException(422, "Add the phone number transfers should ring.")
        conn.execute("UPDATE staff SET phone_e164 = %s, transfer_available = %s, transfer_available_until = "
                     "CASE WHEN %s THEN now() + %s ELSE NULL END WHERE id = %s",
                     (phone, body.available, body.available, timedelta(hours=body.hours), staff.id))
        events.audit(conn, staff.id, "transfer_availability", detail={"available": body.available})
    return {"ok": True}


# ---------------------------------------------------------------- admin and manager
@router.get("/admin/experiment")
def get_experiment(staff: Staff = Depends(require_role("admin", "manager"))):
    with tx() as conn:
        rows = conn.execute("SELECT c.id, c.name, e.assistant_share, e.updated_at FROM experiment_config e "
                            "JOIN clinic c ON c.id = e.clinic_id ORDER BY c.name").fetchall()
    return {"clinics": [{"id": r["id"], "name": r["name"], "assistant_share": float(r["assistant_share"]),
                         "updated_at": r["updated_at"].isoformat()} for r in rows]}


class ShareIn(BaseModel):
    assistant_share: Decimal = Field(ge=0, le=1)


@router.put("/admin/experiment/{clinic_id}")
def put_experiment(clinic_id: str, body: ShareIn, request: Request, staff: Staff = Depends(require_role("admin"))):
    from .auth import require_csrf
    require_csrf(request)
    try:
        with tx() as conn:
            experiment.set_share(conn, clinic_id, body.assistant_share, staff.id)
            events.audit(conn, staff.id, "experiment_share_changed",
                         detail={"clinic": clinic_id, "share": float(body.assistant_share)}, ip_hash=hash_ip(client_ip(request)))
    except PermissionError as e:
        raise HTTPException(409, str(e))
    except ValueError as e:
        raise HTTPException(422, str(e))
    return {"ok": True}


@router.get("/admin/metrics/consistency")
def metrics_consistency(staff: Staff = Depends(require_role("admin", "manager"))):
    with tx() as conn:
        return metrics.consistency(conn, staff.scope(None, conn))


@router.get("/audit")
def audit_log(lead_id: uuid.UUID, staff: Staff = Depends(require_role("admin", "manager"))):
    with tx() as conn:
        rows = conn.execute("SELECT a.at, a.action, a.detail, s.display_name FROM audit_log a "
                            "LEFT JOIN staff s ON s.id = a.staff_id WHERE a.lead_id = %s ORDER BY a.at DESC LIMIT 200",
                            (lead_id,)).fetchall()
    return {"entries": [{"at": r["at"].isoformat(), "action": r["action"], "by": r["display_name"],
                         "detail": r["detail"]} for r in rows]}
