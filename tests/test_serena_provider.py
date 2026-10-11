import ast
import json
import sys
import time
from pathlib import Path

import pytest

from klapcontext.providers import AnalysisServices, Capability, CapabilityResolver, ProviderRegistry, ResultState, default_registry
from klapcontext.providers.native import NativeGraphProvider, PhpTreeSitterProvider
from klapcontext.providers.serena import SerenaProvider, SerenaSettings, load_serena_settings, serena_diagnostics
from klapcontext.providers.serena.client import SerenaMcpClient


TOOL_SCHEMAS = {
    "find_symbol": {"name_path_pattern", "relative_path", "depth", "include_body", "include_info", "substring_matching", "max_matches", "max_answer_chars"},
    "get_symbols_overview": {"relative_path", "depth", "max_answer_chars"},
    "find_referencing_symbols": {"name_path", "relative_path", "max_answer_chars"},
    "find_implementations": {"name_path", "relative_path", "include_info", "max_answer_chars"},
}


class FakeClient:
    def __init__(self, tools=TOOL_SCHEMAS, outputs=None, error=None):
        self.server_info = {"name": "Serena", "version": "mcp-sdk"}
        self.tools = {
            name: {"name": name, "inputSchema": {"type": "object", "properties": {key: {} for key in properties}}}
            for name, properties in tools.items()
        }
        self.outputs = outputs or {}
        self.error = error
        self.calls = []
        self.closed = False

    def list_tools(self):
        if self.error:
            raise self.error
        return self.tools

    def call(self, name, arguments):
        self.calls.append((name, arguments))
        value = self.outputs.get(name, [])
        return value(arguments) if callable(value) else value

    def close(self):
        self.closed = True


def settings(**overrides):
    values = {"command": sys.executable, "args": ("fake_server.py",), "timeout_seconds": 1.0, "configured": True}
    values.update(overrides)
    return SerenaSettings(**values)


def symbol(name="ProcessRequestService", path="app/Services/ProcessRequestService.php", start=3, body=None):
    value = {"name_path": name, "kind": "Class", "relative_path": path, "body_location": {"start_line": start, "end_line": start + 2}}
    if body:
        value["body"] = body
    return value


def provider(tmp_path, client):
    return SerenaProvider(tmp_path, settings(), client=client)


def test_core_modules_do_not_import_serena_adapter():
    root = Path(__file__).parents[1]
    paths = [
        root / "src/klapcontext/cli.py",
        root / "src/klapcontext/context_builder.py",
        root / "src/klapcontext/agent/compiler.py",
        root / "src/klapcontext/agent/impact.py",
        root / "src/klapcontext/agent/capabilities.py",
        root / "src/klapcontext/providers/services.py",
        root / "mcp_server.py",
    ]
    offenders = []
    for path in paths:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            module = node.module if isinstance(node, ast.ImportFrom) else ""
            names = [item.name for item in node.names] if isinstance(node, ast.Import) else []
            if "serena" in (module or "").casefold() or any("serena" in item.casefold() for item in names):
                offenders.append(f"{path.name}:{node.lineno}")
    assert offenders == []


def test_absent_and_installed_unconfigured_are_distinct(tmp_path, monkeypatch):
    monkeypatch.setattr("klapcontext.providers.serena.config.shutil.which", lambda command: None)
    absent = serena_diagnostics(tmp_path)
    assert not absent["configured"] and not absent["detected"] and absent["missing_dependencies"] == ["serena"]

    monkeypatch.setattr("klapcontext.providers.serena.config.shutil.which", lambda command: "serena")
    installed = serena_diagnostics(tmp_path)
    assert installed["detected"] and not installed["configured"] and installed["startable"] is None


def test_portable_config_enabled_mode_timeout_command_and_args(tmp_path):
    config = tmp_path / ".klap" / "providers.json"
    config.parent.mkdir()
    config.write_text(json.dumps({"providers": {"serena": {
        "enabled": False, "mode": "configured", "timeout_seconds": 7,
        "command": "serena", "args": ["start-mcp-server", "--context=ide"],
        "max_results": 9, "max_answer_chars": 9000,
    }}}), encoding="utf-8")
    value = load_serena_settings(tmp_path)
    assert not value.enabled and value.mode == "configured" and value.timeout_seconds == 7
    assert value.command == "serena" and value.args[-1] == "--context=ide"
    assert str(tmp_path.resolve()) in value.launch_args(tmp_path)


