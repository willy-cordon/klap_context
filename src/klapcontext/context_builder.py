"""Build the product-level system model from deterministic evidence providers."""
from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path

from .detector import detect_project
from .frameworks.laravel import analyze as analyze_laravel
from .git import commit
from .system import deployment, documents, entry_points, external_systems, purpose


def _nodes(graph: dict) -> list[dict]:
    return graph.get("nodes", []) if isinstance(graph.get("nodes"), list) else graph.get("graph", {}).get("nodes", [])


def _modules(nodes: list[dict]) -> list[dict]:
    return [{"name": node.get("label") or node.get("name") or node.get("id"), "path": node.get("file") or node.get("path"), "kind": node.get("type", "module"), "description": None, "status": "CONFIRMED", "evidence": []} for node in nodes if (node.get("label") or node.get("name") or node.get("id")) and (node.get("file") or node.get("path"))][:100]


def _runtime(points: list[dict], background: list[dict], frameworks: list[str]) -> dict:
    modes, descriptions = [], []
    if any(point["type"] == "http" for point in points): modes.append("http"); descriptions.append("Las solicitudes HTTP ingresan por las rutas detectadas.")
    if any(point["type"] in {"cli", "artisan_command"} for point in points): modes.append("cli"); descriptions.append("La aplicación expone comandos ejecutables.")
    if background: modes.append("scheduler"); descriptions.append("La aplicación declara procesamiento en segundo plano.")
    return {"modes": modes, "layers": frameworks, "description": " ".join(descriptions) or None, "status": "CONFIRMED" if descriptions else "UNKNOWN"}


def _io(points: list[dict], systems: list[dict], stores: list[dict]) -> tuple[list[dict], list[dict]]:
    inputs, outputs = [], []
    if any(point["type"] == "http" for point in points):
        inputs.append({"type": "http_request", "description": "Solicitudes HTTP", "status": "CONFIRMED"})
        outputs.append({"type": "http_response", "description": "Respuestas HTTP", "status": "INFERRED"})
    if any(point["type"] in {"cli", "artisan_command"} for point in points): inputs.append({"type": "cli", "description": "Invocación por línea de comandos", "status": "CONFIRMED"})
    if stores:
        inputs.append({"type": "datastore", "description": "Base de datos", "status": "INFERRED"})
        outputs.append({"type": "datastore", "description": "Escrituras de base de datos", "status": "INFERRED"})
    return inputs, outputs


def _flows(root: Path, laravel: dict, stores: list[dict], systems: list[dict]) -> list[dict]:
    flows = []
    for route in laravel["routes"][:8]:
        steps = [{"name": route["name"], "kind": "route", "path": route["source"], "status": "CONFIRMED"}]
        if route.get("target"):
            steps.append({"name": route["target"], "kind": "controller", "path": route["source"], "status": "CONFIRMED"})
            controller = root / "app" / "Http" / "Controllers" / (route["target"].split("::")[0] + ".php")
            if controller.exists():
                names = re.findall(r"\b(\w*(?:Service|Repository))\b", controller.read_text(encoding="utf-8", errors="replace"))
                if names: steps.append({"name": names[0], "kind": "service", "path": str(controller.relative_to(root)), "status": "INFERRED"})
        if stores: steps.append({"name": stores[0]["name"], "kind": "datastore", "path": None, "status": "INFERRED"})
        elif systems: steps.append({"name": systems[0]["name"], "kind": "external_system", "path": None, "status": "INFERRED"})
        if len(steps) > 1:
            status = "CONFIRMED" if all(step["status"] == "CONFIRMED" for step in steps) else "INFERRED"
            flows.append({"name": route["name"], "trigger": "http", "entry_point": route["name"], "steps": steps, "status": status, "confidence": 1.0 if status == "CONFIRMED" else .7, "evidence": route["evidence"], "inputs": [], "outputs": [], "external_systems": [], "datastores": [], "tests": []})
    for command in laravel["scheduled_processes"][:3]:
        flows.append({"name": command["name"], "trigger": "scheduler", "entry_point": command["name"], "steps": [{"name": "Scheduler", "kind": "scheduler", "path": command["path"], "status": "CONFIRMED"}, {"name": command["name"], "kind": "command", "path": command["path"], "status": "CONFIRMED"}], "status": "CONFIRMED", "confidence": 1.0, "evidence": command["evidence"], "inputs": [], "outputs": [], "external_systems": [], "datastores": [], "tests": []})
    return flows[:10]


def _interactions(flows: list[dict], systems: list[dict], stores: list[dict]) -> dict:
    nodes, edges = [], []
    def add_node(name, kind):
        if not any(item["name"] == name for item in nodes): nodes.append({"name": name, "type": kind})
    for flow in flows:
        previous = None
        for step in flow["steps"]:
            add_node(step["name"], step["kind"])
            if previous: edges.append({"source": previous, "target": step["name"], "label": "uses" if step["kind"] in {"datastore", "external_system"} else "calls"})
            previous = step["name"]
    for store in stores: add_node(store["name"], "datastore")
    for system in systems: add_node(system["name"], "external_system")
    return {"nodes": nodes[:30], "edges": edges[:45], "status": "INFERRED" if edges else "UNKNOWN"}


