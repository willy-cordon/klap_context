"""Safe, idempotent onboarding for AGENTS.md-compatible coding agents."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path

from .git import commit, dirty_files, is_repository, run_git
from .graphify import command_prefix

START = "<!-- KLAPCONTEXT:START -->"
END = "<!-- KLAPCONTEXT:END -->"
AGENT_FILE = "AGENTS.md"


@dataclass
class AgentSetupResult:
    status: str
    path: str = AGENT_FILE
    mode: str = "private"
    created: bool = False
    updated: bool = False
    tracked: bool = False
    mcp_configured: bool = False
    message: str = ""

    def as_dict(self) -> dict:
        return asdict(self)


def is_tracked(root: Path, relative: str = AGENT_FILE) -> bool:
    return is_repository(root) and run_git(root, "ls-files", "--error-unmatch", relative) is not None


def marker_state(text: str) -> str:
    starts, ends = text.count(START), text.count(END)
    if starts == ends == 0:
        return "absent"
    if starts == ends == 1 and text.index(START) < text.index(END):
        return "valid"
    return "malformed"


def context_freshness(root: Path) -> dict:
    state_file = root / ".klap" / "state.json"
    if not state_file.exists():
        return {"status": "MISSING", "reason": "No existe .klap/state.json"}
    try:
        state = json.loads(state_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"status": "INVALID", "reason": "state.json no es válido"}
    current = commit(root)
    ignored = (".klap/", "graphify-out/", AGENT_FILE)
    relevant = [path for path in dirty_files(root) if not path.replace("\\", "/").startswith(ignored)]
    if state.get("git_commit") != current:
        return {"status": "STALE", "reason": "El commit analizado no coincide con HEAD", "changed_files": relevant}
    if relevant:
        return {"status": "STALE", "reason": "Hay cambios relevantes sin confirmar", "changed_files": relevant}
    return {"status": "CURRENT", "reason": "El contexto coincide con el código confirmado", "changed_files": []}


def generate_mcp_configs(root: Path) -> dict:
    """Write local examples only; never mutate global agent configuration."""
    graph = (root / ".klap" / "graphify" / "graph.json").resolve()
    directory = root / ".klap" / "mcp"
    directory.mkdir(parents=True, exist_ok=True)
    prefix = command_prefix()
    available = bool(prefix and graph.exists())
    command = sys.executable
    args = ["-m", "graphify.serve", str(graph)]
    generic = {"mcpServers": {"graphify": {"command": command, "args": args}}}
    (directory / "generic.json").write_text(json.dumps(generic, indent=2) + "\n", encoding="utf-8")
    codex = "[mcp_servers.graphify]\n" + f'command = {json.dumps(command)}\nargs = {json.dumps(args)}\n'
    (directory / "codex.toml").write_text(codex, encoding="utf-8")
    instructions = f"""# Graphify MCP setup

Generated local configuration examples. They contain no credentials.

- Generic / Claude Code project config: `.klap/mcp/generic.json`
- Cursor project config: copy the same JSON to `.cursor/mcp.json` only when you explicitly want project configuration.
- Codex project config snippet: `.klap/mcp/codex.toml`

The configured stdio command is:

`{command} {' '.join(args)}`

Run `klap doctor --agent --probe-mcp` to verify that the server can start. A configuration file alone does not prove a client connection.
"""
    (directory / "README.md").write_text(instructions, encoding="utf-8")
    return {"available": available, "directory": ".klap/mcp", "generic": ".klap/mcp/generic.json", "codex": ".klap/mcp/codex.toml"}


def _overview(context: dict) -> str:
    project = context.get("project", {})
    system = context.get("system_model", {})
    stack = context.get("stack", {})
    purpose = system.get("purpose", {}).get("text")
    languages = ", ".join(stack.get("languages", []))
    frameworks = ", ".join(stack.get("frameworks", []))
    facts = [f"Repository `{project.get('name', 'project')}`"]
    if languages:
        facts.append(f"uses {languages}")
    if frameworks:
        facts.append(f"with {frameworks}")
    summary = " ".join(facts) + "."
    if purpose:
        summary += " " + purpose.strip()
    flows = system.get("main_flows", [])
    if flows:
        summary += f" KlapContext detected {len(flows)} main execution flow(s)."
    return summary


def render_agent_block(context: dict, *, shared: bool) -> str:
    shared_note = "\nIf `.klap/` is missing, run `klap init` before relying on generated context.\n" if shared else ""
    return f"""{START}

## KlapContext — Engineering Context

This repository has been analyzed by KlapContext.

### Project overview

{_overview(context)}
{shared_note}
### Before starting a task

1. Run `klap status`; if relevant context is stale, run `klap update`.
2. Read `.klap/agent-context.md` progressively; do not load the entire graph.
3. Use Graphify MCP for dependencies, call paths, callers and impact analysis.
4. Identify the relevant execution flow before modifying code.
5. Read the actual source code and related tests before making changes.
6. Treat inferred relationships as hypotheses until verified.

### Context resources

- `.klap/agent-context.md`
- `.klap/context.json`
- `.klap/index.html`
- `.klap/graphify/graph.json`
- `.klap/mcp/README.md`

### Working rules

- Respect existing architecture, conventions and contracts.
- Prefer focused Graphify queries over broad repository searches.
- Never modify code based only on generated context; verify the source first.
- Preserve existing contracts unless the task explicitly requires changing them.

