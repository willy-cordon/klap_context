from __future__ import annotations
import argparse, json, os, sys, webbrowser
from datetime import datetime, timezone
from pathlib import Path

from . import __version__
from .agent_context import write as write_agent
from .agent_setup import AgentInstructionsManager, context_freshness, doctor_agent, generate_mcp_configs, is_tracked
from .context_builder import build
from .git import commit, dirty_files, exclude_klap, is_repository
from .graphify import GraphifyError
from .portal import write as write_portal
from .providers import default_provider


def root_path(value: str | None) -> Path:
    return Path(value or os.getcwd()).resolve()


def generate_all(root: Path, update: bool = False, *, shared: bool = False, allow_tracked_agents: bool = False) -> dict:
    if not is_repository(root):
        raise RuntimeError(f"Not a Git repository: {root}")
    exclude_klap(root)
    klap = root / ".klap"
    klap.mkdir(exist_ok=True)
    provider = default_provider()
    graph_path = provider.generate(root, update)
    files = provider.copy_outputs(root, klap / "graphify")
    context = build(root, provider.load_graph(graph_path))
    (klap / "context.json").write_text(json.dumps(context, indent=2) + "\n", encoding="utf-8")
    agent = write_agent(context, klap / "agent-context.md")
    mcp = generate_mcp_configs(root)
    setup = AgentInstructionsManager(root).apply(context, shared=shared, allow_tracked=allow_tracked_agents)
    context["agent_onboarding"] = {**setup.as_dict(), "mcp": mcp}
    (klap / "context.json").write_text(json.dumps(context, indent=2) + "\n", encoding="utf-8")
    write_portal(context, agent, files, klap / "index.html")
    state = {
        "schema_version": "0.3",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "git_commit": commit(root),
        "provider": {"name": provider.name, "version": provider.version()},
        "klap_version": __version__,
        "agent_onboarding": setup.as_dict(),
    }
    (klap / "state.json").write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
    return context


def _permission(args, root: Path, action: str) -> tuple[bool, bool]:
    shared = getattr(args, "shared", False)
    allow = getattr(args, "allow_tracked_agents", False)
    if not shared and is_tracked(root) and not allow and sys.stdin.isatty():
        allow = input(f"AGENTS.md está versionado. ¿{action} la sección KlapContext? [y/N] ").strip().lower() in {"y", "yes", "s", "si", "sí"}
    return shared, allow


def cmd_init(args):
    root = root_path(args.path)
    print("KlapContext\n")
    shared, allow = _permission(args, root, "Agregar o actualizar")
    try:
        context = generate_all(root, shared=shared, allow_tracked_agents=allow) if shared or allow else generate_all(root)
    except (RuntimeError, GraphifyError) as error:
        print(f"✗ {error}", file=sys.stderr)
        return 1
    print("✓ Git repository detected\n✓ Graphify available\n✓ Graph generated\n✓ Engineering context generated\n✓ Agent context generated\n✓ Human portal generated")
    setup = context.get("agent_onboarding", {})
    print(("✓ " if setup.get("status") in {"configured", "unchanged"} else "! ") + setup.get("message", "Agent onboarding not configured"))
    coverage = context["system_model"]["exploration"]["coverage"]
    print(f"Coverage: {coverage['code_files_with_graph_nodes']}/{coverage['eligible_code_files']} code files represented in graph ({coverage['status']}); graph nodes do not guarantee complete symbol analysis")
    stack_items = [item for values in context["stack"].values() if isinstance(values, list) for item in values]
    print(f"\nProject: {context['project']['name']}\nStack: {' / '.join(stack_items) or 'unknown'}\nContext: CURRENT\n\nHuman portal:\n.klap/index.html\n\nAgent context:\n.klap/agent-context.md")
    return 0


def cmd_update(args):
    root = root_path(args.path)
    shared, allow = _permission(args, root, "Actualizar")
    try:
        context = generate_all(root, update=True, shared=shared, allow_tracked_agents=allow) if shared or allow else generate_all(root, update=True)
    except (RuntimeError, GraphifyError) as error:
        print(f"✗ {error}", file=sys.stderr)
        return 1
    coverage = context["system_model"]["exploration"]["coverage"]
    print(f"✓ KlapContext updated; graph coverage: {coverage['code_files_with_graph_nodes']}/{coverage['eligible_code_files']} code files ({coverage['status']})")
    return 0


