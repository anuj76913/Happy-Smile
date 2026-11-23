"""Browser demo line (development only): form -> worker 'dials' the browser -> patient answers in the tab."""

import uuid

import pytest

from happysmile import config, demo_mode, orchestrator, telephony
from happysmile.db import tx

from .conftest import enquiry, login_as
from .test_voice_flow import place, q


@pytest.fixture
def browser_line(monkeypatch):
    monkeypatch.setenv("VOICE_AGENT_ENABLED", "true")
    monkeypatch.setenv("TELEPHONY_PROVIDER", "browser")
    config.get_settings.cache_clear()
    telephony.set_provider(None)
    with tx() as conn:
        conn.execute("UPDATE experiment_config SET assistant_share = 1 WHERE clinic_id = 'riverside'")
    yield
    monkeypatch.undo()
    config.get_settings.cache_clear()
    telephony.set_provider(None)


def submit(client, **over):
    body = enquiry(disclosure_version="assistant-en-v1", **over)
    r = client.post("/v1/enquiries", json=body)
    assert r.status_code == 201, r.text
    lead = q("SELECT id FROM lead WHERE public_ref = %s", r.json()["ref"])[0]["id"]
    return body["client_token"], lead


def test_demo_line_is_off_unless_the_browser_provider_is_set(client):
    assert client.get("/v1/enquiry-config").json()["browser_calls"] is False
    assert client.get(f"/v1/demo-call/{uuid.uuid4()}").status_code == 404


def test_demo_form_lists_only_clinics_the_assistant_calls(client, browser_line):
    assert [c["id"] for c in client.get("/v1/enquiry-config").json()["clinics"]] == ["riverside"]
    with tx() as conn:
        conn.execute("UPDATE experiment_config SET assistant_share = 0")
    assert len(client.get("/v1/enquiry-config").json()["clinics"]) == 12  # demo mode off: nothing hidden


def test_form_rings_the_browser_and_the_call_books(client, browser_line):
    assert client.get("/v1/enquiry-config").json()["browser_calls"] is True
    tok, lead = submit(client)
    base = f"/v1/demo-call/{tok}"
    assert client.get(base).json()["state"] == "queued"
    assert client.post(base + "/answer").status_code == 409  # nothing is ringing yet

    attempt = place(lead)
    assert q("SELECT provider, provider_call_id FROM call_attempt WHERE id = %s", attempt)[0]["provider"] == "browser"
    assert client.get(base).json() == {"state": "ringing", "lang": "en"}

    first = client.post(base + "/answer").json()
    assert "virtual assistant" in first["say"] and first["lang"] == "en"
    assert client.get(base).json()["state"] == "in_call"
    assert client.post(base + "/answer").status_code == 409  # already answered

    r = client.post(base + "/turn", json={"silence": True}).json()  # silence is a turn, not an error
    assert r["say"] and r["end"] is False
    for said in ["yes", "yes", "no", "yes", "tomorrow evening", "the first one", "no"]:
        r = client.post(base + "/turn", json={"text": said}).json()
        if r["end"]:
            break
    assert r["end"] and r["outcome"] == "booked" and r["result"] == {"state": "ended", "outcome": "booked"}
    assert q("SELECT status FROM lead WHERE id = %s", lead)[0]["status"] == "booked"
    assert q("SELECT created_by FROM booking WHERE lead_id = %s", lead)[0]["created_by"] == "assistant"
    assert client.post(base + "/turn", json={"text": "hello?"}).status_code == 409


def test_decline_is_a_missed_call_and_is_retried(client, browser_line):
    tok, lead = submit(client)
    place(lead)
    s = client.post(f"/v1/demo-call/{tok}/decline").json()
    assert s["state"] == "queued" and s["retry"] is True
    assert q("SELECT outcome FROM call_attempt WHERE lead_id = %s", lead)[0]["outcome"] == "no_answer"


