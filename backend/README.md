# HappySmile backend

## Quick start (Windows)

Needs uv and PostgreSQL 15+ on PATH. In PowerShell:

```powershell
cd "c:\Users\anuj.gupta\Desktop\New folder\Happy Smile\backend"
powershell -ExecutionPolicy Bypass -File .\run-dev.ps1          # add -Demo for simulated calls, -VoiceDemo to talk to the assistant
```

Then open http://127.0.0.1:8000/ (enquiry form) and http://127.0.0.1:8000/console (sign in as `kavya` / `riverside-demo`, `ops` / `manager-demo` or `admin` / `admin-demo`). Groq is used if `backend\.env` has a key and model IDs. Stop with Ctrl+C, close the worker window, then `.\run-dev.ps1 -Stop`.

Deploying a public demo (Railway + Vercel): see [DEPLOY.md](../DEPLOY.md).

### Talk to the assistant after the form (browser voice demo)

```powershell
powershell -ExecutionPolicy Bypass -File .\run-dev.ps1 -VoiceDemo
```

Open http://127.0.0.1:8000/ in Chrome or Edge, fill in the form at a pilot clinic (Riverside, Hillcrest or Lotus Square), keep **Call me now** and submit. Within a few seconds the tab rings: **Answer**, allow the microphone, and talk (or type). The call runs through the real path (worker → call attempt → agent → booking/handover), so the result shows up live in the staff console.

- How: `TELEPHONY_PROVIDER=browser` makes the worker "dial" the patient's tab instead of a phone. The tab polls `/v1/demo-call/{submission token}` and answers, declines and talks through it. Declining counts as a missed call and is retried in 5 minutes. A tab that never answers (90 s) or goes quiet mid-call (5 min) is swept like a phone network would.
- `-VoiceDemo` also opens the calling window 24 h, turns off duplicate-merging (so you can reuse your number), sets the pilot clinics to 100% assistant (`python -m happysmile.demo_mode on`) and turns off the automatic kill switch. The next normal `run-dev.ps1` puts the share back to 0%.
- Development only: staging/production refuse `TELEPHONY_PROVIDER=browser`, and the `/v1/demo-call` endpoints return 404 unless it is set.
- Staff can still practise without the form at http://127.0.0.1:8000/voice (practice call, books nothing).

## Phase 6: after the pilot (status)

Only applies if G4 says **Scale**; enforced in staging/production. Details: [docs/phase6-scale.md](docs/phase6-scale.md).

| Candidate | Status |
|---|---|
| Waves of 3 clinics, gated on G4 + previous wave steady + onboarding | Built (`rollout.py`, Ops → Rollout) |
| Permanent control share (10%: assistant share capped at 90%) | Built, always enforced |
| Calendar API integration | Adapter + sync + confirm-first booking built; real vendor mapping waits on P0-03 |
| Live warm transfer ("asked for a person", staffed hours) | Built; needs the telephony provider's transfer API |
| Appointment reminders, no-show recovery (assistant group) | Built; 2 new WhatsApp templates need approval |
| More languages | Readiness checker (`python -m happysmile.languages <code>`); none added without P0-04 data |
| India-hosted LLM option | Config switch (`LLM_BASE_URL`, `LLM_API_KEY`, `LLM_PROVIDER`) |

## Phase 5: ramp and pilot readout (status)

| ID | Item | Where | Status |
|---|---|---|---|
| P5-01 | Ramp 20% → 50% behind gate G3 | Ops → Assistant share; `ops.check_share_change` | Done (enforced in staging/production) |
| P5-02 | Daily call reviews (10/clinic/day), weekly feedback review | Console **Reviews**; Ops → Weekly review; `reviews.py` | Done |
| P5-03 | Tuning with a versioned change log | `voice.RULES_VERSION`, table `rules_change`, Ops → Change log | Done; every call records its rules version |
| P5-04 | Attendance for both arms | Console **Attendance**; `/v1/bookings/{id}/attendance` | Done |
| P5-05 | Pilot readout, G4 recommendation and recorded decision | `readout.py`, Ops → Pilot readout, `python -m happysmile.readout` | Done; demonstrated on **synthetic** data ([report](eval_reports/pilot-readout-synthetic.md)) |

Runbook: [docs/phase5-readout.md](docs/phase5-readout.md). The real readout needs a real pilot: four weeks of live calls after gate G2.

## Phase 4: Hindi, WhatsApp, limited go-live (status)

