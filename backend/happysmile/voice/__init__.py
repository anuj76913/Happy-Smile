"""Voice agent: conversation state machine, understanding, guardrails, tools (architecture §4.5-4.10, §7)."""

# Bump on every change to lines, keywords, understanding, prompts or thresholds, and add a
# matching entry to the rules change log (console Ops -> Change log). Every call records it,
# so metric shifts can be tied to changes (architecture §15.3).
RULES_VERSION = "r5.1"  # r5.1: rules-first merge of LLM understanding; stricter classifier for non-urgent triggers
