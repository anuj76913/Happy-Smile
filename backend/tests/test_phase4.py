"""Phase 4: WhatsApp messaging, no-answer flow, language switch, kill switch, alerts, go-live gates."""

import dataclasses
import hashlib
import hmac
import json
import os
import uuid
from datetime import datetime, timedelta

import httpx
import pytest

from happysmile import config, enquiries, messaging, ops, orchestrator, telephony
from happysmile.config import IST
from happysmile.db import tx
from happysmile.voice.language import detect

from .conftest import CSRF, enquiry, login_as
from .test_voice_flow import DAY, converse, place, q, submit

SECRET = "app-secret"


@pytest.fixture
def voice_on():
    os.environ.update({"VOICE_AGENT_ENABLED": "true", "WHATSAPP_APP_SECRET": SECRET, "WHATSAPP_VERIFY_TOKEN": "vt"})
    config.get_settings.cache_clear()
    with tx() as conn:
        conn.execute("UPDATE experiment_config SET assistant_share = 1 WHERE clinic_id = 'riverside'")
    telephony.set_provider(telephony.SimProvider())
    sim = messaging.SimWhatsApp()
    messaging.set_provider(sim)
    yield sim


def meta_post(client, payload: dict):
    raw = json.dumps(payload).encode()
    sig = "sha256=" + hmac.new(SECRET.encode(), raw, hashlib.sha256).hexdigest()
    return client.post("/v1/hooks/whatsapp", content=raw, headers={"x-hub-signature-256": sig, "content-type": "application/json"})


def status_payload(mid, status, error=None):
    st = {"id": mid, "status": status}
    if error:
        st["errors"] = [{"code": 131026, "title": error}]
    return {"entry": [{"changes": [{"value": {"statuses": [st]}}]}]}


def inbound_payload(phone, text):
    return {"entry": [{"changes": [{"value": {"messages": [
        {"from": phone.lstrip("+"), "id": f"wamid.in-{uuid.uuid4()}", "type": "text", "text": {"body": text}}]}}]}]}


def book_by_assistant(client):
    lead = submit(client)
    converse(place(lead), ["yes", "yes", "no", "yes", "tomorrow evening", "first", "no"])
    return lead


# ---------------------------------------------------------------- messaging
def test_assistant_booking_sends_confirmation_and_tracks_status(client, voice_on):
    lead = book_by_assistant(client)
    m = q("SELECT * FROM message WHERE lead_id = %s", lead)[0]
    assert m["template_id"] == "booking_confirm_v1" and m["status"] == "queued" and "Dr." in m["body"]
    assert messaging.dispatch_due() == ["sent"]
    sent = voice_on.sent[0]
    assert sent["template"] == "booking_confirm_v1" and len(sent["params"]) == 5 and sent["to"].startswith("+91")
    mid = sent["id"]
    assert meta_post(client, status_payload(mid, "delivered")).status_code == 200
    assert meta_post(client, status_payload(mid, "read")).status_code == 200
    meta_post(client, status_payload(mid, "delivered"))                        # out of order: ignored
    assert q("SELECT whatsapp_status FROM booking")[0]["whatsapp_status"] == "read"
    assert messaging.dispatch_due() == []                                       # never sent twice (EC-WA-07)


def test_webhook_rejects_bad_signature_and_dedupes(client, voice_on):
    raw = json.dumps(status_payload("x", "read")).encode()
    assert client.post("/v1/hooks/whatsapp", content=raw, headers={"x-hub-signature-256": "sha256=bad"}).status_code == 401
    lead = book_by_assistant(client)
    messaging.dispatch_due()
    payload = inbound_payload(q("SELECT phone_e164 FROM lead WHERE id = %s", lead)[0]["phone_e164"], "Can I change the time?")
    meta_post(client, payload)
    meta_post(client, payload)                                                   # same event delivered twice
    assert q("SELECT count(*) AS n FROM message WHERE direction = 'inbound'")[0]["n"] == 1
    assert client.get("/v1/hooks/whatsapp?hub.mode=subscribe&hub.verify_token=vt&hub.challenge=42").text == "42"


def test_control_arm_gets_no_automated_messages(client, voice_on):
    with tx() as conn:
        conn.execute("UPDATE experiment_config SET assistant_share = 0")
    r = client.post("/v1/enquiries", json=enquiry())
    lead = q("SELECT id FROM lead WHERE public_ref = %s", r.json()["ref"])[0]["id"]
    login_as(client, "kavya")
    slot = client.get("/v1/slots?clinic=riverside").json()["slots"][0]["id"]
    client.post(f"/v1/leads/{lead}/bookings", json={"slot_id": slot}, headers=CSRF)
    assert q("SELECT count(*) AS n FROM message")[0]["n"] == 0


