from __future__ import annotations
import argparse, json, os, sys, webbrowser
from datetime import datetime, timezone
from pathlib import Path
from . import __version__
from .agent_context import write as write_agent
from .context_builder import build
from .git import commit, dirty_files, exclude_klap, is_repository
from .graphify import GraphifyError
from .portal import write as write_portal
from .providers import default_provider

def root_path(value: str | None) -> Path: return Path(value or os.getcwd()).resolve()

def generate_all(root: Path, update: bool=False) -> dict:
    if not is_repository(root): raise RuntimeError(f"Not a Git repository: {root}")
    exclude_klap(root); klap=root/".klap"; klap.mkdir(exist_ok=True)
    provider=default_provider()
    graph_path=provider.generate(root, update); files=provider.copy_outputs(root, klap/"graphify")
    context=build(root, provider.load_graph(graph_path)); (klap/"context.json").write_text(json.dumps(context, indent=2)+"\n", encoding="utf-8")
    agent=write_agent(context, klap/"agent-context.md"); write_portal(context, agent, files, klap/"index.html")
    state={"schema_version":"0.2","generated_at":datetime.now(timezone.utc).isoformat(),"git_commit":commit(root),"provider":{"name":provider.name,"version":provider.version()},"klap_version":__version__}
    (klap/"state.json").write_text(json.dumps(state, indent=2)+"\n", encoding="utf-8")
    return context

def cmd_init(args):
    root=root_path(args.path); print("KlapContext\n")
    try:
        context=generate_all(root)
    except (RuntimeError, GraphifyError) as e:
        print(f"✗ {e}", file=sys.stderr); return 1
    print("✓ Git repository detected\n✓ Graphify available\n✓ Graph generated\n✓ Engineering context generated\n✓ Agent context generated\n✓ Human portal generated")
    print(f"\nProject: {context['project']['name']}\nStack: {' / '.join(sum((v for v in context['stack'].values()), [])) or 'unknown'}\nContext: CURRENT\n\nHuman portal:\n.klap/index.html\n\nAgent context:\n.klap/agent-context.md")
    return 0

def cmd_update(args):
    try: generate_all(root_path(args.path), update=True)
    except (RuntimeError, GraphifyError) as e: print(f"✗ {e}", file=sys.stderr); return 1
    print("✓ KlapContext updated"); return 0

def cmd_status(args):
    root=root_path(args.path); state_file=root/".klap"/"state.json"
    if not state_file.exists(): print("⚠ No KlapContext found. Run: klap init"); return 1
    state=json.loads(state_file.read_text(encoding="utf-8")); current=commit(root); dirty=dirty_files(root)
    fresh=state.get("git_commit")==current and not dirty
    print(f"Context commit: {(state.get('git_commit') or 'none')[:12]}\nCurrent commit: {(current or 'none')[:12]}\nUncommitted changes: {len(dirty)} files\n\nStatus: {'✓ CURRENT' if fresh else '⚠ STALE'}")
    return 0 if fresh else 2

def cmd_open(args):
    page=root_path(args.path)/".klap"/"index.html"
    if not page.exists(): print("⚠ No human portal found. Run: klap init", file=sys.stderr); return 1
    webbrowser.open(page.as_uri()); print(f"Opened {page}"); return 0

def cmd_agent(args):
    graph=root_path(args.path)/".klap"/"graphify"/"graph.json"
    if not graph.exists(): print("⚠ No Graphify graph found. Run: klap init", file=sys.stderr); return 1
    print("Graphify MCP (stdio):\npython -m graphify.serve " + str(graph) + "\n\nGeneric configuration:\n{\n  \"mcpServers\": {\n    \"graphify\": {\n      \"command\": \"python\",\n      \"args\": [\"-m\", \"graphify.serve\", \"" + str(graph).replace('\\','\\\\') + "\"]\n    }\n  }\n}")
    return 0

def cmd_context(args):
    from .agent.compiler import compile_context
    result=compile_context(root_path(args.path), args.query, detail=args.detail, max_tokens=args.max_tokens)
    if args.json: print(json.dumps(result, ensure_ascii=False, indent=2))
    else: print(f"Intent: {result['intent']}\nÁrea: {result['area']}\nRead first:\n" + "\n".join(f"- {item.get('path', item.get('name'))}: {item['reason']}" for item in result['read_first']))
    return 0

def main(argv=None):
    # PowerShell's legacy cp1252 console otherwise raises on the intended status symbols.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    parser=argparse.ArgumentParser(prog="klap", description="Make your repository understandable to humans and AI.")
    parser.add_argument("--version", action="version", version=__version__)
    subs=parser.add_subparsers(dest="command", required=True)
    for name, func, help_text in (("init",cmd_init,"Generate engineering context"),("update",cmd_update,"Refresh engineering context"),("status",cmd_status,"Show context freshness"),("open",cmd_open,"Open the human portal"),("agent",cmd_agent,"Show Graphify MCP setup")):
        p=subs.add_parser(name, help=help_text); p.add_argument("path", nargs="?", help="Repository root (defaults to current directory)"); p.set_defaults(func=func)
    p=subs.add_parser("context", help="Compile compact context for an agent task"); p.add_argument("query"); p.add_argument("path", nargs="?", default="."); p.add_argument("--detail", choices=("minimal", "standard", "deep"), default="standard"); p.add_argument("--max-tokens", type=int, default=5000); p.add_argument("--json", action="store_true"); p.set_defaults(func=cmd_context)
    args=parser.parse_args(argv); return args.func(args)

if __name__ == "__main__": raise SystemExit(main())
