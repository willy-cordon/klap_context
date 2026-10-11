"""Small capability contracts implemented independently by analysis adapters."""
from __future__ import annotations

from enum import Enum
from typing import Any, Protocol, runtime_checkable

from .models import ProviderResult


class Capability(str, Enum):
    FRAMEWORK_ANALYSIS = "framework_analysis"
    SYMBOL_LOOKUP = "symbol_lookup"
    REFERENCES = "references"
    IMPLEMENTATIONS = "implementations"
    CALL_GRAPH = "call_graph"
    CALLERS = "callers"
    CALLEES = "callees"
    ENTRY_POINT_DISCOVERY = "entry_point_discovery"
    STRUCTURAL_RELATIONS = "structural_relations"
    DEPENDENCY_GRAPH = "dependency_graph"
    DEPENDENCIES = "dependencies"
    EVIDENCE_PROVENANCE = "evidence_provenance"
    FLOW_RECONSTRUCTION = "flow_reconstruction"
    PATH_SEARCH = "path_search"
    TEST_DISCOVERY = "test_discovery"
    INTEGRATION_DISCOVERY = "integration_discovery"
    AUTOMATION_DISCOVERY = "automation_discovery"
    CONFIG_DISCOVERY = "config_discovery"
    IMPACT_ANALYSIS = "impact_analysis"
    MINIMAL_EDIT_CONTEXT = "minimal_edit_context"
    GIT_HISTORY = "git_history"


@runtime_checkable
class SymbolProvider(Protocol):
    def find_symbols(self, request: Any) -> ProviderResult: ...


@runtime_checkable
class ReferenceProvider(Protocol):
    def find_references(self, request: Any) -> ProviderResult: ...


@runtime_checkable
class ImplementationProvider(Protocol):
    def find_implementations(self, request: Any) -> ProviderResult: ...


@runtime_checkable
class CallGraphProvider(Protocol):
    def call_graph(self, request: Any) -> ProviderResult: ...


@runtime_checkable
class EntryPointProvider(Protocol):
    def entry_points(self, request: Any) -> ProviderResult: ...


@runtime_checkable
class StructuralRelationProvider(Protocol):
    def structural_relations(self, request: Any) -> ProviderResult: ...


@runtime_checkable
class DependencyGraphProvider(Protocol):
    def dependency_graph(self, request: Any) -> ProviderResult: ...


@runtime_checkable
class DependencyProvider(Protocol):
    def dependencies(self, request: Any) -> ProviderResult: ...


@runtime_checkable
class ProvenanceProvider(Protocol):
    def provenance(self, request: Any) -> ProviderResult: ...