def test_hangup_mid_call_closes_the_attempt(client, browser_line):
    tok, lead = submit(client)
    place(lead)
    client.post(f"/v1/demo-call/{tok}/answer")
    r = client.post(f"/v1/demo-call/{tok}/turn", json={"hangup": True}).json()
    assert r["end"] is True and r["say"] is None
    assert q("SELECT state FROM call_attempt WHERE lead_id = %s", lead)[0]["state"] == "completed"
    assert r["outcome"] == q("SELECT outcome FROM conversation")[0]["outcome"]
    # Hanging up during the greeting is treated like a dropped phone call: the real policy decides what's next.
    assert r["result"]["state"] in ("queued", "ended", "staff")


def test_worker_sweeps_unanswered_and_abandoned_browser_calls(client, browser_line):
    tok1, lead1 = submit(client)
    a1 = place(lead1)
    tok2, lead2 = submit(client, mobile="+91 91234 56789")
    a2 = place(lead2)
    client.post(f"/v1/demo-call/{tok2}/answer")
    with tx() as conn:  # tab never answered / tab closed mid-call
        conn.execute("UPDATE call_attempt SET started_at = now() - interval '5 minutes' WHERE id = %s", (a1,))
        conn.execute("UPDATE conversation SET updated_at = now() - interval '10 minutes' WHERE call_attempt_id = %s", (a2,))
    assert orchestrator.sweep_browser_calls() == 2
    states = {str(r["id"]): (r["state"], r["outcome"]) for r in q("SELECT id, state, outcome FROM call_attempt")}
    assert states[a1] == ("completed", "no_answer") and states[a2][0] == "completed"
    assert client.get(f"/v1/demo-call/{tok1}").json()["state"] == "queued"  # retried later, like a missed phone call


def test_unknown_and_merged_submissions_have_no_demo_call(client, browser_line, monkeypatch):
    assert client.get(f"/v1/demo-call/{uuid.uuid4()}").status_code == 404
    submit(client)
    dup = enquiry(disclosure_version="assistant-en-v1")
    assert client.post("/v1/enquiries", json=dup).json().get("deduplicated") is True
    assert client.get(f"/v1/demo-call/{dup['client_token']}").status_code == 404
    # The demo can turn duplicate-merging off so the same number can try again.
    monkeypatch.setenv("DEDUPE_HOURS", "0")
    config.get_settings.cache_clear()
    again = enquiry(disclosure_version="assistant-en-v1")
    assert client.post("/v1/enquiries", json=again).status_code == 201
    assert client.get(f"/v1/demo-call/{again['client_token']}").json()["state"] == "queued"


def test_demo_reuses_your_number_even_if_it_was_in_control(client, browser_line, monkeypatch):
    with tx() as conn:  # your number was first seen while the share was 0%
        conn.execute("UPDATE experiment_config SET assistant_share = 0 WHERE clinic_id = 'riverside'")
    first = enquiry()
    assert client.post("/v1/enquiries", json=first).status_code == 201
    with tx() as conn:
        conn.execute("UPDATE experiment_config SET assistant_share = 1 WHERE clinic_id = 'riverside'")
    monkeypatch.setenv("DEDUPE_HOURS", "0")
    config.get_settings.cache_clear()
    tok, lead = submit(client)
    assert q("SELECT arm FROM lead WHERE id = %s", lead)[0]["arm"] == "assistant"
    assert client.get(f"/v1/demo-call/{tok}").json()["state"] == "queued"


def test_demo_mode_switch_and_production_refusal(monkeypatch):
    names = demo_mode.set_demo(True)
    assert len(names) == 3
    assert {float(r["assistant_share"]) for r in q("SELECT assistant_share FROM experiment_config")} == {1.0}
    demo_mode.set_demo(False)
    assert {float(r["assistant_share"]) for r in q("SELECT assistant_share FROM experiment_config")} == {0.0}

    monkeypatch.setenv("APP_ENV", "staging")
    monkeypatch.setenv("VOICE_AGENT_ENABLED", "true")
    monkeypatch.setenv("TELEPHONY_PROVIDER", "browser")
    config.get_settings.cache_clear()
    with pytest.raises(RuntimeError, match="browser demo"):
        config.get_settings()
    monkeypatch.undo()
    config.get_settings.cache_clear()


