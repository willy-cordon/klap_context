"""Provider contracts, registry and shared service composition."""
from .contracts import Capability
from .models import Confidence, Evidence, ProviderIdentity, ProviderResult, ResultState, SourceLocation, StructuralRelation, SymbolIdentity
from .registry import ProviderRegistry
from .resolver import AGGREGATE_CAPABILITIES, SINGLE_PROVIDER_CAPABILITIES, CapabilityResolver
from .services import AnalysisServices, default_registry, migrate_legacy_graphs

__all__ = [
    "AnalysisServices",
    "AGGREGATE_CAPABILITIES",
    "Capability",
    "CapabilityResolver",
    "Confidence",
    "Evidence",
    "ProviderIdentity",
    "ProviderRegistry",
    "ProviderResult",
    "ResultState",
    "SINGLE_PROVIDER_CAPABILITIES",
    "SourceLocation",
    "StructuralRelation",
    "SymbolIdentity",
    "default_registry",
    "migrate_legacy_graphs",
]


def default_provider():
    """Deprecated compatibility factory for the historical Graphify adapter."""
    from .graphify import GraphifyProvider
    return GraphifyProvider()
