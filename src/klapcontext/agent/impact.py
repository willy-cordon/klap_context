"""Explain structural impact through shared provider-backed services."""
from __future__ import annotations

from pathlib import Path

from ..providers import AnalysisServices, ResultState
from ..scope import IndexScope


def analyze_impact(root: Path, symbol: str, *, services: AnalysisServices | None = None) -> dict:
    scope = IndexScope.load(root, write_default=False)
    services = services or AnalysisServices(root=root)
    impact_result = services.impact(root, symbol, scope=scope)
    structural = impact_result.data if impact_result.state in {ResultState.OK, ResultState.NO_RESULTS} and isinstance(impact_result.data, dict) else {
        "direct_callers": [], "consumers": [], "relationship_paths": [], "indirect_callers": [], "related_tests": []
    }
    context, _ = services.build_context(root, graph={"nodes": []}, scope=scope, existing_only=True)
    model = context["system_model"]
    callers = structural.get("direct_callers", []) + [{"source_symbol": item, "confidence": "INFERRED"} for item in structural.get("indirect_callers", [])]
    names = {symbol, *(item["source_symbol"] for item in callers)}
    flows = [item for item in model["main_flows"] if any(any(name.endswith(step["name"]) or step["name"].endswith(name) for name in names) for step in item["steps"])]
    entries = [item for item in model["entry_points"] if any(item.get("handler", "").endswith(name) or name.endswith(item.get("handler", "")) for name in names)]
    tests = sorted(set(structural.get("related_tests", []) + [item["path"] for item in model["important_files"] if "test" in item["path"].casefold()]))
    uncertainties = list(model["unknowns"])
    uncertainties.extend(impact_result.limitations)
    if impact_result.state not in {ResultState.OK, ResultState.NO_RESULTS}:
        uncertainties.append(impact_result.error or "Impact analysis provider unavailable.")
    return {
        "symbol": symbol,
        "statement": "Elementos potencialmente afectados según relaciones estructurales; no predice fallas.",
        "status": impact_result.state.value,
        "provider": impact_result.provider.name if impact_result.provider else None,
        "provider_trace": impact_result.trace,
        "warnings": impact_result.warnings,
        "direct_callers": structural.get("direct_callers", []),
        "consumers": structural.get("consumers", []),
        "relationship_paths": structural.get("relationship_paths", []),
        "indirect_callers": structural.get("indirect_callers", []),
        "entry_points": entries,
        "flows": flows,
        "tests": tests,
        "configuration": [item for item in model["important_files"] if item["path"].startswith("config/")],
        "integrations": model["external_systems"],
        "uncertainties": uncertainties,
    }
