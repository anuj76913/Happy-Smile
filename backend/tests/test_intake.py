"""Exit criterion: dedupe, consent capture and idempotency are covered by automated tests."""

from concurrent.futures import ThreadPoolExecutor

import psycopg
import pytest

from happysmile.db import tx

from .conftest import enquiry


def rows(sql, *args):
    with tx() as conn:
        return conn.execute(sql, args).fetchall()


def test_create_enquiry_records_lead_consent_arm_and_events(client):
    r = client.post("/v1/enquiries", json=enquiry(), headers={"user-agent": "pytest"})
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["ref"].startswith("HS-") and body["deduplicated"] is False
    assert body["contact"] == {"who": "team", "channel": "call", "when": "clinic_hours"}  # no AI promise at 0%

    lead = rows("SELECT * FROM lead")[0]
    assert lead["phone_e164"] == "+919876543210"
    assert lead["arm"] == "control" and lead["status"] == "awaiting_call"

    consent = rows("SELECT * FROM consent")
    assert len(consent) == 1 and consent[0]["disclosure_version"] == "team-en-v1"
    assert consent[0]["ip_hash"] and consent[0]["ip_hash"] != "testclient"  # IP stored hashed only

    types = [e["type"] for e in rows("SELECT type FROM event ORDER BY id")]
    assert types == ["lead.created", "consent.recorded", "lead.assigned", "lead.status_changed"]


def test_same_client_token_is_idempotent(client):
    body = enquiry()
    first = client.post("/v1/enquiries", json=body)
    again = client.post("/v1/enquiries", json=body)
    assert first.status_code == 201 and again.status_code == 200
    assert again.json()["ref"] == first.json()["ref"] and again.json()["replayed"] is True
    assert len(rows("SELECT id FROM lead")) == 1
    assert len(rows("SELECT id FROM consent")) == 1


def test_parallel_double_submit_creates_one_lead(client):
    body = enquiry()
    with ThreadPoolExecutor(6) as pool:
        results = list(pool.map(lambda _: client.post("/v1/enquiries", json=body), range(6)))
    assert sorted(r.status_code for r in results) == [200] * 5 + [201]
    assert len(rows("SELECT id FROM lead")) == 1


def test_parallel_different_tokens_same_phone_dedupe(client):
    with ThreadPoolExecutor(4) as pool:
        results = list(pool.map(lambda _: client.post("/v1/enquiries", json=enquiry()), range(4)))
    assert sorted(r.status_code for r in results) == [200, 200, 200, 201]
    assert len(rows("SELECT id FROM lead")) == 1
    assert len(rows("SELECT id FROM consent")) == 4  # every submission's consent is kept


def test_duplicate_within_24h_merges(client):
    client.post("/v1/enquiries", json=enquiry(treatment="braces"))
    r = client.post("/v1/enquiries", json=enquiry(treatment="whitening", mobile="098765 43210"))
    assert r.status_code == 200 and r.json()["deduplicated"] is True
    lead = rows("SELECT * FROM lead")
    assert len(lead) == 1 and lead[0]["extra_treatments"] == ["whitening"]
    assert [e["type"] for e in rows("SELECT type FROM event WHERE type = 'lead.deduplicated'")] == ["lead.deduplicated"]


def test_duplicate_updates_contact_pref_if_not_yet_reached(client):
    client.post("/v1/enquiries", json=enquiry(contact_pref="now"))
    client.post("/v1/enquiries", json=enquiry(contact_pref="whatsapp"))
    assert rows("SELECT contact_pref FROM lead")[0]["contact_pref"] == "whatsapp"


def test_renewed_interest_reopens_not_interested_lead(client):
    client.post("/v1/enquiries", json=enquiry())
    with tx() as conn:
        conn.execute("UPDATE lead SET status = 'not_interested'")
    client.post("/v1/enquiries", json=enquiry())
    assert rows("SELECT status FROM lead")[0]["status"] == "awaiting_call"


def test_returning_patient_after_24h_gets_new_lead_and_same_arm(client):
    client.post("/v1/enquiries", json=enquiry())
    with tx() as conn:
        conn.execute("UPDATE lead SET created_at = now() - interval '3 days'")
    r = client.post("/v1/enquiries", json=enquiry())
    assert r.status_code == 201
    leads = rows("SELECT arm, returning_of FROM lead ORDER BY created_at")
    assert len(leads) == 2 and leads[1]["returning_of"] is not None and leads[1]["arm"] == leads[0]["arm"]
    reason = rows("SELECT payload->>'reason' AS r FROM event WHERE type = 'lead.assigned' ORDER BY id DESC LIMIT 1")
    assert reason[0]["r"] == "returning_patient"


@pytest.mark.parametrize("override,field", [
    ({"mobile": "12345"}, "mobile"),
    ({"mobile": "+44 7700 900123"}, "mobile"),
    ({"name": "   "}, "name"),
    ({"clinic_id": "nowhere"}, "clinic"),
    ({"consent": False}, "consent"),
    ({"contact_pref": "scheduled", "scheduled_at": "2020-01-01T10:00:00+05:30"}, "scheduled_at"),
])
def test_validation(client, override, field):
    r = client.post("/v1/enquiries", json=enquiry(**override))
    assert r.status_code == 422 and field in r.json()["fields"]
    assert rows("SELECT id FROM lead") == []


def test_script_in_name_is_stored_as_text(client):
    r = client.post("/v1/enquiries", json=enquiry(name="<script>alert(1)</script>"))
    assert r.status_code == 201
    assert rows("SELECT name FROM lead")[0]["name"] == "<script>alert(1)</script>"  # escaped on render


def test_stale_disclosure_version_is_rejected_with_current_wording(client):
    r = client.post("/v1/enquiries", json=enquiry(disclosure_version="assistant-en-v1"))
    assert r.status_code == 409 and r.json()["disclosure"]["version"] == "team-en-v1"


def test_rate_limit_per_phone(client):
    codes = [client.post("/v1/enquiries", json=enquiry()).status_code for _ in range(6)]
    assert codes[:5] == [201, 200, 200, 200, 200] and codes[5] == 429


def test_non_pilot_clinic_is_not_randomised(client):
    client.post("/v1/enquiries", json=enquiry(clinic_id="maple"))
    assert rows("SELECT arm FROM lead")[0]["arm"] == "not_in_pilot"


def test_hindi_form_uses_hindi_disclosure(client):
    cfg = client.get("/v1/enquiry-config?lang=hi").json()
    riverside = next(c for c in cfg["clinics"] if c["id"] == "riverside")
    assert riverside["disclosure"]["version"] == "team-hi-v1"
    r = client.post("/v1/enquiries", json=enquiry(language="hi", disclosure_version="team-hi-v1"))
    assert r.status_code == 201


def test_append_only_and_write_once_are_enforced_by_the_database(client):
    client.post("/v1/enquiries", json=enquiry())
    for sql in ("UPDATE event SET type = 'x'", "DELETE FROM event", "UPDATE consent SET call_consent = false",
                "DELETE FROM consent", "UPDATE lead SET arm = 'assistant'",
                "UPDATE disclosure_version SET consent = 'x'"):
        with pytest.raises(psycopg.errors.RestrictViolation):
            with tx() as conn:
                conn.execute(sql)
