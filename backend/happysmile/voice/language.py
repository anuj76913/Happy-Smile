"""Mid-call language switching (plan P4-01; edge cases EC-LANG-01/02/10).

Switch only on a clear signal, never on one ambiguous word:
  - explicit request ("Hindi mein baat karo", "can we speak English?") -> switch and say so;
  - Devanagari text, or two or more Hinglish markers with at most one English
    function word, while the call is in English -> switch to Hindi;
  - three or more English function words, no Hinglish markers and no Devanagari,
    while the call is in Hindi -> switch to English.
Code-mixed speech ("Actually kal shaam theek hai") keeps the current language.
"""

from __future__ import annotations

import re

_DEVANAGARI = re.compile(r"[ऀ-ॿ]")
_ASK_HI = re.compile(r"hindi (mein|me|main|please|mai)|speak (in )?hindi|हिंदी में|हिन्दी में", re.I)
_ASK_EN = re.compile(r"(speak|talk|continue|go on)( in)? english|english (please|mein|me|main)|in english\b|अंग्रेज़ी में", re.I)
_HINGLISH = {"haan", "nahi", "nahin", "kya", "hai", "hain", "mein", "kal", "parson", "baje", "ji", "theek", "thik", "accha",
             "acha", "mujhe", "aap", "aapka", "hoon", "ho", "karo", "kar", "chahiye", "dard", "subah", "shaam", "dopahar",
             "bataiye", "boliye", "kab", "kitna", "wala", "wali", "sakte", "skte", "raha", "rahi", "bhi", "abhi", "baad"}
_ENGLISH = {"the", "is", "are", "and", "would", "could", "can", "please", "what", "when", "which", "my", "your", "about",
            "that", "this", "with", "for", "have", "need", "want", "tomorrow", "today", "evening", "morning", "time", "it"}


def detect(text: str, current: str) -> tuple[str | None, bool]:
    """Returns (new_language or None, explicit_request)."""
    t = text or ""
    if _ASK_HI.search(t):
        return ("hi" if current != "hi" else None), True
    if _ASK_EN.search(t):
        return ("en" if current != "en" else None), True
    words = re.findall(r"[a-z']+", t.lower())
    hin = sum(w in _HINGLISH for w in words)
    eng = sum(w in _ENGLISH for w in words)
    mostly_hinglish = hin >= 2 and eng <= 1 and hin >= len(words) / 2
    if current == "en" and (_DEVANAGARI.search(t) or mostly_hinglish):
        return "hi", False
    if current == "hi" and not _DEVANAGARI.search(t) and hin == 0 and eng >= 3:
        return "en", False
    return None, False