| ID | Item | Where | Status |
|---|---|---|---|
| P4-01 | Hindi/Hinglish: lines, mid-call language switch | `voice/lines.py`, `voice/language.py` | Done. **Hindi STT/TTS blocked on P0-15** |
| P4-02 | Hindi evaluation (≥ 30) | `evaluation/scenarios.py` | **36 Hindi/Hinglish scenarios; 94/94 pass overall.** Native-speaker review pending |
| P4-03 | WhatsApp: templates, delivery status, inbound → Needs you, STOP | `messaging.py`, `/v1/hooks/whatsapp` | Done (Meta Cloud API adapter + simulator). **Needs Meta account and template approval (P0-11)** |
| P4-04 | Retries +5 min / +2 h, then WhatsApp; voicemail; invalid numbers | `orchestrator.py` | Done |
| P4-05 | "Time I pick" (+10-min reminder), "WhatsApp me instead" | `orchestrator.enqueue_new_lead` | Done |
| P4-06 | No answer tab | console | Done |
| P4-07 | Booking review end to end with WhatsApp updates | `console_voice.review_booking` | Done |
| P4-08 | Ops metrics and alerts | `ops.py`, `/v1/admin/ops`, console **Ops** | Done; alerts go to `ALERT_WEBHOOK_URL` |
| P4-09 | Staff training guide | [docs/staff-guide.md](docs/staff-guide.md) | Written; training session is yours to run |
| P4-10 | Go-live: G2 gate, then 20% | `ops.py` gates, [docs/phase4-go-live.md](docs/phase4-go-live.md) | **Gate enforced, not passed.** It needs real vendors and the sign-offs |

Kill switch: Ops → Stop assistant / Pause AI booking, plus automatic triggers (see the runbook). The worker (`python -m happysmile.orchestrator`) also sends WhatsApp messages and runs the alert rules.

## Phase 3: voice agent MVP (status)

Built: the agent core runs without any vendor and is covered by tests. Real calls need the telephony, speech and Groq accounts from Phase 0.

| ID | Item | Where | Status |
|---|---|---|---|
| P3-01 | Groq client: pinned models, timeouts, 429 retry, redaction, prompt versions, telemetry | `llm.py`, table `llm_call` | Built, tested against a mocked Groq API; **needs a key** for live use |
| P3-02 | Telephony integration | `telephony.py`, `/v1/hooks/telephony/status` | Provider interface, signed webhook, simulator. **Vendor adapter blocked on P0-10** |
| P3-03 | STT/TTS, pre-generated fixed lines | `telephony.SpeechToText/TextToSpeech`, `lines.fixed_audio_manifest()` | Interfaces + manifest. **Blocked on P0-15** |
| P3-04 | 7-stage state machine, disclosure fixed in code | `voice/agent.py`, `voice/lines.py` | Done (EN + HI) |
| P3-05 | Tool allowlist, server-side | `voice/tools.py` | Done |
| P3-06 | Guardrails: rules first, Groq classifier in parallel, output checks | `voice/guardrails.py` | Done |
| P3-07 | Orchestrator: durable jobs, window, ~60 s first call, retries, breaker | `orchestrator.py` (`python -m happysmile.orchestrator`) | Done |
| P3-08 | Handover queue: tags, urgency, SLA, claim, escalation | `handovers.py` | Done (manager notification channel: Phase 4) |
| P3-09 | Console: Needs you, Booked by assistant, panel, feedback, review | `static/console/` | Done |
| P3-10 | Post-call summariser | `voice/summariser.py` | Done (Groq optional, validated) |
| P3-11 | Evaluation set (≥ 60) | `evaluation/` | **74 scenarios, 74/74 pass** (rules) |
| P3-12 | Internal test calls | Console **Test call**; [docs/phase3-internal-testing.md](docs/phase3-internal-testing.md) | Practice calls ready; real-phone calls need vendors |

Design choice: the LLM understands, approved lines speak ([ADR-007](../phase0/decisions/ADR-007-llm-understands-lines-speak.md)).

Run the worker next to the web app: `uv run python -m happysmile.orchestrator`. Try it locally without vendors: `VOICE_AGENT_ENABLED=true uv run python -m happysmile.simulate`.

---

## Phase 2: foundations and control arm

