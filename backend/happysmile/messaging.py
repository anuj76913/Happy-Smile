"""WhatsApp messaging (architecture §4.8; plan P4-03; edge cases EC-WA-01..08).

- Approved templates only (phase0/long-lead/whatsapp-templates.md). No free text in v1.
- Durable outbox in `message`: queued -> sending -> sent -> delivered -> read | failed.
  Dedupe keys stop double sends (EC-WA-07). Consent and suppression are re-checked
  right before sending (EC-WA-06/08).
- Sent only to assistant-arm leads: the control arm keeps today's process, so the
  comparison stays fair (implementation-plan §10).
- Inbound: STOP -> suppression + confirmation; any other reply -> Needs you.
- Providers: SimWhatsApp (dev/tests) and MetaCloudWhatsApp (Cloud API). A BSP adapter
  fits the same interface.
"""

from __future__ import annotations

import hashlib
import hmac
import re
import uuid
from datetime import datetime, timedelta, timezone

import httpx
from psycopg import Connection
from psycopg.types.json import Jsonb

from . import events
from .config import IST, get_settings

# Bodies mirror the submitted templates; params fill {{1}}, {{2}}, ... in order.
TEMPLATES: dict[str, dict] = {
    "enquiry_ack_v1": {"params": ["name", "treatment", "clinic", "when", "caller_id"], "body": {
        "en": "Hi {{1}}, thank you for your enquiry about {{2}} at HappySmile {{3}}. Our virtual assistant will call you {{4}} from {{5}}. Reply STOP if you do not want to be contacted.",
        "hi": "नमस्ते {{1}} जी, HappySmile {{3}} में {{2}} के बारे में पूछताछ के लिए धन्यवाद। हमारी वर्चुअल असिस्टेंट आपको {{4}} {{5}} से कॉल करेगी। संपर्क नहीं चाहते तो STOP लिखकर भेजें।"}},
    "whatsapp_hello_v1": {"params": ["name", "treatment", "clinic"], "body": {
        "en": "Hi {{1}}, thank you for your enquiry about {{2}} at HappySmile {{3}}. Our team will reply here during clinic hours, 9 am to 9 pm. Reply STOP if you do not want to be contacted.",
        "hi": "नमस्ते {{1}} जी, HappySmile {{3}} में {{2}} के बारे में पूछताछ के लिए धन्यवाद। हमारी टीम क्लिनिक के समय, सुबह 9 से रात 9 बजे, यहीं जवाब देगी। संपर्क नहीं चाहते तो STOP लिखें।"}},
    "booking_confirm_v1": {"params": ["date", "time", "clinic", "dentist", "address"], "body": {
        "en": "Your consultation is booked.\nDate: {{1}}\nTime: {{2}}\nClinic: HappySmile {{3}}\nDentist: {{4}}\nAddress: {{5}}\nTo change the time, reply to this message. Reply STOP to stop messages.",
        "hi": "आपकी कंसल्टेशन बुक हो गई है।\nतारीख: {{1}}\nसमय: {{2}}\nक्लिनिक: HappySmile {{3}}\nडेंटिस्ट: {{4}}\nपता: {{5}}\nसमय बदलने के लिए इस मैसेज का जवाब दें। मैसेज बंद करने के लिए STOP लिखें।"}},
    "no_answer_v1": {"params": ["name", "treatment"], "body": {
        "en": "Hi {{1}}, we tried calling you about your {{2}} enquiry but could not reach you. Reply here with a good time to call, and our team will get back to you. Reply STOP if you do not want to be contacted.",
        "hi": "नमस्ते {{1}} जी, हमने आपकी {{2}} संबंधी पूछताछ के लिए कॉल किया, पर बात नहीं हो पाई। कॉल के लिए सही समय यहाँ लिखकर भेजें, हमारी टीम आपसे संपर्क करेगी। संपर्क नहीं चाहते तो STOP लिखें।"}},
    "call_reminder_v1": {"params": ["name", "time", "caller_id"], "body": {
        "en": "Hi {{1}}, as you asked, HappySmile's virtual assistant will call you at {{2}} from {{3}}. Reply CHANGE to pick another time, or STOP to cancel.",
        "hi": "नमस्ते {{1}} जी, आपके कहे अनुसार HappySmile की वर्चुअल असिस्टेंट आपको {{2}} बजे {{3}} से कॉल करेगी। समय बदलने के लिए CHANGE और रद्द करने के लिए STOP लिखें।"}},
    "booking_update_v1": {"params": ["change", "details"], "body": {
        "en": "Update on your HappySmile consultation: {{1}}. New details: {{2}}. Reply to this message if you have any questions.",
        "hi": "आपकी HappySmile कंसल्टेशन के बारे में अपडेट: {{1}}। नई जानकारी: {{2}}। कोई सवाल हो तो इस मैसेज का जवाब दें।"}},
    # Phase 6: reminders and no-show recovery (need Meta approval before use)
    "appointment_reminder_v1": {"params": ["name", "when", "clinic", "address"], "body": {
        "en": "Hi {{1}}, a reminder of your HappySmile consultation {{2}} at our {{3}} clinic, {{4}}. To change the time, reply to this message. Reply STOP to stop messages.",
        "hi": "नमस्ते {{1}} जी, याद दिला दें कि आपकी HappySmile कंसल्टेशन {{2}} हमारे {{3}} क्लिनिक ({{4}}) में है। समय बदलने के लिए इस मैसेज का जवाब दें। मैसेज बंद करने के लिए STOP लिखें।"}},
    "no_show_v1": {"params": ["name", "clinic"], "body": {
        "en": "Hi {{1}}, we missed you at HappySmile {{2}} today. Reply here if you would like a new time, and our team will help. Reply STOP to stop messages.",
        "hi": "नमस्ते {{1}} जी, आज HappySmile {{2}} में आपसे मुलाकात नहीं हो पाई। नया समय चाहिए तो यहाँ जवाब दें, हमारी टीम मदद करेगी। मैसेज बंद करने के लिए STOP लिखें।"}},
    "opt_out_confirm_v1": {"params": [], "body": {
        "en": "You will not receive further calls or messages from HappySmile about this enquiry. If you change your mind, you can request a call on our website at any time.",
        "hi": "अब आपको इस पूछताछ के बारे में HappySmile से कोई कॉल या मैसेज नहीं आएगा। अगर आप फिर से बात करना चाहें, तो कभी भी हमारी वेबसाइट पर कॉल का अनुरोध कर सकते हैं।"}},
}
TREATMENT_WORDS = {"braces": {"en": "braces", "hi": "ब्रेसेस"}, "whitening": {"en": "teeth whitening", "hi": "दाँतों की सफ़ेदी"},
                   "implants": {"en": "implants", "hi": "इम्प्लांट"}, "other": {"en": "dental treatment", "hi": "दाँतों के इलाज"}}
