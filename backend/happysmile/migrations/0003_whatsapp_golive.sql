-- Phase 4: WhatsApp messaging, no-answer flow, ops alerts, kill switch, go-live gates.

-- Lead can be waiting on a WhatsApp reply after unanswered calls (architecture §5).
ALTER TABLE lead DROP CONSTRAINT lead_status_check;
ALTER TABLE lead ADD CONSTRAINT lead_status_check CHECK (status IN (
  'new', 'awaiting_call', 'no_answer', 'follow_up', 'booked', 'not_interested', 'unreachable',
  'queued', 'needs_you', 'whatsapp_sent'));
ALTER TABLE lead ADD COLUMN whatsapp_sent_at timestamptz;

-- Clinic address for booking confirmations (fictional values in the seed).
ALTER TABLE clinic ADD COLUMN address text;

-- Outbound messages are a durable outbox; inbound replies are stored here too (architecture §4.8).
ALTER TABLE message
  ADD COLUMN language text,
  ADD COLUMN params jsonb NOT NULL DEFAULT '[]',
  ADD COLUMN dedupe_key text,
  ADD COLUMN due_at timestamptz,
  ADD COLUMN attempts int NOT NULL DEFAULT 0,
  ADD COLUMN provider text,
  ADD COLUMN provider_message_id text UNIQUE,
  ADD COLUMN error text,
  ADD COLUMN booking_id uuid REFERENCES booking(id),
  ADD COLUMN updated_at timestamptz NOT NULL DEFAULT now();
ALTER TABLE message ADD CONSTRAINT message_status_check CHECK (status IS NULL OR status IN
  ('queued', 'sending', 'sent', 'delivered', 'read', 'failed', 'received', 'cancelled'));
CREATE UNIQUE INDEX message_dedupe ON message(lead_id, template_id, dedupe_key)
  WHERE direction = 'outbound' AND dedupe_key IS NOT NULL;     -- never send the same thing twice (EC-WA-07)
CREATE INDEX message_due ON message(due_at) WHERE status = 'queued';
CREATE INDEX message_lead ON message(lead_id, created_at);

-- Webhook idempotency (EC-CALL-11 for messaging).
CREATE TABLE webhook_event (
  provider     text NOT NULL,
  event_id     text NOT NULL,
  received_at  timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (provider, event_id)
);

-- Kill switch and ramp (implementation-plan §12-13).
ALTER TABLE experiment_config
  ADD COLUMN booking_paused boolean NOT NULL DEFAULT false,
  ADD COLUMN live_since timestamptz;

-- Non-technical go-live items signed off by a named person (gate G2).
CREATE TABLE golive_attestation (
  item         text PRIMARY KEY,
  attested_by  uuid NOT NULL REFERENCES staff(id),
  note         text,
  attested_at  timestamptz NOT NULL DEFAULT now()
);

-- Operational alerts (architecture §15.2; plan P4-08).
CREATE TABLE alert (
  id           bigserial PRIMARY KEY,
  key          text NOT NULL,
  severity     text NOT NULL CHECK (severity IN ('critical', 'warning')),
  clinic_id    text REFERENCES clinic(id),
  message      text NOT NULL,
  opened_at    timestamptz NOT NULL DEFAULT now(),
  resolved_at  timestamptz,
  notified_at  timestamptz
);
CREATE UNIQUE INDEX alert_one_open ON alert(key, coalesce(clinic_id, '')) WHERE resolved_at IS NULL;
