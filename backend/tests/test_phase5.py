"""Phase 5: readout statistics and G4 recommendation, call reviews, change log, attendance."""

import math
from datetime import date, datetime, timedelta, timezone

import psycopg
import pytest

from happysmile import readout
from happysmile.config import IST
from happysmile.db import tx
from happysmile.pilot_synthetic import generate

from .conftest import CSRF, login_as
from .test_phase4 import book_by_assistant, voice_on  # noqa: F401  (fixture)
from .test_voice_flow import q


# ---------------------------------------------------------------- statistics
def test_newcombe_matches_published_example():
    # Newcombe (1998), method 10: 56/70 vs 48/80 -> 0.2000 (0.0524 to 0.3339); 9/10 vs 3/10 -> 0.6 (0.1705 to 0.8090)
    d = readout.diff_ci(56, 70, 48, 80)
    assert d["diff"] == pytest.approx(0.2, abs=1e-6)
    assert d["lo"] == pytest.approx(0.0524, abs=1e-4) and d["hi"] == pytest.approx(0.3339, abs=1e-4)
    d2 = readout.diff_ci(9, 10, 3, 10)
    assert d2["lo"] == pytest.approx(0.1705, abs=1e-4) and d2["hi"] == pytest.approx(0.8090, abs=1e-4)
    lo, hi = readout.wilson(0, 10)
    assert lo == 0 and hi == pytest.approx(0.2775, abs=1e-3)
    assert readout.n_per_arm(0.30) == 356


def _r(diff=(0.09, 0.03, 0.15), att=(0.0, -0.08, 0.08), missed=0, stops=0, sla=0.95, rej=0.02, oo=(0.01, 0.01), have=400):
    def d(t):
        return {"diff": t[0], "lo": t[1], "hi": t[2]}
    return {"primary": {"diff": d(diff)}, "attendance": {"diff": d(att)},
            "safety": {"urgent_missed": missed, "auto_stops": stops, "sla_hit_rate": sla, "review_rejection_rate": rej,
                       "opt_out": {"assistant": {"rate": oo[0]}, "control": {"rate": oo[1]}}},
            "power": {"needed_per_arm_for_10pt_lift": 356, "have_per_arm": have}}


@pytest.mark.parametrize("kw,expected", [
    ({}, "scale"),
    ({"diff": (0.05, -0.02, 0.12)}, "extend"),                       # lift unclear, guardrails fine
    ({"sla": 0.7}, "fix_first"),                                      # lift appears, staff can't keep up
    ({"rej": 0.09}, "fix_first"),
    ({"missed": 1}, "stop_or_redesign"),                              # safety incident
    ({"stops": 1}, "stop_or_redesign"),
    ({"att": (-0.12, -0.2, -0.03)}, "stop_or_redesign"),              # bookings up, attendance down
    ({"oo": (0.06, 0.01)}, "fix_first"),                              # opt-outs much higher
])
def test_g4_decision_table(kw, expected):
    assert readout.decide(_r(**kw))["decision"] == expected


def test_underpowered_is_flagged():
    reasons = readout.decide(_r(diff=(0.05, -0.02, 0.12), have=120))["reasons"]
    assert any("Underpowered" in x for x in reasons)


# ---------------------------------------------------------------- readout on generated pilot data
def test_readout_on_synthetic_pilot(client):
    gen = generate(days=21, per_clinic_day=12, seed=3)
    today = datetime.now(IST).date()
    with tx() as conn:
        r = readout.compute(conn, today - timedelta(days=20), today, ["hillcrest", "lotus", "riverside"])
    assert r["leads"]["total"] == gen["leads"]
    assert r["primary"]["assistant"]["n"] + r["primary"]["control"]["n"] == r["leads"]["matured"]
    assert r["speed"]["assistant"]["p50_min"] < 5 < r["speed"]["control"]["p50_min"]   # the mechanism changed
    assert set(r["segments"]) == {"clinic", "treatment", "language", "hour"}
    assert r["recommendation"]["decision"] in readout.DECISIONS
    md = readout.render_markdown(r, synthetic=True)
    assert "SYNTHETIC DATA" in md and "Booked within 7 days" in md and "Recommendation (gate G4)" in md

    login_as(client, "kavya")
    assert client.get("/v1/admin/readout").status_code == 403
    login_as(client, "ops")
    api = client.get(f"/v1/admin/readout?from={today - timedelta(days=20)}&to={today}").json()
    assert api["primary"]["assistant"]["n"] == r["primary"]["assistant"]["n"]
    dl = client.get(f"/v1/admin/readout.md?from={today - timedelta(days=20)}&to={today}")
    assert dl.status_code == 200 and dl.headers["content-type"].startswith("text/markdown")
    # Recording the G4 decision: admins only, keeps a snapshot, can't be edited
    assert client.post("/v1/admin/readout/decision", json={"decision": "extend", "notes": "Need more data"}, headers=CSRF).status_code == 403
    login_as(client, "admin")
    rec = client.post("/v1/admin/readout/decision", json={"decision": "extend", "notes": "Two more weeks at 50/50."}, headers=CSRF)
    assert rec.status_code == 200
    row = q("SELECT decision, recommended, readout FROM pilot_decision")[0]
    assert row["decision"] == "extend" and row["readout"]["leads"]["total"] == gen["leads"]
    with pytest.raises(psycopg.errors.RestrictViolation):
        with tx() as conn:
            conn.execute("UPDATE pilot_decision SET decision = 'scale'")


