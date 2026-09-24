"""Agent workflows combine compact context with Git and impact evidence."""
from __future__ import annotations

from pathlib import Path

from .compiler import change_context
from .impact import analyze_impact
from ..git import intelligence


def prepare_change(root: Path, task: str, *, detail: str = "standard", max_tokens: int = 5000) -> dict:
    result = change_context(root, task, detail=detail, max_tokens=max_tokens)
    paths = [item.get("path") for item in result["read_first"] if item.get("path")]
    result["git"] = intelligence(root, paths)
    result["workflow"] = "PREPARE_CHANGE"
    return result


def change_impact(root: Path, symbol: str) -> dict:
    result = analyze_impact(root, symbol); result["git"] = intelligence(root); result["workflow"] = "CHANGE_IMPACT"
    return result
