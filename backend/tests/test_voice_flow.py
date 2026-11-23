"""End-to-end voice flows through the database: intake -> job -> simulated call -> agent -> outcome."""

import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

import pytest

from happysmile import config, orchestrator, telephony
from happysmile.config import IST
from happysmile.db import tx

from .conftest import CSRF, enquiry, login_as

DAY = datetime(2026, 11, 24, 14, 20, tzinfo=IST)  # inside the calling window


@pytest.fixture
def voice_on():
    os.environ["VOICE_AGENT_ENABLED"] = "true"
    config.get_settings.cache_clear()
    with tx() as conn:
        conn.execute("UPDATE experiment_config SET assistant_share = 1 WHERE clinic_id = 'riverside'")
    telephony.set_provider(telephony.SimProvider())
    yield


def q(sql, *a):
    with tx() as conn:
        return conn.execute(sql, a).fetchall()


def submit(client, **over) -> str:
    r = client.post("/v1/enquiries", json=enquiry(disclosure_version="assistant-en-v1", **over))
    assert r.status_code == 201, r.text
    return q("SELECT id FROM lead WHERE public_ref = %s", r.json()["ref"])[0]["id"]


def place(lead_id) -> str:
    with tx() as conn:
        conn.execute("UPDATE call_job SET due_at = now() WHERE lead_id = %s AND status = 'pending'", (lead_id,))
    jobs = orchestrator.claim_due()
    assert jobs, "no due job"
    res = orchestrator.process_job(jobs[0], now=DAY)
    assert res.startswith("placed:"), res
    return res.split(":", 1)[1]


def converse(attempt, turns):
    first = orchestrator.on_status(attempt, "answered")
    out = [first]
    for t in turns:
        r = orchestrator.on_caller_turn(attempt, t)
        out.append(r["say"])
        if r["end"]:
            break
    return out


def test_disclosure_wording_follows_share(client, voice_on):
    cfg = client.get("/v1/enquiry-config").json()
    riverside = next(c for c in cfg["clinics"] if c["id"] == "riverside")
    assert riverside["disclosure"]["version"] == "assistant-en-v1"
    assert "virtual assistant" in riverside["disclosure"]["disclosure"]
    r = client.post("/v1/enquiries", json=enquiry())  # team wording for an assistant clinic is refused
    assert r.status_code == 409


def test_full_call_books_and_metrics_match(client, voice_on):
    lead = submit(client)
    job = q("SELECT * FROM call_job WHERE lead_id = %s", lead)[0]
    assert job["status"] == "pending" and job["attempt_no"] == 1
    attempt = place(lead)
    said = converse(attempt, ["yes", "yes", "no", "yes", "tomorrow evening", "the first one", "no"])
    assert "virtual assistant" in said[0] and "recorded" in said[0]
    assert any("You're booked for" in s for s in said)
    l = q("SELECT status, first_reached_at FROM lead WHERE id = %s", lead)[0]
    assert l["status"] == "booked" and l["first_reached_at"]
    b = q("SELECT created_by, review_status FROM booking WHERE lead_id = %s", lead)[0]
    assert b == {"created_by": "assistant", "review_status": "pending"}
    conv = q("SELECT outcome, summary, captured FROM conversation")[0]
    assert conv["outcome"] == "booked" and len(conv["summary"]) == 3 and conv["captured"]["treatment"] == "braces or aligners"

    login_as(client, "ops")
    m = client.get("/v1/metrics/today").json()
    assert m["booked_by_assistant"] == 1 and m["reached_within_5"]["assistant"]["reached_within_5"] == 1
    assert client.get("/v1/admin/metrics/consistency").json()["match"] is True
    items = client.get("/v1/queue?tab=booked").json()["items"]
    assert len(items) == 1 and items[0]["review_status"] == "pending"


