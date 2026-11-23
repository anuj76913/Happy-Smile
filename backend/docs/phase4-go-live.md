# Phase 4: go-live runbook (pilot week 3)

Implements the go-live procedure in [implementation-plan.md §8](../../docs/implementation-plan.md#8-phase-4--hindi-whatsapp-and-limited-go-live-pilot-week-3) and gates G2/G3 (§12). In staging and production the system **enforces** the gates: an assistant share above 0 is refused until G2 passes, and above 20% until G3 passes for that clinic. In development they are reported only.

## 1. Pass gate G2

Console → **Ops** shows the live checklist. `GET /v1/admin/go-live` returns the same as JSON.

**Technical (checked automatically):**
- [ ] `VOICE_AGENT_ENABLED=true` with a real `TELEPHONY_PROVIDER` (not `sim`)
- [ ] `WHATSAPP_PROVIDER=meta` (or a BSP adapter) with token, phone number ID, app secret, verify token
- [ ] `TELEPHONY_WEBHOOK_SECRET` set; Meta webhook pointed at `/v1/hooks/whatsapp`
- [ ] `ALERT_WEBHOOK_URL` set (e.g. a Slack/Teams incoming webhook); alerts reach a person outside the console
- [ ] Evaluation set passes every G1 behaviour check (run in the check itself)
- [ ] Kill switch drilled in the last 14 days (Ops → **Record kill-switch drill**, after actually stopping and restarting one clinic in staging)

**Signed off by a named admin (Ops → Sign off):** front-desk lead script sign-off · native Hindi review · legal: consent and telecom · legal: Groq terms (or Groq unused) · WhatsApp templates approved · caller ID registered · staff trained (with [staff-guide.md](staff-guide.md)) · handover rota staffed · p90 turn latency ≤ 1.2 s measured on real test calls.

## 2. Go live at 20%

```http
PUT /v1/admin/experiment/{clinic}   {"assistant_share": 0.2}
```

Admins only. This records `live_since` and only affects new leads (arm assignment is write-once).

## 3. First live days (plan §8.2)

| When | Who | What |
|---|---|---|
| Day 1 | Voice/AI + front-desk lead | Listen to every assistant call (or read every transcript) the same day |
| Days 2–5 | Front-desk lead | 10 calls per clinic per day, plus every thumbs-down and every cancelled booking |
| Daily | Voice/AI | Turn findings into scenarios in `evaluation/scenarios.py`; re-run the evaluation set; ship line or keyword fixes the same day |
| Daily | PM | Ops screen: first dial, SLA hit rate, urgent missed, review rejections, WhatsApp failures |

## 4. Kill switch (implementation-plan §13)

| Trigger | What happens |
|---|---|
| Urgent handover not claimed within 5 min | **Critical alert** |
| Urgent handover not claimed within 10 min (2× SLA) | **Assistant stopped for that clinic automatically** (`AUTO_KILL_SWITCH=true`); queued leads go to staff; restart needs a person to set the share again (and G2) |
| Review rejection > 15% (≥ 5 reviews today) | **AI booking paused automatically**: the assistant still calls and qualifies, then hands over |
| Handover SLA hit rate < 60% (≥ 5 handovers) | **Critical alert**; lowering the share is a manager's decision |
| Groq or telephony failing | Circuit breaker sends new leads to staff (Phase 3) |
| Anything else that looks wrong | Ops → **Stop assistant** / **Pause AI booking** (reason required, audited) |

Disclosure failures and medical advice can't happen by construction: the assistant speaks only approved lines, and each line passes the output check ([ADR-007](../../phase0/decisions/ADR-007-llm-understands-lines-speak.md)).

## 5. Ramp to 50% (gate G3)

Enforced per clinic: ≥ 3 live days at 20% · no missed urgent handover · handover SLA ≥ 80% · booking-review rejection ≤ 5% · no staff calls to assistant-group leads before handover (contamination). Ops shows each clinic's status.

## 6. Decisions taken in Phase 4 (flagged for review)

- **WhatsApp only for the assistant group.** The control arm keeps today's process, so automated confirmations don't change its attendance and skew the comparison.
- **SMS fallback (EC-WA-01) not built.** It's still a proposed decision and needs DLT registration (P0-16). A failed confirmation goes to Needs you for a call instead.
- **New template `whatsapp_hello_v1`** for "WhatsApp me instead"; added to the submission list.
- **Auto-stop at 2× the urgent SLA, alert at 1×.** The plan says "any missed urgent handover → 0%". Stopping a whole clinic at minute 6 risked stopping on one slow pick-up, so the alert comes first and the switch follows at minute 10. Change it with `AUTO_KILL_SWITCH`, or in `ops.py`.
