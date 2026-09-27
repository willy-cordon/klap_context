"""Deterministic Laravel conventions analyzer; Graphify remains the code graph."""
from __future__ import annotations

import json
import re
from pathlib import Path

from ..evidence import Evidence, from_match
from ..providers.code_intelligence import PhpCodeIntelligenceProvider
from ..semantic import BackgroundTask, Dependency, EntryPoint, Event, EventHandler, ExecutionTransition, SemanticComponent, SemanticModel
from ..scope import IndexScope


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _symbol(target: str) -> str | None:
    match = re.search(r"(?:\[\s*)?([A-Za-z_]\w*(?:\\[A-Za-z_]\w*)*)::class\s*,\s*['\"](\w+)['\"]", target)
    if not match:
        return None
    class_name = match.group(1).rsplit("\\", 1)[-1]
    return f"{class_name}::{match.group(2)}"


def _e(root: Path, path: Path, offset: int, reason: str, *, symbol: str | None = None, status: str = "CONFIRMED") -> list[dict]:
    return [from_match(root, path, offset, reason, symbol=symbol, status=status).as_dict()]


def _category(package: str) -> str:
    package = package.lower()
    if package in {"laravel/framework", "laravel/lumen-framework"}: return "framework"
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
        return [], {"framework": None, "package": None, "version": None, "php": None}
    try:
        data = json.loads(_read(composer))
    except json.JSONDecodeError:
        return [], {"framework": None, "package": None, "version": None, "php": None}
    dependencies = []
    for scope, key in (("runtime", "require"), ("development", "require-dev")):
        for package, version in data.get(key, {}).items():
            evidence = Evidence("manifest", "composer.json", f"Dependencia Composer ({scope})", "CONFIRMED", 1.0, symbol=package).as_dict()
            dependencies.append({"package": package, "version": version, "scope": scope, "category": _category(package), "status": "CONFIRMED", "evidence": [evidence]})
    requirements = data.get("require", {})
    package = "laravel/lumen-framework" if "laravel/lumen-framework" in requirements else "laravel/framework" if "laravel/framework" in requirements else None
    return dependencies, {"framework": "Lumen" if package == "laravel/lumen-framework" else "Laravel" if package else None, "package": package, "version": requirements.get(package) if package else None, "php": requirements.get("php")}


def _group_spans(text: str) -> list[tuple[int, int, str, list[str]]]:
    """Return Lumen/Laravel route-group bodies with their inherited metadata."""
    pattern = re.compile(r"(?:\$router|\$app|Route)->group\s*\(\s*\[(.*?)\]\s*,\s*function\s*\([^)]*\)\s*(?:use\s*\([^)]*\)\s*)?\{", re.S)
    groups = []
    for match in pattern.finditer(text):
        opening = match.end() - 1
        depth, closing = 0, None
        for index in range(opening, len(text)):
            if text[index] == "{": depth += 1
            elif text[index] == "}":
                depth -= 1
                if depth == 0:
                    closing = index
                    break
        if closing is None:
            continue
        options = match.group(1)
        prefix_match = re.search(r"['\"]prefix['\"]\s*=>\s*['\"]([^'\"]*)['\"]", options)
        middleware_match = re.search(r"['\"]middleware['\"]\s*=>\s*(\[[^\]]*\]|['\"][^'\"]*['\"])", options, re.S)
        middleware = re.findall(r"['\"]([^'\"]+)['\"]", middleware_match.group(1)) if middleware_match else []
        groups.append((opening, closing, prefix_match.group(1) if prefix_match else "", middleware))
    return groups


def _comment_spans(text: str, *, include_strings: bool = True) -> list[tuple[int, int]]:
    """Offsets covered by comments and, optionally, string literals using PHP AST."""
    try:
        from tree_sitter import Language, Parser
        import tree_sitter_php

        source = text.encode("utf-8")
        tree = Parser(Language(tree_sitter_php.language_php())).parse(source)
        spans = []
        stack = [tree.root_node]
        inactive_types = {"comment"}
        if include_strings:
            inactive_types.update({"string", "encapsed_string", "heredoc", "nowdoc"})
        while stack:
            node = stack.pop()
            if node.type in inactive_types:
                start = len(source[:node.start_byte].decode("utf-8", errors="replace"))
                end = len(source[:node.end_byte].decode("utf-8", errors="replace"))
                spans.append((start, end))
                continue
            stack.extend(node.children)
        return spans
    except (ImportError, ValueError):
        # Conservative fallback for environments where optional parsing is not
        # available. The package normally ships tree-sitter-php.
        return [(match.start(), match.end()) for match in re.finditer(r"//[^\n]*|\#[^\n]*|/\*.*?\*/", text, re.S)]


