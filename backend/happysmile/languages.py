"""Language readiness (Phase 6: "more languages per clinic, based on P0-04 data").

Adding a language touches five places, plus the database. This checker lists what's
missing for a candidate language, so it can be planned and reviewed before any patient
hears it. Usage:

    python -m happysmile.languages            # coverage for every supported language
    python -m happysmile.languages mr         # what's missing to add Marathi

A language goes live only when every item is present, a native speaker has reviewed it,
and the evaluation set has at least 30 scenarios in it (as Hindi did, plan P4-02).
"""

from __future__ import annotations

import sys

SUPPORTED = {"en": "English", "hi": "Hindi"}
CANDIDATES = {"mr": "Marathi", "ta": "Tamil", "te": "Telugu", "bn": "Bengali", "kn": "Kannada", "gu": "Gujarati"}


def coverage(code: str) -> dict:
    from .disclosures import CURRENT
    from .evaluation.scenarios import S
    from .messaging import TEMPLATES, TREATMENT_WORDS
    from .voice.lines import LINES, TREATMENT
    missing = {
        "assistant_lines": sorted(k for k, v in LINES.items() if code not in v),
        "treatment_words": sorted(k for k, v in TREATMENT.items() if code not in v),
        "form_disclosures": sorted(f"{variant}" for variant in ("team", "mixed", "assistant") if (variant, code) not in CURRENT),
        "whatsapp_templates": sorted(k for k, v in TEMPLATES.items() if code not in v["body"]),
        "whatsapp_treatment_words": sorted(k for k, v in TREATMENT_WORDS.items() if code not in v),
    }
    total = len(LINES) + len(TREATMENT) + 3 + len(TEMPLATES) + len(TREATMENT_WORDS)
    have = total - sum(len(v) for v in missing.values())
    scenarios = sum(1 for s in S if s["lead"]["lang"] == code)
    manual = [
        "Understanding keywords (voice/nlu.py: yes/no, days, times, treatments) in this language",
        "Guardrail keywords (voice/guardrails.py: pain, emergency, person, price, clinical, stop) in this language",
        "Language detection markers (voice/language.py)",
        "Database: widen the language CHECK on lead, disclosure_version (new migration)",
        "Form (static/enquiry): add the language option and UI strings",
        "STT/TTS vendor supports it on phone audio (re-run the P0-15 trial)",
        f"Evaluation set: at least 30 scenarios (has {scenarios})",
        "Native-speaker review of every line and template; Meta approval of templates in this language",
    ]
    return {"code": code, "name": SUPPORTED.get(code) or CANDIDATES.get(code, code), "supported": code in SUPPORTED,
            "coverage": round(have / total, 3), "missing": missing, "also_needed": [] if code in SUPPORTED else manual,
            "eval_scenarios": scenarios}


def main(argv: list[str]) -> None:
    codes = argv or list(SUPPORTED)
    for code in codes:
        c = coverage(code)
        print(f"{c['name']} ({code}): {c['coverage']:.0%} of wording present, {c['eval_scenarios']} evaluation scenarios")
        for area, items in c["missing"].items():
            if items:
                print(f"  missing {area}: {len(items)} ({', '.join(items[:6])}{'...' if len(items) > 6 else ''})")
        for x in c["also_needed"]:
            print(f"  also needed: {x}")


if __name__ == "__main__":
    main(sys.argv[1:])
