"""Graphify adapter; this is the only provider layer coupled to Graphify APIs."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .. import graphify
from ..scope import IndexScope
from .contracts import Capability
from .models import Confidence, ProviderIdentity, ProviderResult, ResultState


class GraphifyProvider:
    name = "graphify"
    capabilities = frozenset({Capability.DEPENDENCY_GRAPH})

    def is_available(self, request: Any = None) -> bool:
        request = request or {}
        if request.get("existing_only"):
            return graphify.canonical_graph(Path(request.get("root", "."))).exists()
        return graphify.command_prefix() is not None

    def dependency_graph(self, request: Any) -> ProviderResult[dict]:
        request = request or {}
        root = Path(request.get("root", ".")).resolve()
        scope = request.get("scope") or IndexScope.load(root)
        if request.get("existing_only"):
            path = graphify.canonical_graph(root)
            if not path.exists():
                return ProviderResult(ResultState.NO_RESULTS, {"nodes": [], "edges": []}, self._identity(), limitations=["No existing Graphify graph was found."])
        else:
            path = self.generate(root, bool(request.get("update")), scope)
        raw = self.load_graph(path)
        if not raw:
            return ProviderResult(ResultState.PROVIDER_ERROR, provider=self._identity(), error="Graphify graph is empty or invalid")
        files = self.copy_outputs(root, path.parent)
        return ProviderResult(ResultState.OK, raw, self._identity(), confidence=Confidence.INFERRED, limitations=["Graph relationships are static evidence and may be incomplete."], warnings=[], trace=[{"artifact": path.relative_to(root).as_posix(), "files": files}])

    def _identity(self) -> ProviderIdentity:
        return ProviderIdentity(self.name, self.version(), self.__class__.__name__)

    # Public compatibility methods retained for existing callers/adapters.
    def generate(self, root: Path, update: bool = False, scope: IndexScope | None = None) -> Path:
        return graphify.generate(root, update, scope)

    def load_graph(self, graph: Path) -> dict:
        return graphify.load_graph(graph)

    def copy_outputs(self, root: Path, destination: Path) -> list[str]:
        return graphify.copy_outputs(root, destination)

    def version(self) -> str | None:
        return graphify.version()
