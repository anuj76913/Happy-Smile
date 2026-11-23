# ADR-007 — The LLM understands the caller; approved lines do the talking

| | |
|---|---|
| **Status** | Accepted for the pilot (Phase 3) |
| **Plan items** | P3-01, P3-04, P3-05, P3-06 |
| **Deciders** | Engineering, PM; front-desk lead signs off the lines |
| **Architecture** | §4.5 says the LLM handles "phrasing within a stage" and "picks a tool". This ADR narrows that. |

## Decision

1. **Understanding:** Groq turns each caller turn into structured meaning (intent, treatment, clinic, day, time window, slot choice), in JSON mode, validated, with rule-based understanding as the fallback.
2. **Speaking:** the assistant only says lines from `voice/lines.py`, in English and Hindi, filled with values from the booking system.
3. **Acting:** the state machine decides which tool to call, through the allowlisted `ToolRegistry`. The LLM never calls tools.
4. **Safety:** guardrail rules run on every turn and win. The Groq classifier can add triggers, never remove them. Every line passes the output check before it's spoken.

## Why

- **Gate G1 asks for certainties:** 100% disclosure in the first sentence, zero claims to be human, zero medical advice. Fixed lines make these properties of the code, not of a prompt.
- **Hindi can be reviewed.** A native speaker and the front-desk lead can sign off every sentence before patients hear it.
- **Speed:** a short JSON reply is faster than generating speech text, which helps the 1.2 s turn budget.
- **Works without Groq:** if Groq is slow, rate-limited or down, the rules keep calls going (P3 exit: "circuit breaker tested"), and the evaluation set passes in that mode.

## Costs

- **Less natural replies** to unexpected questions. Out-of-scope questions go to staff (`needs_staff`), which adds to the handover queue. Watch the handover mix in the pilot.
- **Changing the wording means changing code** and re-running the evaluation set. That's deliberate.

## Revisit when

The evaluation set and live reviews show the fixed lines are the main cause of handovers or drop-offs. Then trial LLM phrasing for specific low-risk stages (e.g. small talk), still behind the output check.
