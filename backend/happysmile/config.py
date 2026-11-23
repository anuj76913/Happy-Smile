"""Settings from environment variables (12-factor).

Secrets (DATABASE_URL, IP_HASH_SALT) come from the environment. In staging and
production they are injected by the secrets manager; never commit them.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")


@dataclass(frozen=True)
class Settings:
    env: str
    database_url: str
    ip_hash_salt: str
    caller_id: str
    cookie_secure: bool
    session_hours: int
    voice_agent_enabled: bool
    calling_window_start: str
    calling_window_end: str
    last_call_cutoff_min: int
    rate_limit_ip_per_10min: int
    rate_limit_phone_per_hour: int
    # Phase 3: LLM (Groq) and telephony
    groq_api_key: str
    groq_base_url: str
    llm_nlu_model: str
    llm_guard_model: str
    llm_summary_model: str
    llm_first_token_timeout_ms: int
    llm_total_timeout_ms: int
    telephony_provider: str
    max_concurrent_calls: int
    staff_hours_start: str
    staff_hours_end: str
    # Phase 4: WhatsApp, alerts, kill switch
    whatsapp_provider: str
    whatsapp_token: str
    whatsapp_phone_number_id: str
    whatsapp_app_secret: str
    whatsapp_verify_token: str
    whatsapp_graph_version: str
    telephony_webhook_secret: str
    alert_webhook_url: str
    auto_kill_switch: bool
    # Phase 6
    llm_provider: str
    permanent_control_share: float
    calendar_api_url: str
    calendar_api_token: str
    dedupe_hours: int
    # Hosting (Railway): run the call worker inside the web process; staff password for a public demo
    run_worker: bool
    demo_staff_password: str

    @property
    def browser_calls(self) -> bool:
        """Demo only (dev or APP_ENV=demo): the assistant 'calls' the patient's browser instead of a phone."""
        return self.telephony_provider == "browser" and not self.is_production_like

    @property
    def is_production_like(self) -> bool:
        return self.env in {"staging", "production"}

    @property
    def llm_enabled(self) -> bool:
        """Groq is used only when a key and all three pinned model IDs are configured."""
        return bool(self.groq_api_key and self.llm_nlu_model and self.llm_guard_model and self.llm_summary_model)


def _bool(name: str, default: bool) -> bool:
    v = os.environ.get(name)
    return default if v is None else v.strip().lower() in {"1", "true", "yes", "on"}


