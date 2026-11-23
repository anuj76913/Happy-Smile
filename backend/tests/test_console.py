"""Staff console: auth, clinic scoping, outcomes, booking, claims, metrics from the event log."""

from concurrent.futures import ThreadPoolExecutor

from fastapi.testclient import TestClient

from happysmile.db import tx
from happysmile.main import app

from .conftest import CSRF, enquiry, login_as


def new_lead(client, **over) -> str:
    r = client.post("/v1/enquiries", json=enquiry(**over))
    assert r.status_code == 201, r.text
    with tx() as conn:
        return str(conn.execute("SELECT id FROM lead WHERE public_ref = %s", (r.json()["ref"],)).fetchone()["id"])


def a_slot(client, clinic="riverside") -> str:
    return client.get(f"/v1/slots?clinic={clinic}").json()["slots"][0]["id"]


# ---------------------------------------------------------------- auth
def test_login_logout_and_me(client):
    assert client.get("/v1/auth/me").status_code == 401
    assert client.post("/v1/auth/login", json={"username": "kavya", "password": "nope"}).status_code == 401
    login_as(client, "kavya")
    me = client.get("/v1/auth/me").json()
    assert me["role"] == "front_desk" and [c["id"] for c in me["clinics"]] == ["riverside"]
    client.post("/v1/auth/logout")
    assert client.get("/v1/auth/me").status_code == 401


def test_login_lockout_after_failures(client):
    for _ in range(5):
        client.post("/v1/auth/login", json={"username": "kavya", "password": "wrong"})
    r = client.post("/v1/auth/login", json={"username": "kavya", "password": "riverside-demo"})
    assert r.status_code == 429


def test_writes_need_csrf_header(client):
    lead = new_lead(client)
    login_as(client, "kavya")
    assert client.post(f"/v1/leads/{lead}/claim").status_code == 403
    assert client.post(f"/v1/leads/{lead}/claim", headers=CSRF).status_code == 200


def test_front_desk_only_sees_own_clinic(client):
    mine = new_lead(client, clinic_id="riverside")
    theirs = new_lead(client, clinic_id="hillcrest", mobile="9123456780")
    login_as(client, "kavya")
    ids = [l["id"] for l in client.get("/v1/leads").json()["leads"]]
    assert ids == [mine]
    assert client.get(f"/v1/leads/{theirs}").status_code == 403                       # EC-Q-12
    assert client.get("/v1/leads?clinic=hillcrest").status_code == 403
    assert client.post(f"/v1/leads/{theirs}/outcome", json={"outcome": "no_answer"}, headers=CSRF).status_code == 403
    with tx() as conn:
        assert conn.execute("SELECT count(*) AS n FROM audit_log WHERE action = 'access_denied'").fetchone()["n"] == 2


def test_manager_sees_all_pilot_clinics_and_admin_rules(client):
    new_lead(client, clinic_id="riverside")
    new_lead(client, clinic_id="lotus", mobile="9123456780")
    login_as(client, "ops")
    assert len(client.get("/v1/leads").json()["leads"]) == 2
    assert client.put("/v1/admin/experiment/riverside", json={"assistant_share": 0.2}, headers=CSRF).status_code == 403
    client.post("/v1/auth/logout")
    login_as(client, "admin")
    # Phase 2: the voice agent is off, so the share must stay at 0.
    r = client.put("/v1/admin/experiment/riverside", json={"assistant_share": 0.2}, headers=CSRF)
    assert r.status_code == 409 and "voice agent" in r.json()["detail"]
    assert client.put("/v1/admin/experiment/riverside", json={"assistant_share": 0}, headers=CSRF).status_code == 200


def test_viewing_a_lead_is_audited(client):
    lead = new_lead(client)
    login_as(client, "kavya")
    client.get(f"/v1/leads/{lead}")
    login_as(client, "ops")
    entries = client.get(f"/v1/audit?lead_id={lead}").json()["entries"]
    assert entries[0]["action"] == "lead_viewed" and entries[0]["by"] == "Kavya S."


# ---------------------------------------------------------------- outcomes
def test_outcomes_move_leads_between_views(client):
    lead = new_lead(client)
    login_as(client, "kavya")
    r = client.post(f"/v1/leads/{lead}/outcome", json={"outcome": "no_answer"}, headers=CSRF)
    assert r.json()["status"] == "no_answer"
    r = client.post(f"/v1/leads/{lead}/outcome", json={"outcome": "reached_follow_up", "note": "Call after 6"}, headers=CSRF)
    assert r.json()["status"] == "follow_up"
    detail = client.get(f"/v1/leads/{lead}").json()
    assert detail["first_reached_at"] and detail["follow_up_note"] == "Call after 6"
    assert [a["outcome"] for a in detail["attempt_log"]] == ["no_answer", "answered"]
    client.post(f"/v1/leads/{lead}/outcome", json={"outcome": "reached_not_interested"}, headers=CSRF)
    assert client.get("/v1/leads").json()["leads"] == []
    assert len(client.get("/v1/leads?view=done").json()["leads"]) == 1
    # Closed leads can't take more outcomes.
    assert client.post(f"/v1/leads/{lead}/outcome", json={"outcome": "no_answer"}, headers=CSRF).status_code == 409


