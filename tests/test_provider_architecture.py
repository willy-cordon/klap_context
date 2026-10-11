import ast
import json
import subprocess
import time
from pathlib import Path

from klapcontext.context_builder import build
from klapcontext.cli import generate_all
from klapcontext.providers import (
    AnalysisServices,
    Capability,
    CapabilityResolver,
    Confidence,
    ProviderIdentity,
    ProviderRegistry,
    ProviderResult,
    ResultState,
)
from klapcontext.providers.contracts import SymbolProvider
from klapcontext.providers.native import NativeGraphProvider
from klapcontext.providers.resolver import _METHODS
from klapcontext.scope import IndexScope


class FakeProvider:
    def __init__(self, name, result, *, available=True, delay=0):
        self.name = name
        self.capabilities = {Capability.SYMBOL_LOOKUP}
        self.result = result
        self.available = available
        self.delay = delay

    def is_available(self, request=None):
        return self.available

    def find_symbols(self, request):
        if self.delay:
            time.sleep(self.delay)
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


class DynamicProvider(FakeProvider):
    def __init__(self, name, result):
        super().__init__(name, result)
        self.capabilities = {Capability.SYMBOL_LOOKUP, Capability.REFERENCES}

    def capabilities_for(self, request):
        return {Capability.REFERENCES} if request.get("references") else {Capability.SYMBOL_LOOKUP}

    def find_references(self, request):
        return ["reference"]


def test_small_protocol_accepts_external_provider_without_inheritance():
    fake = FakeProvider("external", ["symbol"])
    assert isinstance(fake, SymbolProvider)
    registry = ProviderRegistry()
    registry.register(fake)
    result = CapabilityResolver(registry).resolve(Capability.SYMBOL_LOOKUP, {"query": "x"})
    assert result.state == ResultState.OK and result.data == ["symbol"]
    assert result.provider.name == "external"


def test_priority_failure_fallback_and_trace_are_explicit():
    registry = ProviderRegistry()
    registry.register(FakeProvider("primary", RuntimeError("boom")), priorities={Capability.SYMBOL_LOOKUP: 100})
    registry.register(FakeProvider("fallback", ["ok"]), priorities={Capability.SYMBOL_LOOKUP: 10})
    result = CapabilityResolver(registry).resolve(Capability.SYMBOL_LOOKUP, {})
    assert result.state == ResultState.OK and result.provider.name == "fallback"
    assert [item["state"] for item in result.trace[:2]] == ["PROVIDER_ERROR", "OK"]
    assert result.warnings and "fallback" in result.warnings[0]


def test_states_distinguish_no_results_unsupported_error_and_unknown():
    registry = ProviderRegistry()
    registry.register(FakeProvider("empty", []))
    assert CapabilityResolver(registry).resolve(Capability.SYMBOL_LOOKUP, {}).state == ResultState.NO_RESULTS
    assert CapabilityResolver(ProviderRegistry()).resolve(Capability.SYMBOL_LOOKUP, {}).state == ResultState.UNSUPPORTED

    errors = ProviderRegistry(); errors.register(FakeProvider("broken", ValueError("bad")))
    assert CapabilityResolver(errors).resolve(Capability.SYMBOL_LOOKUP, {}, fallback=False).state == ResultState.PROVIDER_ERROR

    unknown = ProviderRegistry(); unknown.register(FakeProvider("unknown", ProviderResult(ResultState.UNKNOWN, error="ambiguous")))
    assert CapabilityResolver(unknown).resolve(Capability.SYMBOL_LOOKUP, {}, fallback=False).state == ResultState.UNKNOWN


def test_services_auto_detect_query_language_for_native_composition(tmp_path):
    (tmp_path / "main.php").write_text("<?php function target() {}", encoding="utf-8")
    registry = ProviderRegistry()
    registry.register(FakeProvider("php-only", ["found"]), languages={"php"})
    result = AnalysisServices(registry).symbols(tmp_path, "target")
    assert result.state == ResultState.OK and result.data[0] == "found"


