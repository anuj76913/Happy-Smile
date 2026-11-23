"""P0-12 — Groq account check: models, time-to-first-token and rate limits.

Run this once the Groq account exists, to confirm before Phase 3 that:
  - the chosen models are available on the account,
  - time-to-first-token (TTFT) fits the 500 ms budget (architecture §7.4),
  - the plan's rate limits cover ~4 requests/s at peak (architecture §4.13).

Prompts are synthetic. No patient data is sent.

Setup:
    set GROQ_API_KEY in the environment (never commit it)

Usage:
    python groq_check.py --list-models
    python groq_check.py --model <dialogue-model-id> --runs 20
    python groq_check.py --model <guard-model-id> --runs 20 --mode guard

Model IDs are deliberately not hard-coded: Groq's line-up changes. Pick them
from --list-models and record the choice in ../../decisions/ (pinned IDs).
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import time
import urllib.error
import urllib.request

BASE = "https://api.groq.com/openai/v1"
UA = "groq-latency-check/1.0"
TTFT_BUDGET_MS = 500

DIALOGUE_MESSAGES = [
    {"role": "system", "content": (
        "You are a dental clinic's virtual assistant on a phone call. Stage: offer slots. "
        "Reply in one or two short spoken sentences. Never give medical advice.")},
    {"role": "user", "content": "Tuesday evening works best for me, maybe after six?"},
]

GUARD_MESSAGES = [
    {"role": "system", "content": (
        "Classify the caller's turn for a dental clinic assistant. Return JSON with keys "
        "trigger (bool), reason_tag (one of asked_for_person, pain_swelling, price_emi, "
        "clinical_question, none), urgency (urgent or normal), confidence (0-1).")},
    {"role": "user", "content": "Mera gum thoda soojh gaya hai aur dard ho raha hai."},
]


def _key() -> str:
    k = os.environ.get("GROQ_API_KEY", "").strip()
    if not k:
        sys.exit("GROQ_API_KEY is not set. Export it in your shell; do not put it in a file in the repo.")
    return k


def _request(path: str, body: dict | None = None) -> urllib.request.Request:
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(BASE + path, data=data, method="GET" if body is None else "POST")
    req.add_header("Authorization", f"Bearer {_key()}")
    req.add_header("User-Agent", UA)
    if body is not None:
        req.add_header("Content-Type", "application/json")
    return req


def list_models() -> None:
    with urllib.request.urlopen(_request("/models"), timeout=20) as r:
        models = json.load(r).get("data", [])
    for m in sorted(models, key=lambda m: m.get("id", "")):
        ctx = m.get("context_window", "")
        print(f"{m.get('id', ''):55s} owner={m.get('owned_by', ''):15s} context={ctx}")


def one_run(model: str, mode: str) -> tuple[float | None, float, dict]:
    """Returns (ttft_ms, total_ms, rate_limit_headers)."""
    if mode == "guard":
        body = {"model": model, "messages": GUARD_MESSAGES, "temperature": 0,
                "response_format": {"type": "json_object"}, "max_tokens": 80, "stream": False}
    else:
        body = {"model": model, "messages": DIALOGUE_MESSAGES, "temperature": 0.2,
                "max_tokens": 80, "stream": True}

    t0 = time.perf_counter()
    ttft = None
    with urllib.request.urlopen(_request("/chat/completions", body), timeout=30) as r:
        headers = {k.lower(): v for k, v in r.headers.items() if k.lower().startswith("x-ratelimit")}
        if mode == "guard":
            payload = json.load(r)
            ttft = (time.perf_counter() - t0) * 1000  # whole JSON answer is the "first token" here
            content = payload["choices"][0]["message"]["content"]
            json.loads(content)  # must be valid JSON
        else:
            for raw in r:
                line = raw.decode("utf-8", "replace").strip()
                if not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    break
                chunk = json.loads(data)
                delta = chunk.get("choices", [{}])[0].get("delta", {}).get("content")
                if delta and ttft is None:
                    ttft = (time.perf_counter() - t0) * 1000
    return ttft, (time.perf_counter() - t0) * 1000, headers


def pctl(values: list[float], p: float) -> float:
    s = sorted(values)
    return s[min(len(s) - 1, max(0, round(p / 100 * (len(s) - 1))))]


def bench(model: str, runs: int, mode: str) -> None:
    ttfts, totals, last_headers, errors = [], [], {}, 0
    for i in range(runs):
        try:
            ttft, total, headers = one_run(model, mode)
            if ttft is not None:
                ttfts.append(ttft)
            totals.append(total)
            last_headers = headers or last_headers
        except urllib.error.HTTPError as e:
            errors += 1
            print(f"run {i + 1}: HTTP {e.code} {e.reason}")
            if e.code == 429:
                time.sleep(2)
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
            errors += 1
            print(f"run {i + 1}: {type(e).__name__}: {e}")
        time.sleep(0.3)

    label = "time to full JSON answer" if mode == "guard" else "time to first token"
    print(f"\nModel: {model}   mode: {mode}   runs: {runs}   errors: {errors}")
    if ttfts:
        p50, p90 = statistics.median(ttfts), pctl(ttfts, 90)
        verdict = "OK" if p90 <= TTFT_BUDGET_MS else "OVER BUDGET"
        print(f"{label}: p50 {p50:.0f} ms, p90 {p90:.0f} ms  (budget {TTFT_BUDGET_MS} ms p90 -> {verdict})")
        print(f"total response time: p50 {statistics.median(totals):.0f} ms, p90 {pctl(totals, 90):.0f} ms")
        print("Note: measured from this machine. Re-measure from the production region before G1.")
    if last_headers:
        print("\nRate-limit headers from the last response:")
        for k in sorted(last_headers):
            print(f"  {k}: {last_headers[k]}")
        print("Need: ~4 requests/s at peak across the dialogue and guard models, plus summaries.")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--list-models", action="store_true")
    ap.add_argument("--model")
    ap.add_argument("--runs", type=int, default=10)
    ap.add_argument("--mode", choices=["dialogue", "guard"], default="dialogue")
    a = ap.parse_args()

    if a.list_models:
        list_models()
    elif a.model:
        bench(a.model, a.runs, a.mode)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
