-- Phase 6: rollout waves, permanent control, calendar adapters, live transfer, reminders and no-shows.
-- Note: clinic.is_pilot now means "in the programme" (pilot clinics plus clinics activated in later waves).

ALTER TABLE clinic
  ADD COLUMN rollout_wave int,
  ADD COLUMN activated_at timestamptz,
  ADD COLUMN calendar_adapter text NOT NULL DEFAULT 'local' CHECK (calendar_adapter IN ('local', 'http')),
  ADD COLUMN calendar_synced_at timestamptz;

-- Wave 1 = the pilot clinics; the rest in waves of three (editable by admins).
UPDATE clinic SET rollout_wave = 1, activated_at = created_at WHERE is_pilot;
UPDATE clinic SET rollout_wave = 2 WHERE id IN ('maple', 'palm', 'banyan');
UPDATE clinic SET rollout_wave = 3 WHERE id IN ('cedar', 'harbour', 'orchid');
UPDATE clinic SET rollout_wave = 4 WHERE id IN ('sunrise', 'willow', 'lakegate');

-- Per-clinic onboarding items signed off before activation.
CREATE TABLE clinic_onboarding (
  clinic_id  text NOT NULL REFERENCES clinic(id),
  item       text NOT NULL,
  done_by    uuid NOT NULL REFERENCES staff(id),
  note       text,
  done_at    timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (clinic_id, item)
);

ALTER TABLE experiment_config ADD COLUMN steady_since timestamptz;  -- reached the steady-state share

-- External calendar references (calendar adapter).
ALTER TABLE dentist ADD COLUMN external_ref text;
CREATE UNIQUE INDEX dentist_external ON dentist(clinic_id, external_ref) WHERE external_ref IS NOT NULL;
ALTER TABLE slot ADD COLUMN source text NOT NULL DEFAULT 'local' CHECK (source IN ('local', 'external')),
                 ADD COLUMN external_ref text;
CREATE UNIQUE INDEX slot_external ON slot(clinic_id, external_ref) WHERE external_ref IS NOT NULL;
ALTER TABLE booking ADD COLUMN external_ref text;

-- Live warm transfer (architecture §1 out-of-scope list -> Phase 6).
ALTER TABLE staff ADD COLUMN phone_e164 text CHECK (phone_e164 IS NULL OR phone_e164 ~ '^\+91[6-9][0-9]{9}$'),
                  ADD COLUMN transfer_available boolean NOT NULL DEFAULT false,
                  ADD COLUMN transfer_available_until timestamptz;
ALTER TABLE call_attempt ADD COLUMN transferred_to uuid REFERENCES staff(id),
                         ADD COLUMN transferred_at timestamptz;