def test_timeout_disable_language_and_language_agnostic_selection():
    registry = ProviderRegistry()
    registry.register(FakeProvider("php", ["php"]), languages={"php"}, priorities={Capability.SYMBOL_LOOKUP: 20})
    registry.register(FakeProvider("agnostic", ["any"]), priorities={Capability.SYMBOL_LOOKUP: 10})
    resolver = CapabilityResolver(registry)
    assert resolver.resolve(Capability.SYMBOL_LOOKUP, {}, language="Python").provider.name == "agnostic"
    registry.enable("agnostic", False)
    assert resolver.resolve(Capability.SYMBOL_LOOKUP, {}, language="Python").state == ResultState.UNSUPPORTED

    timeout_registry = ProviderRegistry(); timeout_registry.register(FakeProvider("slow", ["late"], delay=.1))
    result = CapabilityResolver(timeout_registry).resolve(Capability.SYMBOL_LOOKUP, {}, timeout=.01, fallback=False)
    assert result.state == ResultState.PROVIDER_ERROR and "timed out" in result.error


def test_dynamic_capabilities_and_local_configuration(tmp_path):
    registry = ProviderRegistry(); registry.register(DynamicProvider("dynamic", ["symbol"]))
    resolver = CapabilityResolver(registry)
    assert resolver.resolve(Capability.SYMBOL_LOOKUP, {"references": False}).state == ResultState.OK
    assert resolver.resolve(Capability.REFERENCES, {"references": True}).data == ["reference"]
    assert resolver.resolve(Capability.REFERENCES, {"references": False}).state == ResultState.UNSUPPORTED

    config = tmp_path / "providers.json"
    config.write_text(
        '{"providers":{"dynamic":{"enabled":false,"timeout_seconds":2,"priorities":{"symbol_lookup":77}}}}',
        encoding="utf-8-sig",
    )
    assert registry.apply_config(config) == []
    assert not registry.registrations()[0].enabled
    assert registry.registrations()[0].priority(Capability.SYMBOL_LOOKUP) == 77


def test_native_only_context_is_useful_and_records_degradation(tmp_path):
    (tmp_path / "main.php").write_text("<?php function main() { return 1; }")
    registry = ProviderRegistry(); registry.register(NativeGraphProvider(), priorities={Capability.DEPENDENCY_GRAPH: -100})
    context, result = AnalysisServices(registry).build_context(tmp_path, scope=IndexScope.load(tmp_path, write_default=False))
    assert result.state == ResultState.NO_RESULTS and result.provider.name == "klap-native"
    assert context["semantic_model"]["analysis_mode"] == "GENERIC"
    assert context["entry_points"] and context["providers"]["dependency_graph"]["state"] == "NO_RESULTS"
    assert any("grafo externo" in item for item in context["system_model"]["unknowns"])


def test_graph_provider_available_and_failing_modes_use_same_service(tmp_path):
    (tmp_path / "a.py").write_text("print('a')")
    class Graph:
        name = "graph"
        capabilities = {Capability.DEPENDENCY_GRAPH}
        def dependency_graph(self, request):
            return {"nodes": [{"name": "A", "path": "a.py"}], "edges": []}

    registry = ProviderRegistry(); registry.register(Graph(), priorities={Capability.DEPENDENCY_GRAPH: 100}); registry.register(NativeGraphProvider(), priorities={Capability.DEPENDENCY_GRAPH: -100})
    context, result = AnalysisServices(registry).build_context(tmp_path, scope=IndexScope.load(tmp_path, write_default=False))
    assert result.state == ResultState.OK and result.provider.name == "graph"
    assert context["technical_model"]["graph"]["nodes"] == 1

    class BrokenGraph(Graph):
        name = "broken"
        def dependency_graph(self, request):
            raise RuntimeError("offline")

    failed = ProviderRegistry(); failed.register(BrokenGraph(), priorities={Capability.DEPENDENCY_GRAPH: 100}); failed.register(NativeGraphProvider(), priorities={Capability.DEPENDENCY_GRAPH: -100})
    _, fallback = AnalysisServices(failed).build_context(tmp_path, scope=IndexScope.load(tmp_path, write_default=False))
    assert fallback.state == ResultState.NO_RESULTS and fallback.provider.name == "klap-native"
    assert fallback.trace[0]["state"] == "PROVIDER_ERROR" and fallback.warnings


