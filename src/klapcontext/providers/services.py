"""Shared internal services used by CLI, portal generation and MCP surfaces."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from ..scope import IndexScope
from .contracts import Capability
from .models import Confidence, ProviderIdentity, ProviderResult, ResultState
from .native import NativeGraphProvider, PhpTreeSitterProvider
from .registry import ProviderRegistry
from .resolver import AGGREGATE_CAPABILITIES, SINGLE_PROVIDER_CAPABILITIES, CapabilityResolver


INIT_AGGREGATE_CAPABILITIES = (
    Capability.ENTRY_POINT_DISCOVERY,
    Capability.STRUCTURAL_RELATIONS,
    Capability.DEPENDENCIES,
    Capability.EVIDENCE_PROVENANCE,
    Capability.TEST_DISCOVERY,
    Capability.INTEGRATION_DISCOVERY,
    Capability.AUTOMATION_DISCOVERY,
    Capability.CONFIG_DISCOVERY,
)

_SEMANTIC_FIELDS = {
    Capability.ENTRY_POINT_DISCOVERY: "entry_points",
    Capability.STRUCTURAL_RELATIONS: "transitions",
    Capability.DEPENDENCIES: "dependencies",
    Capability.TEST_DISCOVERY: "tests",
    Capability.INTEGRATION_DISCOVERY: "integrations",
    Capability.AUTOMATION_DISCOVERY: "background_tasks",
    Capability.CONFIG_DISCOVERY: "configurations",
}


def default_registry(root: Path | None = None, *, graphify: bool = True) -> ProviderRegistry:
    registry = ProviderRegistry()
    if graphify:
        # Optional adapter import stays at the composition boundary.
        from .graphify import GraphifyProvider
        registry.register(GraphifyProvider(), priorities={Capability.DEPENDENCY_GRAPH: 100}, timeout=120.0)
    registry.register(NativeGraphProvider(), priorities={Capability.DEPENDENCY_GRAPH: -100})
    registry.register(PhpTreeSitterProvider(), languages={"php"}, priorities={capability: 50 for capability in PhpTreeSitterProvider.capabilities})
    if root is not None:
        from .optional import register_optional_providers
        register_optional_providers(registry, Path(root))
        registry.apply_config(Path(root) / ".klap" / "providers.json")
    return registry


class AnalysisServices:
    def __init__(self, registry: ProviderRegistry | None = None, *, root: Path | None = None, default_timeout: float = 30.0):
        self.registry = registry or default_registry(root)
        self.resolver = CapabilityResolver(self.registry, default_timeout=default_timeout)

    def close(self) -> None:
        """Close stateful optional providers; stateless providers need no hook."""
        for registration in self.registry.registrations():
            close = getattr(registration.provider, "close", None)
            if callable(close):
                try:
                    close()
                except Exception:
                    pass

    def dependency_graph(self, root: Path, scope: IndexScope, *, update: bool = False, existing_only: bool = False) -> ProviderResult[dict]:
        result = self.resolver.resolve(Capability.DEPENDENCY_GRAPH, {"root": root, "scope": scope, "update": update, "existing_only": existing_only})
        result.warnings = [*self.registry.warnings, *result.warnings]
        return result

    def build_context(self, root: Path, *, graph: dict | None = None, scope: IndexScope | None = None, update: bool = False, existing_only: bool = False) -> tuple[dict, ProviderResult[dict]]:
        """Execute init capabilities, compose their facts, then build projections.

        Framework analysis and every additive init capability go through the
        resolver. Query-shaped capabilities (symbols, references, callers,
        impact, path search, and minimal edit context) are intentionally not run
        without a query during init.
        """
        from ..context_builder import _empty_raw, build
        from ..detector import detect_project
        from ..semantic import SemanticModel

        root = Path(root).resolve()
        scope = scope or IndexScope.load(root, write_default=not existing_only)
        stack, _ = detect_project(root)
        language = stack["languages"][0] if stack["languages"] else None
        framework = stack["frameworks"][0] if stack["frameworks"] else None
        request: dict[str, Any] = {
            "root": root,
            "scope": scope,
            "update": update,
            "existing_only": existing_only,
            "stack": stack,
        }

        graph_result = ProviderResult(ResultState.OK, graph, ProviderIdentity("supplied-graph"), confidence=Confidence.UNKNOWN) if graph is not None else self.resolver.resolve(Capability.DEPENDENCY_GRAPH, request, language=language, framework=framework)
        graph_result.warnings = [*self.registry.warnings, *graph_result.warnings]
        framework_result = self.resolver.resolve(Capability.FRAMEWORK_ANALYSIS, request, language=language, framework=framework)
        aggregate_results = {
            capability: self.resolver.resolve_all(capability, request, language=language, framework=framework)
            for capability in INIT_AGGREGATE_CAPABILITIES
            if self.registry.candidates(capability, language=language, framework=framework, request=request)
        }

        empty_model = SemanticModel(language).as_dict()
        raw = _empty_raw()
        if framework_result.state in {ResultState.OK, ResultState.NO_RESULTS} and isinstance(framework_result.data, dict):
            supplied_model = framework_result.data.get("semantic_model")
            supplied_raw = framework_result.data.get("raw")
            if isinstance(supplied_model, dict):
                empty_model.update(supplied_model)
            if isinstance(supplied_raw, dict):
                raw.update(supplied_raw)
        model = empty_model
        for capability, result in aggregate_results.items():
            field = _SEMANTIC_FIELDS.get(capability)
            if field and result.state in {ResultState.OK, ResultState.NO_RESULTS}:
                model[field] = self._legacy_projection(capability, result.data or [])
        # Keep package/framework dependency projections aligned with composed
        # semantic facts. Provider-neutral facts remain lossless in analysis.
        raw["dependencies"] = model.get("dependencies", raw.get("dependencies", []))

        raw_graph = graph_result.data if isinstance(graph_result.data, dict) else {"nodes": [], "edges": []}
        filtered = scope.filter_graph(raw_graph)
        context = build(root, filtered, scope, semantic_override=(model, raw))
        executions = {Capability.DEPENDENCY_GRAPH: graph_result, Capability.FRAMEWORK_ANALYSIS: framework_result, **aggregate_results}
        context["providers"] = {
            "dependency_graph": {
                "state": graph_result.state.value,
                "provider": graph_result.provider.name if graph_result.provider else None,
                "confidence": graph_result.confidence.value,
                "limitations": graph_result.limitations,
                "warnings": graph_result.warnings,
                "trace": graph_result.trace,
            }
        }
        context["analysis"] = self._analysis_report(context, executions, request, language=language, framework=framework)
        if graph_result.state != ResultState.OK or not self._fact_count(graph_result.data):
            context["system_model"]["unknowns"].append("No hay grafo externo disponible; el contexto usa analizadores nativos y puede omitir relaciones entre archivos.")
        return context, graph_result

    @staticmethod
    def _legacy_projection(capability: Capability, facts: list[Any]) -> list[dict]:
        """Project normalized provider facts into the historical semantic schema."""
        projected: list[dict] = []
        for value in facts:
            if not isinstance(value, dict):
                continue
            item = dict(value)
            item.pop("provenance", None)
            item.pop("confidence", None)
            if capability != Capability.STRUCTURAL_RELATIONS:
                item.pop("provider", None)
            if capability == Capability.ENTRY_POINT_DISCOVERY:
                if not item.get("name"):
                    continue
                item.setdefault("type", "UNKNOWN"); item.setdefault("status", "INFERRED"); item.setdefault("evidence", [])
            elif capability == Capability.STRUCTURAL_RELATIONS:
                if not item.get("source") or not item.get("target"):
                    continue
                location = item.get("location") if isinstance(item.get("location"), dict) else {}
                item.setdefault("type", item.get("kind") or item.get("relation") or "RELATED")
                item.setdefault("file", location.get("path")); item.setdefault("line", location.get("line"))
                item.setdefault("status", "INFERRED"); item.setdefault("evidence", [])
            elif capability == Capability.DEPENDENCIES:
                if not item.get("name"):
                    continue
                item.setdefault("status", "INFERRED"); item.setdefault("evidence", [])
            elif capability in {Capability.TEST_DISCOVERY, Capability.CONFIG_DISCOVERY}:
                if not item.get("name") or not item.get("file"):
                    continue
                item.setdefault("status", "INFERRED"); item.setdefault("evidence", [])
            elif capability in {Capability.INTEGRATION_DISCOVERY, Capability.AUTOMATION_DISCOVERY}:
                if not item.get("name"):
                    continue
                item.setdefault("status", "INFERRED"); item.setdefault("evidence", [])
            projected.append(item)
        return projected

    def _analysis_report(
        self,
        context: dict,
        executions: dict[Capability, ProviderResult],
        request: dict[str, Any],
        *,
        language: str | None,
        framework: str | None,
    ) -> dict:
        coverage: dict[str, dict] = {}
        contributions: dict[str, dict] = {}
        for capability, result in executions.items():
            facts = result.data if isinstance(result.data, list) else ([] if result.data is None else [result.data])
            successful = [item["provider"] for item in result.trace if item.get("provider") and item.get("state") in {ResultState.OK.value, ResultState.NO_RESULTS.value}]
            if not successful and result.provider and result.state in {ResultState.OK, ResultState.NO_RESULTS}:
                successful = [result.provider.name]
            failures = [item for item in result.trace if item.get("state") in {ResultState.PROVIDER_ERROR.value, ResultState.UNKNOWN.value}]
            if capability == Capability.DEPENDENCY_GRAPH and (result.state != ResultState.OK or not self._fact_count(result.data)):
                state = "DEGRADED"
            elif result.state == ResultState.OK:
                state = "DEGRADED" if failures else "COMPLETE"
            elif result.state == ResultState.NO_RESULTS:
                state = "DEGRADED" if failures else "EMPTY"
            else:
                state = "MISSING"
            coverage[capability.value] = {
                "state": state,
                "facts": self._fact_count(result.data),
                "providers": list(dict.fromkeys(successful)),
                "mode": "aggregate" if capability in INIT_AGGREGATE_CAPABILITIES else "single_provider_fallback",
            }
            if capability in INIT_AGGREGATE_CAPABILITIES:
                contributions[capability.value] = {
                    "state": result.state.value,
                    "facts": facts,
                    "provider": result.provider.name if result.provider else None,
                    "confidence": result.confidence.value,
                    "limitations": result.limitations,
                    "warnings": result.warnings,
                    "trace": result.trace,
                }

        # Flow reconstruction is derived from the composed entry points and
        # structural facts. It is not a provider invocation during init.
        coverage[Capability.FLOW_RECONSTRUCTION.value] = {
            "state": "COMPLETE" if context.get("flows") else "EMPTY",
            "facts": len(context.get("flows", [])),
            "providers": [],
            "mode": "derived_from_composed_facts",
        }

        invocations: dict[str, list[dict]] = {}
        for capability, result in executions.items():
            for item in result.trace:
                name = item.get("provider")
                if not name:
                    continue
                invocations.setdefault(name, []).append({"capability": capability.value, **item})
        provider_rows = []
        languages = {item.casefold() for item in request.get("stack", {}).get("languages", [])}
        frameworks = {item.casefold() for item in request.get("stack", {}).get("frameworks", [])}
        for registration in self.registry.registrations():
            available = registration.available(request)
            applicable = (not registration.languages or bool(registration.languages & languages)) and (not registration.frameworks or bool(registration.frameworks & frameworks))
            calls = invocations.get(registration.name, [])
            executed_calls = [item for item in calls if not (item.get("state") == ResultState.UNSUPPORTED.value and item.get("reason") == "provider unavailable")]
            executed = bool(executed_calls)
            states = [item.get("state") for item in executed_calls]
            if ResultState.PROVIDER_ERROR.value in states:
                status = ResultState.PROVIDER_ERROR.value
            elif ResultState.UNKNOWN.value in states:
                status = ResultState.UNKNOWN.value
            elif ResultState.OK.value in states:
                status = ResultState.OK.value
            elif ResultState.NO_RESULTS.value in states:
                status = ResultState.NO_RESULTS.value
            elif executed_calls:
                status = ResultState.UNSUPPORTED.value
            else:
                status = "OMITTED"
            if not registration.enabled:
                reason = "disabled by provider configuration"
            elif not available:
                reason = "not installed or unavailable"
            elif not applicable:
                reason = "incompatible with detected language/framework"
            elif not executed:
                reason = "not selected for an init capability"
            elif status == ResultState.PROVIDER_ERROR.value:
                reason = next((item.get("error") for item in executed_calls if item.get("error")), "provider failed")
            else:
                reason = None
            provider_rows.append({
                "name": registration.name,
                "enabled": registration.enabled,
                "detected": available,
                "applicable": applicable,
                "executed": executed,
                "status": status,
                "reason": reason,
                "executions": executed_calls,
                "capabilities": sorted(item.value for item in registration.capabilities),
            })
        overall = "COMPLETE" if all(item["state"] in {"COMPLETE", "EMPTY"} for item in coverage.values()) else "PARTIAL"
        return {
            "status": overall,
            "coverage": coverage,
            "providers": provider_rows,
            "contributions": contributions,
            "composition": {
                "aggregate": sorted(item.value for item in AGGREGATE_CAPABILITIES),
                "single_provider_fallback": sorted(item.value for item in SINGLE_PROVIDER_CAPABILITIES),
                "init_aggregate": [item.value for item in INIT_AGGREGATE_CAPABILITIES],
                "query_shaped_not_run": sorted(item.value for item in {
                    Capability.SYMBOL_LOOKUP, Capability.REFERENCES, Capability.IMPLEMENTATIONS,
                    Capability.CALL_GRAPH, Capability.CALLERS, Capability.CALLEES,
                    Capability.IMPACT_ANALYSIS, Capability.MINIMAL_EDIT_CONTEXT, Capability.PATH_SEARCH,
                }),
            },
        }

    @staticmethod
    def _fact_count(data: Any) -> int:
        if isinstance(data, list):
            return len(data)
        if isinstance(data, dict):
            nodes = data.get("nodes")
            if isinstance(nodes, list):
                return len(nodes)
            nested = data.get("graph")
            if isinstance(nested, dict) and isinstance(nested.get("nodes"), list):
                return len(nested["nodes"])
            return 1 if data else 0
        return 0 if data is None else 1

    def impact(self, root: Path, symbol: str, *, language: str | None = None, scope: IndexScope | None = None) -> ProviderResult:
        if language is None:
            from ..detector import detect_project
            stack, _ = detect_project(Path(root))
            language = stack.get("languages", [None])[0] if stack.get("languages") else None
        scope = scope or IndexScope.load(root, write_default=False)
        return self.resolver.resolve(Capability.IMPACT_ANALYSIS, {"root": root, "scope": scope, "symbol": symbol}, language=language)

    @staticmethod
    def _query_language(root: Path, language: str | None) -> str | None:
        if language:
            return language
        from ..detector import detect_project
        stack, _ = detect_project(Path(root))
        return stack.get("languages", [None])[0] if stack.get("languages") else None

    def symbols(self, root: Path, query: str, *, operation: str = "lookup", path: str | None = None, language: str | None = None, max_results: int = 50, max_answer_chars: int = 20_000) -> ProviderResult:
        root = Path(root).resolve()
        request = {"root": root, "query": query, "symbol": query, "operation": operation, "path": path, "max_results": max_results, "max_answer_chars": max_answer_chars}
        return self.resolver.resolve_all(Capability.SYMBOL_LOOKUP, request, language=self._query_language(root, language))

    def references(self, root: Path, symbol: str, *, path: str | None = None, language: str | None = None, max_results: int = 50, max_answer_chars: int = 20_000) -> ProviderResult:
        root = Path(root).resolve()
        request = {"root": root, "symbol": symbol, "path": path, "max_results": max_results, "max_answer_chars": max_answer_chars}
        return self.resolver.resolve_all(Capability.REFERENCES, request, language=self._query_language(root, language))

    def implementations(self, root: Path, symbol: str, *, path: str | None = None, language: str | None = None, max_results: int = 50, max_answer_chars: int = 20_000) -> ProviderResult:
        root = Path(root).resolve()
        request = {"root": root, "symbol": symbol, "path": path, "max_results": max_results, "max_answer_chars": max_answer_chars}
        return self.resolver.resolve_all(Capability.IMPLEMENTATIONS, request, language=self._query_language(root, language))

    def dependencies(self, root: Path, *, language: str | None = None, max_results: int = 100) -> ProviderResult:
        root = Path(root).resolve()
        request = {"root": root, "scope": IndexScope.load(root, write_default=False), "max_results": max_results}
        return self.resolver.resolve_all(Capability.DEPENDENCIES, request, language=self._query_language(root, language))


def migrate_legacy_graphs(root: Path, *, apply: bool = False) -> dict:
    """Compatibility operation owned by the optional Graphify adapter boundary."""
    from ..graphify import migrate_legacy_graphs as migrate
    return migrate(root, apply=apply)
