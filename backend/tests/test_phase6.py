"""Phase 6: rollout waves + permanent control, calendar adapter, live transfer, reminders/no-shows, LLM endpoint, languages."""

import json
import os
import secrets
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import httpx
import pytest

from happysmile import calendar_sync, config, experiment, handovers, rollout, telephony
from happysmile.config import IST
from happysmile.db import tx

from .conftest import CSRF, enquiry, login_as
from .test_phase4 import book_by_assistant, staging, voice_on  # noqa: F401  (fixture)
from .test_voice_flow import converse, place, q, submit


def record_g4(decision: str):
    with tx() as conn:
        admin = conn.execute("SELECT id FROM staff WHERE username = 'admin'").fetchone()["id"]
        conn.execute("INSERT INTO pilot_decision (decision, recommended, notes, decided_by, readout) "
                     "VALUES (%s, %s, 'test decision', %s, '{}')", (decision, decision, admin))


# ---------------------------------------------------------------- permanent control + rollout
def test_permanent_control_share_is_always_kept(client):
    os.environ["VOICE_AGENT_ENABLED"] = "true"
    config.get_settings.cache_clear()
    with tx() as conn:
        with pytest.raises(PermissionError, match="90%"):
            experiment.set_share(conn, "riverside", Decimal("1"), None)
        experiment.set_share(conn, "riverside", Decimal("0.9"), None)   # dev: allowed up to the cap
        assert conn.execute("SELECT steady_since FROM experiment_config WHERE clinic_id = 'riverside'").fetchone()["steady_since"]


def test_above_50_needs_g4_scale_in_staging(client, voice_on, monkeypatch):  # noqa: F811
    fake = staging(monkeypatch, telephony_provider="vendor", whatsapp_provider="meta", telephony_webhook_secret="s",
                   whatsapp_app_secret="s", alert_webhook_url="https://alerts.invalid")
    monkeypatch.setattr(rollout, "get_settings", lambda: fake)
    with tx() as conn:
        with pytest.raises(PermissionError, match="G4 decision"):
            rollout.check_share(conn, "riverside", Decimal("0.9"))
    record_g4("scale")
    with tx() as conn:
        rollout.check_share(conn, "riverside", Decimal("0.9"))  # G4 ok (G3 is checked separately by ops)


def test_wave_activation_checks_and_activation(client, monkeypatch):
    login_as(client, "admin")
    view = client.get("/v1/admin/rollout").json()
    assert view["max_share"] == pytest.approx(0.9) and set(view["waves"]) == {"2", "3", "4"}
    w2 = {c["id"]: c for c in view["waves"]["2"]}
    assert w2["g4_scale"]["ok"] is False and w2["previous_wave_steady"]["ok"] is False

    fake = __import__("dataclasses").replace(config.get_settings(), env="staging")
    monkeypatch.setattr(rollout, "get_settings", lambda: fake)
    r = client.post("/v1/admin/rollout/waves/2/activate", headers=CSRF)
    assert r.status_code == 409 and "G4" in r.json()["detail"]

    # Make wave 2 ready: G4 scale, wave 1 steady for 7 days, onboarding done for maple/palm/banyan.
    record_g4("scale")
    with tx() as conn:
        conn.execute("UPDATE experiment_config SET steady_since = now() - interval '8 days'")
        staff_id = conn.execute("SELECT id FROM staff WHERE username = 'kavya'").fetchone()["id"]
        for cid in ("maple", "palm", "banyan"):
            conn.execute("INSERT INTO dentist (clinic_id, name) VALUES (%s, 'Dr. Test') ON CONFLICT DO NOTHING", (cid,))
            conn.execute("UPDATE clinic SET address = 'Test address' WHERE id = %s", (cid,))
            conn.execute("INSERT INTO staff_clinic (staff_id, clinic_id) VALUES (%s, %s) ON CONFLICT DO NOTHING", (staff_id, cid))
            conn.execute("INSERT INTO slot_refresh (clinic_id, refreshed_at) VALUES (%s, now()) ON CONFLICT (clinic_id) "
                         "DO UPDATE SET refreshed_at = now()", (cid,))
    for cid in ("maple", "palm", "banyan"):
        for item in rollout.ONBOARDING:
            assert client.post("/v1/admin/rollout/onboarding", json={"clinic_id": cid, "item": item, "note": "done"},
                               headers=CSRF).status_code == 200
    r = client.post("/v1/admin/rollout/waves/2/activate", headers=CSRF)
    assert r.status_code == 200 and sorted(r.json()["activated"]) == ["banyan", "maple", "palm"]
    # New clinics are in the programme at 0%: enquiries are randomised (all to standard callback for now).
    r = client.post("/v1/enquiries", json=enquiry(clinic_id="maple"))
    assert r.status_code == 201
    assert q("SELECT arm FROM lead")[0]["arm"] == "control"
    with tx() as conn:
        conn.execute("DELETE FROM staff_clinic WHERE clinic_id IN ('maple', 'palm', 'banyan')")
        conn.execute("DELETE FROM dentist WHERE name = 'Dr. Test'")