def cmd_status(args):
    root = root_path(args.path)
    state_file = root / ".klap" / "state.json"
    if not state_file.exists():
        print("! No KlapContext found. Run: klap init")
        return 1
    try:
        state = json.loads(state_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        print("Status: INVALID\nstate.json no es válido")
        return 2
    current = commit(root)
    ignored = (".klap/", "graphify-out/", "AGENTS.md")
    relevant = [path for path in dirty_files(root) if not path.replace("\\", "/").startswith(ignored)]
    fresh = state.get("git_commit") == current and not relevant
    reason = "El contexto coincide con el código confirmado" if fresh else "El commit analizado o archivos relevantes cambiaron"
    print(f"Status: {'CURRENT' if fresh else 'STALE'}\n{reason}")
    return 0 if fresh else 2


def cmd_doctor(args):
    result = doctor_agent(root_path(args.path), probe_mcp=getattr(args, "probe_mcp", False))
    print("KlapContext — Agent Doctor\n")
    checks = [
        (result["agents"]["valid"], "AGENTS.md configured"),
        (result["context"]["available"], "Engineering context available"),
        (result["freshness"]["status"] == "CURRENT", "Context is current"),
        (result["graph"]["available"], "Graphify graph available"),
        (result["mcp"]["configured"], "MCP configuration generated"),
    ]
    for ok, label in checks:
        print(("✓" if ok else "!") + " " + label)
    print(("✓" if result["mcp"]["connection_verified"] else "!") + " MCP connection " + ("verified" if result["mcp"]["connection_verified"] else "not yet verified"))
    if result["agents"].get("missing_paths"):
        print("Missing paths: " + ", ".join(result["agents"]["missing_paths"]))
    return 0 if all(ok for ok, _ in checks) else 2


def cmd_open(args):
    page = root_path(args.path) / ".klap" / "index.html"
    if not page.exists():
        print("⚠ No human portal found. Run: klap init", file=sys.stderr)
        return 1
    webbrowser.open(page.as_uri())
    print(f"Opened {page}")
    return 0


def cmd_agent(args):
    root = root_path(args.path)
    graph = root / ".klap" / "graphify" / "graph.json"
    if not graph.exists():
        print("⚠ No Graphify graph found. Run: klap init", file=sys.stderr)
        return 1
    config = generate_mcp_configs(root)
    print(f"Graphify MCP setup generated in {config['directory']}\nGeneric: {config['generic']}\nCodex: {config['codex']}\nRun: klap doctor --agent --probe-mcp")
    return 0


def cmd_context(args):
    from .agent.compiler import compile_context
    result = compile_context(root_path(args.path), args.query, detail=args.detail, max_tokens=args.max_tokens)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"Intent: {result['intent']}\nÁrea: {result['area']}\nRead first:\n" + "\n".join(f"- {item.get('path', item.get('name'))}: {item['reason']}" for item in result["read_first"]))
    return 0


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(prog="klap", description="Make your repository understandable to humans and AI.")
    parser.add_argument("--version", action="version", version=__version__)
    subs = parser.add_subparsers(dest="command", required=True)
    for name, func, help_text in (("init", cmd_init, "Generate engineering context"), ("update", cmd_update, "Refresh engineering context"), ("status", cmd_status, "Show context freshness"), ("open", cmd_open, "Open the human portal"), ("agent", cmd_agent, "Show Graphify MCP setup")):
        command = subs.add_parser(name, help=help_text)
        command.add_argument("path", nargs="?", help="Repository root (defaults to current directory)")
        if name in {"init", "update"}:
            command.add_argument("--shared", action="store_true", help="Create versionable AGENTS.md instructions")
            command.add_argument("--allow-tracked-agents", action="store_true", help="Authorize updating a tracked AGENTS.md")
        command.set_defaults(func=func)
    command = subs.add_parser("doctor", help="Diagnose project and agent readiness")
    command.add_argument("path", nargs="?", default=".")
    command.add_argument("--agent", action="store_true", help="Check AGENTS.md and generated context")
    command.add_argument("--probe-mcp", action="store_true", help="Start Graphify MCP briefly and stop it")
    command.set_defaults(func=cmd_doctor)
    command = subs.add_parser("context", help="Compile compact context for an agent task")
    command.add_argument("query")
    command.add_argument("path", nargs="?", default=".")
    command.add_argument("--detail", choices=("minimal", "standard", "deep"), default="standard")
    command.add_argument("--max-tokens", type=int, default=5000)
    command.add_argument("--json", action="store_true")
    command.set_defaults(func=cmd_context)
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
