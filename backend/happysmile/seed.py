"""Seed reference data for development and staging.

Creates the 12 clinics (3 pilot), dentists, experiment config at 0% assistant share,
demo staff accounts and a week of open slots for the pilot clinics. Safe to re-run.

Usage:  python -m happysmile.seed [--with-demo-leads]

Refuses to create demo staff accounts in production.
"""

from __future__ import annotations

import secrets
import sys
from datetime import datetime, timedelta

from .config import IST, get_settings
from .db import tx
from .disclosures import register_all
from .security import hash_password

CLINICS = [("riverside", "Riverside", True), ("hillcrest", "Hillcrest", True), ("lotus", "Lotus Square", True),
           ("maple", "Maple Road", False), ("palm", "Palm Grove", False), ("banyan", "Banyan Park", False),
           ("cedar", "Cedar Avenue", False), ("harbour", "Harbour View", False), ("orchid", "Orchid Lane", False),
           ("sunrise", "Sunrise Plaza", False), ("willow", "Willow Street", False), ("lakegate", "Lake Gate", False)]
DENTISTS = {"riverside": ["Dr. Meera Rao", "Dr. Nisha Pillai"], "hillcrest": ["Dr. Karan Bhatia", "Dr. Sana Mirza"],
            "lotus": ["Dr. Leena Das", "Dr. Vivek Menon"]}
# username, display name, role, clinics, dev password
STAFF = [("kavya", "Kavya S.", "front_desk", ["riverside"], "riverside-demo"),
         ("arif", "Arif K.", "front_desk", ["hillcrest"], "hillcrest-demo"),
         ("neelam", "Neelam P.", "front_desk", ["lotus"], "lotus-demo"),
         ("ops", "Ops Manager", "manager", [], "manager-demo"),
         ("admin", "Pilot Admin", "admin", [], "admin-demo")]
# Used when OPEN_CONSOLE is on (public demo): front desk for all pilot clinics, no Ops/admin rights, no password login.
GUEST = ("guest", "Demo visitor", "front_desk", ["riverside", "hillcrest", "lotus"])


def seed(with_staff: bool = True, slot_days: int = 7) -> None:
    with tx() as conn:
        register_all(conn)
        for cid, name, pilot in CLINICS:
            conn.execute("INSERT INTO clinic (id, name, is_pilot) VALUES (%s, %s, %s) ON CONFLICT (id) DO NOTHING",
                         (cid, name, pilot))
            if pilot:
                conn.execute("INSERT INTO experiment_config (clinic_id, assistant_share, salt) VALUES (%s, 0, %s) "
                             "ON CONFLICT (clinic_id) DO NOTHING", (cid, secrets.token_hex(16)))
        waves = {"riverside": 1, "hillcrest": 1, "lotus": 1, "maple": 2, "palm": 2, "banyan": 2,
                 "cedar": 3, "harbour": 3, "orchid": 3, "sunrise": 4, "willow": 4, "lakegate": 4}
        for cid, wave in waves.items():
            conn.execute("UPDATE clinic SET rollout_wave = coalesce(rollout_wave, %s), "
                         "activated_at = CASE WHEN is_pilot THEN coalesce(activated_at, now()) ELSE activated_at END WHERE id = %s",
                         (wave, cid))
        addresses = {"riverside": "14 River Walk, Riverside", "hillcrest": "2 Crest Road, Hillcrest",
                     "lotus": "88 Lotus Square Market, Lotus Square"}  # fictional
        for cid, addr in addresses.items():
            conn.execute("UPDATE clinic SET address = %s WHERE id = %s AND address IS NULL", (addr, cid))
        for cid, names in DENTISTS.items():
            for n in names:
                if not conn.execute("SELECT 1 FROM dentist WHERE clinic_id = %s AND name = %s", (cid, n)).fetchone():
                    conn.execute("INSERT INTO dentist (clinic_id, name) VALUES (%s, %s)", (cid, n))
        if with_staff:
            override = get_settings().demo_staff_password  # public demo: never the published dev passwords
            for username, display, role, clinics, pw in STAFF:
                row = conn.execute("SELECT id FROM staff WHERE username = %s", (username,)).fetchone()
                if row is None:
                    row = conn.execute("INSERT INTO staff (username, display_name, role, password_hash) "
                                       "VALUES (%s, %s, %s, %s) RETURNING id",
                                       (username, display, role, hash_password(override or pw))).fetchone()
                elif override:
                    conn.execute("UPDATE staff SET password_hash = %s WHERE id = %s", (hash_password(override), row["id"]))
                for c in clinics:
                    conn.execute("INSERT INTO staff_clinic (staff_id, clinic_id) VALUES (%s, %s) ON CONFLICT DO NOTHING",
                                 (row["id"], c))
            username, display, role, clinics = GUEST
            row = conn.execute("SELECT id FROM staff WHERE username = %s", (username,)).fetchone()
            if row is None:  # random password nobody knows: the account is only used by OPEN_CONSOLE
                row = conn.execute("INSERT INTO staff (username, display_name, role, password_hash) VALUES (%s, %s, %s, %s) "
                                   "RETURNING id", (username, display, role, hash_password(secrets.token_urlsafe(24)))).fetchone()
            for c in clinics:
                conn.execute("INSERT INTO staff_clinic (staff_id, clinic_id) VALUES (%s, %s) ON CONFLICT DO NOTHING", (row["id"], c))
        # A week of 30-minute slots, 10:00-13:00 and 16:00-20:00, for each pilot dentist.
        today = datetime.now(IST).date()
        for d in conn.execute("SELECT id, clinic_id FROM dentist").fetchall():
            for offset in range(slot_days):
                day = today + timedelta(days=offset)
                for start_h, end_h in ((10, 13), (16, 20)):
                    t = datetime(day.year, day.month, day.day, start_h, tzinfo=IST)
                    while t.hour < end_h:
                        conn.execute("INSERT INTO slot (clinic_id, dentist_id, start_at, duration_min) VALUES (%s, %s, %s, 30) "
                                     "ON CONFLICT (dentist_id, start_at) DO NOTHING", (d["clinic_id"], d["id"], t))
                        t += timedelta(minutes=30)
            conn.execute("INSERT INTO slot_refresh (clinic_id, refreshed_at) VALUES (%s, now()) "
                         "ON CONFLICT (clinic_id) DO UPDATE SET refreshed_at = now()", (d["clinic_id"],))


if __name__ == "__main__":
    from .db import close_pool
    s = get_settings()
    if s.env == "production":
        seed(with_staff=False)
        close_pool()
        print("Seeded reference data (no demo staff in production).")
        sys.exit(0)
    seed()
    close_pool()
    print("Seeded clinics, dentists, experiment config (0% assistant), slots and demo staff:")
    for username, display, role, clinics, pw in STAFF:
        shown = "(DEMO_STAFF_PASSWORD)" if s.demo_staff_password else pw
        print(f"  {username:8s} / {shown:22s} {role:10s} {', '.join(clinics) or 'all clinics'}")