# ---------------------------------------------------------------- calendar adapter
class FakeCalendar(httpx.MockTransport):
    def __init__(self):
        self.booked, self.cancelled, self.conflict = [], [], False
        self.slots = [{"id": "ext-1", "dentist_id": "D9", "dentist_name": "Dr. External", "duration_min": 30,
                       "start": (datetime.now(IST) + timedelta(days=1)).replace(hour=18, minute=0, second=0, microsecond=0).isoformat()},
                      {"id": "ext-2", "dentist_id": "D9", "dentist_name": "Dr. External", "duration_min": 30,
                       "start": (datetime.now(IST) + timedelta(days=1)).replace(hour=19, minute=0, second=0, microsecond=0).isoformat()}]
        super().__init__(self.handle)

    def handle(self, req: httpx.Request):
        if req.method == "GET":
            return httpx.Response(200, json={"slots": self.slots})
        if req.method == "POST":
            if self.conflict:
                return httpx.Response(409, json={"error": "taken"})
            body = json.loads(req.content)
            self.booked.append(body)
            return httpx.Response(201, json={"id": f"bk-{len(self.booked)}"})
        self.cancelled.append(req.url.path)
        return httpx.Response(204)


@pytest.fixture
def ext_calendar():
    os.environ.update({"CALENDAR_API_URL": "https://calendar.invalid/api", "CALENDAR_API_TOKEN": "t"})
    config.get_settings.cache_clear()
    fake = FakeCalendar()
    calendar_sync.set_adapter(calendar_sync.HttpCalendar(transport=fake))
    with tx() as conn:
        conn.execute("UPDATE clinic SET calendar_adapter = 'http' WHERE id = 'riverside'")
        conn.execute("UPDATE slot SET status = 'blocked' WHERE clinic_id = 'riverside' AND source = 'local'")  # only external slots
        res = calendar_sync.sync(conn, "riverside")
    assert res == {"remote": 2, "created": 2, "blocked": 0}
    yield fake
    with tx() as conn:
        conn.execute("UPDATE slot SET status = 'open' WHERE clinic_id = 'riverside' AND source = 'local' AND status = 'blocked'")


def test_calendar_sync_and_staff_booking(client, ext_calendar):
    lead = client.post("/v1/enquiries", json=enquiry()).json()["ref"]
    lead_id = q("SELECT id FROM lead WHERE public_ref = %s", lead)[0]["id"]
    login_as(client, "kavya")
    slots = client.get("/v1/slots?clinic=riverside").json()["slots"]
    assert [s["dentist"] for s in slots] == ["Dr. External", "Dr. External"]
    r = client.post(f"/v1/leads/{lead_id}/bookings", json={"slot_id": slots[0]["id"]}, headers=CSRF)
    assert r.status_code == 200
    assert ext_calendar.booked[0]["slot_id"] == "ext-1" and ext_calendar.booked[0]["patient"]["phone"].startswith("+91")
    assert q("SELECT external_ref FROM booking")[0]["external_ref"] == "bk-1"


def test_calendar_conflict_blocks_slot_and_refuses(client, ext_calendar):
    ext_calendar.conflict = True
    lead = client.post("/v1/enquiries", json=enquiry()).json()["ref"]
    lead_id = q("SELECT id FROM lead WHERE public_ref = %s", lead)[0]["id"]
    login_as(client, "kavya")
    slot = client.get("/v1/slots?clinic=riverside").json()["slots"][0]["id"]
    r = client.post(f"/v1/leads/{lead_id}/bookings", json={"slot_id": slot}, headers=CSRF)
    assert r.status_code == 409 and "calendar" in r.json()["detail"]
    assert q("SELECT status FROM slot WHERE id = %s", slot)[0]["status"] == "blocked"
    assert q("SELECT count(*) AS n FROM booking")[0]["n"] == 0
    assert q("SELECT status FROM lead WHERE id = %s", lead_id)[0]["status"] == "awaiting_call"


def test_calendar_slot_taken_elsewhere_is_blocked_on_sync(client, ext_calendar):
    ext_calendar.slots = ext_calendar.slots[1:]
    with tx() as conn:
        assert calendar_sync.sync(conn, "riverside")["blocked"] == 1


# ---------------------------------------------------------------- live transfer
@pytest.fixture
def staffed(monkeypatch):
    monkeypatch.setattr(handovers, "staffed_promise", lambda now, urgency: (now + timedelta(minutes=15), "minutes", 15))


