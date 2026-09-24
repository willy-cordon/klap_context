"""Contract for code-analysis engines feeding KlapContext evidence."""
from __future__ import annotations

from pathlib import Path
from typing import Protocol


class AnalysisProvider(Protocol):
    name: str

    def generate(self, root: Path, update: bool = False) -> Path: ...
    def load_graph(self, graph: Path) -> dict: ...
    def copy_outputs(self, root: Path, destination: Path) -> list[str]: ...
    def version(self) -> str | None: ...
