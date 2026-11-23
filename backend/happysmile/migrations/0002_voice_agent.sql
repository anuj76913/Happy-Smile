-- Phase 3: voice agent, call orchestration, handover queue (architecture §4.4-4.10, §8).

-- Durable call scheduler (architecture §4.4). One open job per lead.
CREATE TABLE call_job (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  lead_id       uuid NOT NULL REFERENCES lead(id),
  attempt_no    int NOT NULL,
  due_at        timestamptz NOT NULL,
  status        text NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'running', 'done', 'cancelled', 'failed')),
  locked_until  timestamptz,
  last_error    text,
  created_at    timestamptz NOT NULL DEFAULT now(),
  updated_at    timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX call_job_one_open_per_lead ON call_job(lead_id) WHERE status IN ('pending', 'running');
CREATE INDEX call_job_due ON call_job(due_at) WHERE status = 'pending';

-- Live call state: status of the attempt and the agent's session between turns.
ALTER TABLE call_attempt
  ADD COLUMN provider text NOT NULL DEFAULT 'staff',
  ADD COLUMN state text NOT NULL DEFAULT 'completed'
      CHECK (state IN ('dialing', 'ringing', 'in_progress', 'completed', 'failed')),
  ADD COLUMN started_at timestamptz,
  ADD COLUMN ended_at timestamptz;
ALTER TABLE call_attempt DROP CONSTRAINT call_attempt_outcome_check;
ALTER TABLE call_attempt ALTER COLUMN outcome DROP NOT NULL;
ALTER TABLE call_attempt ADD CONSTRAINT call_attempt_outcome_check
  CHECK (outcome IS NULL OR outcome IN ('answered', 'no_answer', 'busy', 'voicemail', 'invalid', 'failed'));

ALTER TABLE conversation
  ADD COLUMN session jsonb,                 -- agent state between turns
  ADD COLUMN transcript jsonb NOT NULL DEFAULT '[]',
  ADD COLUMN outcome text,
  ADD COLUMN prompt_version text,
  ADD COLUMN guard_events jsonb NOT NULL DEFAULT '[]',
  ADD COLUMN created_at timestamptz NOT NULL DEFAULT now(),
  ADD COLUMN updated_at timestamptz NOT NULL DEFAULT now();

-- Handovers: escalation tracking (architecture §4.9).
ALTER TABLE handover
  ADD COLUMN overdue_at timestamptz,
  ADD COLUMN escalated_at timestamptz,
  ADD COLUMN call_attempt_id uuid REFERENCES call_attempt(id),
  ADD COLUMN promised text;
CREATE INDEX handover_open ON handover(lead_id) WHERE resolved_at IS NULL;
CREATE UNIQUE INDEX handover_one_open_per_lead ON handover(lead_id) WHERE resolved_at IS NULL;

ALTER TABLE handover_feedback ADD COLUMN reason text;

-- Assistant bookings: review trail (architecture §4.7).
ALTER TABLE booking
  ADD COLUMN reviewed_by uuid REFERENCES staff(id),
  ADD COLUMN reviewed_at timestamptz,
  ADD COLUMN cancel_reason text,
  ADD COLUMN call_attempt_id uuid REFERENCES call_attempt(id);

-- People who asked us to stop (EC-MAN-06, EC-WHO-03).
CREATE TABLE suppression (
  phone_e164  text PRIMARY KEY,
  reason      text NOT NULL,
  lead_id     uuid REFERENCES lead(id),
  created_at  timestamptz NOT NULL DEFAULT now()
);

-- Circuit breaker state for the voice agent's dependencies (architecture §4.4).
CREATE TABLE breaker (
  name          text PRIMARY KEY,
  failures      int NOT NULL DEFAULT 0,
  window_start  timestamptz NOT NULL DEFAULT now(),
  open_until    timestamptz
);

-- Practice calls from the console (plan P3-11/P3-12): staff play the caller. They read real
-- slots but never write leads, bookings or handovers.
CREATE TABLE test_call (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  staff_id    uuid NOT NULL REFERENCES staff(id),
  session     jsonb NOT NULL,
  backend     jsonb NOT NULL DEFAULT '{}',
  created_at  timestamptz NOT NULL DEFAULT now(),
  updated_at  timestamptz NOT NULL DEFAULT now()
);

-- LLM call telemetry without personal data (architecture §15.2).
CREATE TABLE llm_call (
  id              bigserial PRIMARY KEY,
  purpose         text NOT NULL,          -- nlu | guard | summary
  model           text NOT NULL,
  prompt_version  text NOT NULL,
  ok              boolean NOT NULL,
  error           text,
  ttft_ms         int,
  total_ms        int,
  prompt_tokens   int,
  output_tokens   int,
  at              timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX llm_call_at ON llm_call(at DESC);
