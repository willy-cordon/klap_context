"""Adapters for KlapContext's built-in local analyzers."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from ..scope import IndexScope
from .contracts import Capability
from .models import Confidence, Evidence, ProviderIdentity, ProviderResult, ResultState, SourceLocation, StructuralRelation, SymbolIdentity


class NativeGraphProvider:
    """Safe graph fallback: native semantic analyzers remain useful without a graph."""

    name = "klap-native"
    capabilities = frozenset({
        Capability.DEPENDENCY_GRAPH,
        Capability.FRAMEWORK_ANALYSIS,
        Capability.ENTRY_POINT_DISCOVERY,
        Capability.STRUCTURAL_RELATIONS,
        Capability.FLOW_RECONSTRUCTION,
        Capability.TEST_DISCOVERY,
        Capability.INTEGRATION_DISCOVERY,
        Capability.AUTOMATION_DISCOVERY,
        Capability.CONFIG_DISCOVERY,
        Capability.DEPENDENCIES,
        Capability.EVIDENCE_PROVENANCE,
    })

    @staticmethod
    def _analysis(request: Any):
        from ..context_builder import _semantic
        from ..detector import detect_project
        request = request or {}
        if isinstance(request, dict) and request.get("_native_analysis") is not None:
            return request["_native_analysis"]
        root = Path(request.get("root", ".")).resolve()
        scope = request.get("scope") or IndexScope.load(root, write_default=False)
        stack = request.get("stack")
        if stack is None:
            stack, _ = detect_project(root)
        result = _semantic(root, stack, scope)
        if isinstance(request, dict):
            request["_native_analysis"] = result
        return result

    @classmethod
    def _semantic(cls, request: Any):
        return cls._analysis(request)[0]

    def entry_points(self, request: Any) -> ProviderResult:
        values = self._semantic(request).as_dict()["entry_points"]
        return ProviderResult(ResultState.OK if values else ResultState.NO_RESULTS, values, ProviderIdentity(self.name), confidence=Confidence.INFERRED)

    def dependencies(self, request: Any) -> ProviderResult:
        values = self._semantic(request).as_dict()["dependencies"]
        return ProviderResult(ResultState.OK if values else ResultState.NO_RESULTS, values, ProviderIdentity(self.name), confidence=Confidence.INFERRED)

    def structural_relations(self, request: Any) -> ProviderResult:
        values = self._semantic(request).as_dict()["transitions"]
        return ProviderResult(ResultState.OK if values else ResultState.NO_RESULTS, values, ProviderIdentity(self.name), confidence=Confidence.INFERRED)

    def provenance(self, request: Any) -> ProviderResult:
        model = self._semantic(request).as_dict()
        values = [evidence for group in (model["components"], model["entry_points"], model["transitions"]) for item in group for evidence in item.get("evidence", [])]
        return ProviderResult(ResultState.OK if values else ResultState.NO_RESULTS, values, ProviderIdentity(self.name), confidence=Confidence.INFERRED)

    def framework_analysis(self, request: Any) -> ProviderResult:
        semantic, raw = self._analysis(request)
        value = semantic.as_dict()
        data = {"semantic_model": value, "raw": raw}
        confidence = Confidence.CONFIRMED if value["framework"] else Confidence.INFERRED
        return ProviderResult(ResultState.OK, data, ProviderIdentity(self.name), confidence=confidence)

    def flows(self, request: Any) -> ProviderResult:
        values = self._semantic(request).as_dict()["flows"]
        return ProviderResult(ResultState.OK if values else ResultState.NO_RESULTS, values, ProviderIdentity(self.name), confidence=Confidence.INFERRED)

    def tests(self, request: Any) -> ProviderResult:
        values = list(self._semantic(request).as_dict()["tests"])
        root = Path((request or {}).get("root", ".")).resolve()
        scope = (request or {}).get("scope") or IndexScope.load(root, write_default=False)
        known = {item.get("file") for item in values}
        for path in sorted(scope.included_paths):
            parts = Path(path).parts
            if path not in known and (any(part.casefold() in {"test", "tests"} for part in parts[:-1]) or Path(path).name.casefold().startswith("test_")):
                values.append({"name": Path(path).stem, "file": path, "status": "CONFIRMED", "evidence": [{"source": "repository scope", "path": path}]})
        return ProviderResult(ResultState.OK if values else ResultState.NO_RESULTS, values, ProviderIdentity(self.name), confidence=Confidence.INFERRED)

    def integrations(self, request: Any) -> ProviderResult:
        values = self._semantic(request).as_dict()["integrations"]
        return ProviderResult(ResultState.OK if values else ResultState.NO_RESULTS, values, ProviderIdentity(self.name), confidence=Confidence.INFERRED)

    def automations(self, request: Any) -> ProviderResult:
        values = self._semantic(request).as_dict()["background_tasks"]
        return ProviderResult(ResultState.OK if values else ResultState.NO_RESULTS, values, ProviderIdentity(self.name), confidence=Confidence.INFERRED)

    def configurations(self, request: Any) -> ProviderResult:
        values = self._semantic(request).as_dict()["configurations"]
        return ProviderResult(ResultState.OK if values else ResultState.NO_RESULTS, values, ProviderIdentity(self.name), confidence=Confidence.INFERRED)

    def dependency_graph(self, request: Any) -> ProviderResult[dict]:
        return ProviderResult.no_results(
            ProviderIdentity(self.name, adapter=self.__class__.__name__),
            {"nodes": [], "edges": []},
            limitation="No external dependency graph is available; framework and local structural analysis continue.",
        )


class PhpTreeSitterProvider:
    """Normalize the existing PHP Tree-sitter analyzer behind capability contracts."""

    name = "php-tree-sitter"
    capabilities = frozenset({
        Capability.SYMBOL_LOOKUP,
        Capability.REFERENCES,
        Capability.IMPLEMENTATIONS,
        Capability.CALL_GRAPH,
        Capability.CALLERS,
        Capability.CALLEES,
        Capability.STRUCTURAL_RELATIONS,
        Capability.DEPENDENCIES,
        Capability.EVIDENCE_PROVENANCE,
        Capability.IMPACT_ANALYSIS,
        Capability.MINIMAL_EDIT_CONTEXT,
    })

    def is_available(self, request: Any = None) -> bool:
        from .code_intelligence import available
        return available()

    @staticmethod
    def _values(request: Any) -> tuple[Path, IndexScope | None, str | None]:
        request = request or {}
        root = Path(request.get("root", ".")).resolve()
        return root, request.get("scope"), request.get("symbol") or request.get("query")

    def _provider(self, request: Any):
        from .code_intelligence import PhpCodeIntelligenceProvider
        root, scope, _ = self._values(request)
        return PhpCodeIntelligenceProvider(root, scope)

    @staticmethod
    def _identity() -> ProviderIdentity:
        return ProviderIdentity("php-tree-sitter", adapter="PhpTreeSitterProvider")

    def find_symbols(self, request: Any) -> ProviderResult[list[SymbolIdentity]]:
        _, _, query = self._values(request)
        if not query:
            return ProviderResult(ResultState.UNKNOWN, provider=self._identity(), error="symbol/query is required")
        values = []
        for item in self._provider(request).find_symbol(query):
            location = SourceLocation(item["file"], item.get("start_line"), item.get("end_line"))
            values.append(SymbolIdentity(item["id"], item["name"], item["type"], item.get("qualified_name"), "PHP", location, self._identity(), (Evidence("tree-sitter AST", location),), Confidence.CONFIRMED))
        return ProviderResult(ResultState.OK if values else ResultState.NO_RESULTS, values, self._identity(), confidence=Confidence.CONFIRMED)

    def structural_relations(self, request: Any) -> ProviderResult[list[StructuralRelation]]:
        values = []
        for item in self._provider(request).index()["relations"]:
            location = SourceLocation(item["file"], item.get("line"))
            confidence = Confidence(item.get("confidence", "UNKNOWN")) if item.get("confidence") in Confidence._value2member_map_ else Confidence.UNKNOWN
            values.append(StructuralRelation(item["source_symbol"], item["target_symbol"], item["relation"], location, self._identity(), (Evidence("tree-sitter AST", location, reason=item.get("metadata", {}).get("expression")),), confidence))
        return ProviderResult(ResultState.OK if values else ResultState.NO_RESULTS, values, self._identity(), confidence=Confidence.INFERRED, limitations=["Static relationships are best effort and do not prove runtime execution."])

    def find_references(self, request: Any) -> ProviderResult:
        _, _, symbol = self._values(request)
        values = self._provider(request).consumers(symbol or "") if symbol else []
        return ProviderResult(ResultState.OK if values else ResultState.NO_RESULTS, values, self._identity(), confidence=Confidence.INFERRED)

    def find_implementations(self, request: Any) -> ProviderResult:
        _, _, symbol = self._values(request)
        values = [item for item in self._provider(request).index()["relations"] if item["relation"] in {"IMPLEMENTS", "EXTENDS"} and item["target_symbol"].endswith(symbol or "\0")]
        return ProviderResult(ResultState.OK if values else ResultState.NO_RESULTS, values, self._identity(), confidence=Confidence.CONFIRMED)

    def call_graph(self, request: Any) -> ProviderResult:
        _, _, symbol = self._values(request)
        if not symbol:
            return ProviderResult(ResultState.UNKNOWN, provider=self._identity(), error="symbol is required")
        value = self._provider(request).call_graph(symbol, depth=int((request or {}).get("depth", 3)))
        return ProviderResult(ResultState.OK if value["edges"] else ResultState.NO_RESULTS, value, self._identity(), confidence=Confidence.INFERRED)

    def callers(self, request: Any) -> ProviderResult:
        _, _, symbol = self._values(request); values = self._provider(request).callers(symbol or "") if symbol else []
        return ProviderResult(ResultState.OK if values else ResultState.NO_RESULTS, values, self._identity(), confidence=Confidence.INFERRED)

    def callees(self, request: Any) -> ProviderResult:
        _, _, symbol = self._values(request); values = self._provider(request).callees(symbol or "") if symbol else []
        return ProviderResult(ResultState.OK if values else ResultState.NO_RESULTS, values, self._identity(), confidence=Confidence.INFERRED)

    def dependencies(self, request: Any) -> ProviderResult:
        values = [item for item in self._provider(request).index()["relations"] if item["relation"] in {"INJECTS", "EXTENDS", "IMPLEMENTS", "INSTANTIATES"}]
        return ProviderResult(ResultState.OK if values else ResultState.NO_RESULTS, values, self._identity(), confidence=Confidence.INFERRED)

    def provenance(self, request: Any) -> ProviderResult:
        relations = self.structural_relations(request)
        evidence = [item.evidence[0] for item in relations.data or [] if item.evidence]
        return ProviderResult(relations.state, evidence, self._identity(), confidence=relations.confidence, limitations=relations.limitations)

    def impact(self, request: Any) -> ProviderResult:
        _, _, symbol = self._values(request)
        if not symbol:
            return ProviderResult(ResultState.UNKNOWN, provider=self._identity(), error="symbol is required")
        return ProviderResult(ResultState.OK, self._provider(request).impact(symbol), self._identity(), confidence=Confidence.INFERRED, limitations=["Impact is structural, not a prediction of failures."])

    def minimal_edit_context(self, request: Any) -> ProviderResult:
        _, _, symbol = self._values(request)
        if not symbol:
            return ProviderResult(ResultState.UNKNOWN, provider=self._identity(), error="symbol is required")
        value = self._provider(request).minimal_edit_context(symbol, max_tokens=int((request or {}).get("max_tokens", 1200)))
        state = ResultState.UNKNOWN if value.get("status") == "UNKNOWN" else ResultState.OK
        return ProviderResult(state, value, self._identity(), confidence=Confidence.INFERRED)
