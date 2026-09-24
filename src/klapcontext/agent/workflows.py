"""Agent workflows combine compact context with Git and impact evidence."""
from __future__ import annotations

from pathlib import Path

from .compiler import change_context
from .impact import analyze_impact
from ..git import intelligence
from ..git import dirty_files, run_git


def prepare_change(root: Path, task: str, *, detail: str = "standard", max_tokens: int = 5000) -> dict:
    result = change_context(root, task, detail=detail, max_tokens=max_tokens)
    paths = [item.get("path") for item in result["read_first"] if item.get("path")]
    result["git"] = intelligence(root, paths)
    result["workflow"] = "PREPARE_CHANGE"
    return result


def change_impact(root: Path, symbol: str) -> dict:
    result = analyze_impact(root, symbol); result["git"] = intelligence(root); result["workflow"] = "CHANGE_IMPACT"
    return result


def verify_change(root: Path) -> dict:
    changed = dirty_files(root)
    diff = run_git(root, "diff", "--name-only") or ""
    changed = sorted(set(changed + [line for line in diff.splitlines() if line]))
    context = prepare_change(root, "verificar cambio", detail="minimal", max_tokens=1200)
    tests = [item for item in context["tests"] if item.get("path")]
    return {"workflow": "VERIFY_CHANGE", "changed_files": changed, "related_tests": tests, "potential_risks": context["uncertainties"], "statement": "Hallazgos verificables del diff actual; no aprueba ni rechaza el cambio automáticamente."}
