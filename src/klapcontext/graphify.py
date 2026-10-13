from __future__ import annotations

import importlib.metadata
import json
import shutil
import subprocess
import sys
from contextlib import contextmanager
from pathlib import Path
from datetime import datetime, timezone

from .scope import IndexScope


class GraphifyError(RuntimeError):
    pass


@contextmanager
def _scoped_graphifyignore(root: Path, scope: IndexScope):
    """Apply IndexScope through Graphify's supported ignore-file contract.

    Graphify releases in the supported range do not consistently implement an
    ``extract --exclude`` flag (and some Windows builds terminate when it is
    supplied).  Preserve any project-owned file byte-for-byte and expose the
    generated rules only for the duration of extraction.
    """
    path = root / ".graphifyignore"
    existed = path.exists()
    original = path.read_bytes() if existed else None
    try:
        existing = original.decode("utf-8-sig", errors="replace") if original is not None else ""
        generated = "\n".join(scope.graphify_excludes())
        separator = "" if not existing or existing.endswith(("\n", "\r")) else "\n"
        content = existing + separator + "# KlapContext temporary IndexScope\n" + generated + "\n"
        path.write_text(content, encoding="utf-8")
        yield
    finally:
        if existed and original is not None:
            path.write_bytes(original)
        else:
            path.unlink(missing_ok=True)


def executable(root: Path | None = None) -> str | None:
    if root is not None:
        from .providers.lifecycle import managed_command
        managed = managed_command(Path(root), "graphify")
        if managed:
            return managed
    return shutil.which("graphify")


def command_prefix(root: Path | None = None) -> list[str] | None:
    """Use the console script when present; PyPI also supports python -m graphify."""
    if executable(root):
        return [executable(root)]
    try:
        import graphify  # noqa: F401
        return [sys.executable, "-m", "graphify"]
    except ImportError:
        return None


def version(root: Path | None = None) -> str | None:
    if root is not None:
        command = executable(root)
        if command:
            try:
                output = subprocess.run([command, "--version"], text=True, capture_output=True, timeout=5, check=False)
                if output.returncode == 0:
                    return (output.stdout or output.stderr).strip().rsplit(" ", 1)[-1]
            except (OSError, subprocess.SubprocessError):
                pass
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
    # Preserve the public no-argument command resolver for existing callers;
    # only a project-managed runtime needs an explicit root-aware prefix.
    from .providers.lifecycle import managed_command
    managed = managed_command(root, "graphify")
    prefix = [managed] if managed else command_prefix()
    if not prefix:
        raise GraphifyError("Graphify is required. Install it with: pipx install graphifyy")
    scope = scope or IndexScope.load(root)
    output_parent = root / ".klap"
    output_parent.mkdir(parents=True, exist_ok=True)
    # Graphify's supported --out writes one graphify-out directory beneath the
    # selected parent. The temporary ignore file applies central scope before
    # AST extraction while remaining compatible across supported releases.
    command = [*prefix, "extract", str(root), "--code-only", "--out", str(output_parent)]
    if update:
        # A normal extract reuses Graphify's manifest/cache in the canonical
        # directory while still pruning files that became excluded.
        command.append("--no-cluster")
    try:
        with _scoped_graphifyignore(root, scope):
            result = subprocess.run(command, cwd=root, text=True, capture_output=True, timeout=120)
    except subprocess.TimeoutExpired as error:
        raise GraphifyError("Graphify extraction timed out after 120s") from error
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
    try:
        subprocess.run(prefix + ["export", "html", "--graph", str(graph)], cwd=root, text=True, capture_output=True, timeout=30)
        subprocess.run(prefix + ["export", "callflow-html", str(graph)], cwd=root, text=True, capture_output=True, timeout=30)
    except subprocess.TimeoutExpired:
        pass
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
