"""Framework-neutral semantic facts consumed by flows and agent intelligence.

Framework adapters translate conventions into this vocabulary.  Nothing above
this layer needs to know whether an HTTP endpoint came from Laravel, FastAPI,
or a generic executable script.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field


@dataclass
class SemanticComponent:
    name: str
    type: str
    file: str | None = None
    symbol: str | None = None
    status: str = "CONFIRMED"
    evidence: list[dict] = field(default_factory=list)


@dataclass
class EntryPoint:
    type: str
    name: str
    handler: str | None = None
    protocol: str | None = None
    method: str | None = None
    path: str | None = None
    file: str | None = None
    line: int | None = None
    framework: str | None = None
    status: str = "CONFIRMED"
    evidence: list[dict] = field(default_factory=list)


@dataclass
class ExecutionTransition:
    source: str
    target: str
    type: str
    file: str | None = None
    line: int | None = None
    status: str = "CONFIRMED"
    provider: str = "klap-native"
    evidence: list[dict] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)


@dataclass
class SemanticModel:
    language: str | None
    framework: str | None = None
    analysis_mode: str = "GENERIC"
    components: list[SemanticComponent] = field(default_factory=list)
    entry_points: list[EntryPoint] = field(default_factory=list)
    transitions: list[ExecutionTransition] = field(default_factory=list)
    background_tasks: list[dict] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {
            "language": self.language,
            "framework": self.framework,
            "analysis_mode": self.analysis_mode,
            "components": [asdict(item) for item in self.components],
            "entry_points": [asdict(item) for item in self.entry_points],
            "transitions": [asdict(item) for item in self.transitions],
            "background_tasks": self.background_tasks,
            "metadata": self.metadata,
        }
