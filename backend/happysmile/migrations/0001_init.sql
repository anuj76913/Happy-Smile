-- HappySmile Phase 2 schema (architecture §11).
-- All timestamps are timestamptz (stored in UTC, shown in IST).

-- ---------------------------------------------------------------- helpers
CREATE FUNCTION hs_forbid_change() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  RAISE EXCEPTION '% is append-only: % is not allowed', TG_TABLE_NAME, TG_OP
    USING ERRCODE = 'restrict_violation';
END $$;

-- ---------------------------------------------------------------- reference data
CREATE TABLE clinic (
  id          text PRIMARY KEY,
  name        text NOT NULL,
  is_pilot    boolean NOT NULL DEFAULT false,
  created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE dentist (
  id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  clinic_id  text NOT NULL REFERENCES clinic(id),
  name       text NOT NULL,
  active     boolean NOT NULL DEFAULT true
);
CREATE INDEX dentist_clinic ON dentist(clinic_id);

CREATE TABLE staff (
  id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  username       text NOT NULL UNIQUE,
  display_name   text NOT NULL,
  role           text NOT NULL CHECK (role IN ('front_desk', 'manager', 'admin')),
  password_hash  text NOT NULL,
  active         boolean NOT NULL DEFAULT true,
  created_at     timestamptz NOT NULL DEFAULT now()
);

-- Front-desk staff see only their clinics; managers and admins see every clinic.
CREATE TABLE staff_clinic (
  staff_id   uuid NOT NULL REFERENCES staff(id) ON DELETE CASCADE,
  clinic_id  text NOT NULL REFERENCES clinic(id),
  PRIMARY KEY (staff_id, clinic_id)
);

CREATE TABLE staff_session (
  token_hash  text PRIMARY KEY,
  staff_id    uuid NOT NULL REFERENCES staff(id) ON DELETE CASCADE,
  created_at  timestamptz NOT NULL DEFAULT now(),
  expires_at  timestamptz NOT NULL,
  revoked_at  timestamptz
);

CREATE TABLE login_attempt (
  id          bigserial PRIMARY KEY,
  username    text NOT NULL,
  ok          boolean NOT NULL,
  at          timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX login_attempt_user_at ON login_attempt(username, at DESC);

-- ---------------------------------------------------------------- experiment (architecture §4.3, §10)
CREATE TABLE experiment_config (
  clinic_id        text PRIMARY KEY REFERENCES clinic(id),
  assistant_share  numeric(4, 3) NOT NULL DEFAULT 0 CHECK (assistant_share >= 0 AND assistant_share <= 1),
  salt             text NOT NULL,
  updated_at       timestamptz NOT NULL DEFAULT now(),
  updated_by       uuid REFERENCES staff(id)
);

-- Exact disclosure + consent wording shown on the form, versioned (EC-PRIV-02).
CREATE TABLE disclosure_version (
  version      text PRIMARY KEY,
  variant      text NOT NULL CHECK (variant IN ('team', 'mixed', 'assistant')),
  language     text NOT NULL CHECK (language IN ('en', 'hi')),
  disclosure   text NOT NULL,
  consent      text NOT NULL,
  sha256       text NOT NULL,
  created_at   timestamptz NOT NULL DEFAULT now(),
  UNIQUE (variant, language, sha256)
);
CREATE TRIGGER disclosure_version_immutable BEFORE UPDATE OR DELETE ON disclosure_version
  FOR EACH ROW EXECUTE FUNCTION hs_forbid_change();

-- ---------------------------------------------------------------- leads
CREATE TABLE lead (
  id                    uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  public_ref            text NOT NULL UNIQUE,
  name                 text NOT NULL CHECK (char_length(name) BETWEEN 1 AND 60),
  phone_e164            text NOT NULL CHECK (phone_e164 ~ '^\+91[6-9][0-9]{9}$'),
  treatment             text NOT NULL CHECK (treatment IN ('braces', 'whitening', 'implants', 'other')),
  treatment_other_text  text CHECK (treatment_other_text IS NULL OR char_length(treatment_other_text) <= 80),
  extra_treatments      text[] NOT NULL DEFAULT '{}',      -- added by merged duplicates (EC-FORM-12)
  clinic_id             text NOT NULL REFERENCES clinic(id),
  language              text NOT NULL CHECK (language IN ('en', 'hi')),
  contact_pref          text NOT NULL CHECK (contact_pref IN ('now', 'scheduled', 'whatsapp')),
  scheduled_at          timestamptz,
  arm                   text CHECK (arm IN ('assistant', 'control', 'not_in_pilot')),
  arm_assigned_at       timestamptz,
  status                text NOT NULL DEFAULT 'new' CHECK (status IN (
                          'new',
                          -- control arm / staff work
                          'awaiting_call', 'no_answer', 'follow_up', 'booked', 'not_interested', 'unreachable',
                          -- assistant arm (Phase 3+)
                          'queued', 'needs_you')),
  first_reached_at      timestamptz,
  claimed_by            uuid REFERENCES staff(id),
  claimed_at            timestamptz,
  follow_up_note        text,
  returning_of          uuid REFERENCES lead(id),          -- earlier lead from the same phone (EC-FORM-14)
  created_at            timestamptz NOT NULL DEFAULT now(),
  updated_at            timestamptz NOT NULL DEFAULT now(),
  CHECK (contact_pref <> 'scheduled' OR scheduled_at IS NOT NULL)
);
CREATE INDEX lead_phone_created ON lead(phone_e164, created_at DESC);
CREATE INDEX lead_clinic_status ON lead(clinic_id, status);
CREATE INDEX lead_created ON lead(created_at DESC);

-- Arm assignment is write-once (architecture §4.3).
CREATE FUNCTION lead_arm_write_once() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF OLD.arm IS NOT NULL AND NEW.arm IS DISTINCT FROM OLD.arm THEN
    RAISE EXCEPTION 'lead.arm is write-once (lead %)', OLD.id USING ERRCODE = 'restrict_violation';
  END IF;
  NEW.updated_at := now();
  RETURN NEW;
END $$;
CREATE TRIGGER lead_arm_write_once BEFORE UPDATE ON lead FOR EACH ROW EXECUTE FUNCTION lead_arm_write_once();

-- One row per form submission, keyed by the browser's token: a retried or double-clicked
-- submit returns the original result (EC-FORM-10/11). Duplicates merged into an existing
-- lead (EC-FORM-12) get their own row pointing at that lead.
CREATE TABLE enquiry_submission (
  client_token  uuid PRIMARY KEY,
  lead_id       uuid NOT NULL REFERENCES lead(id),
  kind          text NOT NULL CHECK (kind IN ('created', 'merged')),
  response      jsonb NOT NULL,
  created_at    timestamptz NOT NULL DEFAULT now()
);

-- Every submission's consent, immutable (architecture §4.2, §14).
-- Data-rights deletion (EC-PRIV-01) will need a privileged procedure added in a later phase.
CREATE TABLE consent (
  id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  lead_id             uuid NOT NULL REFERENCES lead(id),
  disclosure_version  text NOT NULL REFERENCES disclosure_version(version),
  call_consent        boolean NOT NULL,
  whatsapp_consent    boolean NOT NULL,
  language            text NOT NULL,
  ip_hash             text,
  user_agent          text,
  created_at          timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX consent_lead ON consent(lead_id);
CREATE TRIGGER consent_immutable BEFORE UPDATE OR DELETE ON consent
  FOR EACH ROW EXECUTE FUNCTION hs_forbid_change();

-- Rate limiting for the public form (EC-FORM-16), keyed by hashed IP and phone.
CREATE TABLE enquiry_hit (
  id          bigserial PRIMARY KEY,
  ip_hash     text,
  phone_e164  text,
  at          timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX enquiry_hit_ip ON enquiry_hit(ip_hash, at DESC);
CREATE INDEX enquiry_hit_phone ON enquiry_hit(phone_e164, at DESC);

-- ---------------------------------------------------------------- calls and conversations
CREATE TABLE call_attempt (
  id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  lead_id           uuid NOT NULL REFERENCES lead(id),
  attempt_no        int NOT NULL,
  made_by           text NOT NULL CHECK (made_by IN ('assistant', 'staff')),
  staff_id          uuid REFERENCES staff(id),
  outcome           text NOT NULL CHECK (outcome IN ('answered', 'no_answer', 'busy', 'voicemail', 'invalid', 'failed')),
  occurred_at       timestamptz NOT NULL DEFAULT now(),
  provider_call_id  text UNIQUE,
  UNIQUE (lead_id, attempt_no)
);

CREATE TABLE conversation (  -- filled by the voice agent from Phase 3
  call_attempt_id     uuid PRIMARY KEY REFERENCES call_attempt(id),
  recording_uri       text,
  transcript_uri      text,
  summary             text[],
  captured            jsonb,
  stt_confidence_avg  numeric(4, 3),
  final_stage         int
);

-- ---------------------------------------------------------------- handovers (Phase 3+)
CREATE TABLE handover (
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  lead_id      uuid NOT NULL REFERENCES lead(id),
  reason_tags  text[] NOT NULL,
  urgency      text NOT NULL CHECK (urgency IN ('urgent', 'normal')),
  sla_due_at   timestamptz NOT NULL,
  created_at   timestamptz NOT NULL DEFAULT now(),
  claimed_by   uuid REFERENCES staff(id),
  claimed_at   timestamptz,
  resolved_at  timestamptz,
  resolution   text
);

CREATE TABLE handover_feedback (
  handover_id  uuid NOT NULL REFERENCES handover(id),
  staff_id     uuid NOT NULL REFERENCES staff(id),
  is_correct   boolean NOT NULL,
  comment      text,
  created_at   timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (handover_id, staff_id)
);

-- ---------------------------------------------------------------- pilot slot store and bookings (ADR-001 option B)
CREATE TABLE slot (
  id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  clinic_id        text NOT NULL REFERENCES clinic(id),
  dentist_id       uuid NOT NULL REFERENCES dentist(id),
  start_at         timestamptz NOT NULL,
  duration_min     int NOT NULL CHECK (duration_min BETWEEN 10 AND 120),
  status           text NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'held', 'booked', 'blocked')),
  hold_expires_at  timestamptz,
  created_by       uuid REFERENCES staff(id),
  created_at       timestamptz NOT NULL DEFAULT now(),
  UNIQUE (dentist_id, start_at)
);
CREATE INDEX slot_clinic_start ON slot(clinic_id, start_at);

CREATE TABLE slot_refresh (  -- when each clinic's slot list was last maintained (EC-BOOK-11)
  clinic_id     text PRIMARY KEY REFERENCES clinic(id),
  refreshed_at  timestamptz NOT NULL,
  refreshed_by  uuid REFERENCES staff(id)
);

CREATE TABLE booking (
  id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  lead_id          uuid NOT NULL REFERENCES lead(id),
  slot_id          uuid NOT NULL REFERENCES slot(id),
  clinic_id        text NOT NULL REFERENCES clinic(id),
  dentist_id       uuid NOT NULL REFERENCES dentist(id),
  start_at         timestamptz NOT NULL,
  created_by       text NOT NULL CHECK (created_by IN ('assistant', 'staff')),
  created_by_staff uuid REFERENCES staff(id),
  review_status    text NOT NULL CHECK (review_status IN ('pending', 'approved', 'changed', 'cancelled')),
  whatsapp_status  text CHECK (whatsapp_status IN ('sent', 'delivered', 'read', 'failed')),
  attended         boolean,
  status           text NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'cancelled')),
  created_at       timestamptz NOT NULL DEFAULT now()
);
-- One active booking per slot: the database refuses double-booking (EC-BOOK-02).
CREATE UNIQUE INDEX booking_one_active_per_slot ON booking(slot_id) WHERE status = 'active';