def test_claim_conflict(client):
    lead = new_lead(client)
    login_as(client, "kavya")
    assert client.post(f"/v1/leads/{lead}/claim", headers=CSRF).status_code == 200
    with TestClient(app) as other:
        login_as(other, "ops")
        r = other.post(f"/v1/leads/{lead}/claim", headers=CSRF)
        assert r.status_code == 409 and "Kavya S." in r.json()["detail"]


# ---------------------------------------------------------------- booking
def test_booking_closes_lead_and_takes_slot(client):
    lead = new_lead(client)
    login_as(client, "kavya")
    slot = a_slot(client)
    r = client.post(f"/v1/leads/{lead}/bookings", json={"slot_id": slot}, headers=CSRF)
    assert r.status_code == 200
    d = client.get(f"/v1/leads/{lead}").json()
    assert d["status"] == "booked" and d["booking"]["created_by"] == "staff" and d["first_reached_at"]
    assert slot not in [s["id"] for s in client.get("/v1/slots?clinic=riverside").json()["slots"]]


def test_same_slot_cannot_be_double_booked(client):
    a = new_lead(client)
    b = new_lead(client, mobile="9123456780")
    login_as(client, "kavya")
    slot = a_slot(client)
    with ThreadPoolExecutor(2) as pool:
        codes = sorted(pool.map(lambda lid: client.post(f"/v1/leads/{lid}/bookings", json={"slot_id": slot},
                                                        headers=CSRF).status_code, [a, b]))
    assert codes == [200, 409]
    with tx() as conn:
        assert conn.execute("SELECT count(*) AS n FROM booking WHERE slot_id = %s", (slot,)).fetchone()["n"] == 1


def test_slot_from_another_clinic_is_refused(client):
    lead = new_lead(client)
    login_as(client, "ops")
    other = a_slot(client, "lotus")
    assert client.post(f"/v1/leads/{lead}/bookings", json={"slot_id": other}, headers=CSRF).status_code == 409


def test_add_slots_marks_store_fresh(client):
    login_as(client, "kavya")
    dentist = client.get("/v1/dentists").json()["dentists"][0]["id"]
    from datetime import date, timedelta
    day = (date.today() + timedelta(days=10)).isoformat()
    r = client.post("/v1/slots/bulk", json={"clinic_id": "riverside", "dentist_id": dentist, "day": day,
                                            "start": "09:00", "end": "11:00", "duration_min": 30}, headers=CSRF)
    assert r.json()["created"] == 4
    again = client.post("/v1/slots/bulk", json={"clinic_id": "riverside", "dentist_id": dentist, "day": day,
                                                "start": "09:00", "end": "11:00", "duration_min": 30}, headers=CSRF)
    assert again.json()["created"] == 0  # no duplicates
    assert client.get("/v1/slots?clinic=riverside").json()["stale"] is False


# ---------------------------------------------------------------- metrics
def test_event_log_reproduces_top_strip(client):
    """Plan P2 exit criterion: the event log reproduces the top-strip numbers exactly."""
    ids = [new_lead(client, mobile=f"98765432{n:02d}") for n in range(6)]
    new_lead(client, mobile="9876543299")  # duplicate of nobody; counts as enquiry
    client.post("/v1/enquiries", json=enquiry(mobile="9876543200"))  # merge, not a new enquiry
    login_as(client, "kavya")
    client.post(f"/v1/leads/{ids[0]}/outcome", json={"outcome": "no_answer"}, headers=CSRF)
    client.post(f"/v1/leads/{ids[1]}/outcome", json={"outcome": "reached_follow_up"}, headers=CSRF)
    client.post(f"/v1/leads/{ids[2]}/outcome", json={"outcome": "reached_not_interested"}, headers=CSRF)
    client.post(f"/v1/leads/{ids[3]}/outcome", json={"outcome": "invalid_number"}, headers=CSRF)
    client.post(f"/v1/leads/{ids[4]}/bookings", json={"slot_id": a_slot(client)}, headers=CSRF)

    m = client.get("/v1/metrics/today").json()
    assert m["enquiries_received"] == 7
    assert m["booked_by_staff"] == 1 and m["booked_by_assistant"] == 0
    assert m["waiting_for_staff"] == 2          # ids[5] and the 7th lead
    assert m["no_answer"] == 1
    assert m["reached_within_5"]["control"] == {"leads": 7, "reached_within_5": 3, "reached": 3}

    login_as(client, "ops")
    c = client.get("/v1/admin/metrics/consistency").json()
    assert c["match"] is True, c


# ---------------------------------------------------------------- pages
def test_pages_and_security_headers(client):
    for path in ("/", "/console"):
        r = client.get(path)
        assert r.status_code == 200 and "text/html" in r.headers["content-type"]
        assert "frame-ancestors 'none'" in r.headers["content-security-policy"]
        assert r.headers["x-content-type-options"] == "nosniff"
    assert client.get("/healthz").json()["ok"] is True
