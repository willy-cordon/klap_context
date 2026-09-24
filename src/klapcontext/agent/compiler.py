"""Compile a small, explainable agent context from the system model."""
from __future__ import annotations

import json
import re
from pathlib import Path

from .planner import ContextPlanner
from ..context_builder import build

DETAIL_LIMITS = {"minimal": 3, "standard": 6, "deep": 12}


def _terms(query: str, area: str) -> set[str]:
    return {item for item in re.findall(r"[a-zA-Z_]{4,}", f"{query} {area}".casefold()) if item not in {"quiero", "modificar", "cambiar", "sobre", "para"}}


def _rank(items: list[dict], terms: set[str], limit: int) -> list[dict]:
    ranked = []
    for original in items:
        text = json.dumps(original, ensure_ascii=False).casefold(); matches = sum(term in text for term in terms)
        if matches or not terms:
            item = dict(original); item["relevance"] = "directa" if matches else "contextual"; item["reason"] = "Coincide con la tarea" if matches else "Contexto estructural cercano"; ranked.append((matches, item))
    return [item for _, item in sorted(ranked, key=lambda pair: pair[0], reverse=True)[:limit]]


def compile_context(root: Path, query: str, *, detail: str = "standard", max_tokens: int = 5000) -> dict:
    plan = ContextPlanner().plan(query, detail=detail, max_tokens=max_tokens)
    context = build(root, {"nodes": []}); model = context["system_model"]; limit = min(DETAIL_LIMITS[detail], max(1, max_tokens // 350)); terms = _terms(query, plan.area)
    entries = _rank(model["entry_points"], terms, limit); flows = _rank(model["main_flows"], terms, limit); files = _rank(model["important_files"], terms, limit)
    read_first = ([{"path": item.get("file"), "reason": "Punto de entrada relacionado", "relevance": item["relevance"]} for item in entries if item.get("file")] + files)[:limit]
    result = {"intent": plan.intent, "confidence": plan.confidence, "query": query, "area": plan.area, "detail": detail, "max_tokens": max_tokens, "entry_points": entries, "flows": flows, "symbols": _rank(model["semantic_model"]["components"], terms, limit), "files": files, "dependencies": _rank(model["dependencies"], terms, limit), "tests": _rank(context["tests"], terms, limit), "read_first": read_first, "evidence": [evidence for group in entries + flows for evidence in group.get("evidence", [])][:limit], "uncertainties": model["unknowns"], "strategy": plan.strategy}
    result["estimated_tokens"] = min(max_tokens, len(json.dumps(result, ensure_ascii=False)) // 4)
    return result
