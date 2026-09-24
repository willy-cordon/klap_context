"""Contracts for framework-specific enrichment of the generic semantic model."""
from __future__ import annotations

from pathlib import Path
from typing import Protocol

from ..semantic import SemanticModel


class FrameworkAdapter(Protocol):
    """Detect one framework and emit framework-neutral semantic facts."""

    name: str

    def detect(self, root: Path) -> bool: ...

    def analyze(self, root: Path) -> SemanticModel: ...