# ---------------------------------------------------------------- reviews, change log, attendance
def test_daily_review_flow(client, voice_on):  # noqa: F811
    book_by_assistant(client)
    login_as(client, "kavya")
    sample = client.get("/v1/reviews/sample").json()["calls"]
    assert len(sample) == 1 and sample[0]["outcome"] == "booked" and sample[0]["rules_version"]
    call = client.get(f"/v1/reviews/calls/{sample[0]['call_id']}").json()
    assert "virtual assistant" in call["transcript"][0]["text"]
    r = client.post(f"/v1/reviews/calls/{sample[0]['call_id']}", json={"disclosure_ok": True, "booking_ok": False, "tone_ok": True,
                    "issue_tags": ["wrong_booking", "not-a-tag"], "notes": "Read-back missed the dentist"}, headers=CSRF)
    assert r.status_code == 200
    assert client.get("/v1/reviews/sample").json()["calls"][0]["reviewed_by_me"] is True
    login_as(client, "arif")  # Hillcrest only
    assert client.get(f"/v1/reviews/calls/{sample[0]['call_id']}").status_code == 403
    login_as(client, "ops")
    wk = client.get("/v1/admin/weekly-review").json()
    assert wk["calls_reviewed"] == 1 and wk["checklist_failures"] == {"booking": 1} and wk["issue_tags"] == {"wrong_booking": 1}


def test_rules_version_recorded_and_change_log(client, voice_on):  # noqa: F811
    from happysmile.voice import RULES_VERSION
    book_by_assistant(client)
    assert q("SELECT prompt_version FROM conversation")[0]["prompt_version"] == RULES_VERSION
    login_as(client, "kavya")
    assert client.post("/v1/admin/rules-changes", json={"version": "r5.1", "area": "keywords", "description": "Add 'sujan' spelling"},
                       headers=CSRF).status_code == 403
    login_as(client, "ops")
    assert client.post("/v1/admin/rules-changes", json={"version": "r5.1", "area": "keywords",
                       "description": "Add 'sujan' spelling", "reason": "3 thumbs-down"}, headers=CSRF).status_code == 200
    log = client.get("/v1/admin/rules-changes").json()
    assert log["current_version"] == RULES_VERSION and log["changes"][0]["version"] == "r5.1"
    with pytest.raises(psycopg.errors.RestrictViolation):
        with tx() as conn:
            conn.execute("DELETE FROM rules_change")


def test_attendance_for_both_arms(client, voice_on):  # noqa: F811
    book_by_assistant(client)
    b = q("SELECT id FROM booking")[0]["id"]
    login_as(client, "kavya")
    assert client.post(f"/v1/bookings/{b}/attendance", json={"attended": True}, headers=CSRF).status_code == 409  # not yet happened
    with tx() as conn:
        conn.execute("UPDATE booking SET start_at = now() - interval '1 day'")
    items = client.get("/v1/attendance").json()["appointments"]
    assert len(items) == 1 and items[0]["attended"] is None
    assert client.post(f"/v1/bookings/{b}/attendance", json={"attended": False}, headers=CSRF).status_code == 200
    assert q("SELECT attended, attendance_recorded_by FROM booking")[0]["attended"] is False
    assert q("SELECT payload->>'arm' AS arm FROM event WHERE type = 'booking.attendance'")[0]["arm"] == "assistant"
