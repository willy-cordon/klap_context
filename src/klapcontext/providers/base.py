"""Compatibility exports for the capability-specific provider contracts.

`AnalysisProvider` historically meant the Graphify lifecycle API. It now aliases
the narrow dependency-graph capability; new adapters should import only the
Protocol(s) they implement from `providers.contracts`.
"""
from .contracts import (
    CallGraphProvider,
    DependencyGraphProvider,
    DependencyProvider,
    EntryPointProvider,
    ImplementationProvider,
    ProvenanceProvider,
    ReferenceProvider,
    StructuralRelationProvider,
    SymbolProvider,
)

AnalysisProvider = DependencyGraphProvider

__all__ = [
    "AnalysisProvider",
    "CallGraphProvider",
    "DependencyGraphProvider",
    "DependencyProvider",
    "EntryPointProvider",
    "ImplementationProvider",
    "ProvenanceProvider",
    "ReferenceProvider",
    "StructuralRelationProvider",
    "SymbolProvider",
]
