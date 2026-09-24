"""Small high-level MCP surface for KlapContext."""
from __future__ import annotations

from pathlib import Path

from mcp.server.fastmcp import FastMCP

from klapcontext.agent.compiler import area_context, compile_context, debug_context
from klapcontext.agent.impact import analyze_impact
from klapcontext.agent.workflows import prepare_change
from klapcontext.context_builder import build

mcp = FastMCP("KlapContext")

def _root(path: str) -> Path: return Path(path).resolve()

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
    return analyze_impact(_root(path), symbol)

@mcp.tool()
def klap_debug_context(task: str, path: str = ".", detail: str = "standard", max_tokens: int = 5000) -> dict:
    return debug_context(_root(path), task, detail=detail, max_tokens=max_tokens)

@mcp.tool()
def klap_get_uncertainties(path: str = ".") -> dict:
    return {"uncertainties": build(_root(path), {"nodes": []})["system_model"]["unknowns"]}

if __name__ == "__main__":
    mcp.run()