STOP_WORDS = re.compile(r"^\s*(stop|unsubscribe|band karo|bandh karo|mat bhejo|बंद करो|बंद)\b", re.IGNORECASE)
STATUS_ORDER = {"queued": 0, "sending": 1, "sent": 2, "delivered": 3, "read": 4}
MAX_ATTEMPTS = 3


def render(template: str, lang: str, params: list[str]) -> str:
    body = TEMPLATES[template]["body"][lang if lang in ("en", "hi") else "en"]
    for i, p in enumerate(params, 1):
        body = body.replace("{{%d}}" % i, str(p))
    return body


def _clean(p: str) -> str:
    # WhatsApp template parameters can't contain newlines, tabs or 4+ spaces.
    return re.sub(r"\s+", " ", str(p)).strip()[:200]


# ---------------------------------------------------------------- providers
class SimWhatsApp:
    name = "sim"

    def __init__(self):
        self.sent: list[dict] = []
        self.fail_next = False

    def send_template(self, to_e164: str, template: str, lang: str, params: list[str]) -> str:
        if self.fail_next:
            self.fail_next = False
            raise RuntimeError("simulated send failure")
        mid = f"wamid.sim-{uuid.uuid4()}"
        self.sent.append({"to": to_e164, "template": template, "lang": lang, "params": params, "id": mid})
        return mid