-- ---------------------------------------------------------------- messaging (Phase 4)
CREATE TABLE message (
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  lead_id      uuid NOT NULL REFERENCES lead(id),
  direction    text NOT NULL CHECK (direction IN ('outbound', 'inbound')),
  template_id  text,
  body         text,
  status       text,
  created_at   timestamptz NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------- event log and audit (architecture §4.12, §13)
CREATE TABLE event (
  id           bigserial PRIMARY KEY,
  lead_id      uuid REFERENCES lead(id),
  clinic_id    text REFERENCES clinic(id),
  type         text NOT NULL,
  payload      jsonb NOT NULL DEFAULT '{}',
  actor        text NOT NULL,             -- 'public', 'system', 'assistant' or 'staff:<uuid>'
  occurred_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX event_lead ON event(lead_id, id);
CREATE INDEX event_type_time ON event(type, occurred_at);
CREATE INDEX event_clinic_id ON event(clinic_id, id);
CREATE TRIGGER event_append_only BEFORE UPDATE OR DELETE ON event
  FOR EACH ROW EXECUTE FUNCTION hs_forbid_change();

CREATE TABLE audit_log (
  id         bigserial PRIMARY KEY,
  staff_id   uuid REFERENCES staff(id),
  action     text NOT NULL,
  lead_id    uuid REFERENCES lead(id),
  detail     jsonb NOT NULL DEFAULT '{}',
  ip_hash    text,
  at         timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX audit_lead ON audit_log(lead_id, at DESC);
CREATE TRIGGER audit_append_only BEFORE UPDATE OR DELETE ON audit_log
  FOR EACH ROW EXECUTE FUNCTION hs_forbid_change();
