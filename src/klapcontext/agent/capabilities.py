"""Compatibility planning facade over the provider registry/resolver."""
from __future__ import annotations

from dataclasses import dataclass

from ..providers.contracts import Capability
from ..providers.registry import ProviderRegistry
from ..providers.resolver import CapabilityResolver
from ..providers.services import default_registry


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


class _InfoProvider:
    def __init__(self, info: ProviderInfo):
        self.name = info.name
        self.capabilities = info.capabilities
        self._available = info.available

    def is_available(self, request=None) -> bool:
        return self._available


class CapabilityRouter:
    """Legacy plan-time API; execution is delegated to CapabilityResolver."""

    def __init__(self, providers: list[ProviderInfo] | ProviderRegistry):
        if isinstance(providers, ProviderRegistry):
            self.registry = providers
        else:
            self.registry = ProviderRegistry()
            for index, info in enumerate(providers):
                self.registry.register(_InfoProvider(info), name=info.name, capabilities=info.capabilities, priorities={item: 1000 - index for item in info.capabilities})
        self.resolver = CapabilityResolver(self.registry)

    def resolve(self, capability: Capability) -> CapabilityResolution:
        value = self.resolver.select(capability)
        status = "READY" if value.status == "READY" else "UNAVAILABLE"
        return CapabilityResolution(capability, value.provider, status, value.fallbacks)


def default_providers(graphify_ready: bool | None = None) -> list[ProviderInfo]:
    registry = default_registry()
    result = []
    for item in registry.registrations():
        available = item.available()
        if item.name == "graphify" and graphify_ready is not None:
            available = graphify_ready
        capabilities = item.capabilities
        # Preserve the historical plan-time meaning: an empty native graph is
        # an execution fallback, not an available dependency-graph capability.
        if item.name == "klap-native":
            capabilities = frozenset(value for value in capabilities if value != Capability.DEPENDENCY_GRAPH)
        result.append(ProviderInfo(item.name, capabilities, available, item.name not in {"klap-native", "php-tree-sitter"}))
    return result