class MetaCloudWhatsApp:
    """WhatsApp Business Cloud API: POST /{phone_number_id}/messages with a template payload."""

    name = "meta"

    def __init__(self, transport: httpx.BaseTransport | None = None):
        s = get_settings()
        self.s = s
        self._client = httpx.Client(base_url=f"https://graph.facebook.com/{s.whatsapp_graph_version}", transport=transport,
                                    headers={"Authorization": f"Bearer {s.whatsapp_token}"}, timeout=10)

    def send_template(self, to_e164: str, template: str, lang: str, params: list[str]) -> str:
        body = {"messaging_product": "whatsapp", "to": to_e164.lstrip("+"), "type": "template",
                "template": {"name": template, "language": {"code": lang},
                             "components": ([{"type": "body", "parameters": [{"type": "text", "text": p} for p in params]}]
                                            if params else [])}}
        r = self._client.post(f"/{self.s.whatsapp_phone_number_id}/messages", json=body)
        r.raise_for_status()
        return r.json()["messages"][0]["id"]


def verify_meta_signature(raw: bytes, header: str | None) -> bool:
    secret = get_settings().whatsapp_app_secret
    if not secret or not header or not header.startswith("sha256="):
        return False
    expected = hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, header[7:])


def parse_meta_webhook(payload: dict) -> list[dict]:
    """Normalise a Cloud API webhook into status updates and inbound messages."""
    out: list[dict] = []
    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {})
            for st in value.get("statuses", []):
                err = (st.get("errors") or [{}])[0]
                out.append({"kind": "status", "event_id": f"st:{st.get('id')}:{st.get('status')}", "message_id": st.get("id"),
                            "status": st.get("status"), "error": err.get("title") or err.get("message")})
            for m in value.get("messages", []):
                text = (m.get("text") or {}).get("body") or (m.get("button") or {}).get("text") \
                    or ((m.get("interactive") or {}).get("button_reply") or {}).get("title") or f"[{m.get('type')}]"
                out.append({"kind": "inbound", "event_id": f"in:{m.get('id')}", "message_id": m.get("id"),
                            "from": "+" + str(m.get("from", "")).lstrip("+"), "text": text})
    return out


_provider = None


def provider():
    global _provider
    if _provider is None:
        name = get_settings().whatsapp_provider
        _provider = SimWhatsApp() if name == "sim" else MetaCloudWhatsApp() if name == "meta" else None
        if _provider is None:
            raise RuntimeError(f"Unknown WHATSAPP_PROVIDER {name!r}")
    return _provider


def set_provider(p) -> None:  # tests
    global _provider
    _provider = p


# ---------------------------------------------------------------- queueing
def _consented(conn: Connection, lead_id) -> bool:
    c = conn.execute("SELECT whatsapp_consent FROM consent WHERE lead_id = %s ORDER BY created_at DESC LIMIT 1", (lead_id,)).fetchone()
    return bool(c and c["whatsapp_consent"])


def _suppressed(conn: Connection, phone: str) -> bool:
    return conn.execute("SELECT 1 FROM suppression WHERE phone_e164 = %s", (phone,)).fetchone() is not None


def enqueue(conn: Connection, lead: dict, template: str, params: dict, *, due_at: datetime | None = None,
            dedupe_key: str | None = "once", booking_id=None) -> bool:
    """Queue a template message. Returns False if it can't be sent (no consent, suppressed, duplicate)."""
    if template != "opt_out_confirm_v1" and (not _consented(conn, lead["id"]) or _suppressed(conn, lead["phone_e164"])):
        return False
    lang = lead["language"] if lead["language"] in ("en", "hi") else "en"
    values = [_clean(params[k]) for k in TEMPLATES[template]["params"]]
    row = conn.execute(
        "INSERT INTO message (lead_id, direction, template_id, body, status, language, params, dedupe_key, due_at, booking_id) "
        "VALUES (%s, 'outbound', %s, %s, 'queued', %s, %s, %s, %s, %s) "
        "ON CONFLICT (lead_id, template_id, dedupe_key) WHERE direction = 'outbound' AND dedupe_key IS NOT NULL DO NOTHING "
        "RETURNING id",
        (lead["id"], template, render(template, lang, values), lang, Jsonb(values), dedupe_key,
         due_at or datetime.now(timezone.utc), booking_id)).fetchone()
    if row:
        events.append(conn, "message.queued", lead_id=lead["id"], clinic_id=lead["clinic_id"],
                      payload={"template": template, "due_at": (due_at or datetime.now(timezone.utc)).isoformat()})
    return row is not None


