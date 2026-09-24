"""Deterministic Laravel conventions analyzer; Graphify remains the code graph."""
from __future__ import annotations

import json
import re
from pathlib import Path

from ..evidence import Evidence, from_match
from ..providers.code_intelligence import PhpCodeIntelligenceProvider
from ..semantic import EntryPoint, ExecutionTransition, SemanticComponent, SemanticModel


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _symbol(target: str) -> str | None:
    match = re.search(r"(?:\[\s*)?([A-Za-z_]\w*(?:\\[A-Za-z_]\w*)*)::class\s*,\s*['\"](\w+)['\"]", target)
    return f"{match.group(1).split('\\')[-1]}::{match.group(2)}" if match else None


def _e(root: Path, path: Path, offset: int, reason: str, *, symbol: str | None = None, status: str = "CONFIRMED") -> list[dict]:
    return [from_match(root, path, offset, reason, symbol=symbol, status=status).as_dict()]


def _category(package: str) -> str:
    package = package.lower()
    if package == "laravel/framework": return "framework"
    if any(token in package for token in ("mysql", "postgres", "mongodb", "redis", "doctrine/dbal")): return "database"
    if any(token in package for token in ("queue", "horizon", "rabbit", "kafka")): return "queue"
    if any(token in package for token in ("jwt", "sanctum", "passport", "auth")): return "authentication"
    if any(token in package for token in ("guzzle", "http", "curl", "soap")): return "http"
    if any(token in package for token in ("sentry", "telescope", "prometheus", "opentelemetry")): return "observability"
    if any(token in package for token in ("phpunit", "pest", "faker")): return "testing"
    if any(token in package for token in ("flysystem", "s3", "filesystem")): return "storage"
    return "other"


def _composer(root: Path) -> tuple[list[dict], dict]:
    composer = root / "composer.json"
    if not composer.exists():
        return [], {"laravel": None, "php": None}
    try:
        data = json.loads(_read(composer))
    except json.JSONDecodeError:
        return [], {"laravel": None, "php": None}
    dependencies = []
    for scope, key in (("runtime", "require"), ("development", "require-dev")):
        for package, version in data.get(key, {}).items():
            evidence = Evidence("manifest", "composer.json", f"Dependencia Composer ({scope})", "CONFIRMED", 1.0, symbol=package).as_dict()
            dependencies.append({"package": package, "version": version, "scope": scope, "category": _category(package), "status": "CONFIRMED", "evidence": [evidence]})
    requirements = data.get("require", {})
    return dependencies, {"laravel": requirements.get("laravel/framework"), "php": requirements.get("php")}


def _routes(root: Path) -> tuple[list[dict], list[dict]]:
    routes, scheduled = [], []
    directory = root / "routes"
    if not directory.is_dir():
        return routes, scheduled
    route_pattern = re.compile(r"Route::(get|post|put|patch|delete|options|any)\s*\(\s*['\"]([^'\"]+)['\"]\s*,\s*(.+?)\);", re.S | re.I)
    resource_pattern = re.compile(r"Route::(?:api)?resource\s*\(\s*['\"]([^'\"]+)['\"]\s*,\s*([A-Za-z_]\w*(?:\\[A-Za-z_]\w*)*)::class", re.I)
    schedule_pattern = re.compile(r"Schedule::(?:command|job)\s*\(\s*['\"]([^'\"]+)['\"]\s*\).*?->([A-Za-z]\w*)\s*\(", re.S)
    for file in directory.glob("*.php"):
        text = _read(file)
        for match in route_pattern.finditer(text):
            method, uri, target = match.groups()
            handler = _symbol(target)
            name = f"{method.upper()} /{uri.lstrip('/')}"
            routes.append({"type": "http", "method": method.upper(), "uri": "/" + uri.lstrip("/"), "name": name, "path": str(file.relative_to(root)), "source": str(file.relative_to(root)), "line": text.count("\n", 0, match.start()) + 1, "target": handler, "handler": handler, "middleware": [], "status": "CONFIRMED", "evidence": _e(root, file, match.start(), "Declaración de ruta Laravel", symbol=name)})
        for match in resource_pattern.finditer(text):
            resource, controller = match.groups()
            name = f"RESOURCE /{resource.lstrip('/')}"
            routes.append({"type": "http", "method": "RESOURCE", "uri": "/" + resource.lstrip("/"), "name": name, "path": str(file.relative_to(root)), "source": str(file.relative_to(root)), "line": text.count("\n", 0, match.start()) + 1, "target": controller.split("\\")[-1], "handler": controller.split("\\")[-1], "middleware": [], "status": "INFERRED", "evidence": _e(root, file, match.start(), "Declaración resource de Laravel", symbol=name, status="INFERRED")})
        if file.name == "console.php":
            for match in schedule_pattern.finditer(text):
                command, frequency = match.groups()
                scheduled.append({"name": command, "type": "scheduled_command", "schedule": frequency, "path": str(file.relative_to(root)), "line": text.count("\n", 0, match.start()) + 1, "status": "CONFIRMED", "evidence": _e(root, file, match.start(), "Comando programado de Laravel", symbol=command)})
    return routes, scheduled


