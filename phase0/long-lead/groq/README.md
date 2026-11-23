# P0-12 / P0-13 — Groq setup and data terms

Groq is the chosen LLM provider (architecture §4.13). Phase 0 confirms that the account, models, latency and rate limits fit the plan, and starts the data review legal needs before go-live (gate G2).

## P0-12 — Account, models, limits

### Steps

1. Create the Groq account as an **organisation account owned by HappySmile** (not a personal account), with at least two admins.
2. Create separate API keys for **staging** and **production**. Store them in the secrets manager only (implementation-plan §11.2).
3. List the available models and pick three roles (architecture §4.13):
   - **Dialogue**: larger instruction-tuned model with tool calling and streaming.
   - **Guard**: small, fast model with JSON output.
   - **Summary**: larger model with JSON output.
4. Measure latency and read the rate limits with `groq_check.py`:

   ```bash
   # GROQ_API_KEY must be set in your shell
   python groq_check.py --list-models
   python groq_check.py --model <dialogue-model-id> --runs 20
   python groq_check.py --model <guard-model-id> --runs 20 --mode guard
   ```

   The script sends only synthetic prompts. It reports p50/p90 time to first token against the 500 ms budget and prints the `x-ratelimit-*` headers.

5. Compare the limits with the need below, and upgrade the plan or request higher limits if needed.
6. Record the pinned model IDs and results in the table at the bottom.

### Capacity needed

| Item | Estimate |
|---|---|
| Concurrent calls at peak | 10 |
| Caller turns per call per second | ~1 every 5 s |
| LLM requests per turn | 2 (dialogue + guard, in parallel) |
| **Peak requests per second** | **~4**, plus summaries after calls |
| Tokens per dialogue request | ~1,000–2,000 in (prompt + history), ~60 out |
| Peak tokens per minute (dialogue model) | ~2 req/s × 60 × ~1,500 ≈ **180,000** |

Check both requests-per-minute and tokens-per-minute limits for each model.

## P0-13 — Data processing questions for Groq (for legal)

Ask Groq in writing and attach the answers to the legal review ([legal-review-brief.md](../legal-review-brief.md)):

1. In which countries are prompts and completions processed and stored?
2. Are prompts or outputs retained? For how long? Can retention be turned off?
3. Are customer prompts or outputs ever used to train or improve models?
4. Is a data processing agreement available? Which sub-processors are involved?
5. What security certifications and audit reports can you share?
6. How are incidents involving customer data notified, and how quickly?
7. Is there any option to process data in or near India?

Until the answers are accepted, the plan's minimisation rules apply: no phone numbers in prompts, first name only when needed, and redaction of stored prompt logs (architecture §4.13).

## Record

| Role | Model ID (pinned) | p50 TTFT | p90 TTFT | RPM limit | TPM limit | Date |
|---|---|---|---|---|---|---|
| Dialogue (understanding) | `qwen/qwen3.8-27b` | 132 ms | 156 ms | 1,000 requests (window resets ~24 min; looks daily) | 8,000 / min | 2026-11-22 |
| Guard (classifier, JSON) | `qwen/qwen3.8-27b` | 251 ms* | 321 ms* | same account | same | 2026-11-22 |
| Summary (JSON) | `qwen/qwen3.8-27b` | (as guard) | (as guard) | same account | same | 2026-11-22 |

\* Time to the complete JSON answer, not just the first token.

Latency measured from: a developer laptop in India over home broadband (re-measure from the production region before G1).

**Models rejected:** `openai/gpt-oss-20b` and `openai/gpt-oss-120b` are reasoning models. In JSON mode with small token limits they returned HTTP 400 ("Failed to validate JSON"). With 400 tokens, 120b answered with a trigger outside the allowed list. 20b streamed no text in 80 tokens. Their first token was also near or over the 500 ms budget (120b: p90 507 ms).

**Plan tier: too small for the pilot.** This account allows 8,000 tokens and 1,000 requests per period. The pilot needs about 4 requests/s and about 180,000 tokens/min at peak. Upgrade the plan or request higher limits before G2. Until then, calls over the limit get HTTP 429, and the agent falls back to rules (safe, but no LLM understanding).
