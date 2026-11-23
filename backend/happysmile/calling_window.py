"""Calling window rules (architecture §4.4, EC-TIME-01/02)."""

from __future__ import annotations

from datetime import datetime, time, timedelta

from .config import IST, get_settings


def _hhmm(s: str) -> time:
    h, m = s.split(":")
    return time(int(h), int(m))


def window() -> tuple[time, time, int]:
    s = get_settings()
    return _hhmm(s.calling_window_start), _hhmm(s.calling_window_end), s.last_call_cutoff_min


def can_call_now(now: datetime) -> bool:
    """True if a new call may start now: inside the window and not in the last-call cutoff."""
    start, end, cutoff = window()
    local = now.astimezone(IST)
    last = (datetime.combine(local.date(), end) - timedelta(minutes=cutoff)).time()
    return start <= local.time() <= last


def next_opening(now: datetime) -> datetime:
    """Next time the calling window opens, in IST."""
    start, _, _ = window()
    local = now.astimezone(IST)
    today_open = datetime.combine(local.date(), start, tzinfo=IST)
    return today_open if local < today_open else today_open + timedelta(days=1)


def is_valid_scheduled_time(at: datetime, now: datetime, max_days: int = 7) -> bool:
    """A picked call time must be in the future, within the window, and within max_days (EC-TIME-06)."""
    start, end, cutoff = window()
    local = at.astimezone(IST)
    last = (datetime.combine(local.date(), end) - timedelta(minutes=cutoff)).time()
    return now < at <= now + timedelta(days=max_days) and start <= local.time() <= last