Implements Phase 2 of [implementation-plan.md](../docs/implementation-plan.md#6-phase-2--foundations-and-control-arm-pilot-week-1): real enquiries come in, are randomised, and the standard-callback (control) arm runs **before** any AI call exists. The assistant share is locked at 0% until the voice agent is enabled.

**Stack:** Python 3.11+, FastAPI, Postgres 15+ (tested on 18), psycopg 3. The form and console are static pages served by the app ([ADR-006](../phase0/decisions/ADR-006-console-frontend.md)).

## Run it locally

```bash
cd backend
uv sync                                   # Python deps into .venv

# Postgres: either the bundled helper (needs Postgres binaries on PATH) ...
uv run python scripts/localdb.py init     # private cluster on 127.0.0.1:54329, data in .localdb/
# ... or Docker:
#   docker run -d --name hs-pg -p 54329:5432 -e POSTGRES_HOST_AUTH_METHOD=trust postgres:17
#   docker exec hs-pg createdb -U postgres happysmile

uv run python -m happysmile.migrate       # apply SQL migrations
uv run python -m happysmile.seed          # clinics, dentists, 0% config, slots, demo staff
uv run uvicorn happysmile.main:app --reload --port 8000
```

- Enquiry form: http://127.0.0.1:8000/
- Staff console: http://127.0.0.1:8000/console
- API docs: http://127.0.0.1:8000/v1/docs

Demo staff from the seed (development only; the seed won't create them in production):

| Username | Password | Role | Sees |
|---|---|---|---|
| kavya | riverside-demo | front desk | Riverside |
| arif | hillcrest-demo | front desk | Hillcrest |
| neelam | lotus-demo | front desk | Lotus Square |
| ops | manager-demo | manager | all pilot clinics, audit log |
| admin | admin-demo | admin | + experiment config |

## Tests

```bash
uv run pytest            # 149 tests; creates and drops a happysmile_test database
```

`TEST_ADMIN_DATABASE_URL` points at a server where the tests may create databases (default: the local cluster on port 54329). CI runs the same suite against a Postgres 17 service: [.github/workflows/backend-ci.yml](../.github/workflows/backend-ci.yml).

## What's built (plan P2-01 to P2-10)

| ID | Item | Where |
|---|---|---|
| P2-01 | Project, CI, environment config, secrets via env | `pyproject.toml`, `uv.lock`, CI workflow, `.env.example`, `config.py` (refuses to start in staging/production with dev secrets or a local DB) |
| P2-02 | Postgres schema, all architecture §11 tables | `migrations/0001_init.sql`: write-once `lead.arm`; append-only `event`, `consent`, `audit_log`, `disclosure_version`; one active booking per slot |
| P2-03 | Production enquiry form | `static/enquiry/`: EN/HI, server-driven wording, idempotent retry, inline errors |
| P2-04 | `POST /v1/enquiries` | `enquiries.py`: normalise, 24 h dedupe and merge, immutable consent record, rate limits by hashed IP and phone |
| P2-05 | Experiment assigner | `experiment.py`: per-clinic salt and share, deterministic hash, returning patients keep their arm, **0% locked** until `VOICE_AGENT_ENABLED` |
| P2-06 | Event log | `events.py`: same transaction as each state change; ordered ids for the live stream |
| P2-07 | Console skeleton | `static/console/`: sign-in, clinic scoping, top strip, **Standard callback** tab with outcome capture |
| P2-08 | Staff booking from the pilot slot store | `slots.py`, Slots dialog in the console; stale-store warning |
| P2-09 | Metrics endpoint and live stream | `metrics.py` (from events only), `GET /v1/stream` (SSE, resumes via Last-Event-ID) |
| P2-10 | Audit log and roles | `auth.py`, `audit_log`: logins, failed logins, lead views, denied access, outcomes, bookings, config changes |

### How the form stays honest about who will call

The arm is decided **after** the form is submitted, but the disclosure must be shown **before**. So the wording depends on the clinic's assistant share: 0% → "our team will call" (Phase 2); between 0 and 100% → both the assistant and the team are disclosed; 100% → assistant only. The form sends back the version it showed; the server rejects a stale version and returns the current wording to re-confirm. Each consent row stores the exact version agreed to. Texts live in `disclosures.py`; a released version can't be edited, only replaced.

## Exit criteria (plan §6.2)

| Criterion | Status | Evidence |
|---|---|---|
| Pilot-clinic enquiries arrive in the console within seconds | **Met locally** | End-to-end browser run: submitted on the form, appeared in a signed-in console after ~1.5 s without reload |
| Staff record outcomes for control leads, measured like the assistant arm will be | **Met** | Outcomes record a call attempt; first contact emits `lead.reached` with exact seconds since enquiry |
| Event log reproduces the top-strip numbers exactly | **Met** | `test_event_log_reproduces_top_strip`; `/v1/admin/metrics/consistency` |
| Dedupe, consent capture and idempotency have automated tests | **Met** | `tests/test_intake.py`, including parallel double-submits |

## Not done in Phase 2 (needs you or a later phase)

- **Staging and production environments are not provisioned.** The code is ready for them (env config, production guard, CI), but hosting in an Indian region and the secrets manager need an account decision.
- **No git repository yet.** `git init` and the first commit are left to you; CI runs once the code is on GitHub.
- Click-to-call through the telephony provider (Phase 3). Today **Call** is a `tel:` link and marks the lead as being called.
- Booking cancellation and rescheduling, WhatsApp confirmations (Phase 4).
- Public status polling (`GET /v1/enquiries/{id}/status`): only needed when the assistant calls (Phase 3).
- Data-rights deletion (EC-PRIV-01) needs a privileged procedure, because consent and events are append-only.

## Layout

```
backend/
  happysmile/
    config.py  db.py  migrate.py  seed.py  main.py  api.py
    enquiries.py  experiment.py  disclosures.py  events.py
    auth.py  security.py  leads.py  slots.py  metrics.py
    phone.py  calling_window.py
    migrations/0001_init.sql
    static/shared/ static/enquiry/ static/console/
  scripts/localdb.py
  tests/ (49 tests)
```