def test_public_demo_site_needs_real_secrets(monkeypatch):
    monkeypatch.setenv("APP_ENV", "demo")
    monkeypatch.setenv("TELEPHONY_PROVIDER", "browser")
    monkeypatch.delenv("IP_HASH_SALT", raising=False)  # falls back to the dev-only salt
    config.get_settings.cache_clear()
    with pytest.raises(RuntimeError) as e:
        config.get_settings()
    assert "IP_HASH_SALT" in str(e.value) and "DEMO_STAFF_PASSWORD" in str(e.value) and "local database" in str(e.value)
    monkeypatch.undo()
    config.get_settings.cache_clear()


def test_demo_site_allows_browser_calls_and_secure_cookies(monkeypatch):
    for k, v in {"APP_ENV": "demo", "TELEPHONY_PROVIDER": "browser", "IP_HASH_SALT": "x" * 32,
                 "DEMO_STAFF_PASSWORD": "a-long-demo-password", "DATABASE_URL": "postgresql://u@db.internal:5432/app"}.items():
        monkeypatch.setenv(k, v)
    config.get_settings.cache_clear()
    s = config.get_settings()
    assert s.browser_calls and s.cookie_secure and not s.is_production_like
    monkeypatch.undo()
    config.get_settings.cache_clear()


def test_demo_staff_password_replaces_the_published_ones(client, monkeypatch):
    from happysmile.seed import seed
    monkeypatch.setenv("DEMO_STAFF_PASSWORD", "a-long-demo-password")
    config.get_settings.cache_clear()
    seed(slot_days=1)
    assert client.post("/v1/auth/login", json={"username": "kavya", "password": "riverside-demo"}).status_code == 401
    assert client.post("/v1/auth/login", json={"username": "kavya", "password": "a-long-demo-password"}).status_code == 200
    monkeypatch.undo()
    config.get_settings.cache_clear()
    _restore_dev_passwords()


def _restore_dev_passwords():
    from happysmile.security import hash_password
    from happysmile.seed import STAFF
    with tx() as conn:
        for username, _, _, _, pw in STAFF:
            conn.execute("UPDATE staff SET password_hash = %s WHERE username = %s", (hash_password(pw), username))


def test_open_console_needs_no_login_but_keeps_ops_locked(client, monkeypatch):
    assert client.get("/v1/auth/me").status_code == 401  # off by default
    monkeypatch.setenv("OPEN_CONSOLE", "true")
    config.get_settings.cache_clear()
    me = client.get("/v1/auth/me").json()
    assert me["username"] == "guest" and me["role"] == "front_desk"
    assert {c["id"] for c in me["clinics"]} == {"riverside", "hillcrest", "lotus"}
    assert client.get("/v1/queue?tab=needs_you").status_code == 200
    assert client.get("/v1/admin/ops").status_code == 403  # kill switch, gates: managers/admins only
    assert client.post("/v1/admin/kill-switch", json={"action": "stop_assistant", "reason": "x"},
                       headers={"X-Requested-With": "hs-console"}).status_code == 403
    assert client.post("/v1/auth/login", json={"username": "guest", "password": ""}).status_code in (401, 422)
    login_as(client, "ops")  # a real sign-in still wins over the guest
    assert client.get("/v1/auth/me").json()["username"] == "ops"
    monkeypatch.undo()
    config.get_settings.cache_clear()


def test_open_console_is_refused_in_production(monkeypatch):
    monkeypatch.setenv("APP_ENV", "staging")
    monkeypatch.setenv("OPEN_CONSOLE", "true")
    config.get_settings.cache_clear()
    with pytest.raises(RuntimeError, match="OPEN_CONSOLE"):
        config.get_settings()
    monkeypatch.undo()
    config.get_settings.cache_clear()