{END}"""


class AgentInstructionsManager:
    def __init__(self, root: Path):
        self.root = root.resolve()
        self.path = self.root / AGENT_FILE

    def apply(self, context: dict, *, shared: bool = False, allow_tracked: bool = False) -> AgentSetupResult:
        mode = "shared" if shared else "private"
        tracked = is_tracked(self.root)
        if tracked and not (shared or allow_tracked):
            return AgentSetupResult("authorization_required", mode=mode, tracked=True, message="AGENTS.md está versionado; se requiere autorización explícita.")
        existing = self.path.read_text(encoding="utf-8") if self.path.exists() else ""
        state = marker_state(existing)
        if state == "malformed":
            return AgentSetupResult("conflict", mode=mode, tracked=tracked, message="Marcadores KLAPCONTEXT incompletos o duplicados; no se modificó AGENTS.md.")
        block = render_agent_block(context, shared=shared)
        if state == "valid":
            start = existing.index(START)
            end = existing.index(END, start) + len(END)
            updated = existing[:start] + block + existing[end:]
        elif existing.strip():
            updated = existing.rstrip() + "\n\n" + block + "\n"
        else:
            updated = block + "\n"
        if updated == existing:
            if shared:
                self._include_shared_agents()
            return AgentSetupResult("unchanged", mode=mode, tracked=tracked, mcp_configured=True, message="AGENTS.md ya está actualizado.")
        self._atomic_write(updated, existing if self.path.exists() else None)
        if shared:
            self._include_shared_agents()
        elif not tracked and is_repository(self.root):
            self._exclude_private_agents()
        return AgentSetupResult("configured", mode=mode, created=not bool(existing), updated=bool(existing), tracked=tracked, mcp_configured=True, message="AGENTS.md configurado de forma segura.")

    def _atomic_write(self, content: str, previous: str | None) -> None:
        if previous is not None:
            backup = self.root / ".klap" / "backups" / AGENT_FILE
            backup.parent.mkdir(parents=True, exist_ok=True)
            backup.write_text(previous, encoding="utf-8")
        fd, name = tempfile.mkstemp(prefix=".AGENTS.", suffix=".tmp", dir=self.root)
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(name, self.path)
        finally:
            if os.path.exists(name):
                os.unlink(name)

    def _exclude_private_agents(self) -> None:
        git_dir = run_git(self.root, "rev-parse", "--git-dir")
        if not git_dir:
            return
        exclude = (self.root / git_dir / "info" / "exclude").resolve()
        existing = exclude.read_text(encoding="utf-8") if exclude.exists() else ""
        if AGENT_FILE not in {line.strip() for line in existing.splitlines()}:
            exclude.write_text(existing.rstrip() + ("\n" if existing.strip() else "") + AGENT_FILE + "\n", encoding="utf-8")

    def _include_shared_agents(self) -> None:
        git_dir = run_git(self.root, "rev-parse", "--git-dir")
        if not git_dir:
            return
        exclude = (self.root / git_dir / "info" / "exclude").resolve()
        if not exclude.exists():
            return
        lines = exclude.read_text(encoding="utf-8").splitlines()
        filtered = [line for line in lines if line.strip() != AGENT_FILE]
        if filtered != lines:
            exclude.write_text("\n".join(filtered).rstrip() + ("\n" if filtered else ""), encoding="utf-8")

    def validate(self) -> dict:
        if not self.path.exists():
            return {"status": "missing", "valid": False, "message": "AGENTS.md no existe"}
        text = self.path.read_text(encoding="utf-8")
        state = marker_state(text)
        paths = [".klap/agent-context.md", ".klap/context.json", ".klap/index.html", ".klap/graphify/graph.json"]
        missing = [path for path in paths if not (self.root / path).exists()]
        return {"status": state, "valid": state == "valid" and not missing, "missing_paths": missing, "message": "Configuración válida" if state == "valid" and not missing else "Configuración incompleta"}


def probe_graphify_mcp(root: Path, timeout: float = 2.0) -> dict:
    graph = root / ".klap" / "graphify" / "graph.json"
    prefix = command_prefix()
    if not prefix or not graph.exists():
        return {"startable": False, "connection_verified": False, "reason": "Graphify o graph.json no disponible"}
    command = [sys.executable, "-m", "graphify.serve", str(graph)]
    process = subprocess.Popen(command, cwd=root, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        process.wait(timeout=timeout)
        return {"startable": process.returncode == 0, "connection_verified": False, "reason": "El proceso terminó sin una sesión MCP"}
    except subprocess.TimeoutExpired:
        process.terminate()
        try:
            process.wait(timeout=1)
        except subprocess.TimeoutExpired:
            process.kill()
        return {"startable": True, "connection_verified": False, "reason": "El servidor inició; no se verificó conexión de un cliente"}


def doctor_agent(root: Path, *, probe_mcp: bool = False) -> dict:
    manager = AgentInstructionsManager(root)
    agents = manager.validate()
    freshness = context_freshness(root)
    graph = root / ".klap" / "graphify" / "graph.json"
    mcp_files = [root / ".klap" / "mcp" / "generic.json", root / ".klap" / "mcp" / "codex.toml"]
    mcp_probe = probe_graphify_mcp(root) if probe_mcp else {"startable": bool(command_prefix() and graph.exists()), "connection_verified": False, "reason": "Use --probe-mcp para comprobar el arranque"}
    return {"agents": agents, "context": {"available": (root / ".klap" / "agent-context.md").exists() and (root / ".klap" / "context.json").exists()}, "freshness": freshness, "graph": {"available": graph.exists()}, "mcp": {"configured": all(path.exists() for path in mcp_files), **mcp_probe}}