def _scheduled_kernel(root: Path) -> list[dict]:
    kernel = root / "app" / "Console" / "Kernel.php"
    if not kernel.exists():
        return []
    text = _read(kernel)
    pattern = re.compile(r"\$schedule->(?:command|job)\s*\(\s*['\"]([^'\"]+)['\"]\s*\).*?->([A-Za-z]\w*)\s*\(", re.S)
    return [{"name": match.group(1), "type": "scheduled_command", "schedule": match.group(2), "path": str(kernel.relative_to(root)), "line": text.count("\n", 0, match.start()) + 1, "status": "CONFIRMED", "evidence": _e(root, kernel, match.start(), "Scheduler de Laravel", symbol=match.group(1))} for match in pattern.finditer(text)]


def _classes(root: Path, folder: str, kind: str, predicate=None) -> list[dict]:
    directory = root / folder
    if not directory.is_dir():
        return []
    result = []
    for file in directory.rglob("*.php"):
        text = _read(file)
        if predicate and not predicate(text):
            continue
        name = file.stem
        match = re.search(r"\bclass\s+(\w+)", text)
        if match:
            name = match.group(1)
        result.append({"name": name, "type": kind, "path": str(file.relative_to(root)), "line": text.count("\n", 0, match.start()) + 1 if match else 1, "status": "CONFIRMED", "evidence": _e(root, file, match.start() if match else 0, f"Clase Laravel de tipo {kind}", symbol=name)})
    return result


def analyze(root: Path) -> dict:
    routes, scheduled = _routes(root)
    scheduled.extend(_scheduled_kernel(root))
    dependencies, versions = _composer(root)
    commands = _classes(root, "app/Console/Commands", "artisan_command")
    for command in commands:
        text = _read(root / command["path"])
        signature = re.search(r"(?:protected|public)\s+\$signature\s*=\s*['\"]([^'\"]+)", text)
        if signature:
            command["name"] = signature.group(1)
            command["evidence"] = _e(root, root / command["path"], signature.start(), "Firma de comando Artisan", symbol=command["name"])
    jobs = _classes(root, "app/Jobs", "queue_job", lambda text: "ShouldQueue" in text)
    for job in jobs:
        text = _read(root / job["path"])
        queue = re.search(r"(?:public|protected)\s+\$queue\s*=\s*['\"]([^'\"]+)", text)
        job["queue"] = queue.group(1) if queue else None
    events = _classes(root, "app/Events", "event")
    listeners = _classes(root, "app/Listeners", "listener")
    components = []
    for folder, kind in (("app/Http/Controllers", "controller"), ("app/Http/Middleware", "middleware"), ("app/Services", "service"), ("app/Repositories", "repository"), ("app/Models", "model"), ("database/migrations", "migration"), ("database/seeders", "seeder")):
        components.extend(_classes(root, folder, kind))
    important = []
    for path, role in (("routes/api.php", "Rutas HTTP API"), ("routes/web.php", "Rutas web"), ("routes/console.php", "Programación de comandos"), ("routes/channels.php", "Canales de broadcast"), ("app/Console/Kernel.php", "Scheduler Laravel"), ("config/database.php", "Configuración de datos"), ("config/services.php", "Configuración de integraciones"), (".env.example", "Variables de entorno documentadas"), ("composer.json", "Dependencias PHP")):
        if (root / path).exists():
            important.append({"path": path, "role": role, "reason": f"{role} detectado"})
    surfaces = []
    for kind, label, values in (("http", "HTTP", routes), ("cli", "CLI", commands), ("scheduler", "Scheduler", scheduled), ("queue", "Queue", jobs), ("event", "Eventos", events), ("listener", "Listeners", listeners)):
        if values:
            surfaces.append({"type": kind, "label": label, "count": len(values), "items": values})
    return {"framework": {"name": "Laravel", "version": versions["laravel"], "php_version": versions["php"], "status": "CONFIRMED", "evidence": [Evidence("manifest", "composer.json", "laravel/framework declarado", "CONFIRMED", 1.0, symbol="laravel/framework").as_dict()]}, "routes": routes, "commands": commands, "scheduled_processes": scheduled, "queue_jobs": jobs, "events": events, "listeners": listeners, "components": components, "dependencies": dependencies, "runtime_surfaces": surfaces, "important_files": important}


