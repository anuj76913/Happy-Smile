-- Phase 5: call reviews, rules change log, attendance, pilot decision (plan P5-02..P5-05; architecture §15.3).

-- Daily sampled call reviews against the §15.3 checklist.
CREATE TABLE call_review (
  id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  call_attempt_id  uuid NOT NULL REFERENCES call_attempt(id),
  reviewer_id      uuid NOT NULL REFERENCES staff(id),
  disclosure_ok    boolean NOT NULL,
  booking_ok       boolean,            -- null = no booking on this call
  handover_ok      boolean,            -- null = no handover on this call
  tone_ok          boolean NOT NULL,
  issue_tags       text[] NOT NULL DEFAULT '{}',
  notes            text,
  created_at       timestamptz NOT NULL DEFAULT now(),
  UNIQUE (call_attempt_id, reviewer_id)
);

-- Every change to lines, keywords, prompts or thresholds, with the version it ships in (§15.3).
CREATE TABLE rules_change (
  id           bigserial PRIMARY KEY,
  version      text NOT NULL,
  area         text NOT NULL CHECK (area IN ('lines', 'keywords', 'understanding', 'prompt', 'thresholds', 'other')),
  description  text NOT NULL,
  reason       text,
  author_id    uuid REFERENCES staff(id),
  created_at   timestamptz NOT NULL DEFAULT now()
);
CREATE TRIGGER rules_change_append_only BEFORE UPDATE OR DELETE ON rules_change
  FOR EACH ROW EXECUTE FUNCTION hs_forbid_change();

-- Attendance for both arms (plan P5-04, EC-POST-07).
ALTER TABLE booking ADD COLUMN attendance_recorded_by uuid REFERENCES staff(id),
                    ADD COLUMN attendance_recorded_at timestamptz;

-- Gate G4: the recorded pilot decision, with the readout it was based on.
CREATE TABLE pilot_decision (
  id            bigserial PRIMARY KEY,
  decision      text NOT NULL CHECK (decision IN ('scale', 'extend', 'fix_first', 'stop_or_redesign')),
  recommended   text NOT NULL,
  notes         text NOT NULL,
  decided_by    uuid NOT NULL REFERENCES staff(id),
  readout       jsonb NOT NULL,
  decided_at    timestamptz NOT NULL DEFAULT now()
);
CREATE TRIGGER pilot_decision_append_only BEFORE UPDATE OR DELETE ON pilot_decision
  FOR EACH ROW EXECUTE FUNCTION hs_forbid_change();