def test_pain_goes_to_needs_you_and_staff_resolve_it(client, voice_on):
    lead = submit(client)
    attempt = place(lead)
    said = converse(attempt, ["yes", "yes", "yes, my gum is swollen"])
    assert "passing this to our clinic team" in said[-1]
    login_as(client, "kavya")
    items = client.get("/v1/queue?tab=needs_you").json()["items"]
    assert len(items) == 1 and items[0]["urgency"] == "urgent" and items[0]["tags"] == ["pain_swelling"]
    extra = client.get(f"/v1/leads/{lead}/assistant").json()
    assert extra["handover"]["sla_minutes"] == 5 and extra["conversation"]["summary"]
    hid = items[0]["handover_id"]
    assert client.post(f"/v1/handovers/{hid}/feedback", json={"is_correct": True}, headers=CSRF).status_code == 200
    assert client.post(f"/v1/leads/{lead}/claim", headers=CSRF).status_code == 200
    slot = client.get("/v1/slots?clinic=riverside").json()["slots"][0]["id"]
    assert client.post(f"/v1/leads/{lead}/bookings", json={"slot_id": slot}, headers=CSRF).status_code == 200
    assert client.get("/v1/queue?tab=needs_you").json()["items"] == []
    h = q("SELECT resolution, claimed_at FROM handover")[0]
    assert h["resolution"] == "booked_by_staff" and h["claimed_at"]


def test_no_answer_retries_then_whatsapp(client, voice_on):
    lead = submit(client)
    for expected_gap in (5, 120):
        attempt = place(lead)
        orchestrator.on_status(attempt, "no_answer")
        job = q("SELECT due_at, created_at, updated_at FROM call_job WHERE lead_id = %s AND status = 'pending'", lead)[0]
        gap = (job["due_at"] - datetime.now(job["due_at"].tzinfo)).total_seconds() / 60
        assert expected_gap - 1 < gap <= expected_gap + 0.5
    attempt = place(lead)
    orchestrator.on_status(attempt, "no_answer")
    # Phase 4: after three calls, WhatsApp them and wait for a reply (architecture §5)
    assert q("SELECT status FROM lead WHERE id = %s", lead)[0]["status"] == "whatsapp_sent"
    assert q("SELECT template_id FROM message")[0]["template_id"] == "no_answer_v1"
    assert orchestrator.on_status(attempt, "answered") is None  # late webhook ignored (EC-CALL-11)


def test_voice_off_or_breaker_open_falls_back_to_staff(client, voice_on):
    lead = submit(client)
    with tx() as conn:
        conn.execute("INSERT INTO breaker (name, failures, open_until) VALUES ('telephony', 3, now() + interval '2 minutes')")
        conn.execute("UPDATE call_job SET due_at = now()")
    assert orchestrator.process_job(orchestrator.claim_due()[0], now=DAY) == "fallback"
    assert q("SELECT reason_tags FROM handover WHERE lead_id = %s", lead)[0]["reason_tags"] == ["system_fallback"]


def test_provider_failure_falls_back_and_counts_toward_breaker(client, voice_on):
    class Down:
        name = "down"

        def place_call(self, *a):
            raise ConnectionError("provider down")
    telephony.set_provider(Down())
    for n in range(3):
        lead = submit(client, mobile=f"98765432{n:02d}")
        with tx() as conn:
            conn.execute("UPDATE call_job SET due_at = now()")
        assert orchestrator.process_job(orchestrator.claim_due()[0], now=DAY) == "fallback"
    assert orchestrator.breaker_open("telephony")


def test_parallel_workers_never_claim_the_same_job(client, voice_on):
    for n in range(6):
        submit(client, mobile=f"91234567{n:02d}")
    with tx() as conn:
        conn.execute("UPDATE call_job SET due_at = now()")
    with ThreadPoolExecutor(3) as pool:
        batches = list(pool.map(lambda _: orchestrator.claim_due(limit=6), range(3)))
    claimed = [j for b in batches for j in b]
    assert len(claimed) == 6 and len(set(claimed)) == 6


def test_stop_calling_suppresses_number(client, voice_on):
    lead = submit(client)
    attempt = place(lead)
    converse(attempt, ["please don't call me again"])
    assert q("SELECT reason FROM suppression")[0]["reason"] == "stop_calling"
    assert q("SELECT status FROM lead WHERE id = %s", lead)[0]["status"] == "not_interested"


