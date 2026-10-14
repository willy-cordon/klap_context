"""Project-local Archify renderer lifecycle and Klap flow projection.

Archify is deliberately a renderer, not an analysis provider.  This module
accepts canonical Klap facts and owns every Archify-specific representation.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import urllib.request
import zipfile
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ARCHIFY_VERSION = "3.1.0"
ARCHIFY_COMMIT = "2e1dba8653b800400f41c84a058561e960c21963"
ARCHIFY_URL = f"https://github.com/tt-a1i/archify/releases/download/v{ARCHIFY_VERSION}/archify.zip"
ARCHIFY_SHA256 = "ffedc53390c9da6e859f41e432c5d2d0615a23cf00a503181f07efbba88a7ce8"
NODE_MINIMUM = 18
DEFAULT_LIMITS = {"max_flows": 12, "max_nodes": 6, "max_depth": 6, "timeout_seconds": 45}


@dataclass
class ArchifyResult:
    state: str
    version: str = ARCHIFY_VERSION
    source: str = ARCHIFY_URL
    commit: str = ARCHIFY_COMMIT
    executable: str | None = None
    installed_version: str | None = None
    generated_at: str | None = None
    diagrams: list[dict[str, Any]] | None = None
    warnings: list[str] | None = None
    error: str | None = None

    def as_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["diagrams"] = value["diagrams"] or []
        value["warnings"] = value["warnings"] or []
        return value


def runtime_root(root: Path) -> Path:
    return Path(root) / ".klap" / "renderer-runtime" / "archify"


def output_root(root: Path) -> Path:
    return Path(root) / ".klap" / "flows"


def state_path(root: Path) -> Path:
    return Path(root) / ".klap" / "archify-state.json"


def config(root: Path) -> dict[str, Any]:
    value = dict(DEFAULT_LIMITS)
    path = Path(root) / ".klap" / "archify.json"
    if path.exists():
        try:
            payload = json.loads(path.read_text(encoding="utf-8-sig"))
            if isinstance(payload, dict):
                value.update({key: payload[key] for key in DEFAULT_LIMITS if key in payload})
                value["enabled"] = payload.get("enabled", True)
        except (OSError, json.JSONDecodeError):
            value["configuration_warning"] = "Invalid .klap/archify.json; defaults were used."
    value.setdefault("enabled", True)
    return value


def write_state(root: Path, result: ArchifyResult | dict[str, Any]) -> dict[str, Any]:
    value = result.as_dict() if isinstance(result, ArchifyResult) else result
    path = state_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"schema_version": 1, "renderer": value}, indent=2) + "\n", encoding="utf-8")
    return value


def _node() -> tuple[str | None, str | None]:
    command = shutil.which("node")
    if not command:
        return None, "Node.js was not found; Archify requires Node.js >=18."
    try:
        completed = subprocess.run([command, "--version"], text=True, capture_output=True, timeout=10, check=False)
        match = re.search(r"v?(\d+)(?:\.(\d+))?", completed.stdout or completed.stderr)
        if completed.returncode or not match:
            return None, "Unable to determine the installed Node.js version."
        if int(match.group(1)) < NODE_MINIMUM:
            return None, f"Node.js {match.group(0)} is incompatible; Archify requires >=18."
        return command, None
    except (OSError, subprocess.SubprocessError) as error:
        return None, f"Node.js probe failed: {type(error).__name__}: {error}"


def _safe_extract(archive: Path, destination: Path) -> None:
    with zipfile.ZipFile(archive) as bundle:
        base = destination.resolve()
        for member in bundle.infolist():
            target = (destination / member.filename).resolve()
            if os.path.commonpath((base, target)) != str(base):
                raise RuntimeError(f"Unsafe Archify archive entry: {member.filename}")
        bundle.extractall(destination)


def prepare(root: Path, *, disabled: bool = False, repair: bool = False, timeout_seconds: int = 120) -> ArchifyResult:
    root = Path(root).resolve()
    settings = config(root)
    if disabled:
        return ArchifyResult("SKIPPED", error="Skipped by --no-archify")
    if settings.get("enabled") is False:
        return ArchifyResult("SKIPPED", error="Disabled by .klap/archify.json")
    node, error = _node()
    if error:
        return ArchifyResult("UNAVAILABLE", error=error)
    folder = runtime_root(root)
    cli = folder / "bin" / "archify.mjs"
    release = folder / "skill-release.json"
    if cli.is_file() and release.is_file() and not repair:
        try:
            installed = json.loads(release.read_text(encoding="utf-8")).get("version")
            if installed == ARCHIFY_VERSION:
                return ArchifyResult("READY", executable=str(cli), installed_version=installed)
        except (OSError, json.JSONDecodeError):
            pass
    try:
        folder.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="klap-archify-") as temporary:
            archive = Path(temporary) / "archify.zip"
            with urllib.request.urlopen(ARCHIFY_URL, timeout=timeout_seconds) as response:
                archive.write_bytes(response.read())
            digest = hashlib.sha256(archive.read_bytes()).hexdigest()
            if digest != ARCHIFY_SHA256:
                raise RuntimeError(f"Archify package integrity mismatch: expected {ARCHIFY_SHA256}, got {digest}")
            unpacked = Path(temporary) / "unpacked"
            _safe_extract(archive, unpacked)
            candidate = unpacked / "archify"
            if not (candidate / "bin" / "archify.mjs").is_file():
                raise RuntimeError("The verified Archify package does not contain its CLI")
            replacement = folder.parent / ".archify-next"
            if replacement.exists():
                shutil.rmtree(replacement)
            shutil.copytree(candidate, replacement)
            if folder.exists():
                shutil.rmtree(folder)
            replacement.replace(folder)
        completed = subprocess.run([node, str(cli), "doctor"], cwd=root, text=True, capture_output=True, timeout=30, check=False)
        if completed.returncode:
            raise RuntimeError((completed.stderr or completed.stdout or "Archify doctor failed")[-1000:])
        return ArchifyResult("READY", executable=str(cli), installed_version=ARCHIFY_VERSION)
    except Exception as exception:
        return ArchifyResult("FAILED", error=f"{type(exception).__name__}: {exception}")


def _slug(value: str, fallback: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9_-]+", "-", value).strip("-").lower()
    if not slug or not slug[0].isalpha():
        slug = f"flow-{slug or fallback}"
    return slug[:64]


def _node_label(value: object) -> str:
    label = str(value).split("\\")[-1]
    return label if len(label) <= 30 else label[:27] + "…"


def _source_path(value: object) -> str | None:
    """Return a safe repo-relative POSIX path for Archify evidence."""
    path = str(value).strip().replace("\\", "/")
    if not path or path.startswith(("/", "~/")) or re.match(r"^[a-zA-Z]:/", path):
        return None
    parts = [part for part in path.split("/") if part not in {"", "."}]
    if not parts or ".." in parts or any(part.lower() == ".env" for part in parts):
        return None
    return "/".join(parts)[:240]


def _sources(step: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    direct_path = step.get("path") or step.get("file")
    normalized = _source_path(direct_path) if direct_path else None
    if normalized:
        source = {"path": normalized, "label": str(step.get("status") or "Klap flow step")[:48]}
        if isinstance(step.get("line"), int) and step["line"] > 0:
            source["line"] = step["line"]
        rows.append(source)
    for item in step.get("evidence", [])[:3]:
        path = item.get("path") or item.get("file")
        normalized = _source_path(path) if path else None
        if not normalized:
            continue
        source = {"path": normalized, "label": str(item.get("reason") or "Klap evidence")[:48]}
        line = item.get("line")
        if isinstance(line, int) and line > 0:
            source["line"] = line
        rows.append(source)
    return rows


def project_flows(context: dict[str, Any], *, limits: dict[str, Any] | None = None, repository_url: str | None = None) -> list[dict[str, Any]]:
    """Project evidenced Klap flows to deterministic Archify workflow IRs."""
    limits = {**DEFAULT_LIMITS, **(limits or {})}
    candidates = context.get("system_model", {}).get("main_flows", [])
    revision = str(context.get("project", {}).get("git_commit") or "")
    repository_url = repository_url or context.get("project", {}).get("repository_url")
    repository_evidence = bool(repository_url and re.fullmatch(r"[a-fA-F0-9]{40}", revision))
    projected: list[dict[str, Any]] = []
    seen: set[tuple[str, ...]] = set()
    for flow_index, flow in enumerate(candidates[: max(0, int(limits["max_flows"]))]):
        steps = [step for step in flow.get("steps", []) if step.get("name")]
        bounded = steps[: min(int(limits["max_nodes"]), int(limits["max_depth"]), 6)]
        identity = tuple(str(step["name"]) for step in bounded)
        if len(identity) < 2 or identity in seen:
            continue
        seen.add(identity)
        flow_id = _slug(str(flow.get("id") or flow.get("name") or flow_index), str(flow_index))
        nodes, lanes = [], []
        for index, step in enumerate(bounded):
            lane_id = f"lane-{index}"
            node_id = f"step-{index}"
            lane_label = str(step.get("type") or step.get("role") or "Code").replace("_", " ").title()
            lanes.append({"id": lane_id, "label": lane_label})
            source_rows = _sources(step)
            if index == 0 and not source_rows:
                source_rows = _sources({"evidence": flow.get("evidence", [])})
            kind = str(step.get("kind") or step.get("type") or "code").lower()
            component_type = "external" if "external" in kind else "database" if any(word in kind for word in ("store", "repository", "model", "database")) else "messagebus" if any(word in kind for word in ("queue", "event", "dispatch", "listener")) else "frontend" if kind in {"http", "route"} else "backend"
            node = {"id": node_id, "lane": lane_id, "col": index, "type": component_type, "label": _node_label(step["name"]), "sublabel": f"{kind} · {str(step.get('status') or flow.get('status') or 'UNKNOWN').lower()}"[:120], "width": 168}
            if source_rows and repository_evidence:
                node["sources"] = source_rows
            nodes.append(node)
        explicit_edges = flow.get("edges", [])
        edges = []
        if explicit_edges:
            for edge_index, edge in enumerate(explicit_edges):
                source_index, target_index = edge.get("from"), edge.get("to")
                if isinstance(source_index, int) and isinstance(target_index, int) and 0 <= source_index < len(nodes) and 0 <= target_index < len(nodes):
                    role = edge.get("role") if edge.get("role") in {"main", "branch", "async", "return", "error"} else "branch"
                    edges.append({"id": f"edge-{edge_index}", "from": f"step-{source_index}", "to": f"step-{target_index}", "role": role, "variant": "dashed" if role != "main" else "default", **({"label": str(edge["label"])[:80]} if edge.get("label") else {})})
        else:
            edges = [{"id": f"edge-{index}", "from": f"step-{index}", "to": f"step-{index + 1}", "role": "main", "variant": "default"} for index in range(len(nodes) - 1)]
        main_path = [nodes[0]["id"]]
        while True:
            following = next((edge["to"] for edge in edges if edge.get("role") == "main" and edge["from"] == main_path[-1] and edge["to"] not in main_path), None)
            if not following:
                break
            main_path.append(following)
        if len(main_path) < 2:
            main_path = [node["id"] for node in nodes]
        limitations = list(flow.get("limitations", []))
        if str(flow.get("status", "")).upper() != "CONFIRMED" or any(str(step.get("status", "")).upper() != "CONFIRMED" for step in bounded):
            limitations.append("The traversal includes inferred static-analysis relationships; inspect node sources and confidence.")
        if len(steps) > len(bounded):
            limitations.append(f"Truncated from {len(steps)} to {len(bounded)} steps by configured limits.")
        if not any(_sources(step) for step in bounded):
            limitations.append("No step-level source references were available; relationships come from Klap's static-analysis model.")
        title = str(flow.get("name") or f"Flow {flow_index + 1}")
        meta = {"title": title, "subtitle": "Static-analysis relationships; not a production trace", "output": f"flows/{flow_id}.html", "animation": "trace", "visual_preset": "signal-flow", "quality_profile": "standard"}
        if repository_evidence:
            meta["repository"] = {"url": repository_url, "revision": revision, "link_mode": "local-only"}
        ir = {
            "schema_version": 2,
            "diagram_type": "workflow",
            "meta": meta,
            "lanes": lanes,
            "mainPath": main_path,
            "nodes": nodes,
            "edges": edges,
            "cards": [{"dot": "amber", "title": "Analysis boundaries", "items": ["Relationships reconstructed by static analysis; not observed production traces", *(limitations[:3] or ["Review linked evidence before changing behavior"])]}],
        }
        evidence = [*flow.get("evidence", []), *(item for step in bounded for item in step.get("evidence", []))]
        projected.append({"id": flow_id, "title": title, "entry_point": identity[0], "status": "PARTIAL" if limitations else "CURRENT", "confidence": flow.get("confidence"), "evidence": evidence, "limitations": limitations, "ir": ir})
    return projected


def render(root: Path, context: dict[str, Any], runtime: ArchifyResult, *, limits: dict[str, Any] | None = None) -> ArchifyResult:
    root = Path(root).resolve()
    settings = {**config(root), **(limits or {})}
    if runtime.state != "READY" or not runtime.executable:
        return runtime
    node, error = _node()
    if error:
        return ArchifyResult("UNAVAILABLE", error=error)
    repository_url = None
    try:
        remote = subprocess.run(["git", "remote", "get-url", "origin"], cwd=root, text=True, capture_output=True, timeout=5, check=False)
        candidate = remote.stdout.strip()
        if remote.returncode == 0 and candidate and not re.search(r"https?://[^/@]+@", candidate):
            repository_url = candidate
    except (OSError, subprocess.SubprocessError):
        pass
    projected = project_flows(context, limits=settings, repository_url=repository_url)
    if not projected:
        return ArchifyResult("NO_RESULTS", executable=runtime.executable, installed_version=runtime.installed_version, generated_at=datetime.now(timezone.utc).isoformat(), warnings=["No flow contained at least two evidenced static-analysis steps."])
    destination = output_root(root)
    destination.mkdir(parents=True, exist_ok=True)
    diagrams, warnings = [], []
    timeout = max(1, int(settings["timeout_seconds"]))
    for item in projected:
        source = destination / f"{item['id']}.workflow.json"
        output = destination / f"{item['id']}.html"
        source.write_text(json.dumps(item.pop("ir"), indent=2) + "\n", encoding="utf-8")
        temporary = destination / f".{item['id']}.tmp.html"
        try:
            validate = subprocess.run([node, runtime.executable, "validate", "workflow", str(source), "--json", "--repo-root", str(root)], cwd=root, text=True, capture_output=True, timeout=timeout, check=False, env={**os.environ, "ARCHIFY_UPDATE_CHECK_DISABLED": "1"})
            if validate.returncode:
                raise RuntimeError((validate.stderr or validate.stdout or "Archify validation failed")[-1200:])
            rendered = subprocess.run([node, runtime.executable, "render", "workflow", str(source), str(temporary), "--repo-root", str(root)], cwd=root, text=True, capture_output=True, timeout=timeout, check=False, env={**os.environ, "ARCHIFY_UPDATE_CHECK_DISABLED": "1"})
            if rendered.returncode or not temporary.is_file():
                raise RuntimeError((rendered.stderr or rendered.stdout or "Archify render failed")[-1200:])
            temporary.replace(output)
            item.update({"html": f"flows/{output.name}", "ir": f"flows/{source.name}", "renderer": ARCHIFY_VERSION})
            diagrams.append(item)
        except (OSError, subprocess.SubprocessError, RuntimeError) as exception:
            temporary.unlink(missing_ok=True)
            warnings.append(f"{item['title']}: {type(exception).__name__}: {exception}")
    state = "READY" if diagrams and not warnings else "PARTIAL" if diagrams else "FAILED"
    return ArchifyResult(state, executable=runtime.executable, installed_version=runtime.installed_version, generated_at=datetime.now(timezone.utc).isoformat(), diagrams=diagrams, warnings=warnings, error=warnings[-1] if warnings and not diagrams else None)


def generate(root: Path, context: dict[str, Any], *, disabled: bool = False, repair: bool = False) -> dict[str, Any]:
    previous: dict[str, Any] = {}
    if state_path(root).exists():
        try:
            previous = json.loads(state_path(root).read_text(encoding="utf-8")).get("renderer", {})
        except (OSError, json.JSONDecodeError):
            pass
    try:
        runtime = prepare(root, disabled=disabled, repair=repair)
        result = render(root, context, runtime)
    except Exception as exception:
        # Rendering is optional by contract: malformed renderer configuration,
        # I/O failures, and unexpected third-party errors must not abort Klap.
        result = ArchifyResult("FAILED", error=f"{type(exception).__name__}: {exception}")
    if result.state in {"FAILED", "UNAVAILABLE"} and not result.diagrams and previous.get("diagrams"):
        stale = []
        for diagram in previous["diagrams"]:
            if (Path(root) / ".klap" / diagram.get("html", "")).is_file():
                stale.append({**diagram, "status": "STALE", "limitations": [*diagram.get("limitations", []), "Retained from the previous successful render; the current renderer run failed."]})
        if stale:
            result.diagrams = stale
            result.warnings = [*(result.warnings or []), "Previous valid diagrams were retained and marked STALE."]
    return write_state(root, result)


def diagnostics(root: Path) -> dict[str, Any]:
    settings = config(root)
    node, node_error = _node()
    cli = runtime_root(root) / "bin" / "archify.mjs"
    result = {"enabled": settings.get("enabled", True), "required_version": ARCHIFY_VERSION, "node": node, "node_error": node_error, "runtime": str(cli), "available": bool(node and cli.is_file()), "state": "READY" if node and cli.is_file() else "UNAVAILABLE"}
    if state_path(root).exists():
        try:
            result["last_run"] = json.loads(state_path(root).read_text(encoding="utf-8")).get("renderer", {})
        except (OSError, json.JSONDecodeError):
            result["state_error"] = "Invalid .klap/archify-state.json"
    return result