def test_failed_confirmation_hands_over_to_staff(client, voice_on):
    os.environ["WHATSAPP_PROVIDER"] = "meta"
    config.get_settings.cache_clear()
    messaging.set_provider(messaging.MetaCloudWhatsApp(transport=httpx.MockTransport(
        lambda r: httpx.Response(400, json={"error": {"message": "not a WhatsApp user"}}))))
    lead = book_by_assistant(client)
    assert messaging.dispatch_due() == ["failed"]
    assert q("SELECT whatsapp_status FROM booking")[0]["whatsapp_status"] == "failed"
    h = q("SELECT reason_tags FROM handover WHERE lead_id = %s", lead)[0]
    assert h["reason_tags"] == ["whatsapp_failed"]                              # EC-WA-01: a person calls instead


def test_meta_adapter_payload():
    seen = []

    def handler(req):
        seen.append((req.url.path, json.loads(req.content), req.headers["authorization"]))
        return httpx.Response(200, json={"messages": [{"id": "wamid.ABC"}]})
    os.environ.update({"WHATSAPP_TOKEN": "tok", "WHATSAPP_PHONE_NUMBER_ID": "123"})
    config.get_settings.cache_clear()
    mid = messaging.MetaCloudWhatsApp(transport=httpx.MockTransport(handler)).send_template(
        "+919876543210", "no_answer_v1", "hi", ["Ravi", "ब्रेसेस"])
    path, body, auth = seen[0]
    assert mid == "wamid.ABC" and path.endswith("/123/messages") and auth == "Bearer tok"
    assert body["to"] == "919876543210" and body["template"]["name"] == "no_answer_v1"
    assert body["template"]["language"]["code"] == "hi"
    assert [p["text"] for p in body["template"]["components"][0]["parameters"]] == ["Ravi", "ब्रेसेस"]


# ---------------------------------------------------------------- no-answer flow, replies, STOP
def _no_answer_three_times(client):
    lead = submit(client)
    for _ in range(3):
        orchestrator.on_status(place(lead), "no_answer")
    return lead


def test_reply_after_no_answer_goes_to_needs_you(client, voice_on):
    lead = _no_answer_three_times(client)
    messaging.dispatch_due()
    phone = q("SELECT phone_e164 FROM lead WHERE id = %s", lead)[0]["phone_e164"]
    r = meta_post(client, inbound_payload(phone, "Sorry, call me after 5 pm"))
    assert r.json()["inbound"] == ["needs_you"]
    assert q("SELECT status FROM lead WHERE id = %s", lead)[0]["status"] == "needs_you"
    login_as(client, "kavya")
    items = client.get("/v1/queue?tab=needs_you").json()["items"]
    assert items[0]["tags"] == ["whatsapp_reply"]
    msgs = client.get(f"/v1/leads/{lead}/assistant").json()["messages"]
    assert [m["direction"] for m in msgs] == ["outbound", "inbound"]


def test_no_reply_for_48h_becomes_unreachable(client, voice_on):
    lead = _no_answer_three_times(client)
    login_as(client, "kavya")
    item = client.get("/v1/queue?tab=no_answer").json()["items"][0]
    assert item["calls"] == 3 and item["status"] == "whatsapp_sent"
    with tx() as conn:
        conn.execute("UPDATE lead SET whatsapp_sent_at = now() - interval '49 hours'")
        assert messaging.expire_unanswered(conn) == 1
    assert q("SELECT status FROM lead WHERE id = %s", lead)[0]["status"] == "unreachable"


def test_stop_suppresses_everything(client, voice_on):
    lead = submit(client, contact_pref="scheduled", scheduled_at=(datetime.now(IST) + timedelta(days=1)).replace(
        hour=18, minute=0, second=0, microsecond=0).isoformat())
    phone = q("SELECT phone_e164 FROM lead WHERE id = %s", lead)[0]["phone_e164"]
    assert q("SELECT template_id FROM message")[0]["template_id"] == "call_reminder_v1"
    r = meta_post(client, inbound_payload(phone, "STOP"))
    assert r.json()["inbound"] == ["stopped"]
    assert q("SELECT reason FROM suppression")[0]["reason"] == "whatsapp_stop"
    assert q("SELECT status FROM call_job")[0]["status"] == "cancelled"
    statuses = {m["template_id"]: m["status"] for m in q("SELECT template_id, status FROM message WHERE direction = 'outbound'")}
    assert statuses == {"call_reminder_v1": "cancelled", "opt_out_confirm_v1": "queued"}
    assert messaging.dispatch_due() == ["sent"] and voice_on.sent[0]["template"] == "opt_out_confirm_v1"