def _start(root: Path, laravel: dict, systems: list[dict]) -> list[dict]:
    result = []
    for path, intent in (("routes/api.php", "Entender la API"), ("routes/web.php", "Entender las rutas web"), ("routes/console.php", "Entender procesamiento programado"), ("composer.json", "Entender dependencias"), ("config/database.php", "Entender acceso a datos")):
        if (root / path).exists(): result.append({"intent": intent, "paths": [path], "reason": "Archivo Laravel relevante detectado"})
    if systems: result.append({"intent": "Entender integraciones", "paths": sorted({path for system in systems for path in system["configuration"]}), "reason": "Sistemas externos detectados"})
    return result


def _analysis_evidence(laravel: dict) -> list[dict]:
    seen, result = set(), []
    for group in ("routes", "commands", "scheduled_processes", "queue_jobs", "events", "listeners", "components", "dependencies"):
        for item in laravel.get(group, []):
            for evidence in item.get("evidence", []):
                key = (evidence.get("path"), evidence.get("line"), evidence.get("reason"), evidence.get("symbol"))
                if key not in seen: seen.add(key); result.append(evidence)
    return result


def build(root: Path, graph: dict) -> dict:
    stack, detector_evidence = detect_project(root)
    docs = documents(root); value = purpose(root, docs)
    systems, stores = external_systems(root); deploy, observability, _ = deployment(root)
    empty_laravel = {"routes": [], "commands": [], "scheduled_processes": [], "queue_jobs": [], "events": [], "listeners": [], "components": [], "dependencies": [], "runtime_surfaces": [], "important_files": [], "framework": None}
    laravel = analyze_laravel(root) if "Laravel" in stack["frameworks"] else empty_laravel
    generic_points, generic_background = entry_points(root)
    points = laravel["routes"] + laravel["commands"] + laravel["queue_jobs"] + laravel["listeners"] or generic_points
    background = laravel["scheduled_processes"] + laravel["queue_jobs"] or generic_background
    runtime = _runtime(points, background, stack["frameworks"])
    inputs, outputs = _io(points, systems, stores)
    flows = _flows(root, laravel, stores, systems) if laravel["routes"] else []
    important = laravel["important_files"] or ([{"path": "README.md", "role": "Documentación", "reason": "README detectado"}] if (root / "README.md").exists() else [])
    tests = [{"path": path, "reason": "Tests detectados"} for path in ("tests", "test", "phpunit.xml", "pytest.ini") if (root / path).exists()]
    story = " ".join(item for item in (value["text"], runtime["description"], "La aplicación está contenerizada con Docker." if "Docker" in deploy["tools"] else None) if item)
    system = {"purpose": value, "project_story": {"text": story or None, "status": "CONFIRMED" if story else "UNKNOWN"}, "runtime": runtime, "framework": laravel["framework"], "runtime_surfaces": laravel["runtime_surfaces"], "routes": laravel["routes"], "commands": laravel["commands"], "scheduled_processes": laravel["scheduled_processes"], "queue_jobs": laravel["queue_jobs"], "events": laravel["events"], "listeners": laravel["listeners"], "components": laravel["components"], "dependencies": laravel["dependencies"], "entry_points": points, "main_flows": flows, "system_interactions": _interactions(flows, systems, stores), "capabilities": _modules(_nodes(graph)), "inputs": inputs, "outputs": outputs, "external_systems": systems, "background_processes": background, "datastores": stores, "deployment": deploy, "observability": observability, "important_files": important, "start_here": _start(root, laravel, systems), "unknowns": [item for item, found in (("Propósito de negocio del proyecto", value["text"]), ("Plataforma de despliegue en producción", deploy["tools"])) if not found]}
    technical = {"languages": stack["languages"], "frameworks": stack["frameworks"], "framework": laravel["framework"], "dependencies": laravel["dependencies"], "graph": {"nodes": len(_nodes(graph)), "edges": len(graph.get("edges", graph.get("graph", {}).get("edges", [])))}, "documents": [{"path": doc["path"]} for doc in docs], "tests": tests, "infrastructure": stack["infrastructure"]}
    project = {"name": root.name, "type": stack["frameworks"][0] if stack["frameworks"] else None, "root": str(root.resolve()), "generated_at": datetime.now(timezone.utc).isoformat(), "git_commit": commit(root)}
    return {"schema_version": "0.4", "project": project, "technical_model": technical, "system_model": system, "human_context": {"purpose": None, "users": None, "important_processes": [], "notes": []}, "stack": stack, "architecture": {"style": "MVC" if "Laravel" in stack["frameworks"] else None, "status": "INFERRED" if "Laravel" in stack["frameworks"] else "UNKNOWN", "confidence": None, "evidence": []}, "entry_points": points, "modules": system["capabilities"], "flows": flows, "api": laravel["routes"], "jobs": background, "datastores": stores, "external_systems": systems, "deployment": deploy, "observability": observability, "tests": tests, "evidence": [item.as_dict() for item in detector_evidence] + value["evidence"] + _analysis_evidence(laravel)}