def test_whatsapp_preference_greets_and_goes_to_staff(client, voice_on):
    lead = submit(client, contact_pref="whatsapp")
    assert q("SELECT reason_tags FROM handover WHERE lead_id = %s", lead)[0]["reason_tags"] == ["whatsapp_preferred"]
    assert q("SELECT template_id FROM message WHERE lead_id = %s", lead)[0]["template_id"] == "whatsapp_hello_v1"
    assert q("SELECT count(*) AS n FROM call_job")[0]["n"] == 0


def test_booking_review_approve_change_cancel(client, voice_on):
    leads = []
    for n in range(3):
        lead = submit(client, mobile=f"93333333{n:02d}")
        converse(place(lead), ["yes", "yes", "no", "yes", f"in {n + 2} days evening" if False else "tomorrow evening",
                               "first", "no"])
        leads.append(lead)
    login_as(client, "kavya")
    items = {i["id"]: i for i in client.get("/v1/queue?tab=booked").json()["items"]}
    b0, b1, b2 = (items[str(l)]["booking_id"] for l in leads)
    assert client.post(f"/v1/bookings/{b0}/review", json={"action": "approve"}, headers=CSRF).status_code == 200
    slot = client.get("/v1/slots?clinic=riverside").json()["slots"][-1]["id"]
    assert client.post(f"/v1/bookings/{b1}/review", json={"action": "change", "slot_id": slot}, headers=CSRF).status_code == 200
    assert client.post(f"/v1/bookings/{b2}/review", json={"action": "cancel"}, headers=CSRF).status_code == 422
    assert client.post(f"/v1/bookings/{b2}/review", json={"action": "cancel", "reason": "Wrong dentist"}, headers=CSRF).status_code == 200
    statuses = {r["id"]: (r["review_status"], r["status"]) for r in q("SELECT id, review_status, status FROM booking")}
    assert statuses[__import__("uuid").UUID(b0)] == ("approved", "active")
    assert statuses[__import__("uuid").UUID(b1)] == ("changed", "active")
    assert statuses[__import__("uuid").UUID(b2)] == ("cancelled", "cancelled")
    assert client.get("/v1/queue?tab=needs_you").json()["items"][0]["tags"] == ["booking_cancelled"]  # EC-POST-02


def test_test_call_never_writes_real_records(client):
    login_as(client, "kavya")
    r = client.post("/v1/test-calls", json={"name": "Practice", "treatment": "whitening", "clinic_id": "riverside",
                                           "language": "hi"}, headers=CSRF).json()
    assert "वर्चुअल असिस्टेंट" in r["say"]
    open_before = q("SELECT count(*) AS n FROM slot WHERE status = 'open'")[0]["n"]
    out = None
    for t in ("haan", "haan", "nahi", "haan", "kal shaam", "pehla", "nahi"):
        out = client.post(f"/v1/test-calls/{r['id']}/turn", json={"text": t}, headers=CSRF).json()
    assert out["end"] and out["outcome"] == "booked" and out["booking"] and len(out["summary"]["lines"]) == 3
    assert q("SELECT count(*) AS n FROM booking")[0]["n"] == 0 and q("SELECT count(*) AS n FROM lead")[0]["n"] == 0
    assert q("SELECT count(*) AS n FROM slot WHERE status = 'open'")[0]["n"] == open_before


def test_escalation_sweep(client, voice_on):
    lead = submit(client)
    converse(place(lead), ["can I talk to a person"])
    with tx() as conn:
        conn.execute("UPDATE handover SET sla_due_at = now() - interval '20 minutes'")
        from happysmile import handovers
        res = handovers.sweep(conn)
    assert res == {"overdue": 1, "escalated": 1}
    types = [r["type"] for r in q("SELECT type FROM event WHERE type LIKE 'handover.%%' ORDER BY id")]
    assert types[-2:] == ["handover.overdue", "handover.escalated"]


def test_telephony_webhook_needs_signature(client, voice_on):
    r = client.post("/v1/hooks/telephony/status", content=b'{"event_id":"1","provider_call_id":"x","status":"answered"}')
    assert r.status_code == 401