def test_scheduled_call_gets_reminder_ten_minutes_before(client, voice_on):
    at = (datetime.now(IST) + timedelta(days=1)).replace(hour=18, minute=30, second=0, microsecond=0)
    submit(client, contact_pref="scheduled", scheduled_at=at.isoformat())
    m = q("SELECT due_at, body FROM message WHERE template_id = 'call_reminder_v1'")[0]
    assert m["due_at"] == at - timedelta(minutes=10) and "6:30 pm" in m["body"]


def test_out_of_hours_enquiry_gets_written_acknowledgement(client, voice_on):
    night = datetime.now(IST).replace(hour=23, minute=30)
    sub = enquiries.Submission(client_token=uuid.uuid4(), name="Asha Verma", mobile="9876500000", treatment="braces",
                               treatment_other=None, clinic_id="riverside", language="hi", contact_pref="now",
                               scheduled_at=None, consent=True, disclosure_version="assistant-hi-v1")
    with tx() as conn:
        _, body = enquiries.submit(conn, sub, "1.2.3.4", "t", now=night)
    assert body["contact"]["when"] == "next_opening"
    m = q("SELECT body FROM message WHERE template_id = 'enquiry_ack_v1'")[0]
    assert "कल सुबह 9 बजे के बाद" in m["body"]
    assert q("SELECT due_at FROM call_job")[0]["due_at"].astimezone(IST).hour == 9


def test_review_change_and_cancel_send_updates(client, voice_on):
    lead = book_by_assistant(client)
    login_as(client, "kavya")
    b = client.get("/v1/queue?tab=booked").json()["items"][0]["booking_id"]
    slot = client.get("/v1/slots?clinic=riverside").json()["slots"][-1]["id"]
    client.post(f"/v1/bookings/{b}/review", json={"action": "change", "slot_id": slot}, headers=CSRF)
    client.post(f"/v1/bookings/{b}/review", json={"action": "cancel", "reason": "Duplicate booking"}, headers=CSRF)
    bodies = [m["body"] for m in q("SELECT body FROM message WHERE template_id = 'booking_update_v1' ORDER BY created_at")]
    assert "the time has changed" in bodies[0] and "cancelled" in bodies[1]
    assert q("SELECT status FROM message WHERE template_id = 'booking_confirm_v1'")[0]["status"] == "cancelled"
    assert lead


# ---------------------------------------------------------------- language switch (P4-01)
@pytest.mark.parametrize("text,current,expected", [
    ("Hindi mein baat kar sakte hain?", "en", ("hi", True)),
    ("Can we speak in English please?", "hi", ("en", True)),
    ("haan ji, kal shaam theek hai", "en", ("hi", False)),
    ("हाँ जी", "en", ("hi", False)),
    ("Yes, tomorrow evening would be good for me", "hi", ("en", False)),
    ("yes", "hi", (None, False)),                     # one word is not a signal
    ("Actually kal shaam works for me", "en", (None, False)),   # code-mixed: stay
])
def test_language_detection(text, current, expected):
    assert detect(text, current) == expected


def test_pain_is_not_lost_in_a_language_switch_turn():
    from happysmile.voice.agent import Agent, Session
    from happysmile.voice.tools import MemoryBackend, ToolRegistry
    s = Session(name="A", treatment="braces", clinic_id="riverside", clinic_name="Riverside", lang="hi")
    agent = Agent(s, ToolRegistry(MemoryBackend(DAY)), now=lambda: DAY)
    agent.start()
    turn = agent.handle("Please speak in English, my tooth hurts badly")
    assert s.handover["reason"] == "pain_swelling" and s.lang == "en" and "passing this" in turn.say


