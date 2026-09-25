"""Language-neutral, evidence-based navigation of a Graphify code graph."""
from __future__ import annotations

import os
from collections import defaultdict
from pathlib import Path

EXCLUDED = {".git", ".klap", "graphify-out", "node_modules", "vendor", ".venv", "venv", "build", "dist", "__pycache__"}
CODE_EXTENSIONS = {".py", ".php", ".cs", ".js", ".jsx", ".ts", ".tsx", ".java", ".go", ".rs", ".rb", ".kt", ".vue", ".swift", ".cpp", ".c", ".h"}
CALL_RELATIONS = {"calls", "invokes", "dispatches", "calls_method"}
MEMBER_RELATIONS = {"method", "contains", "defines", "has_method", "member"}


def _path(root: Path, value: object) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    raw = value.replace("\\", "/")
    candidate = Path(raw)
    try:
        relative = candidate.resolve().relative_to(root.resolve()) if candidate.is_absolute() else candidate
    except (ValueError, OSError):
        return None
    if ".." in relative.parts or any(part in EXCLUDED for part in relative.parts):
        return None
    return relative.as_posix()


def _edges(graph: dict) -> list[dict]:
    nested = graph.get("graph", {})
    for container in (graph, nested if isinstance(nested, dict) else {}):
        for key in ("links", "edges"):
            if isinstance(container.get(key), list):
                return container[key]
    return []


def inspect(root: Path, graph: dict, semantic: dict, *, max_files: int = 10000) -> dict:
    """Keep source paths and graph relationships intact, with explicit limits."""
    nodes = graph.get("nodes", [])
    if not isinstance(nodes, list):
        nodes = []
    by_id = {str(n["id"]): n for n in nodes if isinstance(n, dict) and n.get("id") is not None}
    files: dict[str, dict] = {}
    for directory, children, names in os.walk(root):
        children[:] = sorted(c for c in children if c not in EXCLUDED)
        for name in sorted(names):
            path = _path(root, str(Path(directory) / name))
            if path:
                files[path] = {"path": path, "symbols": [], "analyzed": False}
            if len(files) >= max_files:
                break
        if len(files) >= max_files:
            break
    eligible = {path for path in files if Path(path).suffix.lower() in CODE_EXTENSIONS}
    analyzed: set[str] = set()
    for node in nodes:
        if not isinstance(node, dict):
            continue
        path = _path(root, node.get("source_file") or node.get("file") or node.get("path"))
        if not path or path not in files:
            continue
        analyzed.add(path)
        symbol = {"id": str(node.get("id", "")), "name": str(node.get("label") or node.get("name") or node.get("id")),
                  "kind": str(node.get("type") or "symbol"), "line": node.get("source_location") or node.get("line"), "source": "graphify"}
        files[path]["symbols"].append(symbol)
    for component in semantic.get("components", []):
        path = _path(root, component.get("file"))
        if path in files and not files[path]["symbols"]:
            files[path]["symbols"].append({"id": component.get("symbol") or component["name"], "name": component["name"], "kind": component.get("type", "symbol"), "line": None, "source": "klap"})
    for path, item in files.items():
        item["analyzed"] = path in analyzed

    graph_edges = _edges(graph)
    members: dict[str, list[dict]] = defaultdict(list)
    calls: dict[str, list[dict]] = defaultdict(list)
    incoming: set[str] = set()
    for edge in graph_edges:
        if not isinstance(edge, dict):
            continue
        source, target = str(edge.get("source", edge.get("from", ""))), str(edge.get("target", edge.get("to", "")))
        if source not in by_id or target not in by_id:
            continue
        relation = str(edge.get("relation") or edge.get("type") or "").lower()
        if relation in MEMBER_RELATIONS:
            members[source].append({"id": target, "name": str(by_id[target].get("label") or target), "relation": relation})
        if relation in CALL_RELATIONS:
            calls[source].append({"id": target, "relation": relation, "confidence": edge.get("confidence", "UNKNOWN")})
            incoming.add(target)
    for file in files.values():
        for symbol in file["symbols"]:
            symbol["members"] = members.get(symbol["id"], [])[:100]

    # These are graph-backed call paths, not claims that an HTTP request invokes them.
    paths = []
    seeds = [key for key in calls if key not in incoming and _path(root, by_id[key].get("source_file")) in eligible]
    for key in sorted(seeds, key=lambda k: str(by_id[k].get("label", k))):
        chain, visited, current = [], set(), key
        while current in by_id and current not in visited and len(chain) < 6:
            visited.add(current)
            node = by_id[current]
            chain.append({"name": str(node.get("label") or current), "file": _path(root, node.get("source_file")), "id": current})
            neighbors = calls.get(current, [])
            if not neighbors:
                break
            current = neighbors[0]["id"]
        if len(chain) > 1:
            paths.append({"name": chain[0]["name"], "steps": chain, "status": "INFERRED", "source": "graphify",
                          "note": "Recorrido de llamadas del grafo; no confirma un punto de entrada ni el orden de otras ramas.",
                          "branches": sum(max(0, len(calls.get(step["id"], [])) - 1) for step in chain)})
        if len(paths) >= 40:
            break
    return {"files": list(files.values()), "call_paths": paths,
            "coverage": {"files_listed": len(files), "eligible_code_files": len(eligible),
                         "code_files_with_graph_nodes": len(eligible & analyzed),
                         "graph_nodes": len(nodes), "graph_edges": len(graph_edges),
                         "truncated": len(files) >= max_files,
                         "status": "PARTIAL" if eligible - analyzed or len(files) >= max_files else "REPRESENTED",
                         "note": "Un nodo en un archivo indica presencia en el grafo, no análisis exhaustivo de todas sus funciones."}}
