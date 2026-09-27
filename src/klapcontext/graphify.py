from __future__ import annotations

import importlib.metadata
import json
import shutil
import subprocess
import sys
from pathlib import Path
from datetime import datetime, timezone

from .scope import IndexScope


class GraphifyError(RuntimeError):
    pass


def executable() -> str | None:
    return shutil.which("graphify")


def command_prefix() -> list[str] | None:
    """Use the console script when present; PyPI also supports python -m graphify."""
    if executable():
        return [executable()]
    try:
        import graphify  # noqa: F401
        return [sys.executable, "-m", "graphify"]
    except ImportError:
        return None


def version() -> str | None:
    try:
        return importlib.metadata.version("graphifyy")
    except importlib.metadata.PackageNotFoundError:
        return None


def canonical_directory(root: Path) -> Path:
    return root / ".klap" / "graphify-out"


def canonical_graph(root: Path) -> Path:
    return canonical_directory(root) / "graph.json"


def legacy_graphs(root: Path) -> list[str]:
    canonical = canonical_graph(root).resolve()
    paths = [root / "graphify-out" / "graph.json", root / ".klap" / "graphify" / "graph.json"]
    return [path.relative_to(root).as_posix() for path in paths if path.exists() and path.resolve() != canonical]


def migrate_legacy_graphs(root: Path, *, apply: bool = False) -> dict:
    """Plan or explicitly move known legacy graph directories into backups."""
    canonical = canonical_graph(root)
    try:
        payload = json.loads(canonical.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"status": "blocked", "reason": "Canonical graph is missing or invalid", "planned": [], "moved": []}
    if not isinstance(payload, dict):
        return {"status": "blocked", "reason": "Canonical graph is not an object", "planned": [], "moved": []}
    candidates = []
    local_legacy = root / ".klap" / "graphify"
    if (local_legacy / "graph.json").exists():
        candidates.append((local_legacy, "legacy-klap-graphify"))
    root_legacy = root / "graphify-out"
    # Root output is considered Graphify-owned only with its marker. Unknown
    # directories are reported by legacy_graphs() but never moved here.
    if (root_legacy / "graph.json").exists() and (root_legacy / ".graphify_root").exists():
        candidates.append((root_legacy, "legacy-root-graphify-out"))
    planned = [source.relative_to(root).as_posix() for source, _ in candidates]
    if not apply:
        return {"status": "planned" if planned else "clean", "reason": "Use --apply to move verified legacy Graphify-owned directories into .klap/backups.", "planned": planned, "moved": []}
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup_root = root / ".klap" / "backups"
    backup_root.mkdir(parents=True, exist_ok=True)
    moved, errors = [], []
    for source, label in candidates:
        destination = backup_root / f"{label}-{stamp}"
        if destination.exists():
            errors.append(f"Backup already exists: {destination.relative_to(root).as_posix()}")
            continue
        try:
            shutil.move(str(source), str(destination))
            moved.append({"from": source.relative_to(root).as_posix(), "to": destination.relative_to(root).as_posix()})
        except OSError as error:
            errors.append(f"{source}: {error}")
    return {"status": "migrated" if moved and not errors else "partial" if moved else "blocked", "reason": "Legacy directories were preserved as backups; nothing was deleted.", "planned": planned, "moved": moved, "errors": errors}


def generate(root: Path, update: bool = False, scope: IndexScope | None = None) -> Path:
    prefix = command_prefix()
    if not prefix:
        raise GraphifyError("Graphify is required. Install it with: pipx install graphifyy")
    scope = scope or IndexScope.load(root)
    output_parent = root / ".klap"
    output_parent.mkdir(parents=True, exist_ok=True)
    # Graphify's supported --out writes one graphify-out directory beneath the
    # selected parent. --exclude is authoritative even for tracked files, so the
    # central scope is applied before AST extraction rather than filtered later.
    command = [*prefix, "extract", str(root), "--code-only", "--out", str(output_parent)]
    for pattern in scope.graphify_excludes():
        command.extend(["--exclude", pattern])
    if update:
        # A normal extract reuses Graphify's manifest/cache in the canonical
        # directory while still pruning files that became excluded.
        command.append("--no-cluster")
    result = subprocess.run(command, cwd=root, text=True, capture_output=True)
    graph = canonical_graph(root)
    if result.returncode != 0 or not graph.exists():
        message = result.stderr.strip() or result.stdout.strip() or "Graphify did not create the canonical graph.json"
        raise GraphifyError(message)
    try:
        payload = json.loads(graph.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise GraphifyError(f"Graphify created an invalid graph: {error}") from error
    if not isinstance(payload, dict):
        raise GraphifyError("Graphify created an invalid graph object")
    # Visualization exporters consume the exact canonical graph. Failures do
    # not invalidate the graph itself, but are reflected by missing artifacts.
    subprocess.run(prefix + ["export", "html", "--graph", str(graph)], cwd=root, text=True, capture_output=True)
    subprocess.run(prefix + ["export", "callflow-html", str(graph)], cwd=root, text=True, capture_output=True)
    return graph


def load_graph(graph: Path) -> dict:
    try:
        return json.loads(graph.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def output_files(graph: Path) -> list[str]:
    directory = graph.parent
    names = ["graph.json", "graph.html", "GRAPH_REPORT.md"]
    result = [name for name in names if (directory / name).exists()]
    callflows = list(directory.glob("*-callflow.html")) + list(directory.glob("callflow.html"))
    if callflows:
        result.append(callflows[0].name)
    return result


def copy_outputs(root: Path, destination: Path) -> list[str]:
    """Compatibility shim: outputs already live in the canonical directory."""
    graph = canonical_graph(root)
    return output_files(graph) if graph.exists() else []
