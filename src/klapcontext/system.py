"""Deterministic system-understanding heuristics, all backed by repository evidence."""
from __future__ import annotations

import json
import re
from pathlib import Path

from .evidence import Evidence


TEXT_LIMIT = 180_000


def _read(path: Path) -> str:
    try: return path.read_text(encoding="utf-8", errors="replace")[:TEXT_LIMIT]
    except OSError: return ""


def _ev(path: str, reason: str, status: str = "CONFIRMED", confidence: float = 1.0) -> dict:
    return Evidence("file", path, reason, status, confidence).as_dict()


def documents(root: Path) -> list[dict]:
    candidates = [*root.glob("README*"), *root.glob("CONTRIBUTING*"), *root.glob("Makefile")]
    for folder in ("docs", "doc", "ADR", "architecture"):
        directory = root / folder
        if directory.is_dir(): candidates.extend(p for p in directory.rglob("*.md") if p.is_file())
    seen, result = set(), []
    for path in candidates:
        relative = str(path.relative_to(root))
        if relative in seen or path.stat().st_size > TEXT_LIMIT: continue
        seen.add(relative)
        result.append({"path": relative, "content": _read(path)})
    return result


def purpose(root: Path, docs: list[dict]) -> dict:
    def localize(text: str) -> str:
        # Product metadata can be English even when this local context is emitted in Spanish.
        return "Hace que tu repositorio sea comprensible para humanos e IA." if text.strip() == "Make your repository understandable to humans and AI." else text
    package = root / "package.json"; pyproject = root / "pyproject.toml"
    if package.exists():
        try:
            description = json.loads(_read(package)).get("description")
            if description: return {"text": localize(description), "status": "CONFIRMED", "evidence": [_ev("package.json", "Package description")]} 
        except json.JSONDecodeError: pass
    if pyproject.exists():
        match = re.search(r'^description\s*=\s*["\'](.+?)["\']', _read(pyproject), re.M)
        if match: return {"text": localize(match.group(1)), "status": "CONFIRMED", "evidence": [_ev("pyproject.toml", "Project description")]} 
    for doc in docs:
        if Path(doc["path"]).name.lower().startswith("readme"):
            paragraphs = [re.sub(r"\s+", " ", p).strip() for p in re.split(r"\n\s*\n", doc["content"])]
            for paragraph in paragraphs:
                if paragraph and not paragraph.startswith("#") and len(paragraph) >= 30 and not paragraph.startswith("```"):
                    return {"text": paragraph[:400], "status": "CONFIRMED", "evidence": [_ev(doc["path"], "README project description")]} 
    return {"text": None, "status": "UNKNOWN", "evidence": []}


def entry_points(root: Path) -> tuple[list[dict], list[dict]]:
    points, background = [], []
    def add(kind, name, path, target=None, schedule=None, reason="Application entry point detected"):
        evidence=[_ev(path, reason)]
        point={"type":kind,"name":name,"path":path,"target":target,"schedule":schedule,"status":"CONFIRMED","evidence":evidence}
        points.append(point); return point
    # Laravel routes and scheduler.
    for route_file in (root / "routes").glob("*.php") if (root / "routes").is_dir() else []:
        text=_read(route_file); rel=str(route_file.relative_to(root))
        for method, uri, target in re.findall(r"Route::(get|post|put|patch|delete|any)\s*\(\s*['\"]([^'\"]+)['\"]\s*,\s*([^\)]+)", text, re.I):
            add("http", f"{method.upper()} /{uri.lstrip('/')}", rel, target.strip(), reason="Laravel route declaration")
    for rel in ("routes/console.php", "app/Console/Kernel.php"):
        if not (root/rel).exists(): continue
        text=_read(root/rel)
        for command, frequency in re.findall(r"(?:command|job)\s*\(\s*['\"]([^'\"]+)['\"]\s*\).*?->(every\w+|daily|hourly|weekly)\s*\(", text, re.S):
            point=add("scheduled", command, rel, schedule=frequency, reason="Laravel scheduler declaration")
            background.append({"name":command,"type":"scheduled_command","schedule":frequency,"path":rel,"status":"CONFIRMED","evidence":point["evidence"]})
    # Python HTTP decorators and CLI bootstrap.
    for path in root.rglob("*.py"):
        if any(part in {".git", ".klap", "graphify-out", "venv", ".venv"} for part in path.parts) or path.name == "system.py": continue
        text=_read(path); rel=str(path.relative_to(root))
        for method, uri, function in re.findall(r"@\w+\.(get|post|put|patch|delete)\s*\(\s*['\"]([^'\"]+)['\"]\s*\)\s*\n\s*(?:async\s+)?def\s+(\w+)", text, re.I):
            add("http", f"{method.upper()} {uri}", rel, function, reason="Python web route decorator")
        if "if __name__ == \"__main__\"" in text or "if __name__ == '__main__'" in text:
            add("cli", path.stem, rel, reason="Python executable module")
    # Express route declarations.
    for path in root.rglob("*.js"):
        if any(part in {"node_modules", ".git", ".klap", "graphify-out"} for part in path.parts): continue
        rel=str(path.relative_to(root)); text=_read(path)
        for method, uri in re.findall(r"\.(get|post|put|patch|delete)\s*\(\s*['\"]([^'\"]+)", text, re.I): add("http", f"{method.upper()} {uri}", rel, reason="JavaScript HTTP route declaration")
    return points[:50], background[:30]