def _active(offset: int, spans: list[tuple[int, int]]) -> bool:
    return not any(start <= offset < end for start, end in spans)


def _code_only(text: str) -> str:
    chars = list(text)
    for start, end in _comment_spans(text, include_strings=False):
        for index in range(start, min(end, len(chars))):
            if chars[index] != "\n":
                chars[index] = " "
    return "".join(chars)


def _routes(root: Path) -> tuple[list[dict], list[dict], list[dict]]:
    routes, scheduled, disabled = [], [], []
    directory = root / "routes"
    if not directory.is_dir():
        return routes, scheduled, disabled
    route_pattern = re.compile(r"(?:Route|\$app|\$router)(?:::|->)(get|post|put|patch|delete|options|any)\s*\(\s*['\"]([^'\"]+)['\"]\s*,\s*(.+?)\);", re.S | re.I)
    resource_pattern = re.compile(r"Route::(?:api)?resource\s*\(\s*['\"]([^'\"]+)['\"]\s*,\s*([A-Za-z_]\w*(?:\\[A-Za-z_]\w*)*)::class", re.I)
    schedule_pattern = re.compile(r"Schedule::(?:command|job)\s*\(\s*['\"]([^'\"]+)['\"]\s*\)([^;]*);", re.S)
    for file in directory.glob("*.php"):
        text = _read(file)
        groups = _group_spans(text)
        comments = _comment_spans(text)
        for match in route_pattern.finditer(text):
            if not _active(match.start(), comments):
                disabled.append({"kind": "route", "path": str(file.relative_to(root)), "line": text.count("\n", 0, match.start()) + 1, "status": "commented_or_disabled"})
                continue
            method, uri, target = match.groups()
            handler = _symbol(target)
            if not handler:
                callback = re.search(r"['\"]([A-Za-z_]\w*)@([A-Za-z_]\w*)['\"]", target)
                handler = f"{callback.group(1)}::{callback.group(2)}" if callback else None
            active = [group for group in groups if group[0] < match.start() < group[1]]
            prefix = "/".join(group[2].strip("/") for group in active if group[2])
            middleware = [name for group in active for name in group[3]]
            full_uri = "/" + "/".join(part for part in (prefix, uri.strip("/")) if part)
            name = f"{method.upper()} {full_uri}"
            framework = "Lumen" if "lumen-framework" in _read(root / "composer.json") else "Laravel"
            routes.append({"type": "http", "method": method.upper(), "uri": full_uri, "name": name, "path": str(file.relative_to(root)), "source": str(file.relative_to(root)), "line": text.count("\n", 0, match.start()) + 1, "target": handler, "handler": handler, "middleware": middleware, "status": "CONFIRMED", "evidence": _e(root, file, match.start(), f"Declaración de ruta {framework}", symbol=name)})
        for match in resource_pattern.finditer(text):
            if not _active(match.start(), comments):
                disabled.append({"kind": "route", "path": str(file.relative_to(root)), "line": text.count("\n", 0, match.start()) + 1, "status": "commented_or_disabled"})
                continue
            resource, controller = match.groups()
            name = f"RESOURCE /{resource.lstrip('/')}"
            routes.append({"type": "http", "method": "RESOURCE", "uri": "/" + resource.lstrip("/"), "name": name, "path": str(file.relative_to(root)), "source": str(file.relative_to(root)), "line": text.count("\n", 0, match.start()) + 1, "target": controller.split("\\")[-1], "handler": controller.split("\\")[-1], "middleware": [], "status": "INFERRED", "evidence": _e(root, file, match.start(), "Declaración resource de Laravel", symbol=name, status="INFERRED")})
        if file.name == "console.php":
            for match in schedule_pattern.finditer(text):
                command, chain = match.groups()
                line = text.count("\n", 0, match.start()) + 1
                frequency_match = re.search(r"->([A-Za-z]\w*)\s*\((.*?)\)", chain, re.S)
                frequency = frequency_match.group(1) if frequency_match else None
                expression = frequency_match.group(2).strip().strip("'\"") if frequency_match else None
                if not _active(match.start(), comments):
                    disabled.append({"kind": "scheduled_command", "name": command, "path": str(file.relative_to(root)), "line": line, "status": "commented_or_disabled"})
                    continue
                status = "CONFIRMED" if frequency else "INFERRED"
                scheduled.append({"name": command, "type": "scheduled_command", "schedule": frequency, "expression": expression, "path": str(file.relative_to(root)), "line": line, "status": status, "evidence": _e(root, file, match.start(), "Comando programado de Laravel", symbol=command, status=status)})
    return routes, scheduled, disabled