def test_live_transfer_when_staff_available(client, voice_on, staffed):  # noqa: F811
    login_as(client, "kavya")
    assert client.post("/v1/me/transfer", json={"available": True}, headers=CSRF).status_code == 422  # phone needed
    assert client.post("/v1/me/transfer", json={"available": True, "phone": "98765 11111"}, headers=CSRF).status_code == 200
    assert client.get("/v1/me/transfer").json()["available"] is True
    lead = submit(client)
    said = converse(place(lead), ["Can I talk to a real person?"])
    assert "connecting you to Kavya" in said[-1]
    t = telephony.provider().transfers
    assert len(t) == 1 and t[0]["to"] == "+919876511111"
    h = q("SELECT reason_tags, claimed_by FROM handover")[0]
    assert h["reason_tags"] == ["asked_person", "transferred"] and h["claimed_by"] is not None
    assert q("SELECT outcome FROM conversation")[0]["outcome"] == "transferred"


def test_no_transfer_when_nobody_available_or_it_fails(client, voice_on, staffed):  # noqa: F811
    lead = submit(client)
    said = converse(place(lead), ["Can I talk to a real person?"])
    assert "within 15 minutes" in said[-1]                       # normal handover promise
    login_as(client, "kavya")
    client.post("/v1/me/transfer", json={"available": True, "phone": "9876511111"}, headers=CSRF)
    telephony.provider().fail_transfer = True
    lead2 = submit(client, mobile="9123400000")
    said = converse(place(lead2), ["talk to a person please"])
    assert "within 15 minutes" in said[-1]
    assert q("SELECT claimed_by FROM handover WHERE lead_id = %s", lead2)[0]["claimed_by"] is None


# ---------------------------------------------------------------- reminders, no-shows
def test_reminder_and_no_show_recovery(client, voice_on):  # noqa: F811
    book_by_assistant(client)
    b = q("SELECT id, start_at FROM booking")[0]
    rem = q("SELECT due_at, status FROM message WHERE template_id = 'appointment_reminder_v1'")
    assert len(rem) == 1 and rem[0]["status"] == "queued"
    assert rem[0]["due_at"] in (b["start_at"] - timedelta(hours=24), b["start_at"] - timedelta(hours=3))
    with tx() as conn:
        conn.execute("UPDATE booking SET start_at = now() - interval '2 hours'")
    login_as(client, "kavya")
    assert client.post(f"/v1/bookings/{b['id']}/attendance", json={"attended": False}, headers=CSRF).status_code == 200
    assert q("SELECT count(*) AS n FROM message WHERE template_id = 'no_show_v1'")[0]["n"] == 1
    assert q("SELECT reason_tags FROM handover")[0]["reason_tags"] == ["no_show"]


def test_cancel_at_review_cancels_reminder(client, voice_on):  # noqa: F811
    book_by_assistant(client)
    login_as(client, "kavya")
    b = client.get("/v1/queue?tab=booked").json()["items"][0]["booking_id"]
    client.post(f"/v1/bookings/{b}/review", json={"action": "cancel", "reason": "Duplicate booking"}, headers=CSRF)
    assert q("SELECT status FROM message WHERE template_id = 'appointment_reminder_v1'")[0]["status"] == "cancelled"


def test_control_arm_no_show_gets_no_automated_message(client):
    r = client.post("/v1/enquiries", json=enquiry())
    lead = q("SELECT id FROM lead WHERE public_ref = %s", r.json()["ref"])[0]["id"]
    login_as(client, "kavya")
    slot = client.get("/v1/slots?clinic=riverside").json()["slots"][0]["id"]
    client.post(f"/v1/leads/{lead}/bookings", json={"slot_id": slot}, headers=CSRF)
    b = q("SELECT id FROM booking")[0]["id"]
    with tx() as conn:
        conn.execute("UPDATE booking SET start_at = now() - interval '2 hours'")
    client.post(f"/v1/bookings/{b}/attendance", json={"attended": False}, headers=CSRF)
    assert q("SELECT count(*) AS n FROM message")[0]["n"] == 0


# ---------------------------------------------------------------- LLM endpoint, languages
def test_llm_endpoint_can_be_switched():
    os.environ.update({"LLM_BASE_URL": "https://llm.in.example/v1", "LLM_API_KEY": "k", "LLM_PROVIDER": "india-hosted"})
    config.get_settings.cache_clear()
    s = config.get_settings()
    assert s.groq_base_url == "https://llm.in.example/v1" and s.groq_api_key == "k" and s.llm_provider == "india-hosted"


def test_language_readiness():
    from happysmile.languages import coverage
    assert coverage("en")["coverage"] == 1.0 and coverage("hi")["coverage"] == 1.0
    mr = coverage("mr")
    assert mr["coverage"] == 0 and mr["missing"]["assistant_lines"] and mr["also_needed"]
