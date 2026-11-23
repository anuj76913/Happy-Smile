"""The only module that talks to the LLM provider: Groq by default (architecture §4.13; plan P3-01).

Phase 6: LLM_BASE_URL / LLM_API_KEY / LLM_PROVIDER switch to any OpenAI-compatible endpoint,
e.g. an India-hosted model if the data review (P0-13) requires it. Nothing else changes.

- OpenAI-compatible Chat Completions over httpx; model IDs pinned in config.
- Streaming with a first-token timeout (default 800 ms) and a total timeout.
- HTTP 429 / 5xx: one jittered retry if it still fits the time budget.
- Redaction before sending: phone numbers and long digit runs never leave our system.
- Prompt templates are versioned; every call is logged (no content) to `llm_call`.
- Any failure raises LlmError; callers fall back to rules (never to silence).
"""

from __future__ import annotations

import json
import random
import re
import time
from dataclasses import dataclass

import httpx

from .config import get_settings


class LlmError(Exception):
    pass


_DIGITS = re.compile(r"(?:\+?\d[\s-]?){6,}")


def redact(text: str) -> str:
    """Remove phone numbers, Aadhaar/card numbers and other long digit runs (EC-LLM-13)."""
    return _DIGITS.sub("[number]", text or "")


@dataclass
class LlmResult:
    content: str
    ttft_ms: int | None
    total_ms: int
    prompt_tokens: int | None = None
    output_tokens: int | None = None


class GroqClient:
    def __init__(self, transport: httpx.BaseTransport | None = None):
        s = get_settings()
        self.s = s
        self._client = httpx.Client(base_url=s.groq_base_url, transport=transport,
                                    headers={"Authorization": f"Bearer {s.groq_api_key}",
                                             "User-Agent": "lead-assistant/0.3"})

    def json_completion(self, *, purpose: str, model: str, prompt_version: str, system: str, user: str,
                        max_tokens: int = 200, budget_ms: int | None = None) -> dict:
        """Non-streaming JSON-mode call. Returns the parsed object."""
        res = self._call(purpose, model, prompt_version, system, user, max_tokens, budget_ms, stream=False)
        try:
            out = json.loads(res.content)
        except json.JSONDecodeError as e:
            self._log(purpose, model, prompt_version, False, "invalid_json", res)
            raise LlmError("invalid JSON from model") from e
        if not isinstance(out, dict):
            raise LlmError("model returned a non-object")
        return out

    def stream_text(self, *, purpose: str, model: str, prompt_version: str, system: str, user: str,
                    max_tokens: int = 120) -> LlmResult:
        """Streaming call with a first-token timeout (used for free-text generation)."""
        return self._call(purpose, model, prompt_version, system, user, max_tokens, None, stream=True)

    # ------------------------------------------------------------------ internals
    def _call(self, purpose, model, prompt_version, system, user, max_tokens, budget_ms, stream) -> LlmResult:
        budget = (budget_ms or self.s.llm_total_timeout_ms) / 1000
        t0 = time.perf_counter()
        body = {"model": model, "temperature": 0, "max_tokens": max_tokens, "stream": stream,
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": redact(user)}]}
        if not stream:
            body["response_format"] = {"type": "json_object"}
        last_err = "unknown"
        for attempt in (1, 2):
            remaining = budget - (time.perf_counter() - t0)
            if remaining <= 0.05:
                break
            try:
                res = self._stream(body, t0, remaining) if stream else self._once(body, t0, remaining)
                self._log(purpose, model, prompt_version, True, None, res)
                return res
            except httpx.HTTPStatusError as e:
                last_err = f"http_{e.response.status_code}"
                if e.response.status_code not in (429, 500, 502, 503) or attempt == 2:
                    break
                time.sleep(min(0.25 + random.random() * 0.25, max(0, budget - (time.perf_counter() - t0) - 0.1)))
            except (httpx.TimeoutException, TimeoutError):
                last_err = "timeout"
                break
            except httpx.HTTPError as e:
                last_err = type(e).__name__
                break
        self._log(purpose, model, prompt_version, False, last_err,
                  LlmResult("", None, int((time.perf_counter() - t0) * 1000)))
        raise LlmError(last_err)

    def _once(self, body, t0, remaining) -> LlmResult:
        r = self._client.post("/chat/completions", json=body, timeout=remaining)
        r.raise_for_status()
        data = r.json()
        usage = data.get("usage") or {}
        total = int((time.perf_counter() - t0) * 1000)
        return LlmResult(data["choices"][0]["message"]["content"], total, total,
                         usage.get("prompt_tokens"), usage.get("completion_tokens"))

    def _stream(self, body, t0, remaining) -> LlmResult:
        first_deadline = t0 + self.s.llm_first_token_timeout_ms / 1000
        parts, ttft = [], None
        with self._client.stream("POST", "/chat/completions", json=body, timeout=remaining) as r:
            r.raise_for_status()
            for line in r.iter_lines():
                if ttft is None and time.perf_counter() > first_deadline:
                    raise TimeoutError("first token too slow")
                if not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    break
                delta = json.loads(data).get("choices", [{}])[0].get("delta", {}).get("content")
                if delta:
                    if ttft is None:
                        ttft = int((time.perf_counter() - t0) * 1000)
                    parts.append(delta)
        return LlmResult("".join(parts), ttft, int((time.perf_counter() - t0) * 1000))

    def _log(self, purpose, model, prompt_version, ok, error, res: LlmResult) -> None:
        try:
            from .db import tx
            with tx() as conn:
                conn.execute(
                    "INSERT INTO llm_call (purpose, model, prompt_version, ok, error, ttft_ms, total_ms, prompt_tokens, output_tokens) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
                    (purpose, f"{self.s.llm_provider}/{model}", prompt_version, ok, error, res.ttft_ms, res.total_ms,
                     res.prompt_tokens, res.output_tokens))
        except Exception:  # telemetry must never break a call
            pass


_client: GroqClient | None = None


def client() -> GroqClient | None:
    """Shared client, or None when Groq isn't configured (rules-only mode)."""
    global _client
    if not get_settings().llm_enabled:
        return None
    if _client is None:
        _client = GroqClient()
    return _client


def set_client(c: GroqClient | None) -> None:  # tests
    global _client
    _client = c