def test_config_rejects_personal_project_argument(tmp_path):
    config = tmp_path / ".klap" / "providers.json"
    config.parent.mkdir()
    config.write_text('{"providers":{"serena":{"args":["start-mcp-server","--project","C:/private"]}}}', encoding="utf-8")
    with pytest.raises(ValueError, match="must not set a project"):
        load_serena_settings(tmp_path)


def test_working_lookup_preserves_location_evidence_provider_and_confidence(tmp_path):
    fake = FakeClient(outputs={"find_symbol": json.dumps([symbol(body="class ProcessRequestService")])})
    result = provider(tmp_path, fake).find_symbols({"query": "ProcessRequestService", "operation": "definition"})
    assert result.state == ResultState.OK
    found = result.data[0]
    assert found.qualified_name == "ProcessRequestService" and found.location.path.endswith("ProcessRequestService.php")
    assert found.location.line == 4 and found.provider.name == "serena"
    assert found.evidence[0].excerpt == "class ProcessRequestService" and found.confidence.value == "CONFIRMED"
    assert fake.calls[0][0] == "find_symbol" and fake.calls[0][1]["include_body"] is True


def test_failing_and_partial_toolsets_are_explicit(tmp_path):
    broken = provider(tmp_path, FakeClient(error=RuntimeError("cannot start")))
    registry = ProviderRegistry(); registry.register(broken)
    result = CapabilityResolver(registry).resolve(Capability.SYMBOL_LOOKUP, {"query": "X"}, fallback=False)
    assert result.state == ResultState.PROVIDER_ERROR and "discovery failed" in result.error

    partial = provider(tmp_path, FakeClient(tools={"find_symbol": TOOL_SCHEMAS["find_symbol"]}, outputs={"find_symbol": []}))
    assert Capability.REFERENCES not in partial.capabilities_for()
    refs = partial.find_references({"symbol": "X"})
    assert refs.state == ResultState.UNSUPPORTED and "tools/list" in refs.error


def test_serena_discovery_failure_falls_back_with_trace(tmp_path):
    broken = provider(tmp_path, FakeClient(error=RuntimeError("cannot start")))

    class Fallback:
        name = "fallback"
        capabilities = {Capability.SYMBOL_LOOKUP}
        def find_symbols(self, request):
            return [{"name": "X", "path": "x.py", "line": 1}]

    registry = ProviderRegistry()
    registry.register(broken, priorities={Capability.SYMBOL_LOOKUP: 100})
    registry.register(Fallback(), priorities={Capability.SYMBOL_LOOKUP: 1})
    result = CapabilityResolver(registry).resolve(Capability.SYMBOL_LOOKUP, {"query": "X"})
    assert result.state == ResultState.OK and result.provider.name == "fallback"
    assert result.trace[0]["provider"] == "serena" and result.trace[0]["state"] == "PROVIDER_ERROR"
    assert any("fallback" in warning for warning in result.warnings)


def test_reference_none_duplicate_names_and_impact_labels(tmp_path):
    definitions = [symbol("A/Duplicate", "one.php", 0), symbol("B/Duplicate", "two.php", 5)]
    outputs = {
        "find_symbol": definitions,
        "find_referencing_symbols": lambda args: [] if args["relative_path"] == "one.php" else [symbol("Consumer/useDuplicate", "consumer.php", 8)],
    }
    semantic = provider(tmp_path, FakeClient(outputs=outputs))
    references = semantic.find_references({"symbol": "Duplicate"})
    assert references.state == ResultState.OK and len(references.data) == 1
    assert references.data[0]["verified"] is True and references.data[0]["impact"] == "inferred_from_verified_reference"
    impact = semantic.impact({"symbol": "Duplicate"})
    assert impact.data["direct_callers"][0]["line"] == 9
    assert impact.data["impact"][0]["status"] == "INFERRED"

    no_refs = provider(tmp_path, FakeClient(outputs={"find_symbol": [symbol()], "find_referencing_symbols": []})).find_references({"symbol": "ProcessRequestService"})
    assert no_refs.state == ResultState.NO_RESULTS and no_refs.data == []


def test_paths_outside_root_are_rejected_and_returned_paths_are_dropped(tmp_path):
    semantic = provider(tmp_path, FakeClient(outputs={"find_symbol": [symbol(path="../escape.php")]}))
    with pytest.raises(ValueError, match="project root"):
        semantic.find_symbols({"query": "X", "path": "../outside.php"})
    result = semantic.find_symbols({"query": "X"})
    assert result.state == ResultState.NO_RESULTS


def test_disabled_serena_is_not_called(tmp_path):
    fake = FakeClient(outputs={"find_symbol": [symbol()]})
    registry = ProviderRegistry(); registry.register(provider(tmp_path, fake), enabled=False)
    result = CapabilityResolver(registry).resolve(Capability.SYMBOL_LOOKUP, {"query": "X"})
    assert result.state == ResultState.UNSUPPORTED and fake.calls == []


