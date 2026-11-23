"""Telephony providers (architecture §4.4/§4.5; plan P3-02).

The vendor is still to be chosen (phase0/long-lead/telephony-checklist.md). Everything
vendor-specific sits behind `Provider`; the rest of the system sees only these calls:

  place_call(attempt)        -> provider call id (outbound call starts ringing)
  normalised status webhook  -> answered | no_answer | busy | voicemail | failed | completed
  media stream               -> caller transcripts in, agent text out (via STT/TTS adapters)

`SimProvider` places no real calls. In development it lets the full path run end to end:
`happysmile.simulate` answers simulated calls with scripted callers.
"""

from __future__ import annotations

import hashlib
import hmac
import uuid
from typing import Protocol

from .config import get_settings


class Provider(Protocol):
    name: str

    def place_call(self, attempt_id: str, to_e164: str, caller_id: str) -> str: ...

    def transfer(self, provider_call_id: str, to_e164: str) -> bool:
        """Bridge the live call to a staff phone (warm transfer, Phase 6). True if the transfer started."""
        ...


class SimProvider:
    name = "sim"

    def __init__(self):
        self.placed: list[dict] = []
        self.transfers: list[dict] = []
        self.fail_transfer = False

    def place_call(self, attempt_id: str, to_e164: str, caller_id: str) -> str:
        pid = f"sim-{uuid.uuid4()}"
        self.placed.append({"attempt_id": attempt_id, "to": to_e164, "provider_call_id": pid})
        return pid

    def transfer(self, provider_call_id: str, to_e164: str) -> bool:
        if self.fail_transfer:
            return False
        self.transfers.append({"call": provider_call_id, "to": to_e164})
        return True


class BrowserProvider:
    """Dev-only demo line: 'dials' the patient's own browser tab, which shows an incoming call
    and talks to the assistant with the microphone (see /v1/demo-call). No phone network involved."""

    name = "browser"

    def place_call(self, attempt_id: str, to_e164: str, caller_id: str) -> str:
        return f"browser-{uuid.uuid4()}"

    def transfer(self, provider_call_id: str, to_e164: str) -> bool:
        return False  # a browser call can't be bridged to a staff phone; the normal handover applies


class ProviderUnavailable(Exception):
    pass


_provider = None


def provider():
    global _provider
    if _provider is None:
        name = get_settings().telephony_provider
        if name == "sim":
            _provider = SimProvider()
        elif name == "browser":
            if get_settings().is_production_like:
                raise ProviderUnavailable("The browser demo line is for development only.")
            _provider = BrowserProvider()
        else:
            raise ProviderUnavailable(f"Telephony provider {name!r} has no adapter yet (P0-10 pending).")
    return _provider


def set_provider(p) -> None:  # tests
    global _provider
    _provider = p


# ---------------------------------------------------------------- webhook verification
STATUS_MAP = {
    "answered": "answered", "in-progress": "answered", "completed": "completed", "no-answer": "no_answer",
    "no_answer": "no_answer", "busy": "busy", "failed": "failed", "voicemail": "voicemail", "machine": "voicemail",
    "invalid": "invalid", "invalid-number": "invalid", "unreachable": "no_answer",
}


def verify_signature(body: bytes, signature: str | None, secret: str) -> bool:
    """HMAC-SHA256 over the raw body. Each vendor adapter maps its own scheme onto this."""
    if not secret or not signature:
        return False
    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


class SpeechToText(Protocol):
    """Streaming STT adapter (vendor from P0-15). Yields (text, confidence, is_final)."""

    def feed(self, audio_chunk: bytes) -> list[tuple[str, float, bool]]: ...


class TextToSpeech(Protocol):
    """TTS adapter. Fixed lines come from pre-generated audio (lines.fixed_audio_manifest)."""

    def synthesise(self, text: str, lang: str) -> bytes: ...
