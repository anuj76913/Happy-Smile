"""Indian mobile number normalisation (architecture §4.2, EC-FORM-01/02)."""

from __future__ import annotations

import re

_MOBILE = re.compile(r"^[6-9]\d{9}$")


def normalise_mobile(raw: str) -> str | None:
    """Return +91XXXXXXXXXX for a valid Indian mobile number, else None.

    Accepts spaces, dashes, brackets, a +91 / 91 prefix or a leading 0.
    """
    digits = re.sub(r"\D", "", raw or "")
    if len(digits) == 12 and digits.startswith("91"):
        digits = digits[2:]
    elif len(digits) == 11 and digits.startswith("0"):
        digits = digits[1:]
    return f"+91{digits}" if _MOBILE.match(digits) else None


def display(e164: str) -> str:
    """+919876543210 -> +91 98765 43210"""
    d = e164[3:]
    return f"+91 {d[:5]} {d[5:]}"
