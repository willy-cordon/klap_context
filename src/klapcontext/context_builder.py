"""Build a product-level model from framework-neutral semantic evidence."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from .detector import detect_project
from .frameworks.generic_php import GenericPhpAdapter
from .frameworks.laravel import LaravelAdapter
from .git import commit
from .semantic import SemanticModel
from .system import deployment, documents, external_systems, purpose


def _nodes(graph: dict) -> list[dict]:
    return graph.get("nodes", []) if isinstance(graph.get("nodes"), list) else graph.get("graph", {}).get("nodes", [])


def _modules(nodes: list[dict]) -> list[dict]:
    return [{"name": item.get("label") or item.get("name") or item.get("id"), "path": item.get("file") or item.get("path"), "kind": item.get("type", "module"), "description": None, "status": "CONFIRMED", "evidence": []} for item in nodes if (item.get("label") or item.get("name") or item.get("id")) and (item.get("file") or item.get("path"))][:100]


def _runtime(points: list[dict], background: list[dict], frameworks: list[str]) -> dict:
    types = {item["type"].casefold() for item in points}
    modes, descriptions = [], []
    if "http" in types: modes.append("http"); descriptions.append("Las solicitudes HTTP ingresan por las rutas detectadas.")
    if "cli" in types: modes.append("cli"); descriptions.append("La aplicación expone comandos ejecutables.")
    if background: modes.append("scheduler"); descriptions.append("La aplicación declara procesamiento en segundo plano.")
    return {"modes": modes, "layers": frameworks, "description": " ".join(descriptions) or None, "status": "CONFIRMED" if descriptions else "UNKNOWN"}


def _io(points: list[dict], systems: list[dict], stores: list[dict]) -> tuple[list[dict], list[dict]]:
    inputs, outputs, types = [], [], {item["type"].casefold() for item in points}
    if "http" in types:
        inputs.append({"type": "http_request", "description": "Solicitudes HTTP", "status": "CONFIRMED"}); outputs.append({"type": "http_response", "description": "Respuestas HTTP", "status": "INFERRED"})
    if "cli" in types: inputs.append({"type": "cli", "description": "Invocación por línea de comandos", "status": "CONFIRMED"})
    if stores:
        inputs.append({"type": "datastore", "description": "Base de datos", "status": "INFERRED"}); outputs.append({"type": "datastore", "description": "Escrituras de base de datos", "status": "INFERRED"})
    return inputs, outputs


def _flows(model: dict) -> list[dict]:
    """Reconstruct compact flows from generic entry points and transitions only."""
    components = {item.get("symbol") or item["name"]: item for item in model["components"]}
    outgoing: dict[str, list[dict]] = {}
    for edge in model["transitions"]: outgoing.setdefault(edge["source"], []).append(edge)
    flows = []
    for entry in model["entry_points"][:10]:
        steps = [{"name": entry["name"], "kind": entry["type"].casefold(), "path": entry.get("file"), "status": entry["status"]}]
        current = entry["name"]
        if entry.get("handler"):
            steps.append({"name": entry["handler"], "kind": "handler", "path": entry.get("file"), "status": entry["status"]}); current = entry["handler"]
        seen = {entry["name"], current}
        for _ in range(4):
            candidates = outgoing.get(current, []) or [item for source, values in outgoing.items() if source.endswith(current) for item in values]
            edge = next((item for item in candidates if item["target"] not in seen), None)
            if not edge: break
            target = edge["target"]; component = components.get(target, {})
            steps.append({"name": target, "kind": edge["type"].casefold(), "path": component.get("file") or edge.get("file"), "status": edge["status"]})
            seen.add(target); current = target
        if len(steps) > 1:
            status = "CONFIRMED" if all(item["status"] == "CONFIRMED" for item in steps) else "INFERRED"
            flows.append({"name": entry["name"], "trigger": entry["type"].casefold(), "entry_point": entry["name"], "steps": steps, "status": status, "confidence": 1.0 if status == "CONFIRMED" else .7, "evidence": entry["evidence"], "inputs": [], "outputs": [], "external_systems": [], "datastores": [], "tests": []})
    return flows


def _interactions(flows: list[dict], systems: list[dict], stores: list[dict]) -> dict:
    nodes, edges = [], []
    def add(name: str, kind: str):
        if not any(item["name"] == name for item in nodes): nodes.append({"name": name, "type": kind})
    for flow in flows:
        previous = None
        for step in flow["steps"]:
            add(step["name"], step["kind"])
            if previous: edges.append({"source": previous, "target": step["name"], "label": "calls"})
            previous = step["name"]
    for store in stores: add(store["name"], "datastore")
    for system in systems: add(system["name"], "external_system")
    return {"nodes": nodes[:30], "edges": edges[:45], "status": "INFERRED" if edges else "UNKNOWN"}


def _empty_raw() -> dict:
    return {"routes": [], "commands": [], "scheduled_processes": [], "queue_jobs": [], "events": [], "listeners": [], "components": [], "dependencies": [], "runtime_surfaces": [], "important_files": [], "framework": None}


def _semantic(root: Path, stack: dict) -> tuple[SemanticModel, dict]:
    if "Laravel" in stack["frameworks"]:
        model = LaravelAdapter().analyze(root)
        return model, model.metadata["raw"]
    if "PHP" in stack["languages"]: return GenericPhpAdapter().analyze(root), _empty_raw()
    return SemanticModel(stack["languages"][0] if stack["languages"] else None), _empty_raw()


def _analysis_evidence(raw: dict) -> list[dict]:
    seen, result = set(), []
    for group in ("routes", "commands", "scheduled_processes", "queue_jobs", "events", "listeners", "components", "dependencies"):
        for item in raw.get(group, []):
            for evidence in item.get("evidence", []):
                key = (evidence.get("path"), evidence.get("line"), evidence.get("reason"), evidence.get("symbol"))
                if key not in seen: seen.add(key); result.append(evidence)
    return result


def build(root: Path, graph: dict) -> dict:
    stack, detector_evidence = detect_project(root)
    docs = documents(root); value = purpose(root, docs); systems, stores = external_systems(root); deploy, observability, _ = deployment(root)
    semantic, raw = _semantic(root, stack); model = semantic.as_dict(); points, background = model["entry_points"], model["background_tasks"]
    runtime = _runtime(points, background, stack["frameworks"]); inputs, outputs = _io(points, systems, stores); flows = _flows(model)
    important = raw["important_files"] or ([{"path": "README.md", "role": "Documentación", "reason": "README detectado"}] if (root / "README.md").exists() else [])
    tests = [{"path": item, "reason": "Tests detectados"} for item in ("tests", "test", "phpunit.xml", "pytest.ini") if (root / item).exists()]
    story = " ".join(item for item in (value["text"], runtime["description"], "La aplicación está contenerizada con Docker." if "Docker" in deploy["tools"] else None) if item)
    system = {"purpose": value, "project_story": {"text": story or None, "status": "CONFIRMED" if story else "UNKNOWN"}, "runtime": runtime, "framework": raw["framework"], "runtime_surfaces": raw["runtime_surfaces"], "routes": raw["routes"], "commands": raw["commands"], "scheduled_processes": raw["scheduled_processes"], "queue_jobs": raw["queue_jobs"], "events": raw["events"], "listeners": raw["listeners"], "components": raw["components"], "dependencies": raw["dependencies"], "semantic_model": model, "entry_points": points, "main_flows": flows, "system_interactions": _interactions(flows, systems, stores), "capabilities": _modules(_nodes(graph)), "inputs": inputs, "outputs": outputs, "external_systems": systems, "background_processes": background, "datastores": stores, "deployment": deploy, "observability": observability, "important_files": important, "start_here": [], "unknowns": [item for item, found in (("Propósito de negocio del proyecto", value["text"]), ("Plataforma de despliegue en producción", deploy["tools"])) if not found]}
    technical = {"languages": stack["languages"], "frameworks": stack["frameworks"], "framework": raw["framework"], "dependencies": raw["dependencies"], "graph": {"nodes": len(_nodes(graph)), "edges": len(graph.get("edges", graph.get("graph", {}).get("edges", [])))}, "documents": [{"path": item["path"]} for item in docs], "tests": tests, "infrastructure": stack["infrastructure"]}
    project = {"name": root.name, "type": stack["frameworks"][0] if stack["frameworks"] else None, "root": str(root.resolve()), "generated_at": datetime.now(timezone.utc).isoformat(), "git_commit": commit(root)}
    return {"schema_version": "0.5", "project": project, "technical_model": technical, "system_model": system, "semantic_model": model, "human_context": {"purpose": None, "users": None, "important_processes": [], "notes": []}, "stack": stack, "architecture": {"style": "MVC" if "Laravel" in stack["frameworks"] else None, "status": "INFERRED" if "Laravel" in stack["frameworks"] else "UNKNOWN", "confidence": None, "evidence": []}, "entry_points": points, "modules": system["capabilities"], "flows": flows, "api": raw["routes"], "jobs": background, "datastores": stores, "external_systems": systems, "deployment": deploy, "observability": observability, "tests": tests, "evidence": [item.as_dict() for item in detector_evidence] + value["evidence"] + _analysis_evidence(raw)}
