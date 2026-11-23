"""Test fixtures: a fresh Postgres database per test session, cleaned between tests.

Set TEST_DATABASE_URL to a server you can create databases on. Default: the local
dev cluster from scripts/localdb.py (or the Postgres service in CI).
"""

from __future__ import annotations

import os
import uuid

import psycopg
import pytest

ADMIN_URL = os.environ.get("TEST_ADMIN_DATABASE_URL", "postgresql://postgres@127.0.0.1:54329/postgres")
TEST_DB = "happysmile_test"
TEST_URL = ADMIN_URL.rsplit("/", 1)[0] + "/" + TEST_DB

os.environ["DATABASE_URL"] = TEST_URL
os.environ.setdefault("APP_ENV", "dev")
os.environ.setdefault("IP_HASH_SALT", "test-salt")

from happysmile import config  # noqa: E402

config.get_settings.cache_clear()


@pytest.fixture(scope="session", autouse=True)
def database():
    with psycopg.connect(ADMIN_URL, autocommit=True) as conn:
        conn.execute(f"DROP DATABASE IF EXISTS {TEST_DB} WITH (FORCE)")
        conn.execute(f"CREATE DATABASE {TEST_DB}")
    from happysmile.migrate import migrate
    from happysmile.seed import seed
    migrate(TEST_URL)
    seed()
    yield
    from happysmile.db import close_pool
    close_pool()


@pytest.fixture(autouse=True)
def clean(database):
    from happysmile.db import tx
    with tx() as conn:
        conn.execute("TRUNCATE lead, enquiry_submission, consent, call_attempt, conversation, handover, handover_feedback, "
                     "booking, message, event, audit_log, enquiry_hit, login_attempt, staff_session, call_job, suppression, "
                     "breaker, llm_call, test_call, alert, golive_attestation, webhook_event, call_review, rules_change, "
                     "pilot_decision, clinic_onboarding CASCADE")
        # Phase 6 resets: only the three pilot clinics are in the programme; local calendars; nobody on live transfer.
        conn.execute("UPDATE clinic SET is_pilot = (rollout_wave = 1), calendar_adapter = 'local', calendar_synced_at = NULL")
        conn.execute("DELETE FROM experiment_config WHERE clinic_id NOT IN ('riverside', 'hillcrest', 'lotus')")
        conn.execute("UPDATE experiment_config SET steady_since = NULL")
        conn.execute("UPDATE staff SET transfer_available = false, transfer_available_until = NULL, phone_e164 = NULL")
        conn.execute("DELETE FROM slot WHERE source = 'external'")
        conn.execute("DELETE FROM dentist WHERE external_ref IS NOT NULL")
        conn.execute("INSERT INTO slot_refresh (clinic_id, refreshed_at) SELECT id, now() FROM clinic WHERE is_pilot "
                     "ON CONFLICT (clinic_id) DO UPDATE SET refreshed_at = now()")
        conn.execute("DELETE FROM slot WHERE id NOT IN (SELECT slot_id FROM booking) AND start_at < now() - interval '1 day'")
        conn.execute("UPDATE slot SET status = 'open', hold_expires_at = NULL")
        conn.execute("UPDATE experiment_config SET assistant_share = 0, booking_paused = false, live_since = NULL")
    for k in ("VOICE_AGENT_ENABLED", "GROQ_API_KEY", "LLM_DIALOGUE_MODEL", "LLM_GUARD_MODEL", "LLM_SUMMARY_MODEL",
              "WHATSAPP_PROVIDER", "WHATSAPP_APP_SECRET", "WHATSAPP_VERIFY_TOKEN", "WHATSAPP_TOKEN", "WHATSAPP_PHONE_NUMBER_ID"):
        os.environ.pop(k, None)
    config.get_settings.cache_clear()
    for k in ("PERMANENT_CONTROL_SHARE", "CALENDAR_API_URL", "CALENDAR_API_TOKEN", "LLM_BASE_URL", "LLM_API_KEY", "LLM_PROVIDER"):
        os.environ.pop(k, None)
    config.get_settings.cache_clear()
    from happysmile import calendar_sync, llm, messaging, telephony
    llm.set_client(None)
    telephony.set_provider(None)
    messaging.set_provider(None)
    calendar_sync.set_adapter(None)
    yield


@pytest.fixture(autouse=True)
def daytime_intake(monkeypatch):
    """Intake decides 'call now' vs 'after 9 am' from the wall clock. Pin it to 14:20 IST so tests
    don't change behaviour at night. Tests that pass an explicit `now` (e.g. out-of-hours) are unaffected."""
    from datetime import datetime as real_dt

    from happysmile import enquiries
    from happysmile.config import IST

    class Daytime(real_dt):
        @classmethod
        def now(cls, tz=None):
            t = real_dt.now(IST).replace(hour=14, minute=20, second=0, microsecond=0)
            return t.astimezone(tz) if tz else t.replace(tzinfo=None)

    monkeypatch.setattr(enquiries, "datetime", Daytime)


@pytest.fixture
def client():
    from fastapi.testclient import TestClient
    from happysmile.main import app
    with TestClient(app) as c:
        yield c


def enquiry(**over) -> dict:
    body = {"client_token": str(uuid.uuid4()), "name": "Asha Verma", "mobile": "+91 98765-43210",
            "treatment": "braces", "clinic_id": "riverside", "language": "en", "contact_pref": "now",
            "consent": True, "disclosure_version": "team-en-v1"}
    body.update(over)
    return body


def login_as(client, username: str) -> None:
    pw = {"kavya": "riverside-demo", "arif": "hillcrest-demo", "neelam": "lotus-demo",
          "ops": "manager-demo", "admin": "admin-demo"}[username]
    r = client.post("/v1/auth/login", json={"username": username, "password": pw})
    assert r.status_code == 200, r.text


CSRF = {"X-Requested-With": "hs-console"}