def _scheduled_kernel(root: Path) -> tuple[list[dict], list[dict]]:
    kernel = root / "app" / "Console" / "Kernel.php"
    if not kernel.exists():
        return [], []
    text = _read(kernel)
    spans = _comment_spans(text)
    pattern = re.compile(r"\$schedule->(?:command|job)\s*\(\s*['\"]([^'\"]+)['\"]\s*\)([^;]*);", re.S)
    active, disabled = [], []
    for match in pattern.finditer(text):
        line = text.count("\n", 0, match.start()) + 1
        if not _active(match.start(), spans):
            disabled.append({"kind": "scheduled_command", "name": match.group(1), "path": str(kernel.relative_to(root)), "line": line, "status": "commented_or_disabled"})
            continue
        frequency = re.search(r"->([A-Za-z]\w*)\s*\((.*?)\)", match.group(2), re.S)
        status = "CONFIRMED" if frequency else "INFERRED"
        active.append({"name": match.group(1), "type": "scheduled_command", "schedule": frequency.group(1) if frequency else None, "expression": frequency.group(2).strip().strip("'\"") if frequency else None, "path": str(kernel.relative_to(root)), "line": line, "status": status, "evidence": _e(root, kernel, match.start(), "Scheduler de Laravel", symbol=match.group(1), status=status)})
    return active, disabled


def _classes(root: Path, folder: str, kind: str, predicate=None) -> list[dict]:
    directory = root / folder
    if not directory.is_dir():
        return []
    result = []
    for file in directory.rglob("*.php"):
        text = _read(file)
        spans = _comment_spans(text)
        active_text = _code_only(text)
        if predicate and not predicate(active_text):
            continue
        match = re.search(r"\bclass\s+(\w+)", active_text)
        if not match:
            continue
        name = match.group(1)
        result.append({"name": name, "type": kind, "path": str(file.relative_to(root)), "line": text.count("\n", 0, match.start()) + 1, "status": "CONFIRMED", "evidence": _e(root, file, match.start(), f"Clase Laravel de tipo {kind}", symbol=name)})
    return result


def _listener_relations(root: Path, listeners: list[dict]) -> list[dict]:
    relations = []
    for listener in listeners:
        path = root / listener["path"]
        text = _read(path)
        active = _code_only(text)
        match = re.search(r"function\s+handle\s*\(\s*([A-Za-z_]\w*(?:\\[A-Za-z_]\w*)*)\s+\$", active)
        if match:
            relations.append({"source": listener["name"], "target": match.group(1).split("\\")[-1], "type": "LISTENS_TO", "file": listener["path"], "line": text.count("\n", 0, match.start()) + 1, "status": "CONFIRMED", "evidence": _e(root, path, match.start(), "Tipo de evento en handler de listener", symbol=listener["name"])})
    provider = root / "app" / "Providers" / "EventServiceProvider.php"
    if provider.exists():
        text = _read(provider)
        active = _code_only(text)
        pattern = re.compile(r"([A-Za-z_]\w*(?:\\[A-Za-z_]\w*)*)::class\s*=>\s*\[(.*?)\]", re.S)
        for match in pattern.finditer(active):
            event = match.group(1).split("\\")[-1]
            for listener in re.findall(r"([A-Za-z_]\w*(?:\\[A-Za-z_]\w*)*)::class", match.group(2)):
                relations.append({"source": listener.split("\\")[-1], "target": event, "type": "LISTENS_TO", "file": str(provider.relative_to(root)), "line": text.count("\n", 0, match.start()) + 1, "status": "CONFIRMED", "evidence": _e(root, provider, match.start(), "Registro explícito de listener", symbol=listener)})
    unique = {}
    for relation in relations:
        unique[(relation["source"], relation["target"], relation["type"])] = relation
    return list(unique.values())


