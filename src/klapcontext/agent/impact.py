"""Explain structural impact; it never predicts that a change will break code."""
from __future__ import annotations

from pathlib import Path

from ..context_builder import build
from ..providers.code_intelligence import PhpCodeIntelligenceProvider


def analyze_impact(root: Path, symbol: str) -> dict:
    structural = PhpCodeIntelligenceProvider(root).impact(symbol)
    model = build(root, {"nodes": []})["system_model"]
    callers = structural["direct_callers"] + [{"source_symbol": item, "confidence": "INFERRED"} for item in structural["indirect_callers"]]
    names = {symbol, *(item["source_symbol"] for item in callers)}
    flows = [item for item in model["main_flows"] if any(any(name.endswith(step["name"]) or step["name"].endswith(name) for name in names) for step in item["steps"])]
    entries = [item for item in model["entry_points"] if any(item.get("handler", "").endswith(name) or name.endswith(item.get("handler", "")) for name in names)]
    tests = sorted(set(structural["related_tests"] + [item["path"] for item in model["important_files"] if "test" in item["path"].casefold()]))
    return {"symbol": symbol, "statement": "Elementos potencialmente afectados según relaciones estructurales; no predice fallas.", "direct_callers": structural["direct_callers"], "indirect_callers": structural["indirect_callers"], "entry_points": entries, "flows": flows, "tests": tests, "configuration": [item for item in model["important_files"] if item["path"].startswith("config/")], "integrations": model["external_systems"], "uncertainties": model["unknowns"]}