@lru_cache
def get_settings() -> Settings:
    env = os.environ.get("APP_ENV", "dev")
    s = Settings(
        env=env,
        database_url=os.environ.get("DATABASE_URL", "postgresql://postgres@127.0.0.1:54329/happysmile"),
        ip_hash_salt=os.environ.get("IP_HASH_SALT", "dev-only-salt"),
        caller_id=os.environ.get("CALLER_ID", "+91 90000 12345"),
        cookie_secure=_bool("COOKIE_SECURE", env != "dev"),
        session_hours=int(os.environ.get("SESSION_HOURS", "12")),
        voice_agent_enabled=_bool("VOICE_AGENT_ENABLED", False),
        calling_window_start=os.environ.get("CALLING_WINDOW_START", "09:00"),
        calling_window_end=os.environ.get("CALLING_WINDOW_END", "21:00"),
        last_call_cutoff_min=int(os.environ.get("LAST_CALL_CUTOFF_MIN", "15")),
        rate_limit_ip_per_10min=int(os.environ.get("RATE_LIMIT_IP_PER_10MIN", "20")),
        rate_limit_phone_per_hour=int(os.environ.get("RATE_LIMIT_PHONE_PER_HOUR", "5")),
        # Any OpenAI-compatible endpoint works (e.g. an India-hosted model if the Groq data review requires it).
        groq_api_key=os.environ.get("LLM_API_KEY") or os.environ.get("GROQ_API_KEY", ""),
        groq_base_url=os.environ.get("LLM_BASE_URL") or os.environ.get("GROQ_BASE_URL", "https://api.groq.com/openai/v1"),
        # No defaults on purpose: model IDs are chosen from Groq's list at build time and pinned (architecture §4.13).
        llm_nlu_model=os.environ.get("LLM_DIALOGUE_MODEL", ""),
        llm_guard_model=os.environ.get("LLM_GUARD_MODEL", ""),
        llm_summary_model=os.environ.get("LLM_SUMMARY_MODEL", ""),
        llm_first_token_timeout_ms=int(os.environ.get("LLM_FIRST_TOKEN_TIMEOUT_MS", "800")),
        llm_total_timeout_ms=int(os.environ.get("LLM_TOTAL_TIMEOUT_MS", "2500")),
        telephony_provider=os.environ.get("TELEPHONY_PROVIDER", "sim"),
        max_concurrent_calls=int(os.environ.get("MAX_CONCURRENT_CALLS", "10")),
        staff_hours_start=os.environ.get("STAFF_HOURS_START", "09:00"),
        staff_hours_end=os.environ.get("STAFF_HOURS_END", "21:00"),
        whatsapp_provider=os.environ.get("WHATSAPP_PROVIDER", "sim"),
        whatsapp_token=os.environ.get("WHATSAPP_TOKEN", ""),
        whatsapp_phone_number_id=os.environ.get("WHATSAPP_PHONE_NUMBER_ID", ""),
        whatsapp_app_secret=os.environ.get("WHATSAPP_APP_SECRET", ""),
        whatsapp_verify_token=os.environ.get("WHATSAPP_VERIFY_TOKEN", ""),
        whatsapp_graph_version=os.environ.get("WHATSAPP_GRAPH_VERSION", "v21.0"),
        telephony_webhook_secret=os.environ.get("TELEPHONY_WEBHOOK_SECRET", ""),
        alert_webhook_url=os.environ.get("ALERT_WEBHOOK_URL", ""),
        auto_kill_switch=_bool("AUTO_KILL_SWITCH", True),
        llm_provider=os.environ.get("LLM_PROVIDER", "groq"),
        permanent_control_share=float(os.environ.get("PERMANENT_CONTROL_SHARE", "0.1")),
        calendar_api_url=os.environ.get("CALENDAR_API_URL", ""),
        calendar_api_token=os.environ.get("CALENDAR_API_TOKEN", ""),
        dedupe_hours=int(os.environ.get("DEDUPE_HOURS", "24")),
        run_worker=_bool("RUN_WORKER", False),
        demo_staff_password=os.environ.get("DEMO_STAFF_PASSWORD", ""),
    )
    if s.env == "demo":
        # A public demo site (e.g. Railway + Vercel): synthetic data, browser calls allowed, but real secrets.
        problems = []
        if s.ip_hash_salt == "dev-only-salt":
            problems.append("IP_HASH_SALT must be set to a random value")
        if len(s.demo_staff_password) < 10:
            problems.append("DEMO_STAFF_PASSWORD (10+ characters) must be set: the published dev passwords would let anyone in")
        if "127.0.0.1" in s.database_url or "localhost" in s.database_url:
            problems.append("DATABASE_URL points at a local database")
        if problems:
            raise RuntimeError("Refusing to start the demo site: " + "; ".join(problems))
    if s.is_production_like:
        problems = []
        if s.ip_hash_salt == "dev-only-salt":
            problems.append("IP_HASH_SALT must be set from the secrets manager")
        if not s.cookie_secure:
            problems.append("COOKIE_SECURE must be true")
        if "127.0.0.1" in s.database_url or "localhost" in s.database_url:
            problems.append("DATABASE_URL points at a local database")
        if s.voice_agent_enabled and s.telephony_provider in ("sim", "browser"):
            problems.append("VOICE_AGENT_ENABLED needs a real TELEPHONY_PROVIDER, not the simulator or the browser demo")
        if problems:
            raise RuntimeError(f"Refusing to start in {env}: " + "; ".join(problems))
    return s