def analyze(root: Path) -> dict:
    routes, scheduled, disabled = _routes(root)
    kernel_scheduled, kernel_disabled = _scheduled_kernel(root)
    scheduled.extend(kernel_scheduled)
    disabled.extend(kernel_disabled)
    dependencies, versions = _composer(root)
    commands = _classes(root, "app/Console/Commands", "artisan_command")
    for command in commands:
        text = _read(root / command["path"])
        signature = re.search(r"(?:protected|public)\s+\$signature\s*=\s*['\"]([^'\"]+)", _code_only(text))
        if signature:
            command["name"] = signature.group(1)
            command["evidence"] = _e(root, root / command["path"], signature.start(), "Firma de comando Artisan", symbol=command["name"])
    jobs = _classes(root, "app/Jobs", "queue_job", lambda text: "ShouldQueue" in text)
    for job in jobs:
        text = _read(root / job["path"])
        queue = re.search(r"(?:public|protected)\s+\$queue\s*=\s*['\"]([^'\"]+)", _code_only(text))
        job["queue"] = queue.group(1) if queue else None
    events = _classes(root, "app/Events", "event")
    listeners = _classes(root, "app/Listeners", "listener")
    listener_relations = _listener_relations(root, listeners)
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
    framework = versions["framework"] or "Laravel"
    package = versions["package"] or "laravel/framework"
    return {"framework": {"name": framework, "version": versions["version"], "php_version": versions["php"], "status": "CONFIRMED", "evidence": [Evidence("manifest", "composer.json", f"{package} declarado", "CONFIRMED", 1.0, symbol=package).as_dict()]}, "routes": routes, "commands": commands, "scheduled_processes": scheduled, "disabled_declarations": disabled, "queue_jobs": jobs, "events": events, "listeners": listeners, "listener_relations": listener_relations, "components": components, "dependencies": dependencies, "runtime_surfaces": surfaces, "important_files": important}


class LaravelAdapter:
    """Translate Laravel conventions into the shared semantic vocabulary."""

    name = "Laravel"

    def __init__(self, scope: IndexScope | None = None):
        self.scope = scope

    def detect(self, root: Path) -> bool:
        return (root / "composer.json").exists() and "laravel/framework" in _read(root / "composer.json")

    def analyze(self, root: Path) -> SemanticModel:
        raw = analyze(root)
        components = [SemanticComponent(item["name"], item["type"], item["path"], item["name"], item["status"], item["evidence"]) for item in raw["components"] + raw["queue_jobs"] + raw["events"] + raw["listeners"]]
        entries = []
        transitions = []
        for route in raw["routes"]:
            entries.append(EntryPoint("HTTP", route["name"], route.get("target"), "HTTP", route.get("method"), route.get("uri"), route["path"], route["line"], raw["framework"]["name"], route["status"], route["evidence"]))
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
        index = PhpCodeIntelligenceProvider(root, self.scope).index()
        for relation in index["relations"]:
            transition_type = "CALL" if relation["relation"] == "CALLS" else relation["relation"]
            target = relation["target_symbol"]
            expression = relation.get("metadata", {}).get("expression", "")
            if target.endswith("::dispatch"):
                transition_type = "DISPATCHES"
                target = target.rsplit("::", 1)[0]
            elif target.startswith("Http::") or "Http::" in expression:
                transition_type = "EXTERNAL_CALL"
            evidence = [Evidence("code", relation["file"], "Relación estructural PHP", relation["confidence"], 1.0 if relation["confidence"] == "CONFIRMED" else .7, line=relation["line"], symbol=relation["source_symbol"]).as_dict()]
            transitions.append(ExecutionTransition(relation["source_symbol"], target, transition_type, relation["file"], relation["line"], relation["confidence"], relation["provider"], evidence, relation.get("metadata", {})))
        for relation in raw.get("listener_relations", []):
            transitions.append(ExecutionTransition(relation["source"], relation["target"], relation["type"], relation["file"], relation["line"], relation["status"], "laravel", relation["evidence"]))
        background = [BackgroundTask(item["name"], "SCHEDULED" if item["type"] == "scheduled_command" else "QUEUE", item.get("schedule"), item.get("name"), item["path"], item["status"], item["evidence"]) for item in raw["scheduled_processes"] + raw["queue_jobs"]]
        events = [Event(item["name"], item["path"], item["status"], item["evidence"]) for item in raw["events"]]
        handlers = [EventHandler(item["name"], file=item["path"], status=item["status"], evidence=item["evidence"]) for item in raw["listeners"]]
        dependencies = [Dependency(item["package"], item["version"], item["category"], item["status"], item["evidence"]) for item in raw["dependencies"]]
        return SemanticModel("PHP", raw["framework"]["name"], "FRAMEWORK", components, entries, transitions, background_tasks=background, events=events, event_handlers=handlers, dependencies=dependencies, metadata={"raw": raw})
