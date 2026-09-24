"""Graphify provider adapter. Keeps the engine separate from the system model."""
from __future__ import annotations

from pathlib import Path

from .. import graphify


class GraphifyProvider:
    name = "graphify"

    def generate(self, root: Path, update: bool = False) -> Path:
        return graphify.generate(root, update)

    def load_graph(self, graph: Path) -> dict:
        return graphify.load_graph(graph)

    def copy_outputs(self, root: Path, destination: Path) -> list[str]:
        return graphify.copy_outputs(root, destination)

    def version(self) -> str | None:
        return graphify.version()
