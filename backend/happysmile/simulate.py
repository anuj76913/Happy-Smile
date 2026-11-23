"""Development only: run simulated assistant calls end to end through the database.

Creates enquiries in one pilot clinic with the assistant share at 100%, places the
calls through the simulated telephony provider, and answers them with scripted callers
from the evaluation set. Afterwards the console shows real Needs you / Booked data.

Usage:
    VOICE_AGENT_ENABLED=true python -m happysmile.simulate [--clinic riverside]

Refuses to run outside APP_ENV=dev.
"""

from __future__ import annotations

import argparse
import random
import uuid
from datetime import datetime

from . import enquiries, experiment, orchestrator
from .config import IST, get_settings
from .db import close_pool, tx

SCRIPTS = [
    ("Asha Verma", "braces", ["yes", "yes", "no", "yes", "tomorrow evening", "the first one", "no"]),
    ("Rohan Mehta", "braces", ["Can I talk to a real person?"]),
    ("Sunita Devi", "implants", ["haan", "haan", "haan, masoode mein sujan hai"]),
    ("Farhan Qureshi", "implants", ["yes", "How much does an implant cost, and is EMI available?"]),
    ("Neha Iyer", "whitening", ["yes", "Is whitening safe while breastfeeding?"]),
    ("Meera Kulkarni", "whitening", ["yes", "yes", "no", "yes", "Saturday morning", "second one", "no thanks"]),
    ("Arjun Nair", "braces", ["yes", "yes", "no", "yes", "day after tomorrow afternoon", "first", "no"]),
    ("Imran Shaikh", "other", [{"no_answer": True}]),
]


def main() -> None:
    s = get_settings()
    if s.env != "dev":
        raise SystemExit("simulate is for development only.")
    if not s.voice_agent_enabled:
        raise SystemExit("Set VOICE_AGENT_ENABLED=true (with TELEPHONY_PROVIDER=sim) to run simulated calls.")
    ap = argparse.ArgumentParser()
    ap.add_argument("--clinic", default="riverside")
    clinic = ap.parse_args().clinic
    with tx() as conn:
        # Dev-only scaffolding: force 100% so every scripted caller reaches the assistant. Real share changes go
        # through experiment.set_share, which keeps a permanent control group (max 90%).
        conn.execute("UPDATE experiment_config SET assistant_share = 1 WHERE clinic_id = %s", (clinic,))
    now = datetime.now(IST)
    for name, treatment, turns in SCRIPTS:
        lang = "hi" if name in ("Sunita Devi", "Imran Shaikh") else "en"
        sub = enquiries.Submission(client_token=uuid.uuid4(), name=name, mobile=f"9{random.randint(100000000, 999999999)}",
                                   treatment=treatment, treatment_other=None, clinic_id=clinic, language=lang,
                                   contact_pref="now", scheduled_at=None, consent=True,
                                   disclosure_version=f"assistant-{lang}-v1")
        with tx() as conn:
            _, body = enquiries.submit(conn, sub, "127.0.0.1", "simulate", now=now)
            # Run only this lead's job, so other pending jobs (e.g. scheduled retries) are left alone.
            jobs = [str(r["id"]) for r in conn.execute(
                "UPDATE call_job j SET status = 'running', locked_until = now() + interval '2 minutes' FROM lead l "
                "WHERE l.id = j.lead_id AND l.public_ref = %s AND j.status = 'pending' RETURNING j.id", (body["ref"],))]
        for job in jobs:
            res = orchestrator.process_job(job, now=now.replace(hour=14, minute=20))
            if not res.startswith("placed:"):
                print(f"{name}: {res}")
                continue
            attempt = res.split(":", 1)[1]
            if turns and isinstance(turns[0], dict):
                orchestrator.on_status(attempt, "no_answer")
                print(f"{name}: no answer, retry scheduled")
                continue
            orchestrator.on_status(attempt, "answered")
            for t in turns:
                r = orchestrator.on_caller_turn(attempt, t)
                if r["end"]:
                    break
            with tx() as conn:
                o = conn.execute("SELECT outcome FROM conversation WHERE call_attempt_id = %s", (attempt,)).fetchone()
            print(f"{name}: {o['outcome'] if o else 'in progress'} ({body['ref']})")
    with tx() as conn:
        conn.execute("UPDATE experiment_config SET assistant_share = 0 WHERE clinic_id = %s", (clinic,))
    from . import messaging
    print("WhatsApp (simulated):", messaging.dispatch_due())
    close_pool()


if __name__ == "__main__":
    main()
