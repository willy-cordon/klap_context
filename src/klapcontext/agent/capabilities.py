"""Capabilities are stable; tools that implement them are replaceable."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Capability(str, Enum):
    FRAMEWORK_ANALYSIS = "framework_analysis"
    ENTRY_POINT_DISCOVERY = "entry_point_discovery"
    FLOW_RECONSTRUCTION = "flow_reconstruction"
    DEPENDENCY_GRAPH = "dependency_graph"
    PATH_SEARCH = "path_search"
    TEST_DISCOVERY = "test_discovery"
    INTEGRATION_DISCOVERY = "integration_discovery"
    AUTOMATION_DISCOVERY = "automation_discovery"
    CONFIG_DISCOVERY = "config_discovery"
    SYMBOL_LOOKUP = "symbol_lookup"
    CALL_GRAPH = "call_graph"
    CALLERS = "callers"
    CALLEES = "callees"
    IMPACT_ANALYSIS = "impact_analysis"
    MINIMAL_EDIT_CONTEXT = "minimal_edit_context"
    GIT_HISTORY = "git_history"


@dataclass(frozen=True)
class ProviderInfo:
    name: str
    capabilities: frozenset[Capability]
    available: bool
    optional: bool = False


@dataclass(frozen=True)
class CapabilityResolution:
    capability: Capability
    provider: str | None
    status: str
    fallbacks: tuple[str, ...] = ()


class CapabilityRouter:
    """Select an available provider without leaking provider names to callers."""
    def __init__(self, providers: list[ProviderInfo]):
        self.providers = providers

    def resolve(self, capability: Capability) -> CapabilityResolution:
        candidates = [provider for provider in self.providers if capability in provider.capabilities]
        ready = next((provider for provider in candidates if provider.available), None)
        if ready:
            return CapabilityResolution(capability, ready.name, "READY", tuple(provider.name for provider in candidates if provider.name != ready.name))
        return CapabilityResolution(capability, None, "UNAVAILABLE", tuple(provider.name for provider in candidates))


def default_providers(graphify_ready: bool | None = None) -> list[ProviderInfo]:
    from ..providers.code_intelligence import available as php_code_intelligence_available
    if graphify_ready is None:
        from ..graphify import command_prefix
        graphify_ready = command_prefix() is not None
    return [
        ProviderInfo("klap-native", frozenset({Capability.FRAMEWORK_ANALYSIS, Capability.ENTRY_POINT_DISCOVERY, Capability.FLOW_RECONSTRUCTION, Capability.TEST_DISCOVERY, Capability.INTEGRATION_DISCOVERY, Capability.AUTOMATION_DISCOVERY, Capability.CONFIG_DISCOVERY}), True),
        ProviderInfo("graphify", frozenset({Capability.DEPENDENCY_GRAPH, Capability.PATH_SEARCH, Capability.FLOW_RECONSTRUCTION}), graphify_ready),
        ProviderInfo("php-tree-sitter", frozenset({Capability.SYMBOL_LOOKUP, Capability.CALL_GRAPH, Capability.CALLERS, Capability.CALLEES, Capability.IMPACT_ANALYSIS, Capability.MINIMAL_EDIT_CONTEXT}), php_code_intelligence_available()),
        ProviderInfo("tree-sitter-mcp", frozenset({Capability.SYMBOL_LOOKUP, Capability.CALL_GRAPH, Capability.CALLERS, Capability.CALLEES, Capability.IMPACT_ANALYSIS, Capability.MINIMAL_EDIT_CONTEXT}), False, True),
    ]
