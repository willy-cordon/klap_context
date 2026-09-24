"""Normalize evidence and prevent secrets from entering agent output."""
from __future__ import annotations

import re

SECRET = re.compile(r"(?i)(password|secret|token|api[_-]?key|private[_-]?key)\s*[:=]\s*[^\s,]+")

def sanitize(value):
    if isinstance(value, str): return SECRET.sub(lambda match: match.group(1) + "=[REDACTED]", value)
    if isinstance(value, list): return [sanitize(item) for item in value]
    if isinstance(value, dict): return {key: sanitize(item) for key, item in value.items() if key.casefold() not in {"password", "secret", "token", "api_key", "private_key"}}
    return value

def reconcile(evidence: list[dict]) -> dict:
    unique, seen = [], set()
    for item in evidence:
        clean = sanitize(item); key = (clean.get("path"), clean.get("line"), clean.get("symbol"), clean.get("reason"))
        if key not in seen: seen.add(key); unique.append(clean)
    return {"evidence": unique, "conflicts": [], "status": "CONFIRMED" if unique else "UNKNOWN"}
