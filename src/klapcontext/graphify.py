from __future__ import annotations
import importlib.metadata, json, shutil, subprocess, sys
from pathlib import Path

class GraphifyError(RuntimeError): pass

def executable() -> str | None: return shutil.which("graphify")

def command_prefix() -> list[str] | None:
    """Use the console script when present; PyPI's current package also supports python -m graphify."""
    if executable(): return [executable()]
    try:
        import graphify  # noqa: F401
        return [sys.executable, "-m", "graphify"]
    except ImportError: return None

def version() -> str | None:
    try: return importlib.metadata.version("graphifyy")
    except importlib.metadata.PackageNotFoundError: return None

def generate(root: Path, update: bool = False) -> Path:
    prefix = command_prefix()
    if not prefix: raise GraphifyError("Graphify is required. Install it with: pipx install graphifyy")
    # Graphify owns parsing/incrementality; --code-only keeps KlapContext's base fully local/no-LLM.
    command = prefix + (["update", str(root)] if update else ["extract", str(root), "--code-only"])
    result = subprocess.run(command, cwd=root, text=True, capture_output=True)
    # Some current Windows Graphify builds can abort in `update`; retain its
    # incremental fast path but recover with the documented deterministic scan.
    if update and result.returncode != 0:
        result = subprocess.run(prefix + ["extract", str(root), "--code-only"], cwd=root, text=True, capture_output=True)
    graph = root / "graphify-out" / "graph.json"
    if result.returncode != 0 or not graph.exists():
        message = result.stderr.strip() or result.stdout.strip() or "Graphify did not create graph.json"
        raise GraphifyError(message)
    # Visualization exporters are Graphify's implementation, not a KlapContext reimplementation.
    for export in (["export", "html", "--graph", str(graph)], ["export", "callflow-html", str(graph)]):
        subprocess.run(prefix + export, cwd=root, text=True, capture_output=True)
    return graph

def load_graph(graph: Path) -> dict:
    try: return json.loads(graph.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError): return {}

def copy_outputs(root: Path, destination: Path) -> list[str]:
    import shutil
    source = root / "graphify-out"; destination.mkdir(parents=True, exist_ok=True); copied=[]
    for name in ("graph.json", "graph.html", "GRAPH_REPORT.md"):
        if (source/name).exists(): shutil.copy2(source/name, destination/name); copied.append(name)
    callflows = list(source.glob("*-callflow.html")) + list(source.glob("callflow.html"))
    if callflows:
        shutil.copy2(callflows[0], destination/"callflow.html"); copied.append("callflow.html")
    return copied
