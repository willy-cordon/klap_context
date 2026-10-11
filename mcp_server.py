"""Small high-level MCP surface for KlapContext."""
from __future__ import annotations

import atexit
from collections import OrderedDict
from pathlib import Path
from threading import Lock
import json

from mcp.server.fastmcp import FastMCP

from klapcontext.agent.compiler import area_context, compile_context, debug_context
from klapcontext.agent.impact import analyze_impact
from klapcontext.agent.workflows import prepare_change
from klapcontext.providers import AnalysisServices

mcp = FastMCP("KlapContext")

def _root(path: str) -> Path: return Path(path).resolve()

_SERVICE_CACHE: OrderedDict[str, AnalysisServices] = OrderedDict()
_SERVICE_CACHE_LOCK = Lock()

def _services(path: str) -> AnalysisServices:
    """Reuse provider sessions (notably Serena stdio) across MCP calls per root."""
    key = str(Path(path).resolve())
    with _SERVICE_CACHE_LOCK:
        service = _SERVICE_CACHE.get(key)
        if service is not None:
            _SERVICE_CACHE.move_to_end(key)
            return service
        service = AnalysisServices(root=Path(key))
        _SERVICE_CACHE[key] = service
        if len(_SERVICE_CACHE) > 8:
            _, evicted = _SERVICE_CACHE.popitem(last=False)
            evicted.close()
        return service

def _close_services() -> None:
    with _SERVICE_CACHE_LOCK:
        services = list(_SERVICE_CACHE.values())
        _SERVICE_CACHE.clear()
    for service in services:
        service.close()

atexit.register(_close_services)

def _bounded(value: int, default: int, maximum: int) -> int:
    try:
        return min(max(int(value), 1), maximum)
    except (TypeError, ValueError):
        return default

def _result(value) -> dict:
    return value.as_dict()

@mcp.tool()
def klap_understand_system(path: str = ".", detail: str = "standard", max_tokens: int = 5000) -> dict:
    return compile_context(_root(path), "understand system", detail=detail, max_tokens=max_tokens)

@mcp.tool()
def klap_understand_area(area: str, path: str = ".", detail: str = "standard", max_tokens: int = 5000) -> dict:
    return area_context(_root(path), area, detail=detail, max_tokens=max_tokens)

@mcp.tool()
def klap_task_context(task: str, path: str = ".", detail: str = "standard", max_tokens: int = 5000) -> dict:
    return compile_context(_root(path), task, detail=detail, max_tokens=max_tokens)

@mcp.tool()
def klap_prepare_change(task: str, path: str = ".", detail: str = "standard", max_tokens: int = 5000) -> dict:
    return prepare_change(_root(path), task, detail=detail, max_tokens=max_tokens)

@mcp.tool()
def klap_change_impact(symbol: str, path: str = ".") -> dict:
    root = _root(path)
    return analyze_impact(root, symbol, services=_services(str(root)))

@mcp.tool()
def klap_search_symbols(query: str, path: str = ".", relative_path: str | None = None, language: str | None = None, max_results: int = 50, max_answer_chars: int = 20000) -> dict:
    """Search symbols on demand through available semantic providers."""
    root = _root(path)
    return _result(_services(str(root)).symbols(root, query, path=relative_path, language=language, max_results=_bounded(max_results, 50, 200), max_answer_chars=_bounded(max_answer_chars, 20000, 100000)))

@mcp.tool()
def klap_find_definition(symbol: str, path: str = ".", relative_path: str | None = None, language: str | None = None, max_results: int = 20, max_answer_chars: int = 20000) -> dict:
    """Find semantic definitions without changing the project."""
    root = _root(path)
    return _result(_services(str(root)).symbols(root, symbol, operation="definition", path=relative_path, language=language, max_results=_bounded(max_results, 20, 100), max_answer_chars=_bounded(max_answer_chars, 20000, 100000)))

@mcp.tool()
def klap_find_references(symbol: str, path: str = ".", relative_path: str | None = None, language: str | None = None, max_results: int = 50, max_answer_chars: int = 20000) -> dict:
    """Return verified static references; behavioral impact is labeled inferred."""
    root = _root(path)
    return _result(_services(str(root)).references(root, symbol, path=relative_path, language=language, max_results=_bounded(max_results, 50, 200), max_answer_chars=_bounded(max_answer_chars, 20000, 100000)))

@mcp.tool()
def klap_find_implementations(symbol: str, path: str = ".", relative_path: str | None = None, language: str | None = None, max_results: int = 50, max_answer_chars: int = 20000) -> dict:
    """Find implementations when a provider advertises that exact operation."""
    root = _root(path)
    return _result(_services(str(root)).implementations(root, symbol, path=relative_path, language=language, max_results=_bounded(max_results, 50, 200), max_answer_chars=_bounded(max_answer_chars, 20000, 100000)))

@mcp.tool()
def klap_dependencies(path: str = ".", language: str | None = None, max_results: int = 100) -> dict:
    root = _root(path)
    result = _services(str(root)).dependencies(root, language=language, max_results=_bounded(max_results, 100, 500))
    payload = result.as_dict()
    if isinstance(payload.get("data"), list):
        payload["data"] = payload["data"][:_bounded(max_results, 100, 500)]
    return payload

@mcp.tool()
def klap_flows_and_endpoints(path: str = ".", max_results: int = 50, max_depth: int = 12) -> dict:
    """Return only precompiled/local static flows and endpoints with explicit bounds."""
    root = _root(path)
    context_path = root / ".klap" / "context.json"
    try:
        context = json.loads(context_path.read_text(encoding="utf-8"))
        source = ".klap/context.json"
    except (OSError, json.JSONDecodeError):
        context, _ = _services(str(root)).build_context(root, existing_only=True)
        source = "on-demand native composition"
    limit = _bounded(max_results, 50, 200)
    depth = _bounded(max_depth, 12, 50)
    flows = []
    for flow in context.get("flows", [])[:limit]:
        item = dict(flow); item["steps"] = list(item.get("steps", []))[:depth]; flows.append(item)
    endpoints = [item for item in context.get("entry_points", []) if item.get("type") == "HTTP"][:limit]
    return {"source": source, "dynamic": False, "flows": flows, "endpoints": endpoints, "limitations": ["The HTML portal and this result contain precompiled static evidence; they do not simulate live Serena queries."]}

@mcp.tool()
def klap_debug_context(task: str, path: str = ".", detail: str = "standard", max_tokens: int = 5000) -> dict:
    return debug_context(_root(path), task, detail=detail, max_tokens=max_tokens)

@mcp.tool()
def klap_get_uncertainties(path: str = ".") -> dict:
    root = _root(path)
    context, _ = _services(str(root)).build_context(root, existing_only=True)
    return {"uncertainties": context["system_model"]["unknowns"]}

if __name__ == "__main__":
    mcp.run()