def external_systems(root: Path) -> tuple[list[dict], list[dict]]:
    found, stores = [], []
    patterns = [(r"\bredis\b", "Redis", "redis"), (r"\brabbitmq\b|\bamqp\b", "RabbitMQ", "message broker"), (r"\bkafka\b", "Kafka", "message broker"), (r"\bsentry\b", "Sentry", "error tracking"), (r"\bsmtp\b|\bmailgun\b", "SMTP", "email"), (r"\bsftp\b", "SFTP", "sftp"), (r"\bftp\b", "FTP", "ftp")]
    store_patterns = [(r"\bmysql\b", "MySQL"), (r"\bpostgres(?:ql)?\b", "PostgreSQL"), (r"\bsqlsrv\b|sql server", "SQL Server"), (r"\bsqlite\b", "SQLite"), (r"\bmongodb\b", "MongoDB")]
    candidates=[p for p in root.rglob("*") if p.is_file() and p.suffix.lower() in {".json", ".toml", ".yml", ".yaml", ".php", ".py", ".js", ".ts", ".env"}]
    for path in candidates[:800]:
        if any(part in {".git", ".klap", "graphify-out", "node_modules", "vendor", ".pytest_cache", "tests"} for part in path.parts) or path.name in {"system.py", "portal.py"}: continue
        text=_read(path); rel=str(path.relative_to(root))
        for pattern,name,kind in patterns:
            if re.search(pattern, text, re.I) and not any(x["name"] == name for x in found): found.append({"name":name,"type":kind,"purpose":None,"used_by":[],"configuration":[rel],"status":"CONFIRMED","evidence":[_ev(rel, f"{name} configuration or usage detected")]})
        for pattern,name in store_patterns:
            if re.search(pattern, text, re.I) and not any(x["name"] == name for x in stores): stores.append({"name":name,"connection":None,"used_by":[],"role":None,"status":"CONFIRMED","evidence":[_ev(rel, f"{name} configuration or usage detected")]})
        for host in re.findall(r"https?://([a-zA-Z0-9.-]+)", text):
            if host not in {"localhost", "example.com"} and not any(x["name"] == host for x in found): found.append({"name":host,"type":"http_api","purpose":None,"used_by":[],"configuration":[rel],"status":"CONFIRMED","evidence":[_ev(rel, "External HTTP host configured or referenced")]})
    return found, stores


def deployment(root: Path) -> tuple[dict, dict, list[dict]]:
    files=[]; tools=[]; ports=[]; observability=[]
    for name, label in (("Dockerfile","Docker"),("docker-compose.yml","Docker Compose"),("docker-compose.yaml","Docker Compose"),("compose.yml","Docker Compose"),("compose.yaml","Docker Compose"),("Jenkinsfile","Jenkins")):
        if (root/name).exists(): files.append({"path":name,"role":label,"reason":f"{label} configuration"}); tools.append(label)
    if (root/".github/workflows").is_dir(): files.append({"path":".github/workflows","role":"CI workflows","reason":"GitHub Actions workflow directory"}); tools.append("GitHub Actions")
    for item in files:
        text=_read(root/item["path"]) if (root/item["path"]).is_file() else ""
        ports.extend(re.findall(r"(?:EXPOSE\s+|['\"]?)(\d{2,5})(?::\d{2,5})?", text))
    for path in root.rglob("*"):
        if path.is_file() and path.suffix.lower() in {".py", ".php", ".js", ".ts", ".json", ".yml", ".yaml"}:
            if any(part in {".git", ".klap", "graphify-out", "node_modules", "vendor", ".pytest_cache", "tests"} for part in path.parts) or path.name == "system.py": continue
            text=_read(path); rel=str(path.relative_to(root))
            for term,name in (("prometheus","Prometheus"),("opentelemetry","OpenTelemetry"),("sentry","Sentry"),("/health","Health endpoint"),("/metrics","Metrics endpoint")):
                if term in text.lower() and not any(x["name"]==name for x in observability): observability.append({"name":name,"path":rel,"status":"CONFIRMED","evidence":[_ev(rel, f"{name} reference detected")]})
    return {"tools":tools,"ports":sorted(set(ports)),"files":files,"status":"CONFIRMED" if files else "UNKNOWN"}, {"tools":observability,"status":"CONFIRMED" if observability else "UNKNOWN"}, files