# ---------------------------------------------------------------- kill switch, alerts
def test_kill_switch_stop_assistant_moves_queued_leads_to_staff(client, voice_on):
    lead = submit(client)
    login_as(client, "kavya")
    assert client.post("/v1/admin/kill-switch", json={"action": "stop_assistant", "reason": "drill"}, headers=CSRF).status_code == 403
    login_as(client, "ops")
    r = client.post("/v1/admin/kill-switch", json={"action": "stop_assistant", "clinic_id": "riverside", "reason": "incident"}, headers=CSRF)
    assert r.status_code == 200
    assert q("SELECT assistant_share FROM experiment_config WHERE clinic_id = 'riverside'")[0]["assistant_share"] == 0
    assert q("SELECT reason_tags FROM handover WHERE lead_id = %s", lead)[0]["reason_tags"] == ["system_fallback"]
    assert q("SELECT arm FROM lead WHERE id = %s", lead)[0]["arm"] == "assistant"   # intention-to-treat
    alerts = client.get("/v1/admin/ops").json()["alerts"]
    assert any(a["key"] == "killswitch_stop_assistant" for a in alerts)


def test_pause_booking_makes_assistant_hand_over(client, voice_on):
    with tx() as conn:
        ops.kill_switch(conn, "pause_booking", "riverside", None, reason="test")
    lead = submit(client)
    converse(place(lead), ["yes", "yes", "no", "yes", "tomorrow evening"])
    assert q("SELECT count(*) AS n FROM booking")[0]["n"] == 0
    h = q("SELECT reason_tags FROM handover WHERE lead_id = %s", lead)[0]
    assert h["reason_tags"] == ["booking_paused"]
    assert "tomorrow" in q("SELECT follow_up_note FROM lead WHERE id = %s", lead)[0]["follow_up_note"]


def test_missed_urgent_handover_alerts_and_auto_stops_assistant(client, voice_on):
    lead = submit(client)
    converse(place(lead), ["yes", "yes", "yes, it hurts"])
    with tx() as conn:
        conn.execute("UPDATE handover SET sla_due_at = now() - interval '12 minutes'")
        from happysmile import handovers
        handovers.sweep(conn)
    res = ops.evaluate_alerts()
    assert "urgent_overdue" in res["opened"] and "stop_assistant:riverside" in res["actions"]
    assert q("SELECT assistant_share FROM experiment_config WHERE clinic_id = 'riverside'")[0]["assistant_share"] == 0
    login_as(client, "kavya")
    client.post(f"/v1/leads/{lead}/claim", headers=CSRF)
    ops.evaluate_alerts()
    open_keys = [r["key"] for r in q("SELECT key FROM alert WHERE resolved_at IS NULL")]
    assert "urgent_overdue" not in open_keys and "killswitch_stop_assistant" in open_keys  # restart needs a human


def test_ops_metrics(client, voice_on):
    book_by_assistant(client)
    messaging.dispatch_due()
    login_as(client, "ops")
    m = client.get("/v1/admin/ops").json()["metrics"]
    assert m["first_dial_seconds"]["count"] in (0, 1) and m["whatsapp"]["sent"] == 1
    assert m["clinics"][0]["clinic_id"] == "hillcrest" and "breakers" in m


# ---------------------------------------------------------------- go-live gates
def staging(monkeypatch, **over):
    real = config.get_settings()
    fake = dataclasses.replace(real, env="staging", **over)
    monkeypatch.setattr(ops, "get_settings", lambda: fake)
    return fake


def test_go_live_gates_block_share_changes_in_staging(client, voice_on, monkeypatch):
    staging(monkeypatch)
    with tx() as conn:
        conn.execute("UPDATE experiment_config SET assistant_share = 0")
    login_as(client, "admin")
    r = client.put("/v1/admin/experiment/riverside", json={"assistant_share": 0.2}, headers=CSRF)
    assert r.status_code == 409 and "Gate G2" in r.json()["detail"]
    for item in ops.ATTESTATIONS:
        assert client.post("/v1/admin/go-live/attest", json={"item": item, "note": "ok"}, headers=CSRF).status_code == 200
    gl = client.get("/v1/admin/go-live").json()
    assert all(c["ok"] for c in gl["g2"] if c.get("attestation")) and not gl["g2_passed"]   # sims still configured

    staging(monkeypatch, telephony_provider="vendor", whatsapp_provider="meta", telephony_webhook_secret="s",
            whatsapp_app_secret="s", alert_webhook_url="https://alerts.invalid/hook")
    with tx() as conn:
        ops.kill_switch(conn, "drill", None, None, reason="drill")
    assert client.put("/v1/admin/experiment/riverside", json={"assistant_share": 0.2}, headers=CSRF).status_code == 200
    r = client.put("/v1/admin/experiment/riverside", json={"assistant_share": 0.5}, headers=CSRF)
    assert r.status_code == 409 and "Gate G3" in r.json()["detail"]               # needs 3 live days first
    assert q("SELECT live_since FROM experiment_config WHERE clinic_id = 'riverside'")[0]["live_since"] is not None