def cancel_pending(conn: Connection, lead_id, template: str | None = None) -> None:
    conn.execute("UPDATE message SET status = 'cancelled', updated_at = now() WHERE lead_id = %s AND status = 'queued'"
                 + (" AND template_id = %s" if template else ""), (lead_id, template) if template else (lead_id,))


# Helpers that build parameters in the patient's language.
def treatment_word(lead: dict) -> str:
    return TREATMENT_WORDS.get(lead["treatment"], TREATMENT_WORDS["other"])[lead["language"] if lead["language"] in ("en", "hi") else "en"]


def first_name(lead: dict) -> str:
    return lead["name"].split()[0]


def fmt_date(dt: datetime, lang: str) -> str:
    local = dt.astimezone(IST)
    return local.strftime("%a %d %b %Y").replace(" 0", " ") if lang != "hi" else local.strftime("%d/%m/%Y")


def fmt_time(dt: datetime) -> str:
    local = dt.astimezone(IST)
    return f"{local.hour % 12 or 12}:{local.minute:02d} {'am' if local.hour < 12 else 'pm'}"


def queue_booking_confirmation(conn: Connection, lead: dict, booking_id) -> bool:
    b = conn.execute("SELECT b.start_at, d.name AS dentist, c.name AS clinic, coalesce(c.address, c.name) AS address "
                     "FROM booking b JOIN dentist d ON d.id = b.dentist_id JOIN clinic c ON c.id = b.clinic_id WHERE b.id = %s",
                     (booking_id,)).fetchone()
    lang = lead["language"]
    ok = enqueue(conn, lead, "booking_confirm_v1", {"date": fmt_date(b["start_at"], lang), "time": fmt_time(b["start_at"]),
                                                     "clinic": b["clinic"], "dentist": b["dentist"], "address": b["address"]},
                 dedupe_key=f"booking:{booking_id}", booking_id=booking_id)
    if ok:
        conn.execute("UPDATE booking SET whatsapp_status = NULL WHERE id = %s", (booking_id,))
        queue_appointment_reminder(conn, lead, booking_id)
    return ok


def queue_appointment_reminder(conn: Connection, lead: dict, booking_id) -> bool:
    """Reminder 24 h before (or 3 h before if booked for the next day), to protect attendance (Phase 6)."""
    b = conn.execute("SELECT b.start_at, c.name AS clinic, coalesce(c.address, c.name) AS address FROM booking b "
                     "JOIN clinic c ON c.id = b.clinic_id WHERE b.id = %s", (booking_id,)).fetchone()
    now = datetime.now(timezone.utc)
    due = b["start_at"] - timedelta(hours=24)
    if due < now + timedelta(minutes=30):
        due = b["start_at"] - timedelta(hours=3)
    if due < now + timedelta(minutes=30):
        return False  # too soon for a useful reminder; the confirmation covers it
    lang = lead["language"]
    when = (f"{fmt_date(b['start_at'], lang)}, {fmt_time(b['start_at'])}")
    return enqueue(conn, lead, "appointment_reminder_v1", {"name": first_name(lead), "when": when, "clinic": b["clinic"],
                   "address": b["address"]}, due_at=due, dedupe_key=f"reminder:{booking_id}:{b['start_at'].isoformat()}",
                   booking_id=booking_id)