def test_graphify_serena_and_native_providers_coexist_without_eager_serena(tmp_path):
    (tmp_path / "main.php").write_text("<?php function main() { return 1; }", encoding="utf-8")

    class Graph:
        name = "graphify"
        capabilities = {Capability.DEPENDENCY_GRAPH}
        def dependency_graph(self, request):
            return {"nodes": [{"name": "main", "path": "main.php"}], "edges": []}

    fake = FakeClient(outputs={"find_symbol": [symbol("main", "main.php", 0)]})
    registry = ProviderRegistry()
    registry.register(Graph(), priorities={Capability.DEPENDENCY_GRAPH: 100})
    registry.register(NativeGraphProvider(), priorities={Capability.DEPENDENCY_GRAPH: -100})
    registry.register(PhpTreeSitterProvider(), languages={"php"})
    registry.register(provider(tmp_path, fake), priorities={Capability.SYMBOL_LOOKUP: 80})
    resolver = CapabilityResolver(registry)
    graph = resolver.resolve(Capability.DEPENDENCY_GRAPH, {"root": tmp_path})
    assert graph.provider.name == "graphify" and fake.calls == []
    symbols = resolver.resolve_all(Capability.SYMBOL_LOOKUP, {"root": tmp_path, "query": "main"}, language="php")
    provider_names = {item["provider"].get("name") if isinstance(item.get("provider"), dict) else item.get("provider") for item in symbols.data}
    assert symbols.state == ResultState.OK and provider_names >= {"serena"}


def test_default_registry_registers_configured_serena_but_init_is_not_eager(tmp_path, monkeypatch):
    (tmp_path / "main.py").write_text("def main(): return 1\n", encoding="utf-8")
    config = tmp_path / ".klap" / "providers.json"
    config.parent.mkdir()
    config.write_text(json.dumps({"providers": {"serena": {
        "command": sys.executable,
        "args": ["missing-server.py"],
        "timeout_seconds": 2,
    }}}), encoding="utf-8")
    monkeypatch.setattr(SerenaMcpClient, "list_tools", lambda self: (_ for _ in ()).throw(AssertionError("Serena started during init")))
    registry = default_registry(tmp_path, graphify=False)
    assert "serena" in {item.name for item in registry.registrations()}
    context, _ = AnalysisServices(registry).build_context(tmp_path, graph={"nodes": [], "edges": []})
    row = next(item for item in context["analysis"]["providers"] if item["name"] == "serena")
    assert row["executed"] is False and row["reason"] == "not selected for an init capability"


def test_close_is_delegated_and_read_only_allowlist_is_enforced(tmp_path):
    fake = FakeClient()
    semantic = provider(tmp_path, fake)
    semantic.close()
    assert fake.closed
    with pytest.raises(PermissionError):
        fake_client = SerenaMcpClient(tmp_path, settings())
        fake_client.call("execute_shell_command", {"command": "echo forbidden"})


def test_real_stdio_timeout_cancellation_and_clean_close(tmp_path):
    server = tmp_path / "slow_server.py"
    server.write_text(
        "import time\nfrom mcp.server.fastmcp import FastMCP\nm=FastMCP('slow')\n"
        "@m.tool()\ndef find_symbol(name_path_pattern: str):\n    time.sleep(15)\n    return []\n"
        "if __name__ == '__main__': m.run()\n",
        encoding="utf-8",
    )
    value = SerenaSettings(command=sys.executable, args=(str(server),), timeout_seconds=10.0, configured=True)
    client = SerenaMcpClient(tmp_path, value)
    assert "find_symbol" in client.list_tools()
    started = time.perf_counter()
    with pytest.raises(TimeoutError):
        client.call("find_symbol", {"name_path_pattern": "X"})
    assert time.perf_counter() - started < 12
    client.close()
    assert not client._thread.is_alive()


def test_klap_mcp_surface_reuses_services_and_returns_real_post_flow():
    from mcp_server import _services, klap_flows_and_endpoints

    root = Path(__file__).parent / "fixtures" / "lumen_semantic"
    assert _services(str(root.resolve())) is _services(str(root.resolve()))
    result = klap_flows_and_endpoints(str(root), max_results=10, max_depth=10)
    assert result["dynamic"] is False
    endpoint = next(item for item in result["endpoints"] if item.get("method") == "POST")
    assert endpoint["path"].endswith("call-vtex")
    assert any(flow.get("name", "").startswith("POST") for flow in result["flows"])
