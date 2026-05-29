#!/usr/bin/env python3
"""
Natural language → structured config extractor.

Deterministic: uses regex + keyword matching only (no LLM API calls).
Called by SKILL.md when the user invokes /paywire with a text argument.

Usage:
    python3 parse_intent.py "add tiered subscriptions with a 14-day free trial"
    # Output: {"pricing_model": "tiered", "trial_days": 14}

Only outputs keys that were confidently extracted.
SKILL.md merges this with defaults and asks the user only for the gaps.
"""

import json
import re
import sys
from typing import Any


PRICING_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\bone[- ]time\b|\bsingle[- ]payment\b|\bone[- ]off\b", re.I), "one_time"),
    (re.compile(r"\busage[- ]based\b|\bmetered\b|\bpay[- ]as[- ]you[- ]go\b", re.I), "usage"),
    (re.compile(r"\btiered?\b|\bmulti[- ]tier\b|\bplans?\b", re.I), "tiered"),
    (re.compile(r"\bper[- ]seat\b|\bper[- ]user\b|\bper[- ]member\b", re.I), "per_seat"),
    (re.compile(r"\bsubscri(?:ption|be)\b|\bmonthly\b|\bannual(?:ly)?\b|\brecurring\b", re.I), "subscription"),
]

TRIAL_DAYS_PATTERN = re.compile(
    r"(\d+)[- ]day(?:s)?\s+(?:free\s+)?trial"
    r"|free\s+trial\s+(?:of\s+)?(\d+)\s+days?"
    r"|(no|without)[- ]trial",
    re.I,
)

CURRENCY_PATTERN = re.compile(r"\b(USD|EUR|GBP|CAD|AUD|JPY|CHF|SEK|NOK|DKK)\b", re.I)

CONNECT_PATTERN = re.compile(
    r"\bconnect\b|\bmarketplace\b|\bplatform\b|\bpayout\b|\bsplit[- ]payment\b", re.I
)

FRAMEWORK_PATTERN = re.compile(
    r"\b(fastapi|django|flask|express|next\.?js|rails)\b", re.I
)

FRAMEWORK_ALIASES = {
    "nextjs": "nextjs",
    "next.js": "nextjs",
    "next": "nextjs",
}


def extract(text: str) -> dict[str, Any]:
    result: dict[str, Any] = {}

    # Pricing model — use the first confident match.
    for pattern, model in PRICING_PATTERNS:
        if pattern.search(text):
            result["pricing_model"] = model
            break

    # Trial days.
    m = TRIAL_DAYS_PATTERN.search(text)
    if m:
        if m.group(3):  # "no trial" / "without trial"
            result["trial_days"] = 0
        else:
            days_str = m.group(1) or m.group(2)
            result["trial_days"] = int(days_str)

    # Currencies.
    currencies = [c.lower() for c in CURRENCY_PATTERN.findall(text)]
    if currencies:
        result["currencies"] = sorted(set(currencies))

    # Connect / marketplace.
    if CONNECT_PATTERN.search(text):
        result["with_connect"] = True

    # Framework.
    m = FRAMEWORK_PATTERN.search(text)
    if m:
        fw = m.group(1).lower().replace(".", "")
        result["framework"] = FRAMEWORK_ALIASES.get(fw, fw)

    return result


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("{}", flush=True)
        sys.exit(0)

    user_text = " ".join(sys.argv[1:])
    extracted = extract(user_text)
    print(json.dumps(extracted, indent=2))