def queue_no_show(conn: Connection, lead: dict, booking_id) -> bool:
    clinic = conn.execute("SELECT c.name FROM booking b JOIN clinic c ON c.id = b.clinic_id WHERE b.id = %s", (booking_id,)).fetchone()["name"]
    return enqueue(conn, lead, "no_show_v1", {"name": first_name(lead), "clinic": clinic}, dedupe_key=f"noshow:{booking_id}",
                   booking_id=booking_id)


def queue_booking_update(conn: Connection, lead: dict, booking_id, change: str, details: str) -> bool:
    return enqueue(conn, lead, "booking_update_v1", {"change": change, "details": details},
                   dedupe_key=f"update:{booking_id}:{uuid.uuid4().hex[:8]}", booking_id=booking_id)


# ---------------------------------------------------------------- sending
def dispatch_due(limit: int = 20) -> list[str]:
    from .db import tx
    with tx() as conn:
        ids = [r["id"] for r in conn.execute(
            "UPDATE message SET status = 'sending', attempts = attempts + 1, updated_at = now() WHERE id IN ("
            "  SELECT id FROM message WHERE status = 'queued' AND due_at <= now() ORDER BY due_at LIMIT %s FOR UPDATE SKIP LOCKED"
            ") RETURNING id", (limit,))]
    results = []
    for mid in ids:
        results.append(_send_one(mid))
    return results


def _send_one(message_id) -> str:
    from .db import tx
    with tx() as conn:
        m = conn.execute("SELECT m.*, l.phone_e164 FROM message m JOIN lead l ON l.id = m.lead_id WHERE m.id = %s", (message_id,)).fetchone()
        if m["template_id"] != "opt_out_confirm_v1" and _suppressed(conn, m["phone_e164"]):
            conn.execute("UPDATE message SET status = 'cancelled', error = 'suppressed' WHERE id = %s", (message_id,))
            return "cancelled"
    p = provider()
    try:
        pid = p.send_template(m["phone_e164"], m["template_id"], m["language"], list(m["params"]))
    except Exception as e:
        with tx() as conn:
            if m["attempts"] < MAX_ATTEMPTS and not isinstance(e, httpx.HTTPStatusError):
                conn.execute("UPDATE message SET status = 'queued', due_at = now() + interval '1 minute', error = %s WHERE id = %s",
                             (type(e).__name__, message_id))
                return "retry"
            conn.execute("UPDATE message SET status = 'failed', error = %s, updated_at = now() WHERE id = %s",
                         (str(e)[:200], message_id))
            _on_failed(conn, m)
        return "failed"
    with tx() as conn:
        conn.execute("UPDATE message SET status = 'sent', provider = %s, provider_message_id = %s, error = NULL, updated_at = now() "
                     "WHERE id = %s", (p.name, pid, message_id))
        if m["booking_id"]:
            conn.execute("UPDATE booking SET whatsapp_status = 'sent' WHERE id = %s", (m["booking_id"],))
        lead = conn.execute("SELECT id, clinic_id FROM lead WHERE id = %s", (m["lead_id"],)).fetchone()
        events.append(conn, "message.sent", lead_id=lead["id"], clinic_id=lead["clinic_id"], payload={"template": m["template_id"]})
    return "sent"


def _on_failed(conn: Connection, m: dict) -> None:
    """A message that matters didn't arrive: a person follows up (EC-WA-01/02; SMS fallback not adopted yet)."""
    from . import handovers
    lead = conn.execute("SELECT * FROM lead WHERE id = %s FOR UPDATE", (m["lead_id"],)).fetchone()
    events.append(conn, "message.failed", lead_id=lead["id"], clinic_id=lead["clinic_id"],
                  payload={"template": m["template_id"], "error": (m.get("error") or "")[:100]})
    if m["booking_id"]:
        conn.execute("UPDATE booking SET whatsapp_status = 'failed' WHERE id = %s", (m["booking_id"],))
    note = {"booking_confirm_v1": "WhatsApp confirmation not delivered: call to confirm the booking",
            "booking_update_v1": "WhatsApp update not delivered: call to tell them about the change",
            "no_answer_v1": "Not reached by phone and WhatsApp failed",
            "whatsapp_hello_v1": "Prefers WhatsApp but the message failed: call instead"}.get(m["template_id"])
    if note and lead["status"] not in ("not_interested", "unreachable"):
        handovers.create(conn, lead, ["whatsapp_failed"], "normal", actor="system", note=note)


