"""Lead intake (architecture §4.2; edge cases EC-FORM-*, EC-TIME-*).

One transaction per submission:
  1. Idempotency: a repeated client token returns the stored response (EC-FORM-10/11).
  2. Rate limits by hashed IP and by phone (EC-FORM-16/17).
  3. Same phone within 24 h -> merge into that lead, don't create a second one (EC-FORM-12/13/22).
  4. Otherwise create the lead, record consent, assign the arm, emit events.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta

from psycopg import Connection, errors
from psycopg.types.json import Jsonb

from . import calling_window, disclosures, events, experiment
from .config import IST, get_settings
from .phone import normalise_mobile
from .security import hash_ip, new_public_ref

TREATMENTS = {"braces", "whitening", "implants", "other"}
OPEN_STATUSES = ("new", "awaiting_call", "no_answer", "follow_up", "queued", "needs_you")
DEDUPE_WINDOW = timedelta(hours=24)


class IntakeError(Exception):
    def __init__(self, status: int, code: str, message: str, fields: dict | None = None, extra: dict | None = None):
        super().__init__(message)
        self.status, self.code, self.message, self.fields, self.extra = status, code, message, fields or {}, extra or {}


@dataclass
class Submission:
    client_token: uuid.UUID
    name: str
    mobile: str
    treatment: str
    treatment_other: str | None
    clinic_id: str
    language: str
    contact_pref: str
    scheduled_at: datetime | None
    consent: bool
    disclosure_version: str


def _validate(conn: Connection, s: Submission, now: datetime) -> tuple[str, dict]:
    fields: dict[str, str] = {}
    name = " ".join((s.name or "").split())
    if not name:
        fields["name"] = "required"
    elif len(name) > 60:
        fields["name"] = "too_long"
    phone = normalise_mobile(s.mobile)
    if phone is None:
        fields["mobile"] = "invalid_mobile"
    if s.treatment not in TREATMENTS:
        fields["treatment"] = "invalid"
    if s.treatment_other and len(s.treatment_other) > 80:
        fields["treatment_other"] = "too_long"
    clinic = conn.execute("SELECT id, name, is_pilot FROM clinic WHERE id = %s", (s.clinic_id,)).fetchone()
    if clinic is None:
        fields["clinic"] = "required"
    if s.language not in ("en", "hi"):
        fields["language"] = "invalid"
    if s.contact_pref not in ("now", "scheduled", "whatsapp"):
        fields["contact_pref"] = "invalid"
    if s.contact_pref == "scheduled":
        if s.scheduled_at is None or not calling_window.is_valid_scheduled_time(s.scheduled_at, now):
            fields["scheduled_at"] = "outside_calling_hours"
    if not s.consent:
        fields["consent"] = "required"  # EC-FORM-05: the form blocks this too
    if fields:
        raise IntakeError(422, "invalid", "Some fields need attention.", fields)

    # The wording the person saw must be the wording that applies to this clinic now.
    _, share, _ = experiment.clinic_share(conn, s.clinic_id)
    variant = disclosures.variant_for_share(share, clinic["is_pilot"])
    expected = disclosures.CURRENT[(variant, s.language)]
    if s.disclosure_version != expected:
        raise IntakeError(409, "disclosure_changed", "The wording on the form has changed. Please review and confirm again.",
                          extra={"disclosure": disclosures.render(expected, get_settings().caller_id)})
    return phone, {"name": name, "clinic": clinic}


def _rate_limited(conn: Connection, ip_hash: str | None, phone: str) -> bool:
    s = get_settings()
    if ip_hash:
        n = conn.execute("SELECT count(*) AS n FROM enquiry_hit WHERE ip_hash = %s AND at > now() - interval '10 minutes'",
                         (ip_hash,)).fetchone()["n"]
        if n >= s.rate_limit_ip_per_10min:
            return True
    n = conn.execute("SELECT count(*) AS n FROM enquiry_hit WHERE phone_e164 = %s AND at > now() - interval '1 hour'",
                     (phone,)).fetchone()["n"]
    return n >= s.rate_limit_phone_per_hour


def _contact_info(lead: dict, now: datetime) -> dict:
    """What the confirmation screen may honestly promise."""
    s = get_settings()
    who = "assistant" if lead["arm"] == "assistant" and s.voice_agent_enabled else "team"
    info: dict = {"who": who, "channel": "whatsapp" if lead["contact_pref"] == "whatsapp" else "call"}
    if lead["contact_pref"] == "scheduled":
        info["when"] = "scheduled"
        info["scheduled_at"] = lead["scheduled_at"].astimezone(IST).isoformat()
    elif who == "assistant" and lead["contact_pref"] == "now":
        if calling_window.can_call_now(now):
            info.update(when="now", eta_seconds=120)
        else:
            info.update(when="next_opening", next_opening_at=calling_window.next_opening(now).isoformat())
    else:
        info["when"] = "clinic_hours"
    if who == "assistant":
        info["caller_id"] = s.caller_id
    return info


def submit(conn: Connection, s: Submission, ip: str | None, user_agent: str | None,
           now: datetime | None = None) -> tuple[int, dict]:
    """Returns (http_status, response body)."""
    now = now or datetime.now(IST)

    # 1. Idempotent replay.
    prev = conn.execute("SELECT response FROM enquiry_submission WHERE client_token = %s", (s.client_token,)).fetchone()
    if prev:
        return 200, {**prev["response"], "replayed": True}

    phone, extra = _validate(conn, s, now)
    ip_h = hash_ip(ip)

    # Serialise submissions for the same phone so parallel duplicates can't both create a lead.
    conn.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (phone,))
    prev = conn.execute("SELECT response FROM enquiry_submission WHERE client_token = %s", (s.client_token,)).fetchone()
    if prev:
        return 200, {**prev["response"], "replayed": True}

    # 2. Rate limits.
    if _rate_limited(conn, ip_h, phone):
        raise IntakeError(429, "rate_limited", "Too many requests. Please try again later, or call your clinic.")
    conn.execute("INSERT INTO enquiry_hit (ip_hash, phone_e164) VALUES (%s, %s)", (ip_h, phone))

    # 3. Duplicate within 24 hours -> merge.
    window = timedelta(hours=get_settings().dedupe_hours)  # 24 h; the dev voice demo sets 0 to allow repeat tries
    existing = conn.execute(
        "SELECT * FROM lead WHERE phone_e164 = %s AND created_at > %s ORDER BY created_at DESC LIMIT 1 FOR UPDATE",
        (phone, now - window)).fetchone() if window else None
    if existing:
        return _merge(conn, existing, s, extra, ip_h, user_agent, now)

    # 4. New lead.
    earlier = conn.execute("SELECT id FROM lead WHERE phone_e164 = %s ORDER BY created_at DESC LIMIT 1", (phone,)).fetchone()
    lead = conn.execute(
        """INSERT INTO lead (public_ref, name, phone_e164, treatment, treatment_other_text, clinic_id, language,
                             contact_pref, scheduled_at, returning_of)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING *""",
        (new_public_ref(), extra["name"], phone, s.treatment, (s.treatment_other or None) if s.treatment == "other" else None,
         s.clinic_id, s.language, s.contact_pref, s.scheduled_at if s.contact_pref == "scheduled" else None,
         earlier["id"] if earlier else None)).fetchone()
    events.append(conn, "lead.created", lead_id=lead["id"], clinic_id=lead["clinic_id"], actor="public",
                  payload={"treatment": lead["treatment"], "contact_pref": lead["contact_pref"],
                           "language": lead["language"], "returning": earlier is not None})
    _record_consent(conn, lead, s, ip_h, user_agent)

    arm = experiment.assign(conn, lead)
    if arm == "assistant" and get_settings().voice_agent_enabled:
        from . import orchestrator
        orchestrator.enqueue_new_lead(conn, lead, now)  # first call within ~60 s inside the window (§4.4)
    else:
        if arm == "assistant":  # misconfiguration guard: never leave a lead with nobody to call it (EC-EXP-04)
            events.append(conn, "lead.fallback_to_staff", lead_id=lead["id"], clinic_id=lead["clinic_id"],
                          payload={"reason": "system_fallback"})
        events.status_changed(conn, lead, "awaiting_call", actor="system")

    body = {"ref": lead["public_ref"], "deduplicated": False, "clinic": extra["clinic"]["name"],
            "contact": _contact_info(lead, now)}
    _store_submission(conn, s.client_token, lead["id"], "created", body)
    return 201, body


def _merge(conn: Connection, lead: dict, s: Submission, extra: dict, ip_h, user_agent, now) -> tuple[int, dict]:
    changes: dict = {}
    if s.treatment != lead["treatment"] and s.treatment not in lead["extra_treatments"]:
        conn.execute("UPDATE lead SET extra_treatments = array_append(extra_treatments, %s) WHERE id = %s",
                     (s.treatment, lead["id"]))
        changes["added_treatment"] = s.treatment
    # EC-FORM-22: if nobody has reached them yet, the latest contact preference wins.
    if lead["first_reached_at"] is None and lead["status"] in ("new", "awaiting_call", "queued") and \
            (s.contact_pref != lead["contact_pref"] or s.scheduled_at != lead["scheduled_at"]):
        conn.execute("UPDATE lead SET contact_pref = %s, scheduled_at = %s WHERE id = %s",
                     (s.contact_pref, s.scheduled_at if s.contact_pref == "scheduled" else None, lead["id"]))
        lead["contact_pref"], lead["scheduled_at"] = s.contact_pref, s.scheduled_at
        changes["contact_pref"] = s.contact_pref
    _record_consent(conn, lead, s, ip_h, user_agent)
    events.append(conn, "lead.deduplicated", lead_id=lead["id"], clinic_id=lead["clinic_id"], actor="public",
                  payload=changes)
    # EC-FORM-13: renewed interest after "not interested" reopens the lead in its original arm.
    if lead["status"] == "not_interested":
        events.status_changed(conn, lead, "awaiting_call", actor="public", reason="renewed_interest")

    clinic_name = conn.execute("SELECT name FROM clinic WHERE id = %s", (lead["clinic_id"],)).fetchone()["name"]
    body = {"ref": lead["public_ref"], "deduplicated": True, "clinic": clinic_name,
            "already_in_progress": lead["first_reached_at"] is not None
                                   or lead["status"] not in ("new", "awaiting_call", "queued"),
            "contact": _contact_info(lead, now)}
    _store_submission(conn, s.client_token, lead["id"], "merged", body)
    return 200, body


def _record_consent(conn: Connection, lead: dict, s: Submission, ip_h, user_agent) -> None:
    conn.execute(
        "INSERT INTO consent (lead_id, disclosure_version, call_consent, whatsapp_consent, language, ip_hash, user_agent) "
        "VALUES (%s, %s, true, true, %s, %s, %s)",
        (lead["id"], s.disclosure_version, s.language, ip_h, (user_agent or "")[:300]))
    events.append(conn, "consent.recorded", lead_id=lead["id"], clinic_id=lead["clinic_id"], actor="public",
                  payload={"version": s.disclosure_version})


def _store_submission(conn: Connection, token, lead_id, kind: str, body: dict) -> None:
    try:
        with conn.transaction():
            conn.execute("INSERT INTO enquiry_submission (client_token, lead_id, kind, response) VALUES (%s, %s, %s, %s)",
                         (token, lead_id, kind, Jsonb(body)))
    except errors.UniqueViolation:  # pragma: no cover - guarded by the advisory lock
        raise IntakeError(409, "duplicate_submit", "This request was already received.")


def form_config(conn: Connection, language: str, now: datetime | None = None) -> dict:
    """What the public form needs: clinics, the wording per clinic, the calling window."""
    now = now or datetime.now(IST)
    s = get_settings()
    lang = language if language in ("en", "hi") else "en"
    rows = conn.execute(
        "SELECT c.id, c.name, c.is_pilot, COALESCE(e.assistant_share, 0) AS share FROM clinic c "
        "LEFT JOIN experiment_config e ON e.clinic_id = c.id ORDER BY c.is_pilot DESC, c.name").fetchall()
    clinics = []
    for r in rows:
        variant = disclosures.variant_for_share(float(r["share"]), r["is_pilot"])
        clinics.append({"id": r["id"], "name": r["name"],
                        "disclosure": disclosures.render(disclosures.CURRENT[(variant, lang)], s.caller_id)})
    if s.browser_calls:
        # Dev voice demo: list only clinics where the assistant calls (the others have no slots in demo data).
        clinics = [c for c in clinics if c["disclosure"]["variant"] == "assistant"] or clinics
    start, end, cutoff = calling_window.window()
    return {
        "language": lang,
        "default_disclosure": disclosures.render(disclosures.CURRENT[("team", lang)], s.caller_id),
        "clinics": clinics,
        "calling_window": {"start": start.strftime("%H:%M"), "end": end.strftime("%H:%M"),
                           "last_call_cutoff_min": cutoff, "open_now": calling_window.can_call_now(now)},
        "browser_calls": s.browser_calls,
        "now": now.isoformat(),
    }