def test_shared_service_preserves_relevant_context_builder_output(tmp_path):
    (tmp_path / "main.php").write_text("<?php function main() { return 1; }")
    scope = IndexScope.load(tmp_path, write_default=False)
    graph = {"nodes": [{"name": "main", "path": "main.php"}], "links": []}
    legacy = build(tmp_path, graph, scope)
    registry = ProviderRegistry(); registry.register(NativeGraphProvider(), priorities={Capability.DEPENDENCY_GRAPH: -100})
    current, result = AnalysisServices(registry).build_context(tmp_path, graph=graph, scope=scope)
    assert result.state == ResultState.OK
    for key in ("stack", "entry_points", "flows", "semantic_model"):
        assert current[key] == legacy[key]


def test_core_modules_do_not_import_concrete_graphify_adapter():
    root = Path(__file__).parents[1]
    paths = [
        root / "src/klapcontext/cli.py",
        root / "src/klapcontext/context_builder.py",
        root / "src/klapcontext/agent/compiler.py",
        root / "src/klapcontext/agent/impact.py",
        root / "src/klapcontext/agent/capabilities.py",
    ]
    offenders = []
    for path in paths:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and "graphify" in (node.module or "").casefold():
                offenders.append(f"{path.name}:{node.lineno}")
            if isinstance(node, ast.Import) and any("graphify" in name.name.casefold() for name in node.names):
                offenders.append(f"{path.name}:{node.lineno}")
    assert offenders == []


def test_normalized_result_carries_provider_confidence_and_limitations():
    result = ProviderResult(ResultState.NO_RESULTS, [], ProviderIdentity("fake", "1"), confidence=Confidence.LOW, limitations=["partial index"])
    payload = result.as_dict()
    assert payload["state"] == "NO_RESULTS" and payload["provider"]["name"] == "fake"
    assert payload["confidence"] == "LOW" and payload["limitations"] == ["partial index"]


def test_additive_capabilities_run_all_providers_deduplicate_and_keep_provenance():
    first = FakeProvider("first", [{"id": "same", "name": "A"}, {"id": "one", "name": "B"}])
    second = FakeProvider("second", [{"id": "same", "name": "A"}, {"id": "two", "name": "C"}])
    registry = ProviderRegistry()
    registry.register(first, priorities={Capability.SYMBOL_LOOKUP: 20})
    registry.register(second, priorities={Capability.SYMBOL_LOOKUP: 10})
    result = CapabilityResolver(registry).resolve_all(Capability.SYMBOL_LOOKUP, {"query": "A"})
    assert result.state == ResultState.OK
    assert [item["id"] for item in result.data] == ["same", "one", "two"]
    assert result.data[0]["provider"] == "first" and result.data[-1]["provider"] == "second"
    assert [item["provider"] for item in result.data[0]["provenance"]] == ["first", "second"]
    assert [item["provider"] for item in result.trace] == ["first", "second"]


def test_single_provider_capabilities_keep_priority_and_fallback():
    class Graph:
        capabilities = {Capability.DEPENDENCY_GRAPH}
        def __init__(self, name, value): self.name, self.value = name, value
        def dependency_graph(self, request): return self.value

    registry = ProviderRegistry()
    registry.register(Graph("primary", {"nodes": [{"id": "p"}]}), priorities={Capability.DEPENDENCY_GRAPH: 20})
    registry.register(Graph("secondary", {"nodes": [{"id": "s"}]}), priorities={Capability.DEPENDENCY_GRAPH: 10})
    result = CapabilityResolver(registry).resolve_all(Capability.DEPENDENCY_GRAPH, {})
    assert result.provider.name == "primary" and result.data["nodes"][0]["id"] == "p"


