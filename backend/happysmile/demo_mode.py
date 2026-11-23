"""Browser voice-demo switch (development only).

    python -m happysmile.demo_mode on    # every pilot-clinic enquiry goes to the assistant (share 100%)
    python -m happysmile.demo_mode off   # back to 0%, the safe default

`run-dev.ps1 -VoiceDemo` runs `on` for you. This writes the share directly and skips the go-live
gates and the permanent control group on purpose: it is a local demo, not an experiment, and it
refuses to run in staging or production. Leads created while it is on are demo data.
"""

from __future__ import annotations

import sys

from . import events
from .config import get_settings
from .db import close_pool, init_pool, tx


def set_demo(on: bool) -> list[str]:
    if get_settings().is_production_like:
        raise SystemExit("demo_mode is for local development only.")
    share = 1 if on else 0
    with tx() as conn:
        rows = conn.execute(
            "UPDATE experiment_config e SET assistant_share = %s, booking_paused = false, updated_at = now() "
            "FROM clinic c WHERE c.id = e.clinic_id AND c.is_pilot RETURNING c.name", (share,)).fetchall()
        events.append(conn, "experiment.demo_mode", actor="system", payload={"on": on, "share": share})
    return [r["name"] for r in rows]


def main(argv: list[str]) -> None:
    if len(argv) != 1 or argv[0] not in ("on", "off"):
        raise SystemExit("usage: python -m happysmile.demo_mode on|off")
    on = argv[0] == "on"
    init_pool()
    try:
        names = set_demo(on)
    finally:
        close_pool()
    print(f"Demo mode {'ON' if on else 'OFF'}: assistant share {'100%' if on else '0%'} at {', '.join(names) or 'no pilot clinics'}.")
    if on and get_settings().telephony_provider != "browser":
        print("Note: TELEPHONY_PROVIDER is not 'browser', so calls will not ring in the browser. Use run-dev.ps1 -VoiceDemo.")


if __name__ == "__main__":
    main(sys.argv[1:])