class LaravelAdapter:
    """Translate Laravel conventions into the shared semantic vocabulary."""

    name = "Laravel"

    def detect(self, root: Path) -> bool:
        return (root / "composer.json").exists() and "laravel/framework" in _read(root / "composer.json")

    def analyze(self, root: Path) -> SemanticModel:
        raw = analyze(root)
        components = [SemanticComponent(item["name"], item["type"], item["path"], item["name"], item["status"], item["evidence"]) for item in raw["components"] + raw["queue_jobs"] + raw["events"] + raw["listeners"]]
        entries = []
        transitions = []
        for route in raw["routes"]:
            entries.append(EntryPoint("HTTP", route["name"], route.get("target"), "HTTP", route.get("method"), route.get("uri"), route["path"], route["line"], "Laravel", route["status"], route["evidence"]))
            if route.get("target"):
                transitions.append(ExecutionTransition(route["name"], route["target"], "HTTP_ENTRY", route["path"], route["line"], route["status"], "laravel", route["evidence"]))
        for command in raw["commands"]:
            entries.append(EntryPoint("CLI", command["name"], command["name"], file=command["path"], line=command["line"], framework="Laravel", status=command["status"], evidence=command["evidence"]))
        for scheduled in raw["scheduled_processes"]:
            entries.append(EntryPoint("SCHEDULED", scheduled["name"], scheduled["name"], file=scheduled["path"], line=scheduled["line"], framework="Laravel", status=scheduled["status"], evidence=scheduled["evidence"]))
            transitions.append(ExecutionTransition("Scheduler", scheduled["name"], "SCHEDULED_ENTRY", scheduled["path"], scheduled["line"], scheduled["status"], "laravel", scheduled["evidence"], {"schedule": scheduled.get("schedule")}))
        for job in raw["queue_jobs"]:
            entries.append(EntryPoint("QUEUE", job["name"], f"{job['name']}::handle", file=job["path"], line=job["line"], framework="Laravel", status=job["status"], evidence=job["evidence"]))

        # Structural calls are language-level evidence; Laravel gives the framework
        # meaning to dispatch and HTTP client conventions without leaking that meaning
        # into consumers of this model.
        index = PhpCodeIntelligenceProvider(root).index()
        for relation in index["relations"]:
            transition_type = "CALL" if relation["relation"] == "CALLS" else relation["relation"]
            target = relation["target_symbol"]
            expression = relation.get("metadata", {}).get("expression", "")
            if target.endswith("::dispatch"):
                transition_type = "QUEUE_DISPATCH"
                target = target.rsplit("::", 1)[0]
            elif target.startswith("Http::") or "Http::" in expression:
                transition_type = "EXTERNAL_CALL"
            evidence = [Evidence("code", relation["file"], "Relación estructural PHP", relation["confidence"], 1.0 if relation["confidence"] == "CONFIRMED" else .7, line=relation["line"], symbol=relation["source_symbol"]).as_dict()]
            transitions.append(ExecutionTransition(relation["source_symbol"], target, transition_type, relation["file"], relation["line"], relation["confidence"], relation["provider"], evidence, relation.get("metadata", {})))
        return SemanticModel("PHP", "Laravel", "FRAMEWORK", components, entries, transitions, raw["scheduled_processes"] + raw["queue_jobs"], {"raw": raw})