def test_context_reports_provider_execution_and_partial_capability_coverage(tmp_path):
    (tmp_path / "main.php").write_text("<?php function main() { return 1; }")
    registry = ProviderRegistry(); registry.register(NativeGraphProvider(), priorities={Capability.DEPENDENCY_GRAPH: -100})
    context, _ = AnalysisServices(registry).build_context(tmp_path, scope=IndexScope.load(tmp_path, write_default=False))
    report = context["analysis"]
    assert report["status"] == "PARTIAL"
    assert report["coverage"]["dependency_graph"]["state"] == "DEGRADED"
    assert report["providers"][0]["executed"] is True
    assert "symbol_lookup" in report["composition"]["aggregate"]
    assert "dependency_graph" in report["composition"]["single_provider_fallback"]


def test_builtin_providers_only_advertise_executable_capabilities():
    from klapcontext.providers.graphify import GraphifyProvider
    for provider in (GraphifyProvider(), NativeGraphProvider()):
        missing = [capability.value for capability in provider.capabilities if not callable(getattr(provider, _METHODS.get(capability, ""), None))]
        assert missing == []


class InitEntriesProvider:
    capabilities = {Capability.ENTRY_POINT_DISCOVERY}

    def __init__(self, name, entry):
        self.name = name
        self.entry = entry
        self.calls = 0

    def entry_points(self, request):
        self.calls += 1
        return ProviderResult(ResultState.OK, [{
            "name": self.entry,
            "type": "CLI",
            "file": "main.py",
            "status": "CONFIRMED",
            "evidence": [{"source": self.name, "path": "main.py"}],
        }], ProviderIdentity(self.name), confidence=Confidence.CONFIRMED)


def test_generate_all_executes_and_persists_complementary_provider_facts(tmp_path):
    (tmp_path / "main.py").write_text("print('ok')\n")
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    first = InitEntriesProvider("entries-a", "command:a")
    second = InitEntriesProvider("entries-b", "command:b")
    registry = ProviderRegistry()
    registry.register(NativeGraphProvider(), priorities={Capability.DEPENDENCY_GRAPH: -100})
    registry.register(first, priorities={Capability.ENTRY_POINT_DISCOVERY: 20})
    registry.register(second, priorities={Capability.ENTRY_POINT_DISCOVERY: 10})

    generated = generate_all(tmp_path, services=AnalysisServices(registry))
    persisted = json.loads((tmp_path / ".klap/context.json").read_text(encoding="utf-8"))

    assert first.calls == second.calls == 1
    assert {item["name"] for item in generated["entry_points"]} >= {"command:a", "command:b"}
    assert {item["name"] for item in persisted["entry_points"]} >= {"command:a", "command:b"}
    facts = persisted["analysis"]["contributions"]["entry_point_discovery"]["facts"]
    by_name = {item["name"]: item for item in facts}
    assert by_name["command:a"]["provenance"][0]["provider"] == "entries-a"
    assert by_name["command:b"]["provenance"][0]["provider"] == "entries-b"
    rows = {item["name"]: item for item in persisted["analysis"]["providers"]}
    assert rows["entries-a"]["executed"] and rows["entries-b"]["executed"]
    assert {item["capability"] for item in rows["entries-a"]["executions"]} == {"entry_point_discovery"}


def test_disabled_and_inapplicable_providers_are_omitted_without_invocation(tmp_path):
    (tmp_path / "main.py").write_text("print('ok')\n")
    disabled = InitEntriesProvider("disabled", "disabled")
    incompatible = InitEntriesProvider("php-only", "php")
    registry = ProviderRegistry()
    registry.register(NativeGraphProvider(), priorities={Capability.DEPENDENCY_GRAPH: -100})
    registry.register(disabled, enabled=False)
    registry.register(incompatible, languages={"php"})

    context, _ = AnalysisServices(registry).build_context(tmp_path, scope=IndexScope.load(tmp_path, write_default=False))
    rows = {item["name"]: item for item in context["analysis"]["providers"]}

    assert disabled.calls == incompatible.calls == 0
    assert not rows["disabled"]["executed"] and rows["disabled"]["reason"] == "disabled by provider configuration"
    assert not rows["php-only"]["executed"] and rows["php-only"]["reason"] == "incompatible with detected language/framework"