# ---------------------------------------------------------------- webhooks
def handle_status(conn: Connection, provider_message_id: str, status: str, error: str | None) -> None:
    m = conn.execute("SELECT * FROM message WHERE provider_message_id = %s FOR UPDATE", (provider_message_id,)).fetchone()
    if not m or m["status"] in ("failed", "cancelled"):
        return
    if status == "failed":
        conn.execute("UPDATE message SET status = 'failed', error = %s, updated_at = now() WHERE id = %s", (error, m["id"]))
        _on_failed(conn, {**m, "error": error})
        return
    if STATUS_ORDER.get(status, -1) <= STATUS_ORDER.get(m["status"], -1):
        return  # out-of-order or duplicate: statuses only move forward
    conn.execute("UPDATE message SET status = %s, updated_at = now() WHERE id = %s", (status, m["id"]))
    if m["booking_id"]:
        conn.execute("UPDATE booking SET whatsapp_status = %s WHERE id = %s", (status, m["booking_id"]))


def handle_inbound(conn: Connection, from_e164: str, text: str, provider_message_id: str) -> str:
    from . import handovers
    lead = conn.execute("SELECT * FROM lead WHERE phone_e164 = %s AND created_at > now() - interval '30 days' "
                        "ORDER BY created_at DESC LIMIT 1 FOR UPDATE", (from_e164,)).fetchone()
    if lead is None:
        events.append(conn, "message.inbound_unknown", payload={"chars": len(text or "")})
        return "unknown"
    conn.execute("INSERT INTO message (lead_id, direction, body, status, provider_message_id, provider) "
                 "VALUES (%s, 'inbound', %s, 'received', %s, %s) ON CONFLICT (provider_message_id) DO NOTHING",
                 (lead["id"], (text or "")[:1000], provider_message_id, get_settings().whatsapp_provider))
    events.append(conn, "message.received", lead_id=lead["id"], clinic_id=lead["clinic_id"], actor="public",
                  payload={"chars": len(text or "")})
    if STOP_WORDS.search(text or ""):  # EC-WA-06: stop all contact, confirm once
        conn.execute("INSERT INTO suppression (phone_e164, reason, lead_id) VALUES (%s, 'whatsapp_stop', %s) ON CONFLICT DO NOTHING",
                     (lead["phone_e164"], lead["id"]))
        conn.execute("UPDATE call_job SET status = 'cancelled' WHERE lead_id = %s AND status = 'pending'", (lead["id"],))
        cancel_pending(conn, lead["id"])
        enqueue(conn, lead, "opt_out_confirm_v1", {}, dedupe_key="optout")
        handovers.resolve(conn, lead["id"], "opted_out", "public")
        if lead["status"] not in ("booked", "not_interested", "unreachable"):
            events.status_changed(conn, lead, "not_interested", actor="public", reason="whatsapp_stop")
        return "stopped"
    # Any other reply needs a person (no WhatsApp bot in v1, architecture §1).
    handovers.create(conn, lead, ["whatsapp_reply"], "normal", actor="public", note=f"WhatsApp: {(text or '')[:200]}")
    if lead["status"] == "queued":  # they replied instead of waiting for a call: let a person handle it
        conn.execute("UPDATE call_job SET status = 'cancelled' WHERE lead_id = %s AND status = 'pending'", (lead["id"],))
    return "needs_you"


def expire_unanswered(conn: Connection, hours: int = 48) -> int:
    """No reply 48 h after the no-answer message -> unreachable (architecture §5)."""
    rows = conn.execute("SELECT * FROM lead WHERE status = 'whatsapp_sent' AND whatsapp_sent_at < now() - %s FOR UPDATE",
                        (timedelta(hours=hours),)).fetchall()
    for lead in rows:
        events.status_changed(conn, lead, "unreachable", actor="system", reason="no_reply_48h")
    return len(rows)
